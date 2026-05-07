from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\classified-action-strips")


STRIPS = {
    "hero": ("image (3).png", {"idle": (0, 40, 1024, 330), "walk": (0, 355, 1024, 635), "run": (0, 665, 1024, 965)}),
    "dragon": ("image (4).png", {"idle": (0, 35, 1024, 280), "walk": (0, 285, 1024, 535), "run": (0, 535, 1024, 770), "fly": (0, 760, 1024, 1024)}),
    "fire_fox": ("image (5).png", {"idle": (370, 20, 1024, 235), "walk": (370, 235, 1024, 500), "run": (0, 515, 1024, 750), "actions": (0, 760, 1024, 1024)}),
    "turtle": ("image (6).png", {"idle": (0, 45, 1024, 265), "walk": (0, 270, 1024, 535), "run": (0, 535, 1024, 760), "swim": (0, 760, 1024, 1024)}),
    "wind_bird": ("image (7).png", {"idle": (300, 35, 1024, 280), "walk": (0, 360, 1024, 585), "run": (0, 585, 1024, 785), "fly": (0, 760, 1024, 1024)}),
    "woodsprout": ("image (8).png", {"idle": (300, 30, 1024, 305), "walk": (0, 310, 1024, 525), "run": (0, 525, 1024, 730), "actions": (0, 730, 1024, 1024)}),
    "leafbug": ("image (10).png", {"idle": (350, 30, 1024, 220), "walk": (350, 220, 1024, 450), "run": (0, 450, 1024, 650), "actions": (0, 650, 1024, 870), "extras": (0, 870, 1024, 1024)}),
    "pixelbolt": ("image (11).png", {"idle": (0, 70, 1024, 250), "walk": (0, 270, 1024, 500), "run": (0, 510, 1024, 735), "actions": (0, 735, 1024, 1024)}),
    "digglet": ("image (12).png", {"idle": (290, 35, 1024, 210), "walk": (290, 230, 1024, 410), "run": (290, 420, 1024, 630), "burrow": (0, 690, 1024, 870), "extras": (0, 880, 1024, 1024)}),
    "stone_golem": ("image (14).png", {"idle": (0, 50, 1024, 270), "walk": (0, 300, 1024, 520), "run": (0, 535, 1024, 740), "dig": (0, 750, 1024, 1024)}),
    "elementals": ("image (2).png", {"leaf": (0, 0, 1024, 155), "water": (0, 155, 1024, 320), "rock": (0, 320, 1024, 480), "fire": (0, 480, 1024, 640), "cloud": (0, 640, 1024, 800), "crystal": (0, 800, 1024, 1024)}),
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for sprite, (filename, actions) in STRIPS.items():
        sheet = Image.open(SOURCE_DIR / filename).convert("RGBA")
        sprite_dir = OUT_DIR / sprite
        sprite_dir.mkdir(parents=True, exist_ok=True)
        summary[sprite] = {}
        for action, rect in actions.items():
            crop = sheet.crop(rect)
            path = sprite_dir / f"{action}.png"
            crop.save(path)
            summary[sprite][action] = {"path": str(path), "rect": rect, "size": crop.size}
    (OUT_DIR / "_classified_action_strips_manifest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: list(v.keys()) for k, v in summary.items()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
