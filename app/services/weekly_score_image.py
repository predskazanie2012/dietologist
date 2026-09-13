import math
import struct
import zlib


RGB = tuple[int, int, int]


def render_weekly_score_target(score: int, width: int = 640, height: int = 420) -> bytes:
    score = max(1, min(10, int(score or 0)))
    pixels = bytearray([248, 250, 252] * width * height)

    center_x = width // 2
    center_y = height // 2
    radius = min(width, height) // 2 - 38
    rings: tuple[tuple[float, RGB], ...] = (
        (1.00, (239, 68, 68)),
        (0.82, (249, 115, 22)),
        (0.64, (250, 204, 21)),
        (0.46, (132, 204, 22)),
        (0.28, (34, 197, 94)),
    )

    _draw_circle(pixels, width, height, center_x + 5, center_y + 7, radius + 2, (226, 232, 240))
    for scale, color in rings:
        _draw_circle(pixels, width, height, center_x, center_y, int(radius * scale), color)
    _draw_circle_outline(pixels, width, height, center_x, center_y, radius, (30, 41, 59), 3)
    _draw_circle_outline(pixels, width, height, center_x, center_y, int(radius * 0.28), (255, 255, 255), 3)

    # 1/10 is on the outer edge, 10/10 is exactly in the center.
    offset = radius * (10 - score) / 9
    dot_x = int(center_x - offset)
    dot_y = center_y
    _draw_circle(pixels, width, height, dot_x, dot_y, 18, (255, 255, 255))
    _draw_circle(pixels, width, height, dot_x, dot_y, 13, (15, 23, 42))

    return _png_rgb(width, height, bytes(pixels))


def _draw_circle(pixels: bytearray, width: int, height: int, cx: int, cy: int, radius: int, color: RGB) -> None:
    r2 = radius * radius
    x_min = max(0, cx - radius)
    x_max = min(width - 1, cx + radius)
    y_min = max(0, cy - radius)
    y_max = min(height - 1, cy + radius)
    for y in range(y_min, y_max + 1):
        dy2 = (y - cy) * (y - cy)
        for x in range(x_min, x_max + 1):
            if (x - cx) * (x - cx) + dy2 <= r2:
                index = (y * width + x) * 3
                pixels[index:index + 3] = bytes(color)


def _draw_circle_outline(
    pixels: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    color: RGB,
    thickness: int,
) -> None:
    outer = radius
    inner = max(0, radius - thickness)
    outer2 = outer * outer
    inner2 = inner * inner
    x_min = max(0, cx - outer)
    x_max = min(width - 1, cx + outer)
    y_min = max(0, cy - outer)
    y_max = min(height - 1, cy + outer)
    for y in range(y_min, y_max + 1):
        dy2 = (y - cy) * (y - cy)
        for x in range(x_min, x_max + 1):
            distance2 = (x - cx) * (x - cx) + dy2
            if inner2 <= distance2 <= outer2:
                index = (y * width + x) * 3
                pixels[index:index + 3] = bytes(color)


def _png_rgb(width: int, height: int, rgb: bytes) -> bytes:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(rgb[start:start + stride])

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
