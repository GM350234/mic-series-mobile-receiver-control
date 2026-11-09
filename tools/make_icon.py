"""Generate assets/icon.ico (a simple microphone mark)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icon.ico"


def draw(size: int = 256) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def s(value: float) -> int:
        return int(round(value * scale))

    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=s(58), fill="#0F172A")
    # microphone capsule
    draw.rounded_rectangle((s(96), s(48), s(160), s(154)), radius=s(32), fill="#3B82F6")
    for y in (s(76), s(96), s(116)):
        draw.rounded_rectangle((s(108), y, s(148), y + s(7)), radius=s(3), fill="#DBEAFE")
    # yoke / stand
    draw.arc((s(72), s(92), s(184), s(190)), start=0, end=180, fill="#93C5FD", width=s(12))
    draw.rectangle((s(122), s(184), s(134), s(212)), fill="#93C5FD")
    draw.rounded_rectangle((s(98), s(210), s(158), s(220)), radius=s(5), fill="#93C5FD")
    return image


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = draw(256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    image.save(OUT, format="ICO", sizes=sizes)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
