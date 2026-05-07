from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\extraction-preview")


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def sample_background(img: Image.Image) -> tuple[int, int, int]:
    w, h = img.size
    samples = []
    step = max(1, min(w, h) // 80)
    for x in range(0, w, step):
        samples.append(img.getpixel((x, 0))[:3])
        samples.append(img.getpixel((x, h - 1))[:3])
    for y in range(0, h, step):
        samples.append(img.getpixel((0, y))[:3])
        samples.append(img.getpixel((w - 1, y))[:3])
    buckets: dict[tuple[int, int, int], int] = {}
    for r, g, b in samples:
        key = (round(r / 8) * 8, round(g / 8) * 8, round(b / 8) * 8)
        buckets[key] = buckets.get(key, 0) + 1
    bg = max(buckets.items(), key=lambda item: item[1])[0]
    return tuple(max(0, min(255, c)) for c in bg)


def make_alpha(img: Image.Image, threshold: int = 34) -> Image.Image:
    rgb = img.convert("RGB")
    bg = sample_background(rgb)
    rgba = rgb.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if color_distance((r, g, b), bg) <= threshold:
                px[x, y] = (r, g, b, 0)
    return rgba


def trim_alpha(img: Image.Image, pad: int = 8) -> Image.Image:
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    l = max(0, l - pad)
    t = max(0, t - pad)
    r = min(img.width, r + pad)
    b = min(img.height, b + pad)
    return img.crop((l, t, r, b))


def foreground_mask(img: Image.Image, threshold: int = 34) -> np.ndarray:
    rgb = np.asarray(img.convert("RGB"), dtype=np.int16)
    bg = np.array(sample_background(img.convert("RGB")), dtype=np.int16)
    dist = np.abs(rgb - bg).sum(axis=2)
    return dist > threshold


def connected_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    boxes: list[tuple[int, int, int, int, int]] = []
    for sy in range(h):
        xs = np.flatnonzero(mask[sy] & ~seen[sy])
        for sx in xs:
            if seen[sy, sx] or not mask[sy, sx]:
                continue
            stack = [(int(sx), int(sy))]
            seen[sy, sx] = True
            min_x = max_x = int(sx)
            min_y = max_y = int(sy)
            area = 0
            while stack:
                x, y = stack.pop()
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((nx, ny))
            boxes.append((min_x, min_y, max_x + 1, max_y + 1, area))
    return boxes


def smooth_columns(active: np.ndarray, radius: int = 22) -> np.ndarray:
    padded = np.pad(active.astype(np.uint8), (radius, radius), mode="constant")
    kernel = np.ones(radius * 2 + 1, dtype=np.uint8)
    return np.convolve(padded, kernel, mode="valid") > 0


def column_segments(mask: np.ndarray) -> list[tuple[int, int]]:
    col_counts = mask.sum(axis=0)
    active = col_counts > max(6, mask.shape[0] * 0.012)
    active = smooth_columns(active, 22)
    segments: list[tuple[int, int]] = []
    start = None
    for i, value in enumerate(active):
        if value and start is None:
            start = i
        elif not value and start is not None:
            segments.append((start, i))
            start = None
    if start is not None:
        segments.append((start, len(active)))
    return segments


def crop_region_components(sheet: Image.Image, rect: tuple[int, int, int, int]) -> list[Image.Image]:
    l, t, r, b = rect
    region = sheet.crop((l, t, r, b))
    rgba = make_alpha(region)
    mask = foreground_mask(region)
    raw_boxes = connected_boxes(mask)
    components = []
    for x1, y1, x2, y2, area in raw_boxes:
        bw = x2 - x1
        bh = y2 - y1
        if area < 16 or bw > region.width * 0.55 or bh < 2:
            continue
        if bh <= 5 and bw > 40:
            continue
        components.append((x1, y1, x2, y2, area))

    main_boxes = []
    for x1, y1, x2, y2, area in components:
        bw = x2 - x1
        bh = y2 - y1
        if area < 650 or bw < 28 or bh < 34:
            continue
        if bw > 360 or bh > region.height * 0.96:
            continue
        main_boxes.append((x1, y1, x2, y2))

    boxes: list[tuple[int, int, int, int]] = []
    for mx1, my1, mx2, my2 in main_boxes:
        ux1, uy1, ux2, uy2 = mx1, my1, mx2, my2
        for x1, y1, x2, y2, area in components:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            near_x = mx1 - 55 <= cx <= mx2 + 55
            near_y = my1 - 45 <= cy <= my2 + 45
            if near_x and near_y:
                ux1 = min(ux1, x1)
                uy1 = min(uy1, y1)
                ux2 = max(ux2, x2)
                uy2 = max(uy2, y2)
        boxes.append((ux1, uy1, ux2, uy2))

    deduped = []
    boxes.sort(key=lambda box: (box[0], box[1]))
    for box in boxes:
        if not deduped or abs(box[0] - deduped[-1][0]) > 12:
            deduped.append(box)
    boxes = deduped
    frames = []
    for x1, y1, x2, y2 in boxes:
        pad = 8
        crop = rgba.crop((max(0, x1 - pad), max(0, y1 - pad), min(region.width, x2 + pad), min(region.height, y2 + pad)))
        frames.append(trim_alpha(crop, 2))
    return frames


def crop_frames(sheet: Image.Image, regions: Iterable[tuple[str, tuple[int, int, int, int]]]) -> dict[str, list[Image.Image]]:
    return {name: crop_region_components(sheet, rect) for name, rect in regions}


def compose_preview(title: str, frames: dict[str, list[Image.Image]]) -> Image.Image:
    scale = 2
    row_h = 160
    label_w = 120
    cell_w = 132
    width = label_w + max(len(v) for v in frames.values()) * cell_w
    height = 48 + len(frames) * row_h
    canvas = Image.new("RGBA", (width, height), (246, 242, 225, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 12), title, fill=(42, 48, 39, 255))
    y = 48
    for action, imgs in frames.items():
        draw.text((16, y + 62), action, fill=(42, 48, 39, 255))
        for i, frame in enumerate(imgs):
            f = frame.copy()
            f.thumbnail((110, 130), Image.Resampling.NEAREST)
            x = label_w + i * cell_w + (cell_w - f.width) // 2
            canvas.alpha_composite(f, (x, y + (row_h - f.height) // 2))
        y += row_h
    return canvas.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    hero = Image.open(SOURCE_DIR / "image (3).png")
    hero_regions = [
        ("idle", (210, 95, 1005, 310)),
        ("walk", (205, 405, 1010, 625)),
        ("run", (430, 710, 1015, 945)),
    ]
    hero_frames = crop_frames(hero, hero_regions)
    compose_preview("hero transparent frame extraction", hero_frames).save(OUT_DIR / "hero_extraction_preview.png")

    dragon = Image.open(SOURCE_DIR / "image (4).png")
    dragon_regions = [
        ("idle", (40, 65, 950, 260)),
        ("walk", (20, 320, 1010, 520)),
        ("run", (20, 560, 1010, 755)),
        ("fly", (20, 790, 1010, 985)),
    ]
    dragon_frames = crop_frames(dragon, dragon_regions)
    compose_preview("dragon transparent frame extraction", dragon_frames).save(OUT_DIR / "dragon_extraction_preview.png")


if __name__ == "__main__":
    main()
