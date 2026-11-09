"""Dump raw bytes from the receiver's vendor interface (MI_06) for inspection.

Usage:
    python tools/raw_dump.py [seconds]

Requires the WinUSB binding installed by driver/install_winusb.bat.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dji_mic.winusb import WinUsbDevice, find_interface_path  # noqa: E402


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    path = find_interface_path()
    if not path:
        print("MI_06 not found; install the WinUSB binding first.")
        return 1
    device = WinUsbDevice(path)
    device.open()
    print(f"opened MI_06 for {seconds:.0f}s, IN=0x86")
    deadline = time.time() + seconds
    total = 0
    try:
        while time.time() < deadline:
            chunk = device.read(timeout_ms=300)
            if chunk is None:
                print("read error")
                break
            if not chunk:
                continue
            total += len(chunk)
            print(f"[{time.strftime('%H:%M:%S')}] {len(chunk):4d} bytes")
            for off in range(0, len(chunk), 16):
                part = chunk[off:off + 16]
                hexs = " ".join(f"{b:02x}" for b in part)
                text = "".join(chr(b) if 32 <= b < 127 else "." for b in part)
                print(f"  {off:04x}  {hexs:<47}  {text}")
    finally:
        device.close()
    print(f"total {total} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
