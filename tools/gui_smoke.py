"""Headless smoke test for the Tk UI action path (requires the receiver)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dji_mic.ui import App  # noqa: E402


def pump(app: App, seconds: float, predicate=None) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if predicate and predicate():
            return True
        time.sleep(0.05)
    return bool(predicate and predicate())


def main() -> int:
    app = App()
    app.withdraw()
    try:
        if not pump(app, 8, lambda: app.connected and app.status.receiver.gain_db is not None):
            print("FAIL: device did not connect")
            return 1
        original = app.status.receiver.gain_db
        print("connected, gain =", original)

        app._select_gain(0)
        if not app.gain_dirty:
            print("FAIL: selecting 0 dB did not mark dirty")
            return 1
        app._apply_gain()
        if not pump(app, 8, lambda: app.status.receiver.gain_db == 0 and not app.busy):
            print("FAIL: gain did not change to 0")
            return 1
        print("PASS: UI set gain to 0 dB")

        app._select_gain(original)
        app._apply_gain()
        if not pump(app, 8, lambda: app.status.receiver.gain_db == original and not app.busy):
            print("FAIL: gain did not restore")
            return 1
        print("PASS: restored gain", original)

        before_auto = app.status.receiver.auto_power_off
        app._toggle_auto_off()
        if not pump(app, 8, lambda: app.status.receiver.auto_power_off != before_auto and not app.busy):
            print("FAIL: auto power off did not toggle")
            return 1
        print("PASS: toggled auto power off to", app.status.receiver.auto_power_off)
        app._toggle_auto_off()
        if not pump(app, 8, lambda: app.status.receiver.auto_power_off == before_auto and not app.busy):
            print("FAIL: auto power off did not restore")
            return 1
        print("PASS: restored auto power off", before_auto)
        return 0
    finally:
        app._on_close()


if __name__ == "__main__":
    raise SystemExit(main())
