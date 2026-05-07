from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from extract_preview import make_alpha, trim_alpha


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\classified-frames-v2")


def split(region: tuple[int, int, int, int], count: int) -> list[tuple[int, int, int, int]]:
    l, t, r, b = region
    cell = (r - l) / count
    return [(round(l + i * cell), t, round(l + (i + 1) * cell), b) for i in range(count)]


def rects(*items: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    return list(items)


MANIFEST = {
    "hero": {
        "source": "image (3).png",
        "actions": {
            "idle": split((355, 85, 960, 315), 4),
            "walk": split((335, 385, 1010, 630), 6),
            "run": split((320, 690, 1015, 960), 6),
        },
    },
    "dragon": {
        "source": "image (4).png",
        "actions": {
            "idle": split((35, 55, 965, 265), 4),
            "walk": split((15, 315, 1015, 525), 6),
            "run": split((15, 555, 1015, 765), 6),
            "fly": split((15, 780, 1015, 1000), 6),
        },
    },
    "fire_fox": {
        "source": "image (5).png",
        "actions": {
            "idle": split((380, 45, 1005, 230), 4),
            "walk": split((380, 255, 1005, 465), 6),
            "run": split((15, 525, 1015, 750), 6),
            "dash": rects((20, 780, 180, 970)),
            "jump": rects((180, 780, 335, 970)),
            "land": rects((340, 780, 490, 970)),
            "attack": rects((495, 755, 730, 970)),
            "hurt": rects((735, 780, 870, 970)),
            "faint": rects((870, 780, 1015, 970)),
        },
    },
    "turtle": {
        "source": "image (6).png",
        "actions": {
            "idle": split((45, 60, 965, 265), 4),
            "walk": split((15, 295, 1015, 525), 6),
            "run": split((15, 525, 1015, 750), 5),
            "swim": split((15, 780, 1015, 1005), 4),
        },
    },
    "wind_bird": {
        "source": "image (7).png",
        "actions": {
            "idle": split((320, 55, 1010, 270), 5),
            "walk": split((15, 380, 1015, 575), 6),
            "run": split((15, 620, 1015, 780), 6),
            "fly": split((15, 790, 1015, 1010), 6),
        },
    },
    "woodsprout": {
        "source": "image (8).png",
        "actions": {
            "idle": split((345, 65, 1010, 285), 3),
            "walk": split((45, 340, 1000, 535), 6),
            "run": split((45, 535, 1000, 730), 5),
            "cast": rects((45, 775, 190, 970)),
            "leaf_shot": rects((245, 775, 440, 970)),
            "spin": rects((505, 775, 700, 970)),
            "happy": rects((710, 775, 855, 970)),
            "rest": rects((880, 775, 1015, 970)),
        },
    },
    "leafbug": {
        "source": "image (10).png",
        "actions": {
            "idle": split((355, 60, 1015, 210), 4),
            "walk": split((355, 265, 1015, 430), 5),
            "run": split((10, 490, 1015, 640), 6),
            "hop": rects((45, 690, 180, 830)),
            "attack": rects((280, 690, 465, 830)),
            "hurt": rects((520, 690, 665, 830)),
            "happy": rects((720, 690, 860, 830)),
            "sleep": rects((885, 690, 1015, 830)),
        },
    },
    "pixelbolt": {
        "source": "image (11).png",
        "actions": {
            "idle": split((145, 80, 740, 260), 4),
            "walk": split((135, 300, 1010, 500), 6),
            "run": split((135, 525, 1010, 730), 6),
            "jump": rects((35, 770, 190, 955)),
            "land": rects((190, 770, 355, 955)),
            "dash": rects((365, 760, 545, 955)),
            "attack": rects((555, 770, 725, 955)),
            "hurt": rects((735, 770, 875, 955)),
            "defeated": rects((875, 770, 1015, 955)),
        },
    },
    "digglet": {
        "source": "image (12).png",
        "actions": {
            "idle": split((300, 55, 1010, 210), 6),
            "walk": split((300, 250, 1010, 410), 6),
            "run": split((300, 430, 1010, 640), 8),
            "burrow": split((35, 700, 1010, 870), 7),
        },
    },
    "stone_golem": {
        "source": "image (14).png",
        "actions": {
            "idle": split((60, 55, 945, 275), 4),
            "walk": split((60, 315, 1010, 530), 6),
            "run": split((60, 555, 1010, 745), 5),
            "dig": rects((45, 780, 180, 980), (190, 780, 335, 980), (345, 780, 500, 980), (505, 780, 670, 980), (730, 780, 865, 980), (865, 780, 1015, 980)),
        },
    },
    "elementals": {
        "source": "image (2).png",
        "actions": {
            "leaf": split((20, 15, 1010, 150), 6),
            "water": split((20, 170, 1010, 315), 6),
            "rock": split((20, 335, 1010, 475), 6),
            "fire": split((20, 495, 1010, 635), 6),
            "cloud": split((20, 655, 1010, 795), 6),
            "crystal": split((20, 815, 1010, 1010), 6),
        },
    },
}


def crop_clean(sheet: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    l, t, r, b = box
    crop = sheet.crop((max(0, l), max(0, t), min(sheet.width, r), min(sheet.height, b)))
    return trim_alpha(make_alpha(crop), 6)


def export() -> dict[str, dict[str, list[str]]]:
    if OUT_DIR.exists():
        for path in OUT_DIR.rglob("*.png"):
            path.unlink()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, list[str]]] = {}
    for sprite, spec in MANIFEST.items():
        sheet = Image.open(SOURCE_DIR / spec["source"])
        result[sprite] = {}
        for action, boxes in spec["actions"].items():
            action_dir = OUT_DIR / sprite / action
            action_dir.mkdir(parents=True, exist_ok=True)
            result[sprite][action] = []
            for i, box in enumerate(boxes, 1):
                frame = crop_clean(sheet, box)
                path = action_dir / f"{sprite}_{action}_{i:02d}.png"
                frame.save(path)
                result[sprite][action].append(str(path))
    return result


def contact_sheet(result: dict[str, dict[str, list[str]]]) -> Path:
    rows = [(sprite, action, [Image.open(p).convert("RGBA") for p in paths]) for sprite, actions in result.items() for action, paths in actions.items()]
    row_h = 148
    width = 1600
    height = 58 + len(rows) * row_h
    canvas = Image.new("RGBA", (width, height), (246, 242, 225, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), "classified clean frames v2", fill=(35, 45, 38, 255))
    y = 58
    for sprite, action, imgs in rows:
        draw.text((24, y + 58), f"{sprite}/{action} ({len(imgs)})", fill=(35, 45, 38, 255))
        x = 230
        for img in imgs:
            f = img.copy()
            f.thumbnail((120, 130), Image.Resampling.NEAREST)
            canvas.alpha_composite(f, (x + (126 - f.width) // 2, y + 132 - f.height))
            x += 126
        y += row_h
    path = OUT_DIR / "_contact_sheet.png"
    canvas.save(path)
    return path


def main() -> None:
    result = export()
    summary = {sprite: {action: len(paths) for action, paths in actions.items()} for sprite, actions in result.items()}
    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(contact_sheet(result))


if __name__ == "__main__":
    main()
