from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from extract_preview import make_alpha, trim_alpha


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\classified-frames")


def slots(x0: int, y0: int, w: int, h: int, count: int, step: int) -> list[tuple[int, int, int, int]]:
    return [(x0 + i * step, y0, x0 + i * step + w, y0 + h) for i in range(count)]


MANIFEST = {
    "hero": {
        "source": "image (3).png",
        "actions": {
            "idle": slots(360, 95, 115, 210, 4, 145),
            "walk": slots(340, 390, 120, 230, 6, 115),
            "run": slots(345, 695, 125, 255, 6, 110),
        },
    },
    "dragon": {
        "source": "image (4).png",
        "actions": {
            "idle": slots(50, 55, 180, 205, 4, 245),
            "walk": slots(15, 315, 150, 200, 6, 167),
            "run": slots(15, 555, 155, 205, 6, 166),
            "fly": slots(15, 780, 155, 220, 6, 166),
        },
    },
    "fire_fox": {
        "source": "image (5).png",
        "actions": {
            "idle": slots(380, 55, 145, 175, 4, 150),
            "walk": slots(380, 255, 125, 210, 6, 102),
            "run": slots(15, 530, 150, 220, 6, 155),
            "dash": [(15, 785, 160, 980)],
            "jump": [(170, 785, 315, 980)],
            "land": [(315, 785, 480, 980)],
            "attack": [(495, 760, 720, 980)],
            "hurt": [(720, 785, 860, 980)],
            "faint": [(860, 785, 1015, 980)],
        },
    },
    "turtle": {
        "source": "image (6).png",
        "actions": {
            "idle": slots(55, 65, 170, 205, 4, 245),
            "walk": slots(15, 300, 155, 220, 6, 164),
            "run": slots(15, 520, 170, 230, 5, 188),
            "swim": [(15, 780, 230, 1005), (250, 780, 465, 1005), (485, 780, 700, 1005), (725, 780, 1005, 1005)],
        },
    },
    "wind_bird": {
        "source": "image (7).png",
        "actions": {
            "idle": slots(330, 60, 130, 215, 5, 135),
            "walk": slots(20, 385, 145, 190, 6, 165),
            "run": slots(20, 625, 145, 160, 6, 165),
            "fly": slots(20, 795, 145, 220, 6, 165),
        },
    },
    "woodsprout": {
        "source": "image (8).png",
        "actions": {
            "idle": slots(375, 85, 165, 200, 3, 215),
            "walk": slots(50, 355, 135, 165, 6, 150),
            "run": slots(50, 555, 145, 160, 5, 180),
            "cast": [(55, 790, 175, 965)],
            "leaf_shot": [(245, 790, 420, 965)],
            "spin": [(520, 790, 670, 965)],
            "happy": [(720, 790, 850, 965)],
            "rest": [(895, 790, 1010, 965)],
        },
    },
    "leafbug": {
        "source": "image (10).png",
        "actions": {
            "idle": slots(375, 70, 135, 160, 4, 190),
            "walk": slots(375, 275, 125, 145, 5, 150),
            "run": slots(15, 505, 150, 135, 6, 165),
            "hop": [(55, 695, 175, 825)],
            "attack": [(300, 695, 455, 825)],
            "hurt": [(535, 695, 650, 825)],
            "happy": [(735, 695, 845, 825)],
            "sleep": [(900, 695, 1010, 825)],
        },
    },
    "pixelbolt": {
        "source": "image (11).png",
        "actions": {
            "idle": slots(155, 90, 130, 160, 4, 155),
            "walk": slots(145, 315, 125, 150, 6, 145),
            "run": slots(145, 540, 135, 150, 6, 145),
            "jump": [(45, 780, 180, 950)],
            "land": [(200, 780, 345, 950)],
            "dash": [(375, 780, 535, 950)],
            "attack": [(560, 780, 720, 950)],
            "hurt": [(740, 780, 870, 950)],
            "defeated": [(875, 780, 1015, 950)],
        },
    },
    "digglet": {
        "source": "image (12).png",
        "actions": {
            "idle": slots(310, 70, 120, 135, 6, 115),
            "walk": slots(310, 280, 120, 135, 6, 115),
            "run": slots(310, 475, 120, 130, 8, 112),
            "burrow": slots(40, 735, 120, 130, 7, 135),
        },
    },
    "stone_golem": {
        "source": "image (14).png",
        "actions": {
            "idle": slots(90, 75, 130, 165, 4, 210),
            "walk": slots(75, 335, 130, 165, 6, 160),
            "run": slots(75, 570, 140, 160, 5, 175),
            "dig": [(75, 805, 190, 980), (215, 805, 340, 980), (360, 805, 495, 980), (520, 805, 660, 980), (745, 805, 860, 980), (885, 805, 1010, 980)],
        },
    },
    "elementals": {
        "source": "image (2).png",
        "actions": {
            "leaf": slots(55, 45, 120, 125, 6, 165),
            "water": slots(55, 200, 120, 125, 6, 165),
            "rock": slots(55, 360, 120, 125, 6, 165),
            "fire": slots(55, 520, 120, 125, 6, 165),
            "cloud": slots(55, 680, 120, 125, 6, 165),
            "crystal": slots(55, 840, 120, 125, 6, 165),
        },
    },
}


def crop_clean(sheet: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    l, t, r, b = rect
    l, t = max(0, l), max(0, t)
    r, b = min(sheet.width, r), min(sheet.height, b)
    if r <= l or b <= t:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    crop = sheet.crop((l, t, r, b))
    return trim_alpha(make_alpha(crop), 4)


def export_frames() -> dict[str, dict[str, list[Path]]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exported: dict[str, dict[str, list[Path]]] = {}
    for sprite, spec in MANIFEST.items():
        sheet = Image.open(SOURCE_DIR / spec["source"])
        exported[sprite] = {}
        for action, rects in spec["actions"].items():
            action_dir = OUT_DIR / sprite / action
            action_dir.mkdir(parents=True, exist_ok=True)
            exported[sprite][action] = []
            for index, rect in enumerate(rects, start=1):
                frame = crop_clean(sheet, rect)
                path = action_dir / f"{sprite}_{action}_{index:02d}.png"
                frame.save(path)
                exported[sprite][action].append(path)
    return exported


def make_contact(exported: dict[str, dict[str, list[Path]]]) -> Path:
    rows = []
    for sprite, actions in exported.items():
        for action, paths in actions.items():
            imgs = [Image.open(path).convert("RGBA") for path in paths]
            rows.append((sprite, action, imgs))
    row_h = 150
    width = 1600
    height = 56 + row_h * len(rows)
    canvas = Image.new("RGBA", (width, height), (246, 242, 225, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), "manual classified transparent frames", fill=(38, 48, 42, 255))
    y = 56
    for sprite, action, imgs in rows:
        draw.text((24, y + 58), f"{sprite} / {action} ({len(imgs)})", fill=(38, 48, 42, 255))
        x = 245
        for img in imgs:
            f = img.copy()
            f.thumbnail((118, 130), Image.Resampling.NEAREST)
            canvas.alpha_composite(f, (x + (125 - f.width) // 2, y + 132 - f.height))
            x += 125
        y += row_h
    path = OUT_DIR / "_manual_classified_contact_sheet.png"
    canvas.save(path)
    return path


def main() -> None:
    exported = export_frames()
    contact = make_contact(exported)
    summary = {
        sprite: {action: len(paths) for action, paths in actions.items()}
        for sprite, actions in exported.items()
    }
    (OUT_DIR / "_manifest_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(contact)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
