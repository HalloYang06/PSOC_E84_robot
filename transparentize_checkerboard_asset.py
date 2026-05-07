from __future__ import annotations

import shutil
import sys
from collections import deque
from pathlib import Path

from PIL import Image


def is_bg(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    mx = max(r, g, b)
    mn = min(r, g, b)
    return a > 0 and (mx - mn) <= 18 and mn >= 214


def is_soft_bg(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    mx = max(r, g, b)
    mn = min(r, g, b)
    return a > 0 and (mx - mn) <= 24 and mn >= 205


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: transparentize_checkerboard_asset.py <png>")
        return 2

    src = Path(sys.argv[1])
    backup_dir = src.parents[5] / "Education2D_AssetBackups" / "5月2日ui素材_originals"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / src.name
    preview = src.with_name(f"{src.stem}_transparency_preview.png")

    if not backup.exists():
        shutil.copy2(src, backup)

    image = Image.open(src).convert("RGBA")
    width, height = image.size
    pixels = image.load()
    mask = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        idx = y * width + x
        if not mask[idx] and is_bg(pixels[x, y]):
            mask[idx] = 1
            queue.append((x, y))

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < width and 0 <= ny < height:
                idx = ny * width + nx
                if not mask[idx] and is_bg(pixels[nx, ny]):
                    mask[idx] = 1
                    queue.append((nx, ny))

    expanded = bytearray(mask)
    for y in range(1, height - 1):
        row = y * width
        for x in range(1, width - 1):
            idx = row + x
            if mask[idx] or not is_soft_bg(pixels[x, y]):
                continue
            if mask[idx - 1] or mask[idx + 1] or mask[idx - width] or mask[idx + width]:
                expanded[idx] = 1

    output = Image.new("RGBA", (width, height))
    out_pixels = output.load()
    cleared = 0
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            idx = y * width + x
            if expanded[idx] or a == 0:
                out_pixels[x, y] = (0, 0, 0, 0)
                cleared += 1
            else:
                out_pixels[x, y] = (r, g, b, a)

    output.save(src)
    preview_image = Image.new("RGBA", (width, height), (20, 25, 29, 255))
    preview_image.alpha_composite(output)
    preview_image.save(preview)

    print(f"done cleared={cleared}/{width * height}")
    print(f"backup={backup}")
    print(f"preview={preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
