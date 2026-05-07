from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from extract_preview import make_alpha, trim_alpha


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\core-clean-frames")


MANIFEST = {
    "hero": {
        "source": "image (3).png",
        "actions": {
            "idle": [
                (330, 95, 470, 310),
                (475, 95, 615, 310),
                (620, 95, 760, 310),
                (765, 95, 905, 310),
            ],
            "walk": [
                (330, 385, 460, 625),
                (455, 385, 585, 625),
                (580, 385, 710, 625),
                (705, 385, 835, 625),
                (830, 385, 960, 625),
                (940, 385, 1020, 625),
            ],
            "run": [
                (315, 700, 455, 955),
                (440, 700, 580, 955),
                (565, 700, 705, 955),
                (690, 700, 830, 955),
                (815, 700, 955, 955),
                (930, 700, 1024, 955),
            ],
        },
    },
    "dragon": {
        "source": "image (4).png",
        "actions": {
            "idle": [
                (25, 65, 230, 260),
                (265, 65, 470, 260),
                (510, 65, 715, 260),
                (750, 65, 970, 260),
            ],
            "walk": [
                (10, 315, 175, 520),
                (175, 315, 340, 520),
                (340, 315, 505, 520),
                (505, 315, 670, 520),
                (670, 315, 835, 520),
                (835, 315, 1015, 520),
            ],
            "run": [
                (10, 560, 175, 760),
                (175, 560, 340, 760),
                (340, 560, 505, 760),
                (505, 560, 670, 760),
                (670, 560, 835, 760),
                (835, 560, 1015, 760),
            ],
            "fly": [
                (10, 790, 175, 1000),
                (175, 790, 340, 1000),
                (340, 790, 505, 1000),
                (505, 790, 670, 1000),
                (670, 790, 835, 1000),
                (835, 790, 1015, 1000),
            ],
        },
    },
    "fire_fox": {
        "source": "image (5).png",
        "actions": {
            "idle": [
                (380, 50, 530, 225),
                (530, 50, 680, 225),
                (680, 50, 830, 225),
                (830, 50, 1000, 225),
            ],
            "walk": [
                (385, 255, 500, 455),
                (500, 255, 615, 455),
                (615, 255, 730, 455),
                (730, 255, 845, 455),
                (845, 255, 965, 455),
                (940, 255, 1024, 455),
            ],
            "run": [
                (10, 535, 165, 740),
                (165, 535, 320, 740),
                (320, 535, 475, 740),
                (475, 535, 630, 740),
                (630, 535, 785, 740),
                (785, 535, 1015, 740),
            ],
            "attack": [
                (490, 765, 720, 975),
            ],
        },
    },
}


def crop_frame(sheet: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    l, t, r, b = rect
    crop = sheet.crop((max(0, l), max(0, t), min(sheet.width, r), min(sheet.height, b)))
    return trim_alpha(make_alpha(crop), 6)


def export_frames() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, list[Image.Image]]] = []
    for actor, spec in MANIFEST.items():
        sheet = Image.open(SOURCE_DIR / spec["source"])
        for action, rects in spec["actions"].items():
            action_dir = OUT_DIR / actor / action
            action_dir.mkdir(parents=True, exist_ok=True)
            frames = []
            for index, rect in enumerate(rects, start=1):
                frame = crop_frame(sheet, rect)
                frame.save(action_dir / f"{actor}_{action}_{index:02d}.png")
                frames.append(frame)
            rows.append((actor, action, frames))

    make_contact(rows)


def make_contact(rows: list[tuple[str, str, list[Image.Image]]]) -> None:
    row_h = 150
    width = 1200
    height = 54 + row_h * len(rows)
    canvas = Image.new("RGBA", (width, height), (246, 242, 225, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((22, 16), "core clean frames for Unity animation", fill=(35, 45, 38, 255))
    y = 54
    for actor, action, frames in rows:
        draw.text((22, y + 60), f"{actor}/{action} ({len(frames)})", fill=(35, 45, 38, 255))
        x = 200
        for frame in frames:
            f = frame.copy()
            f.thumbnail((125, 132), Image.Resampling.NEAREST)
            canvas.alpha_composite(f, (x + (132 - f.width) // 2, y + 136 - f.height))
            x += 138
        y += row_h
    canvas.save(OUT_DIR / "_contact_sheet.png")


if __name__ == "__main__":
    export_frames()
