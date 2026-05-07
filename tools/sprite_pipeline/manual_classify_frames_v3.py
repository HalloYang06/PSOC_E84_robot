from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from extract_preview import connected_boxes, foreground_mask, make_alpha, trim_alpha


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\classified-frames-v3")


SPECS = {
    "hero": ("image (3).png", {"idle": ((210, 85, 1015, 320), 4), "walk": ((205, 385, 1015, 635), 6), "run": ((205, 690, 1015, 965), 6)}),
    "dragon": ("image (4).png", {"idle": ((0, 55, 1015, 265), 4), "walk": ((0, 310, 1015, 525), 6), "run": ((0, 555, 1015, 765), 6), "fly": ((0, 780, 1015, 1005), 6)}),
    "fire_fox": ("image (5).png", {"idle": ((370, 45, 1015, 230), 4), "walk": ((370, 250, 1015, 465), 6), "run": ((0, 525, 1015, 750), 6), "actions": ((0, 760, 1015, 985), 6)}),
    "turtle": ("image (6).png", {"idle": ((0, 60, 1015, 265), 4), "walk": ((0, 295, 1015, 525), 6), "run": ((0, 525, 1015, 750), 5), "swim": ((0, 780, 1015, 1005), 4)}),
    "wind_bird": ("image (7).png", {"idle": ((300, 55, 1015, 270), 5), "walk": ((0, 380, 1015, 575), 6), "run": ((0, 620, 1015, 780), 6), "fly": ((0, 790, 1015, 1010), 6)}),
    "woodsprout": ("image (8).png", {"idle": ((300, 65, 1015, 285), 3), "walk": ((0, 330, 1015, 535), 6), "run": ((0, 535, 1015, 730), 5), "actions": ((0, 760, 1015, 985), 5)}),
    "leafbug": ("image (10).png", {"idle": ((350, 60, 1015, 210), 4), "walk": ((350, 260, 1015, 430), 5), "run": ((0, 490, 1015, 640), 6), "actions": ((0, 680, 1015, 835), 5)}),
    "pixelbolt": ("image (11).png", {"idle": ((120, 80, 760, 260), 4), "walk": ((120, 300, 1015, 500), 6), "run": ((120, 525, 1015, 730), 6), "actions": ((0, 760, 1015, 970), 6)}),
    "digglet": ("image (12).png", {"idle": ((290, 55, 1015, 210), 6), "walk": ((290, 250, 1015, 410), 6), "run": ((290, 430, 1015, 640), 8), "burrow": ((0, 700, 1015, 875), 7)}),
    "stone_golem": ("image (14).png", {"idle": ((0, 55, 1015, 275), 4), "walk": ((0, 315, 1015, 530), 6), "run": ((0, 555, 1015, 745), 5), "dig": ((0, 780, 1015, 985), 6)}),
    "elementals": ("image (2).png", {"leaf": ((0, 15, 1015, 150), 6), "water": ((0, 170, 1015, 315), 6), "rock": ((0, 335, 1015, 475), 6), "fire": ((0, 495, 1015, 635), 6), "cloud": ((0, 655, 1015, 795), 6), "crystal": ((0, 815, 1015, 1010), 6)}),
}


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def expand(box: tuple[int, int, int, int], x: int, y: int) -> tuple[int, int, int, int]:
    return box[0] - x, box[1] - y, box[2] + x, box[3] + y


def select_frames(region: Image.Image, count: int) -> list[Image.Image]:
    rgba = make_alpha(region)
    mask = foreground_mask(region)
    comps = []
    for x1, y1, x2, y2, area in connected_boxes(mask):
        w, h = x2 - x1, y2 - y1
        if area < 120 or w < 6 or h < 6:
            continue
        if h <= 5 or (w > 80 and h < 15):
            continue
        # Remove labels near the top edge; frames themselves have enough vertical body.
        if y1 < 18 and h < 42:
            continue
        comps.append((x1, y1, x2, y2, area))

    mains = []
    for x1, y1, x2, y2, area in comps:
        w, h = x2 - x1, y2 - y1
        if area < 450 or w < 24 or h < 28:
            continue
        if w > region.width * 0.38 or h > region.height * 0.95:
            continue
        mains.append((x1, y1, x2, y2, area))

    # Prefer the expected number of largest body-like components, then restore x order.
    mains = sorted(mains, key=lambda item: item[4], reverse=True)[:count]
    mains.sort(key=lambda item: item[0])
    frames = []
    used_centers: list[float] = []
    for x1, y1, x2, y2, _ in mains:
        cx = (x1 + x2) / 2
        if any(abs(cx - old) < 18 for old in used_centers):
            continue
        used_centers.append(cx)
        box = (x1, y1, x2, y2)
        union = box
        halo = expand(box, 58, 42)
        for sx1, sy1, sx2, sy2, area in comps:
            small = (sx1, sy1, sx2, sy2)
            if overlaps(halo, small):
                union = (min(union[0], sx1), min(union[1], sy1), max(union[2], sx2), max(union[3], sy2))
        pad = 8
        crop = rgba.crop((max(0, union[0] - pad), max(0, union[1] - pad), min(region.width, union[2] + pad), min(region.height, union[3] + pad)))
        frames.append(trim_alpha(crop, 4))

    # If a sheet has faint disconnected parts and we under-count, fall back to broad equal slots.
    if len(frames) < count:
        frames = []
        cell = region.width / count
        for i in range(count):
            crop = rgba.crop((round(i * cell), 0, round((i + 1) * cell), region.height))
            frames.append(trim_alpha(crop, 4))
    return frames[:count]


def export() -> dict[str, dict[str, int]]:
    if OUT_DIR.exists():
        for p in OUT_DIR.rglob("*.png"):
            p.unlink()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, int]] = {}
    for sprite, (filename, actions) in SPECS.items():
        sheet = Image.open(SOURCE_DIR / filename)
        summary[sprite] = {}
        for action, (rect, count) in actions.items():
            region = sheet.crop(rect)
            frames = select_frames(region, count)
            action_dir = OUT_DIR / sprite / action
            action_dir.mkdir(parents=True, exist_ok=True)
            for i, frame in enumerate(frames, 1):
                frame.save(action_dir / f"{sprite}_{action}_{i:02d}.png")
            summary[sprite][action] = len(frames)
    return summary


def contact() -> Path:
    rows = []
    for sprite_dir in sorted([p for p in OUT_DIR.iterdir() if p.is_dir()]):
        for action_dir in sorted([p for p in sprite_dir.iterdir() if p.is_dir()]):
            imgs = [Image.open(p).convert("RGBA") for p in sorted(action_dir.glob("*.png"))]
            rows.append((sprite_dir.name, action_dir.name, imgs))
    row_h = 145
    canvas = Image.new("RGBA", (1600, 58 + len(rows) * row_h), (246, 242, 225, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), "classified clean frames v3: component selected", fill=(35, 45, 38, 255))
    y = 58
    for sprite, action, imgs in rows:
        draw.text((24, y + 58), f"{sprite}/{action} ({len(imgs)})", fill=(35, 45, 38, 255))
        x = 230
        for img in imgs:
            f = img.copy()
            f.thumbnail((120, 128), Image.Resampling.NEAREST)
            canvas.alpha_composite(f, (x + (126 - f.width) // 2, y + 130 - f.height))
            x += 126
        y += row_h
    path = OUT_DIR / "_contact_sheet.png"
    canvas.save(path)
    return path


def main() -> None:
    summary = export()
    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(contact())


if __name__ == "__main__":
    main()
