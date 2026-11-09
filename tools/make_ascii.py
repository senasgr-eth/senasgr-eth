"""Turn the GitHub avatar into assets/ascii-art.txt.

Run this only when the avatar changes -- the generated art is committed, so the
daily action never needs Pillow.

    python tools/make_ascii.py                 # fetches github.com/senasgr-eth.png
    python tools/make_ascii.py path/to/img.png

The prep pass matters: the source is a scanned manga panel, so a median filter
plus a white point removes the paper texture before the luminance is mapped to
the character ramp.
"""

from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "ascii-art.txt"
AVATAR = "https://github.com/senasgr-eth.png?size=460"

COLS = 48
RAMP = " .:-=+*#%@"
WHITE_POINT = 205


def ascii_lines(image: Image.Image) -> list[str]:
    image = ImageOps.autocontrast(image.convert("L"), cutoff=4)
    image = image.filter(ImageFilter.MedianFilter(3))
    image = image.point(
        lambda value: 255 if value >= WHITE_POINT else int(value * 255 / WHITE_POINT)
    )

    width, height = image.size
    # A monospace cell is about half as wide as it is tall.
    rows = max(1, round(COLS * (height / width) * 0.5))
    small = image.resize((COLS, rows), Image.LANCZOS)
    pixels = small.load()
    ramp = len(RAMP) - 1
    return [
        "".join(RAMP[round((1 - pixels[x, y] / 255) * ramp)] for x in range(COLS))
        for y in range(rows)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", help="local image (defaults to the GitHub avatar)")
    args = parser.parse_args()

    if args.image:
        raw = Path(args.image).read_bytes()
    else:
        with urllib.request.urlopen(AVATAR) as response:
            raw = response.read()

    lines = ascii_lines(Image.open(io.BytesIO(raw)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({COLS}x{len(lines)})")


if __name__ == "__main__":
    main()
