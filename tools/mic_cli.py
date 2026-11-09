"""Command-line companion for testing the receiver without the GUI.

Examples:
    python tools/mic_cli.py status
    python tools/mic_cli.py status --json
    python tools/mic_cli.py set-gain 0
    python tools/mic_cli.py set-gain +6
    python tools/mic_cli.py set-channel stereo
    python tools/mic_cli.py caps
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dji_mic import duml  # noqa: E402
from dji_mic.device import MicController  # noqa: E402
from dji_mic.winusb import driver_state  # noqa: E402


def status_dict(status: duml.MicStatus) -> dict:
    rx = status.receiver
    return {
        "receiver": {
            "product": rx.identity.product_name,
            "firmware": rx.identity.firmware,
            "serial": rx.identity.serial_number,
            "gain_db": rx.gain_db,
            "channel": rx.channel_name,
            "channel_raw": rx.channel_raw,
            "noise_cancelling": rx.noise_cancelling,
            "noise_level": rx.noise_level,
            "auto_power_off": rx.auto_power_off,
            "battery_level": rx.battery_level,
            "usb": rx.attached_over_usb,
            "connected": sorted(rx.connected),
        },
        "transmitters": {
            str(index): {
                "product": tx.identity.product_name,
                "firmware": tx.identity.firmware,
                "battery_level": tx.battery_level,
                "battery_percent": tx.battery_percent,
                "charging": tx.is_charging,
                "noise_cancelling": tx.noise_cancelling,
                "meter_level": tx.meter_level,
            }
            for index, tx in status.transmitters.items()
        },
    }


def wait_ready(controller: MicController, timeout: float = 6.0) -> duml.MicStatus:
    deadline = time.monotonic() + timeout
    best = None
    while time.monotonic() < deadline:
        status = controller.status
        if controller.connected and status.receiver.gain_db is not None:
            best = status
            # Identity pushes arrive once at connect; wait for them so the
            # firmware/serial fields are populated.
            if status.receiver.identity.firmware is not None:
                return status
        time.sleep(0.1)
    if best is not None:
        return best
    if not controller.connected:
        raise SystemExit(f"无法连接接收器（驱动状态：{driver_state()}）")
    raise SystemExit("已连接，但没有收到状态帧")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    command = argv[0]
    controller = MicController()
    controller.start()
    try:
        if command == "status":
            status = wait_ready(controller)
            if "--json" in argv:
                print(json.dumps(status_dict(status), ensure_ascii=False, indent=2))
            else:
                print_status(status)
        elif command == "caps":
            wait_ready(controller)
            caps = controller.refresh_capabilities()
            print(json.dumps({str(k): {str(i): v.hex() for i, v in items.items()} for k, items in caps.items()}, indent=2))
            print("gain range:", controller.gain_range())
        elif command == "set-gain":
            if len(argv) < 2:
                raise SystemExit("用法: set-gain <dB>")
            wait_ready(controller)
            db = int(argv[1])
            controller.set_gain(db)
            print(f"已设置增益 {db:+d} dB")
            print_status(controller.status)
        elif command == "set-channel":
            if len(argv) < 2:
                raise SystemExit("用法: set-channel mono|stereo")
            wait_ready(controller)
            mode = duml.CHANNEL_MONO if argv[1] == "mono" else duml.CHANNEL_STEREO
            controller.set_channel(mode)
            print(f"已设置声道 {controller.status.receiver.channel_name}")
            print_status(controller.status)
        else:
            print(__doc__)
            return 1
    finally:
        controller.stop()
    return 0


def print_status(status: duml.MicStatus) -> None:
    rx = status.receiver
    print(f"接收器: {rx.identity.product_name or 'DJI Mic Mini 2'}")
    print(f"  固件: {rx.identity.firmware or '—'}   序列号: {rx.identity.serial_number or '—'}")
    print(f"  增益: {rx.gain_db:+d} dB" if rx.gain_db is not None else "  增益: —")
    print(f"  声道: {rx.channel_name}")
    print(f"  降噪: {'开' if rx.noise_cancelling else '关'}  档位: {rx.noise_level}")
    print(f"  自动关机: {'开' if rx.auto_power_off else '关'}   USB: {'是' if rx.attached_over_usb else '否'}")
    if not status.transmitters:
        print("发射器: 未连接")
    for index, tx in sorted(status.transmitters.items()):
        print(f"发射器 TX{index}: {tx.identity.product_name or 'DJI Mic Mini'}")
        print(
            f"  电量: {tx.battery_level}/7 (~{tx.battery_percent}%)  "
            f"充电: {'是' if tx.is_charging else '否'}  "
            f"降噪: {'开' if tx.noise_cancelling else '关'}"
        )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
