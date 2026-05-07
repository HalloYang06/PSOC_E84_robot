from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\full-action-strips")


STRIPS = {
    "hero": ("image (3).png", [("idle", (0, 40, 1024, 330)), ("walk", (0, 355, 1024, 635)), ("run", (0, 665, 1024, 965))]),
    "dragon": ("image (4).png", [("idle", (0, 35, 1024, 280)), ("walk", (0, 285, 1024, 535)), ("run", (0, 535, 1024, 770)), ("fly", (0, 760, 1024, 1024))]),
    "fire_fox": ("image (5).png", [("idle", (370, 20, 1024, 235)), ("walk", (370, 235, 1024, 500)), ("run", (0, 515, 1024, 750)), ("actions", (0, 760, 1024, 1024))]),
    "turtle": ("image (6).png", [("idle", (0, 45, 1024, 265)), ("walk", (0, 270, 1024, 535)), ("run", (0, 535, 1024, 760)), ("swim", (0, 760, 1024, 1024))]),
    "wind_bird": ("image (7).png", [("idle", (300, 35, 1024, 280)), ("walk", (0, 360, 1024, 585)), ("run", (0, 585, 1024, 785)), ("fly", (0, 760, 1024, 1024))]),
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    contact_rows = []
    for sprite, (filename, strips) in STRIPS.items():
        sheet = Image.open(SOURCE_DIR / filename).convert("RGB")
        for action, rect in strips:
            crop = sheet.crop(rect)
            path = OUT_DIR / f"{sprite}_{action}_full_strip.png"
            crop.save(path)
            contact_rows.append((sprite, action, crop))

    width = 1300
    y = 24
    rows = []
    for sprite, action, crop in contact_rows:
        c = crop.copy()
        c.thumbnail((1080, 210), Image.Resampling.LANCZOS)
        rows.append((sprite, action, c))
        y += max(230, c.height + 36)
    canvas = Image.new("RGB", (width, y), (246, 242, 225))
    draw = ImageDraw.Draw(canvas)
    y = 24
    for sprite, action, crop in rows:
        draw.text((24, y + 8), f"{sprite} / {action}", fill=(35, 48, 42))
        canvas.paste(crop, (190, y))
        y += max(230, crop.height + 36)
    canvas.save(OUT_DIR / "all_full_action_strips.png")


if __name__ == "__main__":
    main()
