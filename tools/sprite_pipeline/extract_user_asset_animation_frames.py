from __future__ import annotations

import json
import re
import shutil
from collections import deque
from pathlib import Path

from PIL import Image


SOURCE_DIR = Path("D:/\u6e38\u620f\u7d20\u6750")
PROJECT_DIR = Path.cwd() / "unity-topdown-life-sim"
OUT_DIR = PROJECT_DIR / "Assets" / "Game" / "Art" / "AutoFrames"
ACTION_OUT_DIR = PROJECT_DIR / "Assets" / "Game" / "Art" / "AutoActionFrames"
MANIFEST_PATH = OUT_DIR / "auto_frame_manifest.json"
ACTION_MANIFEST_PATH = ACTION_OUT_DIR / "auto_action_manifest.json"

ACTION_NAME_ORDER = [
    "idle",
    "walk",
    "run",
    "attack",
    "hurt",
    "death",
    "fly",
    "skill_guess",
]

ACTION_OVERRIDES = {
    "image_17": ["idle", "walk", "run", "fly"],
    "image_21": ["idle", "walk", "run", "stealth"],
}

STATIC_SHEET_KEYS = {"image", "image_34", "image_35", "image_36"}


def safe_stem(path: Path) -> str:
    stem = path.stem.lower().replace(" ", "_")
    stem = stem.replace("(", "").replace(")", "")
    return re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")


def make_mask(image: Image.Image) -> list[bytearray]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    corners = [pixels[0, 0], pixels[width - 1, 0], pixels[0, height - 1], pixels[width - 1, height - 1]]
    bg = tuple(sorted(c[i] for c in corners)[len(corners) // 2] for i in range(3))
    alpha_extrema = rgba.getchannel("A").getextrema()
    mask = [bytearray(width) for _ in range(height)]
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if alpha_extrema[0] < 250:
                is_fg = a > 24
            else:
                if max(r, g, b) - min(r, g, b) < 18 and min(r, g, b) > 176:
                    is_fg = False
                    if is_fg:
                        mask[y][x] = 1
                    continue
                diff = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
                is_fg = diff > 55
            if is_fg:
                mask[y][x] = 1
    return mask


def components(mask: list[bytearray], min_area: int = 120) -> list[tuple[int, int, int, int, int]]:
    height = len(mask)
    width = len(mask[0])
    seen = [bytearray(width) for _ in range(height)]
    boxes: list[tuple[int, int, int, int, int]] = []
    for y0 in range(height):
        for x0 in range(width):
            if not mask[y0][x0] or seen[y0][x0]:
                continue
            q: deque[tuple[int, int]] = deque([(x0, y0)])
            seen[y0][x0] = 1
            min_x = max_x = x0
            min_y = max_y = y0
            area = 0
            while q:
                x, y = q.popleft()
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                for nx in (x - 1, x, x + 1):
                    for ny in (y - 1, y, y + 1):
                        if nx < 0 or ny < 0 or nx >= width or ny >= height:
                            continue
                        if seen[ny][nx] or not mask[ny][nx]:
                            continue
                        seen[ny][nx] = 1
                        q.append((nx, ny))
            if area >= min_area:
                boxes.append((min_x, min_y, max_x + 1, max_y + 1, area))
    return boxes


def merge_nearby_boxes(boxes: list[tuple[int, int, int, int, int]]) -> list[tuple[int, int, int, int, int]]:
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    merged: list[tuple[int, int, int, int, int]] = []
    for box in boxes:
        x1, y1, x2, y2, area = box
        if (x2 - x1) < 12 or (y2 - y1) < 12:
            continue
        placed = False
        for i, old in enumerate(merged):
            ox1, oy1, ox2, oy2, oarea = old
            close_x = x1 <= ox2 + 8 and x2 >= ox1 - 8
            close_y = y1 <= oy2 + 8 and y2 >= oy1 - 8
            same_frame_band = abs(((y1 + y2) / 2) - ((oy1 + oy2) / 2)) < max(y2 - y1, oy2 - oy1) * 0.45
            if close_x and close_y and same_frame_band:
                merged[i] = (min(x1, ox1), min(y1, oy1), max(x2, ox2), max(y2, oy2), area + oarea)
                placed = True
                break
        if not placed:
            merged.append(box)
    return merged


def expand_box(box: tuple[int, int, int, int, int], width: int, height: int, pad: int = 8) -> tuple[int, int, int, int]:
    x1, y1, x2, y2, _ = box
    return max(0, x1 - pad), max(0, y1 - pad), min(width, x2 + pad), min(height, y2 + pad)


def action_name(row_index: int, key: str) -> str:
    override = ACTION_OVERRIDES.get(key)
    if override and row_index < len(override):
        return override[row_index]
    if row_index < len(ACTION_NAME_ORDER):
        return ACTION_NAME_ORDER[row_index]
    return f"action_{row_index + 1:02d}_guess"


def group_rows(boxes: list[tuple[int, int, int, int]]) -> list[list[tuple[int, int, int, int]]]:
    rows: list[list[tuple[int, int, int, int]]] = []
    centers: list[float] = []
    for box in sorted(boxes, key=lambda b: ((b[1] + b[3]) / 2, b[0])):
        y_center = (box[1] + box[3]) / 2
        height = box[3] - box[1]
        matched = -1
        for index, center in enumerate(centers):
            row_height = max(r[3] - r[1] for r in rows[index])
            if abs(y_center - center) <= max(32, min(96, max(height, row_height) * 0.58)):
                matched = index
                break

        if matched < 0:
            rows.append([box])
            centers.append(y_center)
            continue

        rows[matched].append(box)
        centers[matched] = sum((r[1] + r[3]) / 2 for r in rows[matched]) / len(rows[matched])

    for row in rows:
        row.sort(key=lambda b: b[0])
    rows.sort(key=lambda row: min(b[1] for b in row))
    return rows


def remove_row_outliers(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    cleaned: list[tuple[int, int, int, int]] = []
    for row in group_rows(boxes):
        if len(row) <= 2:
            cleaned.extend(row)
            continue

        widths = sorted(b[2] - b[0] for b in row)
        heights = sorted(b[3] - b[1] for b in row)
        median_width = widths[(len(widths) - 1) // 2]
        median_height = heights[(len(heights) - 1) // 2]
        for box in row:
            width = box[2] - box[0]
            height = box[3] - box[1]
            strict_large_showcase = len(row) >= 4 and (width > median_width * 1.35 or height > median_height * 1.35)
            too_large = width > median_width * 2.0 or height > median_height * 2.0 or strict_large_showcase
            too_wide_label = height < 84 and width > median_width * 1.7
            if too_large or too_wide_label:
                continue
            cleaned.append(box)
    return cleaned


def extract_sheet(path: Path) -> dict:
    image = Image.open(path).convert("RGBA")
    mask = make_mask(image)
    raw_boxes = components(mask)
    boxes = merge_nearby_boxes(raw_boxes)
    width, height = image.size
    frames = []
    actions = []
    out_subdir = OUT_DIR / safe_stem(path)
    action_subdir = ACTION_OUT_DIR / safe_stem(path)
    out_subdir.mkdir(parents=True, exist_ok=True)
    if action_subdir.exists():
        shutil.rmtree(action_subdir)
    action_subdir.mkdir(parents=True, exist_ok=True)
    for old in out_subdir.glob("*.png"):
        old.unlink()
    for old in action_subdir.glob("*"):
        if old.is_file():
            old.unlink()
        elif old.is_dir():
            for child in old.glob("*.png"):
                child.unlink()
            old.rmdir()

    useful_boxes = []
    for box in boxes:
        x1, y1, x2, y2 = expand_box(box, width, height)
        bw, bh = x2 - x1, y2 - y1
        area = bw * bh
        aspect = bw / max(1, bh)
        if bw < 24 or bh < 48:
            continue
        if bw > width * 0.72 or bh > height * 0.72:
            continue
        if area < 4800:
            continue
        if bh < 80 and aspect > 1.45:
            continue
        if aspect > 3.0 or aspect < 0.25:
            continue
        useful_boxes.append((x1, y1, x2, y2))

    useful_boxes = remove_row_outliers(useful_boxes)
    useful_boxes.sort(key=lambda b: (round(b[1] / 24) * 24, b[0]))
    for index, box in enumerate(useful_boxes[:96]):
        frame = image.crop(box)
        frame_path = out_subdir / f"frame_{index:03d}.png"
        frame.save(frame_path)
        frames.append({"path": str(frame_path.relative_to(PROJECT_DIR)).replace("\\", "/"), "box": box})

    key = safe_stem(path)
    rows = group_rows(useful_boxes)
    if key in STATIC_SHEET_KEYS or (len(useful_boxes) >= 72 and len(rows) >= 7):
        rows = [useful_boxes]

    for row_index, row in enumerate(rows):
        if not row:
            continue
        is_static_props = key in STATIC_SHEET_KEYS or (len(rows) == 1 and len(useful_boxes) >= 72)
        name = "static_props" if is_static_props else action_name(row_index, key)
        action_dir = action_subdir / name
        action_dir.mkdir(parents=True, exist_ok=True)
        action_frames = []
        max_action_frames = 128 if is_static_props else 24
        for frame_index, box in enumerate(row[:max_action_frames]):
            frame = image.crop(box)
            frame_path = action_dir / f"frame_{frame_index:03d}.png"
            frame.save(frame_path)
            action_frames.append({"path": str(frame_path.relative_to(PROJECT_DIR)).replace("\\", "/"), "box": box})
        actions.append({"name": name, "frame_count": len(action_frames), "frames": action_frames})

    return {
        "source": path.name,
        "key": key,
        "frame_count": len(frames),
        "frames": frames,
        "actions": actions,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ACTION_OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for path in sorted(SOURCE_DIR.glob("*.png"), key=lambda p: p.name):
        manifest.append(extract_sheet(path))
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    ACTION_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Wrote {ACTION_MANIFEST_PATH}")
    for item in manifest:
        action_summary = ", ".join(f"{action['name']}={action['frame_count']}" for action in item["actions"])
        print(f"{item['source']}: {item['frame_count']} frames | {action_summary}")


if __name__ == "__main__":
    main()
