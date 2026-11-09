"""Classic Tkinter fallback UI for the Mic Series Mobile Receiver."""
from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox

from . import __version__, duml
from .device import (
    CommandRejected,
    CommandTimeout,
    DeviceError,
    MicController,
    NotApplied,
    NotConnected,
)
from .winusb import driver_state

# Palette
BG = "#F1F5F9"
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
TEXT_2 = "#475569"
MUTED = "#94A3B8"
ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"
ACCENT_SOFT = "#DBEAFE"
GREEN = "#16A34A"
GREEN_SOFT = "#DCFCE7"
AMBER = "#D97706"
AMBER_SOFT = "#FEF3C7"
RED = "#DC2626"
RED_SOFT = "#FEE2E2"
HEADER = "#0F172A"
HEADER_2 = "#1E293B"

FONT = "Microsoft YaHei UI"
MONO = "Consolas"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def make_card(parent: tk.Widget, **kwargs) -> tk.Frame:
    return tk.Frame(
        parent,
        bg=CARD,
        highlightbackground=BORDER,
        highlightthickness=1,
        bd=0,
        **kwargs,
    )


class Pill(tk.Label):
    """A clickable rounded-ish pill."""

    def __init__(self, master, text, command, width=7, **kwargs):
        super().__init__(
            master,
            text=text,
            width=width,
            bg="#F1F5F9",
            fg=TEXT_2,
            activebackground=ACCENT_SOFT,
            font=(FONT, 10, "bold"),
            padx=6,
            pady=7,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER,
            **kwargs,
        )
        self.command = command
        self.selected = False
        self.bind("<Button-1>", lambda _event: self.command())
        self.bind("<Enter>", lambda _event: self._hover(True))
        self.bind("<Leave>", lambda _event: self._hover(False))

    def _hover(self, inside: bool) -> None:
        if self.selected:
            return
        self.configure(bg="#E2E8F0" if inside else "#F1F5F9")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.configure(
            bg=ACCENT_SOFT if selected else "#F1F5F9",
            fg=ACCENT_DARK if selected else TEXT_2,
            highlightbackground="#93C5FD" if selected else BORDER,
        )


class ChannelOption(tk.Frame):
    def __init__(self, master, title: str, subtitle: str, command):
        super().__init__(
            master,
            bg="#F8FAFC",
            highlightbackground=BORDER,
            highlightthickness=2,
            bd=0,
            cursor="hand2",
            padx=12,
            pady=10,
        )
        self.command = command
        self.selected = False
        self.title = tk.Label(self, text=title, bg="#F8FAFC", fg=TEXT, font=(FONT, 11, "bold"))
        self.title.pack(anchor="w")
        self.subtitle = tk.Label(
            self, text=subtitle, bg="#F8FAFC", fg=MUTED, font=(FONT, 9)
        )
        self.subtitle.pack(anchor="w", pady=(2, 0))
        for widget in (self, self.title, self.subtitle):
            widget.bind("<Button-1>", lambda _event: self.command())

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        bg = ACCENT_SOFT if selected else "#F8FAFC"
        border = "#60A5FA" if selected else BORDER
        self.configure(bg=bg, highlightbackground=border)
        self.title.configure(bg=bg)
        self.subtitle.configure(bg=bg)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mic Series Mobile Receiver · 电脑控制台")
        self.geometry("1020x900")
        self.minsize(960, 820)
        self.configure(bg=BG)
        try:
            self.iconbitmap(default=str(app_dir() / "assets" / "icon.ico"))
        except Exception:
            pass

        self.events: queue.Queue = queue.Queue()
        self.status = duml.MicStatus()
        self.connected = False
        self.selected_gain = 6
        self.selected_channel = duml.CHANNEL_MONO
        self.gain_dirty = False
        self.channel_dirty = False
        self.busy = False
        self._driver_install_poll = 0
        self._last_banner_state = ""

        self._build_fonts()
        self._build_header()
        self._build_banner()
        self._build_statusbar()
        self._build_log()
        self._build_content()

        self.controller = MicController(
            on_status=lambda status: self.events.put(("status", status)),
            on_connection=lambda connected, detail: self.events.put(
                ("connection", (connected, detail))
            ),
            on_log=lambda message: self.events.put(("log", message)),
        )
        self.controller.start()
        self.after(0, self._center)
        self.after(100, self._poll)
        self.after(3000, self._refresh_driver_banner)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_driver_banner()
        self._append_log("控制台已启动，正在查找接收器…")

    # ---- construction ----------------------------------------------------

    def _center(self) -> None:
        self.update_idletasks()
        width, height = 1020, 900
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_fonts(self) -> None:
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=FONT, size=10)
            except Exception:
                pass

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=HEADER)
        header.pack(fill="x")

        left = tk.Frame(header, bg=HEADER)
        left.pack(side="left", padx=24, pady=16)
        badge = tk.Label(
            left,
            text="DJI",
            bg="#2563EB",
            fg="white",
            font=(FONT, 13, "bold"),
            padx=10,
            pady=5,
        )
        badge.pack(side="left", padx=(0, 12))
        titles = tk.Frame(left, bg=HEADER)
        titles.pack(side="left")
        tk.Label(
            titles,
            text="Mic Series 电脑控制台",
            bg=HEADER,
            fg="white",
            font=(FONT, 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="不用拔到手机，在 Windows 上直接改增益与声道",
            bg=HEADER,
            fg="#94A3B8",
            font=(FONT, 9),
        ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=HEADER)
        right.pack(side="right", padx=24)
        self.conn_pill = tk.Frame(right, bg=HEADER_2, padx=12, pady=6)
        self.conn_pill.pack(side="left", padx=(0, 10))
        self.conn_dot = tk.Canvas(
            self.conn_pill, width=10, height=10, bg=HEADER_2, highlightthickness=0
        )
        self.conn_dot.pack(side="left", padx=(0, 6))
        self.conn_dot_id = self.conn_dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        self.conn_text = tk.Label(
            self.conn_pill,
            text="未连接",
            bg=HEADER_2,
            fg="#CBD5E1",
            font=(FONT, 9, "bold"),
        )
        self.conn_text.pack(side="left")

        self.reconnect_btn = self._flat_button(right, "重新检测", self._reconnect, dark=True)
        self.reconnect_btn.pack(side="left")

    def _flat_button(self, parent, text, command, dark=False, accent=False, width=None):
        bg = ACCENT if accent else (HEADER_2 if dark else "#F1F5F9")
        fg = "white" if (accent or dark) else TEXT_2
        active = ACCENT_DARK if accent else ("#334155" if dark else "#E2E8F0")
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground="white" if (accent or dark) else TEXT,
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            font=(FONT, 9, "bold"),
            width=width,
        )
        return btn

    def _build_banner(self) -> None:
        self.banner = tk.Frame(
            self,
            bg=AMBER_SOFT,
            highlightbackground="#FCD34D",
            highlightthickness=1,
        )
        self.banner_text = tk.Label(
            self.banner,
            text="",
            bg=AMBER_SOFT,
            fg="#92400E",
            font=(FONT, 9),
            anchor="w",
            justify="left",
        )
        self.banner_text.pack(side="left", padx=16, pady=9)
        self.banner_action = self._flat_button(
            self.banner, "安装驱动", self._install_driver, accent=True
        )
        self.banner_action.pack(side="right", padx=12, pady=6)
        self.banner.pack(fill="x")
        self.banner.pack_forget()

    def _build_content(self) -> None:
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=18, pady=(10, 6))
        content.grid_columnconfigure(0, minsize=392)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        left = make_card(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = make_card(content)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_receiver_panel(left)
        self._build_transmitter_panel(right)

    def _section_title(self, parent, text: str, subtitle: str = ""):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text=text, bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(row, text=subtitle, bg=CARD, fg=MUTED, font=(FONT, 9)).pack(
                anchor="w", pady=(1, 0)
            )
        return row

    def _build_receiver_panel(self, card: tk.Frame) -> None:
        pad = tk.Frame(card, bg=CARD)
        pad.pack(fill="both", expand=True, padx=18, pady=16)

        self._section_title(pad, "接收器", "Mic Series Mobile Receiver · Wireless Mic Rx")
        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=12)

        gain_head = tk.Frame(pad, bg=CARD)
        gain_head.pack(fill="x")
        tk.Label(gain_head, text="增益", bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).pack(
            side="left"
        )
        self.gain_value = tk.Label(
            gain_head, text="+6 dB", bg=CARD, fg=ACCENT, font=(FONT, 18, "bold")
        )
        self.gain_value.pack(side="right")
        tk.Label(
            pad,
            text="控制接收器送到电脑/手机的音量，每档 6 dB。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", pady=(2, 10))

        pills = tk.Frame(pad, bg=CARD)
        pills.pack(fill="x")
        for i in range(5):
            pills.grid_columnconfigure(i, weight=1, uniform="gain")
        self.gain_pills: dict[int, Pill] = {}
        for i, value in enumerate((-12, -6, 0, 6, 12)):
            label = "0" if value == 0 else f"{value:+d}"
            pill = Pill(pills, label, lambda v=value: self._select_gain(v), width=4)
            pill.grid(row=0, column=i, padx=3, sticky="ew")
            self.gain_pills[value] = pill

        self.gain_apply = self._flat_button(
            pad, "应用增益", self._apply_gain, accent=True
        )
        self.gain_apply.pack(fill="x", pady=(10, 0))
        self.gain_apply.configure(state="disabled", bg="#CBD5E1", activebackground="#CBD5E1")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=12)

        self._section_title(pad, "声道模式", "单声道会把两个发射器混在一起；立体声按 TX1 左 / TX2 右输出。")
        options = tk.Frame(pad, bg=CARD)
        options.pack(fill="x", pady=(10, 0))
        options.grid_columnconfigure(0, weight=1, uniform="channel")
        options.grid_columnconfigure(1, weight=1, uniform="channel")
        self.channel_options: dict[int, ChannelOption] = {
            duml.CHANNEL_MONO: ChannelOption(
                options, "单声道", "两路混合 · 适合单人", lambda: self._select_channel(duml.CHANNEL_MONO)
            ),
            duml.CHANNEL_STEREO: ChannelOption(
                options, "立体声", "TX1 左 / TX2 右", lambda: self._select_channel(duml.CHANNEL_STEREO)
            ),
        }
        self.channel_options[duml.CHANNEL_MONO].grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.channel_options[duml.CHANNEL_STEREO].grid(row=0, column=1, padx=(6, 0), sticky="ew")

        self.channel_apply = self._flat_button(
            pad, "应用声道", self._apply_channel, accent=True
        )
        self.channel_apply.pack(fill="x", pady=(10, 0))
        self.channel_apply.configure(state="disabled", bg="#CBD5E1", activebackground="#CBD5E1")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=12)

        info = tk.Frame(pad, bg=CARD)
        info.pack(fill="x")
        self.info_values: dict[str, tk.Label] = {}

        row = tk.Frame(info, bg=CARD)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="降噪（硬件开关）", bg=CARD, fg=TEXT_2, font=(FONT, 9)).pack(
            side="left"
        )
        self.info_values["nc"] = tk.Label(
            row, text="—", bg=CARD, fg=TEXT, font=(FONT, 9, "bold")
        )
        self.info_values["nc"].pack(side="right")

        row = tk.Frame(info, bg=CARD)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="15 分钟自动关机", bg=CARD, fg=TEXT_2, font=(FONT, 9)).pack(
            side="left"
        )
        self.auto_off_btn = tk.Button(
            row,
            text="—",
            command=self._toggle_auto_off,
            bg="#E2E8F0",
            fg=TEXT_2,
            activebackground="#CBD5E1",
            relief="flat",
            bd=0,
            padx=10,
            pady=1,
            width=4,
            cursor="hand2",
            font=(FONT, 8, "bold"),
        )
        self.auto_off_btn.pack(side="right")

        row = tk.Frame(info, bg=CARD)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="USB 连接", bg=CARD, fg=TEXT_2, font=(FONT, 9)).pack(side="left")
        self.info_values["usb"] = tk.Label(
            row, text="—", bg=CARD, fg=TEXT, font=(FONT, 9, "bold")
        )
        self.info_values["usb"].pack(side="right")

        note = tk.Frame(
            pad,
            bg="#F8FAFC",
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        note.pack(side="bottom", fill="x", pady=(14, 0))
        tk.Label(
            note,
            text="设置保存在接收器上",
            bg="#F8FAFC",
            fg=TEXT_2,
            font=(FONT, 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            note,
            text="增益与声道会立即生效，拔下再连接仍会保留。",
            bg="#F8FAFC",
            fg=MUTED,
            font=(FONT, 9),
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        tk.Frame(pad, bg=CARD).pack(fill="both", expand=True)

    def _build_transmitter_panel(self, card: tk.Frame) -> None:
        pad = tk.Frame(card, bg=CARD)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        head = tk.Frame(pad, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="发射器", bg=CARD, fg=TEXT, font=(FONT, 12, "bold")).pack(
            side="left"
        )
        self.tx_summary = tk.Label(
            head, text="等待连接", bg=CARD, fg=MUTED, font=(FONT, 9)
        )
        self.tx_summary.pack(side="right")
        tk.Label(
            pad,
            text="电量、充电与降噪状态由接收器实时转发。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", pady=(2, 12))

        self.tx_cards: dict[int, dict] = {}
        for index in (1, 2):
            self.tx_cards[index] = self._build_tx_card(pad, index)
            self.tx_cards[index]["frame"].pack(fill="x", pady=(0, 10))

        self.hint = tk.Label(
            pad,
            text="提示：发射器上的降噪由单击电源键切换；接收器上的 O/L/H 开关控制降噪档位。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            wraplength=430,
            justify="left",
        )
        self.hint.pack(anchor="w", pady=(6, 0))
        tk.Label(
            pad,
            text="兼容发射器：DJI Mic Mini / Mic 2 / Mic 3（混连方式见 DJI 说明）",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        self.device_line = tk.Label(
            pad,
            text="接收器固件 —   序列号 —",
            bg=CARD,
            fg=MUTED,
            font=(MONO, 8),
            anchor="w",
        )
        self.device_line.pack(side="bottom", fill="x", pady=(8, 0))

    def _build_tx_card(self, parent: tk.Widget, index: int) -> dict:
        frame = tk.Frame(
            parent,
            bg="#F8FAFC",
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        header = tk.Frame(frame, bg="#F8FAFC")
        header.pack(fill="x")
        name = tk.Label(
            header, text=f"TX{index}", bg="#F8FAFC", fg=TEXT, font=(FONT, 12, "bold")
        )
        name.pack(side="left")
        product = tk.Label(
            header, text="未连接", bg="#F8FAFC", fg=MUTED, font=(FONT, 9)
        )
        product.pack(side="left", padx=(8, 0))
        state = tk.Label(
            header, text="离线", bg="#E2E8F0", fg=TEXT_2, font=(FONT, 8, "bold"), padx=8, pady=2
        )
        state.pack(side="right")

        body = tk.Frame(frame, bg="#F8FAFC")
        body.pack(fill="x", pady=(8, 0))
        battery = tk.Label(
            body, text="—", bg="#F8FAFC", fg=TEXT, font=(FONT, 24, "bold")
        )
        battery.pack(side="left")
        detail = tk.Frame(body, bg="#F8FAFC")
        detail.pack(side="left", padx=(10, 0), pady=(4, 0))
        gauge = tk.Label(
            detail, text="电量 —", bg="#F8FAFC", fg=TEXT_2, font=(FONT, 9)
        )
        gauge.pack(anchor="w")
        chips = tk.Frame(detail, bg="#F8FAFC")
        chips.pack(anchor="w", pady=(3, 0))
        nc = tk.Label(
            chips, text="降噪 —", bg="#E2E8F0", fg=TEXT_2, font=(FONT, 8), padx=7, pady=1
        )
        nc.pack(side="left", padx=(0, 5))
        charging = tk.Label(
            chips, text="充电 —", bg="#E2E8F0", fg=TEXT_2, font=(FONT, 8), padx=7, pady=1
        )
        charging.pack(side="left")

        bar = tk.Canvas(frame, height=8, bg="#F8FAFC", highlightthickness=0)
        bar.pack(fill="x", pady=(10, 0))
        level = tk.Canvas(frame, height=5, bg="#F8FAFC", highlightthickness=0)
        level.pack(fill="x", pady=(6, 0))

        return {
            "frame": frame,
            "header": header,
            "name": name,
            "product": product,
            "state": state,
            "battery": battery,
            "gauge": gauge,
            "nc": nc,
            "charging": charging,
            "bar": bar,
            "level": level,
        }

    def _build_log(self) -> None:
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(side="bottom", fill="x", padx=18, pady=(0, 8))
        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="运行日志", bg=BG, fg=TEXT_2, font=(FONT, 9, "bold")).pack(
            side="left"
        )
        copy = tk.Label(
            head,
            text="复制诊断信息",
            bg=BG,
            fg=ACCENT,
            font=(FONT, 9),
            cursor="hand2",
        )
        copy.pack(side="right")
        copy.bind("<Button-1>", lambda _event: self._copy_diagnostics())

        box = tk.Frame(wrap, bg="#0F172A", highlightthickness=0)
        box.pack(fill="x", pady=(4, 0))
        self.log_text = tk.Text(
            box,
            height=3,
            bg="#0F172A",
            fg="#CBD5E1",
            insertbackground="white",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=(MONO, 9),
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(fill="x")

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=BG)
        bar.pack(side="bottom", fill="x", padx=20, pady=(0, 6))
        self.status_label = tk.Label(
            bar, text="就绪", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w"
        )
        self.status_label.pack(side="left")
        tk.Label(
            bar,
            text=f"v{__version__} · 非官方工具",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8),
        ).pack(side="right")

    # ---- event loop ------------------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status = payload
                    self._render_status()
                elif kind == "connection":
                    connected, detail = payload
                    self.connected = connected
                    self._render_connection(connected, detail)
                elif kind == "log":
                    self._append_log(payload)
                elif kind == "toast":
                    self._toast(payload)
                elif kind == "error":
                    self._toast(payload, error=True)
                elif kind == "task_done":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _render_connection(self, connected: bool, detail: str) -> None:
        if connected:
            self.conn_dot.itemconfigure(self.conn_dot_id, fill=GREEN)
            self.conn_text.configure(text="已连接")
            self.banner.pack_forget()
            self._toast("接收器已连接")
        else:
            self.conn_dot.itemconfigure(self.conn_dot_id, fill=MUTED)
            self.conn_text.configure(text="未连接")
            self._refresh_driver_banner()
        self._update_apply_state()

    def _refresh_driver_banner(self) -> None:
        if self.connected:
            self.banner.pack_forget()
            return
        state = driver_state()
        if state == self._last_banner_state and self.banner.winfo_ismapped():
            return
        self._last_banner_state = state
        if state == "driver-missing":
            self.banner_text.configure(
                text="已检测到接收器，但 Windows 控制接口（MI_06）缺少驱动。安装后可读写增益与声道，不影响录音。"
            )
            self.banner_action.configure(text="安装驱动", command=self._install_driver)
            self.banner.pack(fill="x", after=self.winfo_children()[0])
        elif state == "absent":
            self.banner_text.configure(
                text="未检测到接收器。请用 USB-C 线把接收器直接插到电脑，然后点“重新检测”。"
            )
            self.banner_action.configure(text="重新检测", command=self._reconnect)
            self.banner.pack(fill="x", after=self.winfo_children()[0])
        else:
            self.banner.pack_forget()
        self.after(3000, self._refresh_driver_banner)

    # ---- rendering -------------------------------------------------------

    def _render_status(self) -> None:
        status = self.status
        rx = status.receiver
        if rx.gain_db is not None and not self.gain_dirty:
            self.selected_gain = rx.gain_db
            self.gain_value.configure(text=f"{rx.gain_db:+d} dB")
            for value, pill in self.gain_pills.items():
                pill.set_selected(value == rx.gain_db)
        if rx.channel_raw is not None and not self.channel_dirty:
            self.selected_channel = (
                rx.channel_raw
                if rx.channel_raw in (duml.CHANNEL_MONO, duml.CHANNEL_STEREO)
                else duml.CHANNEL_MONO
            )
            for mode, option in self.channel_options.items():
                option.set_selected(mode == rx.channel_raw)
        self.info_values["nc"].configure(
            text=("开" if rx.noise_cancelling else "关") if rx.noise_cancelling is not None else "—"
        )
        if rx.auto_power_off is None:
            self.auto_off_btn.configure(text="—", bg="#E2E8F0", fg=TEXT_2)
        elif rx.auto_power_off:
            self.auto_off_btn.configure(text="开", bg=GREEN_SOFT, fg=GREEN)
        else:
            self.auto_off_btn.configure(text="关", bg="#E2E8F0", fg=TEXT_2)
        self.info_values["usb"].configure(
            text=("已连接" if rx.attached_over_usb else "否") if rx.attached_over_usb is not None else "—"
        )
        firmware = rx.identity.firmware or "—"
        serial = rx.identity.serial_number or "—"
        self.device_line.configure(text=f"接收器固件 {firmware}   序列号 {serial}")
        self._render_transmitters()

    def _render_transmitters(self) -> None:
        transmitters = self.status.transmitters
        connected = self.status.receiver.connected
        if connected:
            names = "、".join(f"TX{i}" for i in sorted(connected))
            self.tx_summary.configure(text=f"{len(connected)} 个在线 · {names}")
        else:
            self.tx_summary.configure(text="未连接发射器")
        for index in (1, 2):
            card = self.tx_cards[index]
            tx = transmitters.get(index)
            present = index in connected and tx is not None
            self._paint_tx_card(card, tx if present else None, present)

    def _paint_tx_card(self, card: dict, tx: duml.TransmitterStatus | None, present: bool) -> None:
        bg = "#F8FAFC" if present else "#FBFCFD"
        card["frame"].configure(bg=bg, highlightbackground=BORDER if present else "#EEF2F7")
        for widget in (card["header"], card["product"].master):
            widget.configure(bg=bg)
        for widget in (card["name"], card["product"], card["gauge"]):
            widget.configure(bg=bg)
        card["battery"].configure(bg=bg)
        card["nc"].master.configure(bg=bg)
        card["bar"].configure(bg=bg)
        card["level"].configure(bg=bg)

        if not present:
            card["product"].configure(text="未连接", fg=MUTED)
            card["state"].configure(text="离线", bg="#E2E8F0", fg=TEXT_2)
            card["battery"].configure(text="—", fg=MUTED)
            card["gauge"].configure(text="电量 —")
            card["nc"].configure(text="降噪 —", bg="#E2E8F0", fg=TEXT_2)
            card["charging"].configure(text="充电 —", bg="#E2E8F0", fg=TEXT_2)
            self._draw_bar(card["bar"], 0, "#E2E8F0")
            self._draw_bar(card["level"], 0, "#E2E8F0")
            return

        card["product"].configure(text=tx.identity.product_name or "DJI Mic Mini", fg=TEXT_2)
        card["state"].configure(
            text="在线" if not tx.is_charging else "充电中",
            bg=GREEN_SOFT if not tx.is_charging else AMBER_SOFT,
            fg=GREEN if not tx.is_charging else AMBER,
        )
        percent = tx.battery_percent
        card["battery"].configure(text=f"{percent}%" if percent is not None else "—", fg=TEXT)
        card["gauge"].configure(text=f"电量 {tx.battery_level or '—'}/7")
        card["nc"].configure(
            text=f"降噪 {'开' if tx.noise_cancelling else '关'}",
            bg=GREEN_SOFT if tx.noise_cancelling else "#E2E8F0",
            fg=GREEN if tx.noise_cancelling else TEXT_2,
        )
        card["charging"].configure(
            text="充电中" if tx.is_charging else "未充电",
            bg=AMBER_SOFT if tx.is_charging else "#E2E8F0",
            fg=AMBER if tx.is_charging else TEXT_2,
        )
        ratio = (8 - (tx.battery_level or 8)) / 7 if tx.battery_level else 0
        color = GREEN if ratio > 0.55 else (AMBER if ratio > 0.25 else RED)
        self._draw_bar(card["bar"], max(0.02, min(1.0, ratio)), color)
        level = (tx.meter_level or 0) / 100
        self._draw_bar(card["level"], max(0.01, min(1.0, level)), "#60A5FA")

    def _draw_bar(self, canvas: tk.Canvas, ratio: float, color: str) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 10)
        height = int(canvas["height"])
        canvas.create_rectangle(0, 0, width, height, fill="#E2E8F0", outline="")
        if ratio > 0:
            canvas.create_rectangle(0, 0, int(width * ratio), height, fill=color, outline="")

    # ---- actions ---------------------------------------------------------

    def _select_gain(self, value: int) -> None:
        self.selected_gain = value
        self.gain_dirty = value != self.status.receiver.gain_db
        self.gain_value.configure(text=f"{value:+d} dB")
        for pill_value, pill in self.gain_pills.items():
            pill.set_selected(pill_value == value)
        self._update_apply_state()

    def _select_channel(self, mode: int) -> None:
        self.selected_channel = mode
        self.channel_dirty = mode != self.status.receiver.channel_raw
        for option_mode, option in self.channel_options.items():
            option.set_selected(option_mode == mode)
        self._update_apply_state()

    def _update_apply_state(self) -> None:
        gain_enabled = self.connected and self.gain_dirty and not self.busy
        channel_enabled = self.connected and self.channel_dirty and not self.busy
        self._set_button_enabled(self.gain_apply, gain_enabled)
        self._set_button_enabled(self.channel_apply, channel_enabled)
        if hasattr(self, "auto_off_btn"):
            state = "normal" if self.connected and not self.busy else "disabled"
            self.auto_off_btn.configure(state=state)

    def _set_button_enabled(self, button: tk.Button, enabled: bool) -> None:
        if enabled:
            button.configure(
                state="normal", bg=ACCENT, activebackground=ACCENT_DARK, fg="white"
            )
        else:
            button.configure(
                state="disabled", bg="#E2E8F0", activebackground="#E2E8F0", fg="#94A3B8"
            )

    def _apply_gain(self) -> None:
        if not self.connected or not self.gain_dirty:
            return
        value = self.selected_gain

        def work() -> None:
            try:
                self.controller.set_gain(value)
                self.events.put(("toast", f"增益已设为 {value:+d} dB"))
                self.gain_dirty = False
            except Exception as error:
                self.events.put(("error", self._describe(error)))
            finally:
                self.events.put(("task_done", None))

        self._set_busy(True, "正在设置增益…")
        threading.Thread(target=work, daemon=True).start()

    def _apply_channel(self) -> None:
        if not self.connected or not self.channel_dirty:
            return
        mode = self.selected_channel
        name = "立体声" if mode == duml.CHANNEL_STEREO else "单声道"

        def work() -> None:
            try:
                self.controller.set_channel(mode)
                self.events.put(("toast", f"声道已切换为{name}"))
                self.channel_dirty = False
            except Exception as error:
                self.events.put(("error", self._describe(error)))
            finally:
                self.events.put(("task_done", None))

        self._set_busy(True, "正在切换声道…")
        threading.Thread(target=work, daemon=True).start()

    def _toggle_auto_off(self) -> None:
        if not self.connected or self.busy:
            return
        target = not bool(self.status.receiver.auto_power_off)

        def work() -> None:
            try:
                self.controller.set_auto_power_off(target)
                self.events.put(("toast", f"自动关机已{'开启' if target else '关闭'}"))
            except Exception as error:
                self.events.put(("error", self._describe(error)))
            finally:
                self.events.put(("task_done", None))

        self._set_busy(True, "正在修改自动关机…")
        threading.Thread(target=work, daemon=True).start()

    def _reconnect(self) -> None:
        if self.busy:
            return
        self._set_busy(True, "正在重新连接…")

        def work() -> None:
            try:
                self.controller.stop()
                self.controller.start()
                self.events.put(("toast", "正在重新查找接收器…"))
            except Exception as error:
                self.events.put(("error", str(error)))
            finally:
                self.events.put(("task_done", None))

        threading.Thread(target=work, daemon=True).start()
        self.after(2500, self._refresh_driver_banner)

    def _install_driver(self) -> None:
        script = app_dir() / "driver" / "install_winusb.ps1"
        if not script.exists():
            messagebox.showerror("找不到驱动脚本", f"缺少文件：\n{script}")
            return
        message = (
            "将给接收器的控制接口（MI_06）绑定微软 WinUSB 驱动。\n\n"
            "• 只影响 MI_06，不影响麦克风录音（MI_01）和 HID（MI_00）\n"
            "• 会创建一个本机自签名证书用于驱动签名\n"
            "• 可用 driver\\uninstall_winusb.bat 完整撤销\n\n"
            "需要管理员权限，接下来会出现 UAC 提示。继续吗？"
        )
        if not messagebox.askyesno("安装 WinUSB 驱动", message, icon="warning"):
            return
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
            messagebox.showerror("无法启动安装程序", f"ShellExecute 返回 {result}")
            return
        self._append_log("已启动驱动安装，请在 UAC 与安装窗口中确认…")
        self._driver_install_poll = 0
        self.after(1500, self._poll_driver_install)

    def _poll_driver_install(self) -> None:
        self._driver_install_poll += 1
        if driver_state() == "ready":
            self._append_log("驱动已就绪，重新连接控制接口")
            self._toast("驱动安装完成")
            self._reconnect()
            return
        if self._driver_install_poll < 60:
            self.after(1500, self._poll_driver_install)
        else:
            self._toast("驱动安装尚未完成，请检查安装窗口", error=True)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.busy = busy
        if message:
            self.status_label.configure(text=message, fg=ACCENT)
        self._update_apply_state()

    def _toast(self, message: str, error: bool = False) -> None:
        self.status_label.configure(text=message, fg=RED if error else GREEN)
        self.after(4000, lambda: self.status_label.configure(text="就绪", fg=MUTED))

    def _append_log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 200:
            self.log_text.delete("1.0", "2.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _copy_diagnostics(self) -> None:
        data = {
            "app": f"DJI Mic PC Control {__version__}",
            "driver": driver_state(),
            "connected": self.connected,
            "status": {
                "receiver": {
                    "product": self.status.receiver.identity.product_name,
                    "firmware": self.status.receiver.identity.firmware,
                    "serial": self.status.receiver.identity.serial_number,
                    "gain_db": self.status.receiver.gain_db,
                    "channel": self.status.receiver.channel_name,
                    "noise_cancelling": self.status.receiver.noise_cancelling,
                    "auto_power_off": self.status.receiver.auto_power_off,
                    "connected": sorted(self.status.receiver.connected),
                },
                "transmitters": {
                    str(i): {
                        "battery": tx.battery_level,
                        "charging": tx.is_charging,
                        "noise_cancelling": tx.noise_cancelling,
                    }
                    for i, tx in self.status.transmitters.items()
                },
            },
            "log": self.log_text.get("1.0", "end").strip(),
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._toast("诊断信息已复制到剪贴板")

    def _describe(self, error: Exception) -> str:
        if isinstance(error, CommandRejected):
            return str(error)
        if isinstance(error, (NotConnected, CommandTimeout, NotApplied)):
            return str(error)
        if isinstance(error, DeviceError):
            return str(error)
        return f"{type(error).__name__}: {error}"

    def _on_close(self) -> None:
        try:
            self.controller.stop()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
