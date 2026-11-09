"""Connection lifecycle and commands for the DJI Mic Mobile Receiver."""
from __future__ import annotations

import copy
import queue
import random
import threading
import time
from typing import Callable

from . import duml
from .winusb import WinUsbDevice, driver_state, find_interface_path, receiver_present


class DeviceError(RuntimeError):
    pass


class NotConnected(DeviceError):
    pass


class CommandRejected(DeviceError):
    def __init__(self, code: int):
        super().__init__(f"接收器拒绝了该设置（返回 0x{code:02x}）")
        self.code = code


class CommandTimeout(DeviceError):
    pass


class NotApplied(DeviceError):
    pass


class MicController:
    """Keeps a live status model and sends the verified settings commands.

    All callbacks run on background threads. The UI should only enqueue them.
    """

    def __init__(
        self,
        on_status: Callable[[duml.MicStatus], None] | None = None,
        on_connection: Callable[[bool, str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        self.on_status = on_status
        self.on_connection = on_connection
        self.on_log = on_log

        self._status = duml.MicStatus()
        self._status_lock = threading.Lock()
        self._link: WinUsbDevice | None = None
        self._link_lock = threading.Lock()
        self._parser = duml.StreamParser()
        self._pending: dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._sequence = random.randint(0x100, 0x7FF0)
        self._write_lock = threading.Lock()

        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._connected = False
        self.capabilities: dict = {}

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        watchdog = threading.Thread(
            target=self._watchdog, name="mic-watchdog", daemon=True
        )
        watchdog.start()
        self._threads.append(watchdog)

    def stop(self) -> None:
        self._stop.set()
        self._close_link(notify=True)
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def status(self) -> duml.MicStatus:
        with self._status_lock:
            return copy.deepcopy(self._status)

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def _set_connected(self, value: bool, detail: str = "") -> None:
        if self._connected == value:
            return
        self._connected = value
        if self.on_connection:
            self.on_connection(value, detail)

    def _watchdog(self) -> None:
        while not self._stop.is_set():
            try:
                if self._link is None:
                    path = find_interface_path()
                    if path:
                        self._open(path)
                elif not find_interface_path():
                    self._log("接收器已断开")
                    self._close_link(notify=True)
            except Exception as error:  # keep retrying
                self._log(f"连接失败：{error}")
                self._close_link(notify=False)
            self._stop.wait(1.0)

    def _open(self, path: str) -> None:
        link = WinUsbDevice(path)
        link.open()
        with self._link_lock:
            self._link = link
        self._parser = duml.StreamParser()
        with self._status_lock:
            self._status = duml.MicStatus()
        self._log("已打开控制接口 MI_06")
        self._set_connected(True, "")
        reader = threading.Thread(
            target=self._read_loop, args=(link,), name="mic-reader", daemon=True
        )
        reader.start()
        self._threads.append(reader)

    def _read_loop(self, link: WinUsbDevice) -> None:
        errors = 0
        try:
            while not self._stop.is_set() and link.is_open:
                data = link.read()
                if data is None:
                    errors += 1
                    if errors >= 3:
                        self._log("控制接口读取失败，正在重连")
                        return
                    time.sleep(0.1)
                    continue
                errors = 0
                if not data:
                    continue
                for frame in self._parser.feed(data):
                    self._handle_frame(frame)
        except Exception as error:
            if not self._stop.is_set():
                self._log(f"读取线程异常：{error}")
        finally:
            if not self._stop.is_set():
                self._close_link(notify=True)

    def _handle_frame(self, frame: duml.Frame) -> None:
        if frame.is_response:
            with self._pending_lock:
                waiter = self._pending.pop(frame.sequence, None)
            if waiter is not None:
                waiter.put(frame)
            return
        with self._status_lock:
            old = self._status
            new = copy.deepcopy(old)
            if not duml.apply_frame(frame, new):
                return
            if new == old:
                return
            self._status = new
        if self.on_status:
            self.on_status(copy.deepcopy(new))

    def _close_link(self, notify: bool) -> None:
        with self._link_lock:
            link, self._link = self._link, None
        if link is not None:
            link.close()
        with self._pending_lock:
            waiters = list(self._pending.values())
            self._pending.clear()
        for waiter in waiters:
            waiter.put(None)
        if notify:
            self._set_connected(False, "")
        with self._status_lock:
            self._status = duml.MicStatus()

    # -- commands ----------------------------------------------------------

    def _next_sequence(self) -> int:
        with self._pending_lock:
            self._sequence += 1
            if self._sequence > 0x7FFF:
                self._sequence = 0x100
            return self._sequence

    def _send(self, frame: bytes, sequence: int, timeout: float = 2.0) -> duml.Frame:
        link = self._link
        if link is None or not link.is_open:
            raise NotConnected("接收器未连接")
        waiter: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[sequence] = waiter
        try:
            with self._write_lock:
                link.write(frame)
            try:
                response = waiter.get(timeout=timeout)
            except queue.Empty:
                raise CommandTimeout("接收器没有应答") from None
            if response is None:
                raise NotConnected("接收器已断开")
            return response
        finally:
            with self._pending_lock:
                self._pending.pop(sequence, None)

    def _send_setting(self, setting: int, value: int) -> None:
        sequence = self._next_sequence()
        frame = duml.set_param_frame(sequence, setting, value)
        response = self._send(frame, sequence)
        result = response.payload[0] if response.payload else 0xFF
        if result != 0:
            raise CommandRejected(result)

    def set_gain(self, db: int) -> None:
        if db < -12 or db > 12:
            raise DeviceError("增益超出范围（-12…+12 dB）")
        self._send_setting(duml.SETTING_RECEIVER_GAIN, db & 0xFF)
        self._wait_status(lambda status: status.receiver.gain_db == db, 3.0)

    def set_channel(self, mode: int) -> None:
        if mode not in (duml.CHANNEL_MONO, duml.CHANNEL_STEREO):
            raise DeviceError("未知声道模式")
        self._send_setting(duml.SETTING_CHANNEL_MODE, mode)
        self._wait_status(lambda status: status.receiver.channel_raw == mode, 3.0)

    def set_auto_power_off(self, enabled: bool) -> None:
        self._send_setting(duml.SETTING_AUTO_POWER_OFF, 1 if enabled else 0)
        self._wait_status(
            lambda status: status.receiver.auto_power_off == bool(enabled), 3.0
        )

    def _wait_status(self, predicate: Callable[[duml.MicStatus], bool], timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self.status):
                return
            time.sleep(0.08)
        raise NotApplied("接收器已接受命令，但状态没有变化")

    def refresh_capabilities(self) -> dict:
        sequence = self._next_sequence()
        frame = duml.get_capability_frame(sequence, duml.CAPABILITY_ALL)
        response = self._send(frame, sequence)
        caps = duml.parse_capabilities(response.payload)
        self.capabilities = caps
        return caps

    def gain_range(self) -> tuple[int, int, int]:
        caps = self.capabilities.get(0, {})
        value = caps.get(duml.CAPABILITY_GAIN)
        if value:
            parsed = duml.capability_range(value)
            if parsed:
                return parsed
        return (-12, 12, 6)

    def state(self) -> str:
        return driver_state()
