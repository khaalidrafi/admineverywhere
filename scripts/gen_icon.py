#!/usr/bin/env python3
"""Generate brand icons: gradient rounded-square PNGs with a 2x2 grid mark.

Pure stdlib (struct + zlib), no PIL. The default mark is a 2x2 rounded
square grid — a generic "admin table" glyph with no letters, so it works
as a neutral identity for any product. `--mark dot` keeps the original
placeholder style (white center dot).

Outputs (written into <out-dir>):
- icon.png        512x512  favicon / app fallback
- icon-1024.png   1024x1024 source for `npx tauri icon`

Usage:
  python scripts/gen_icon.py <hex-primary> <hex-accent> <out-dir> [--mark grid|dot]

Examples:
  python scripts/gen_icon.py '#4f46e5' '#06b6d4' app/brands/default/assets
  python scripts/gen_icon.py '#006e33' '#22be6f' app/brands/freshorama/assets
"""
import argparse
import math
import struct
import sys
import zlib
from pathlib import Path


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: Path, size: int, rgb_fn):
    rows = []
    for y in range(size):
        row = bytearray(b"\x00")  # filter byte
        for x in range(size):
            row += bytes(rgb_fn(x, y))
        rows.append(row)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # RGBA
    png = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
           + png_chunk(b"IDAT", zlib.compress(bytes(b"".join(bytes(r) for r in rows)), 9))
           + png_chunk(b"IEND", b""))
    path.write_bytes(png)


def hex_rgb(h: str):
    return tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def rounded_square_inside(x: float, y: float, cx: float, cy: float,
                          half: float, radius: float) -> bool:
    """Point-in rounded-square test (same shape math as the outer tile)."""
    if abs(x - cx) > half or abs(y - cy) > half:
        return False
    dx = abs(x - cx) - (half - radius)
    dy = abs(y - cy) - (half - radius)
    if dx > 0 and dy > 0:
        return math.sqrt(dx * dx + dy * dy) <= radius
    return True


def make_icon(primary: str, accent: str, out: Path, mark: str = "grid"):
    p, a = hex_rgb(primary), hex_rgb(accent)

    # Grid-mark geometry (fractions of the tile). TL/BR full opacity,
    # TR/BL translucent — reads as a data grid, stays legible at 32px.
    centers = (0.355, 0.645)
    cell_half, cell_radius = 0.117, 0.05

    def px_factory(size: int):
        radius = size * 0.18
        cx = size / 2

        def px(x: int, y: int):
            # diagonal gradient base
            t = (x + y) / (2 * size)
            color = tuple(int(p[i] + (a[i] - p[i]) * t) for i in range(3))
            alpha = 255
            # rounded-corner transparency of the outer tile
            dx = abs(x - cx) - (cx - radius)
            dy = abs(y - cx) - (cx - radius)
            if dx > 0 and dy > 0 and math.sqrt(dx * dx + dy * dy) > radius:
                alpha = 0
            if mark == "dot":
                if math.hypot(x - cx, y - cx) < size * 0.07:
                    color = (255, 255, 255)
            else:  # grid
                for iy, cyf in enumerate(centers):
                    for ix, cxf in enumerate(centers):
                        if rounded_square_inside(
                                x, y, cxf * size, cyf * size,
                                cell_half * size, cell_radius * size):
                            opacity = 0.95 if (ix + iy) % 2 == 0 else 0.55
                            blended = tuple(
                                int(255 * opacity + color[i] * (1 - opacity))
                                for i in range(3))
                            color = blended
            return (*color, alpha)

        return px

    out.mkdir(parents=True, exist_ok=True)
    write_png(out / "icon.png", 512, px_factory(512))
    write_png(out / "icon-1024.png", 1024, px_factory(1024))
    print(f"wrote {out}/icon.png (512) and {out}/icon-1024.png (mark: {mark})")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("primary", help="hex color like #4f46e5")
    ap.add_argument("accent", help="hex color like #06b6d4")
    ap.add_argument("out_dir", help="destination directory (created)")
    ap.add_argument("--mark", choices=["grid", "dot"], default="grid")
    args = ap.parse_args(argv)
    make_icon(args.primary, args.accent, Path(args.out_dir), args.mark)


if __name__ == "__main__":
    main(sys.argv[1:])
