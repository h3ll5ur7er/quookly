#!/usr/bin/env python3
"""Generate the application icons.

Icons are generated from this script rather than committed as opaque binaries, so the
mark can be adjusted and every size stays consistent. Pure standard library — there is no
image toolchain to depend on, and adding one for four small PNGs is not worth it.

The mark is a lowercase q: a ring with a tail, in the primary colour of the light theme.

    just frontend icons
"""

import struct
import zlib
from pathlib import Path

PRIMARY = (0xA5, 0x39, 0x1A)  # --primary, light theme
INK = (0xFB, 0xF9, 0xF6)  # --surface, light theme
SAMPLES = 3  # supersampling factor, for edges that are not jagged


def _coverage(inside, cx: float, cy: float, scale: float) -> float:
    """How much of one pixel the shape covers, by sampling a grid inside it."""
    hits = 0
    step = 1.0 / SAMPLES
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            x = (cx + (sx + 0.5) * step) / scale
            y = (cy + (sy + 0.5) * step) / scale
            if inside(x, y):
                hits += 1
    return hits / (SAMPLES * SAMPLES)


def _blend(under: tuple[int, int, int], over: tuple[int, int, int], alpha: float):
    return tuple(round(u + (o - u) * alpha) for u, o in zip(under, over, strict=True))


def render(size: int, *, padding: float) -> bytes:
    """Render the mark at `size` px. `padding` insets it, for maskable icons."""
    inner = 1.0 - 2 * padding

    def in_background(x: float, y: float) -> bool:
        # Rounded square covering the whole canvas; maskable variants inset the mark
        # instead of the background, so the safe zone is respected without a border.
        radius = 0.22
        dx = max(radius - x, x - (1 - radius), 0.0)
        dy = max(radius - y, y - (1 - radius), 0.0)
        return dx * dx + dy * dy <= radius * radius

    def in_mark(x: float, y: float) -> bool:
        # Map into the padded box so one description serves every size.
        u = (x - padding) / inner
        v = (y - padding) / inner
        if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
            return False

        # The bowl: a ring, slightly above centre.
        dx, dy = u - 0.44, v - 0.42
        distance = (dx * dx + dy * dy) ** 0.5
        if 0.19 <= distance <= 0.30:
            return True

        # The tail: a stroke down the right of the bowl, with a rounded foot.
        if 0.66 <= u <= 0.77 and 0.42 <= v <= 0.82:
            return True
        return (u - 0.715) ** 2 + (v - 0.82) ** 2 <= 0.055**2

    pixels = bytearray()
    for py in range(size):
        pixels.append(0)  # PNG filter type for the row
        for px in range(size):
            background = _coverage(in_background, px, py, size)
            if background == 0.0:
                pixels.extend((0, 0, 0, 0))
                continue
            mark = _coverage(in_mark, px, py, size)
            colour = _blend(PRIMARY, INK, mark)
            pixels.extend((*colour, round(255 * background)))
    return bytes(pixels)


def write_png(path: Path, size: int, raw: bytes) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "public" / "icons"
    out.mkdir(parents=True, exist_ok=True)

    # Plain icons fill the canvas; maskable ones keep the mark inside the safe zone that
    # a platform may crop to a circle or a squircle.
    for size in (192, 512):
        write_png(out / f"icon-{size}.png", size, render(size, padding=0.14))
        write_png(out / f"icon-maskable-{size}.png", size, render(size, padding=0.24))

    for path in sorted(out.iterdir()):
        print(f"  {path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
