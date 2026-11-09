"""Capture a few real frames from the receiver into tests/fixtures/*.hex."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dji_mic import duml
from dji_mic.winusb import WinUsbDevice, find_interface_path


def main() -> int:
    path = find_interface_path()
    if not path:
        print("MI_06 not found; install the WinUSB binding first.")
        return 1
    out = ROOT / "tests" / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    device = WinUsbDevice(path)
    device.open()
    parser = duml.StreamParser()
    seen: dict[tuple[int, int, int], bytes] = {}
    deadline = time.time() + 4
    try:
        while time.time() < deadline:
            data = device.read(timeout_ms=300)
            if not data:
                continue
            for frame in parser.feed(data):
                key = (frame.command_set, frame.command_id, len(frame.payload))
                if key not in seen:
                    seen[key] = frame.encode()
    finally:
        device.close()
    for (command_set, command_id, _), raw in seen.items():
        name = f"{command_set:02x}_{command_id:02x}_{len(raw):03d}.hex"
        (out / name).write_text(raw.hex(" "), encoding="utf-8")
        print(name, len(raw))
    print(f"{len(seen)} unique frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
