"""Local web UI host for the Mic Series Mobile Receiver control console.

The browser window is only the presentation layer: this module owns the USB
controller, serves the static UI from ``web/`` and exposes a small JSON API on
127.0.0.1. It launches Edge/Chrome in app-window mode so the result looks like a
desktop application rather than a browser tab.

Run from source:
    python -m dji_mic            # web UI
    python -m dji_mic --classic  # old Tk UI
"""
from __future__ import annotations

import argparse
import ctypes
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__, duml
from .device import DeviceError, MicController
from .winusb import driver_state

APP_NAME = "Mic Series Mobile Receiver 电脑控制台"
DEFAULT_PORT = 47821
WEB_ROOT_NAME = "web"


def resource_dir() -> Path:
    """Where bundled read-only assets live (web/, inside PyInstaller's temp dir)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[1]


def app_dir() -> Path:
    """Directory of the exe / project root, where driver/ lives."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "MicSeriesControl"
    path.mkdir(parents=True, exist_ok=True)
    return path


def web_root() -> Path:
    return resource_dir() / WEB_ROOT_NAME


class AppState:
    def __init__(self) -> None:
        self.logs: deque[str] = deque(maxlen=140)
        self.last_poll = time.time()
        self.bye_at = 0.0
        self.command_lock = threading.Lock()
        self.quit_event = threading.Event()
        self.version = __version__
        self._driver_state = "absent"
        self._driver_at = 0.0
        self.controller = MicController(
            on_status=self._on_status,
            on_connection=self._on_connection,
            on_log=self.log,
        )

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.controller.start()
        self.log("控制台已启动，正在查找接收器…")

    def stop(self) -> None:
        self.controller.stop()

    def request_quit(self) -> None:
        self.quit_event.set()

    def note_bye(self) -> None:
        self.bye_at = time.time()

    # -- logging -----------------------------------------------------------

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        self.logs.append(line)
        try:
            print(line, flush=True)
        except Exception:
            pass

    def _on_status(self, status: duml.MicStatus) -> None:
        # Status frames arrive several times a second; do not log each one.
        pass

    def _on_connection(self, connected: bool, detail: str) -> None:
        self.log("接收器已连接" if connected else "接收器已断开")

    # -- state -------------------------------------------------------------

    def driver(self) -> str:
        now = time.time()
        if now - self._driver_at > 2.0:
            self._driver_state = driver_state()
            self._driver_at = now
        return self._driver_state

    def snapshot(self) -> dict:
        status = self.controller.status
        rx = status.receiver
        transmitters = []
        for index in (1, 2):
            tx = status.transmitters.get(index)
            online = bool(tx is not None and index in rx.connected)
            transmitters.append(
                {
                    "index": index,
                    "online": online,
                    "product": tx.identity.product_name if tx else None,
                    "firmware": tx.identity.firmware if tx else None,
                    "serial": tx.identity.serial_number if tx else None,
                    "battery": tx.battery_level if tx else None,
                    "percent": tx.battery_percent if tx else None,
                    "charging": tx.is_charging if tx else None,
                    "nc": tx.noise_cancelling if tx else None,
                    "level": tx.meter_level if tx else None,
                    "signal": tx.signal_level if tx else None,
                }
            )
        return {
            "ok": True,
            "app": APP_NAME,
            "version": self.version,
            "connected": self.controller.connected,
            "driver": self.driver(),
            "busy": self.command_lock.locked(),
            "receiver": {
                "product": rx.identity.product_name,
                "firmware": rx.identity.firmware,
                "serial": rx.identity.serial_number,
                "gain_db": rx.gain_db,
                "channel": rx.channel_raw,
                "channel_name": rx.channel_name,
                "nc": rx.noise_cancelling,
                "nc_level": rx.noise_level,
                "auto_off": rx.auto_power_off,
                "usb": rx.attached_over_usb,
                "battery": rx.battery_level,
                "connected": sorted(rx.connected),
            },
            "transmitters": transmitters,
            "logs": list(self.logs),
        }

    # -- commands ----------------------------------------------------------

    def set_gain(self, db: int) -> None:
        with self.command_lock:
            self.controller.set_gain(db)
            self.log(f"接收器增益设为 {db:+d} dB")

    def set_channel(self, mode: int) -> None:
        with self.command_lock:
            self.controller.set_channel(mode)
            self.log(f"声道切换为{self.controller.status.receiver.channel_name}")

    def set_auto_off(self, enabled: bool) -> None:
        with self.command_lock:
            self.controller.set_auto_power_off(enabled)
            self.log(f"15 分钟自动关机{'开启' if enabled else '关闭'}")

    def reconnect(self) -> None:
        with self.command_lock:
            self.log("正在重新连接接收器…")
            self.controller.stop()
            self.controller.start()

    def install_driver(self) -> None:
        script = app_dir() / "driver" / "install_winusb.ps1"
        if not script.exists():
            raise RuntimeError(f"找不到驱动脚本：{script}")
        params = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        result = shell32.ShellExecuteW(
            None, "runas", "powershell.exe", params, str(script.parent), 1
        )
        if result <= 32:
            raise RuntimeError(f"无法启动驱动安装程序（ShellExecute 返回 {result}）")
        self.log("已启动驱动安装，请在 UAC 窗口中确认…")


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    app: AppState
    server_version = "MicSeriesControl/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quiet
        pass

    # -- helpers -----------------------------------------------------------

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 64 * 1024:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as error:
            raise ValueError("请求不是合法 JSON") from error
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        root = web_root().resolve()
        target = (root / unquote(path).lstrip("/")).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        body = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".js":
            mime = "text/javascript; charset=utf-8"
        elif target.suffix == ".css":
            mime = "text/css; charset=utf-8"
        elif target.suffix == ".svg":
            mime = "image/svg+xml"
        elif target.suffix == ".html":
            mime = "text/html; charset=utf-8"
        elif target.suffix == ".ttf":
            mime = "font/ttf"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        # The app ships its own UI and is replaced in place; never let a browser
        # reuse an old app.css/app.js against a new index.html.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/state":
                self.app.last_poll = time.time()
                self.app.bye_at = 0.0
                self._send_json(200, self.app.snapshot())
                return
            if path == "/api/ping":
                self._send_json(200, {"ok": True, "app": APP_NAME})
                return
            self._serve_static(path)
        except BrokenPipeError:
            pass
        except Exception as error:
            self._send_json(500, {"ok": False, "error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            data = self._read_json()
            if path == "/api/gain":
                db = int(data.get("db"))
                if db not in (-12, -6, 0, 6, 12):
                    raise ValueError("增益必须是 -12 / -6 / 0 / +6 / +12")
                self.app.set_gain(db)
                self._send_json(200, {"ok": True})
            elif path == "/api/channel":
                mode = int(data.get("mode"))
                if mode not in (duml.CHANNEL_MONO, duml.CHANNEL_STEREO):
                    raise ValueError("声道必须是 0（单声道）或 2（立体声）")
                self.app.set_channel(mode)
                self._send_json(200, {"ok": True})
            elif path == "/api/auto-off":
                self.app.set_auto_off(bool(data.get("enabled")))
                self._send_json(200, {"ok": True})
            elif path == "/api/reconnect":
                self.app.reconnect()
                self._send_json(200, {"ok": True})
            elif path == "/api/install-driver":
                self.app.install_driver()
                self._send_json(200, {"ok": True})
            elif path == "/api/quit":
                threading.Timer(0.35, self.app.request_quit).start()
                self._send_json(200, {"ok": True})
            elif path == "/api/bye":
                self.app.note_bye()
                self.send_response(204)
                self.end_headers()
            else:
                self._send_json(404, {"ok": False, "error": "not found"})
        except (ValueError, TypeError) as error:
            self._send_json(400, {"ok": False, "error": str(error)})
        except DeviceError as error:
            self._send_json(409, {"ok": False, "error": str(error)})
        except Exception as error:
            self._send_json(500, {"ok": False, "error": str(error)})


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------


def find_browser() -> str | None:
    candidates = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        candidates += [
            str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        ]
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def open_browser(url: str) -> None:
    browser = find_browser()
    if browser:
        profile = data_dir() / "browser"
        profile.mkdir(parents=True, exist_ok=True)
        args = [
            browser,
            f"--app={url}",
            "--window-size=1280,900",
            "--window-position=40,40",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--disable-session-crashed-bubble",
            "--disable-features=Translate,MediaRouter",
        ]
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return
    try:
        webbrowser.open(url)
    except Exception:
        ctypes.windll.user32.MessageBoxW(0, f"请用浏览器打开：\n{url}", APP_NAME, 0)


def is_ours(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/ping", timeout=0.7
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("app") == APP_NAME
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="只启动服务，不开窗口")
    parser.add_argument("--no-quit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    app = AppState()

    port = args.port
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        if is_ours(port):
            url = f"http://127.0.0.1:{port}/"
            print(f"控制台已在运行：{url}")
            if not args.no_browser:
                open_browser(url)
            return 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    app.start()
    Handler.app = app
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/"
    app.log(f"控制台服务已启动：{url}")

    thread = threading.Thread(target=server.serve_forever, name="web-ui", daemon=True)
    thread.start()

    def watchdog() -> None:
        while not app.quit_event.wait(5.0):
            now = time.time()
            if now - app.last_poll > 180:
                app.log("界面已关闭，自动退出")
                app.quit_event.set()
                return
            if app.bye_at and now - app.bye_at > 3 and app.last_poll < app.bye_at:
                app.log("窗口已关闭，退出")
                app.quit_event.set()
                return

    if not args.no_quit:
        threading.Thread(target=watchdog, name="web-watchdog", daemon=True).start()

    if not args.no_browser:
        open_browser(url)
    else:
        print(f"Web UI: {url}")

    try:
        while not app.quit_event.wait(0.25):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        app.stop()
        print("已退出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
