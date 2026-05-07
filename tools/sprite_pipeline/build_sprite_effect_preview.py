from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from extract_preview import crop_frames


SOURCE_DIR = Path(r"D:\游戏素材")
OUT_DIR = Path(r"D:\ai合作产品\art\unity-sprite-demo\effect-preview")


SPRITES = {
    "hero": {
        "file": "image (3).png",
        "regions": [("idle", (210, 95, 1005, 310)), ("walk", (205, 405, 1010, 625)), ("run", (300, 705, 1015, 950))],
    },
    "dragon": {
        "file": "image (4).png",
        "regions": [("idle", (40, 65, 950, 260)), ("walk", (20, 320, 1010, 520)), ("run", (20, 560, 1010, 755)), ("fly", (20, 790, 1010, 985))],
    },
    "fire_fox": {
        "file": "image (5).png",
        "regions": [("idle", (390, 50, 990, 225)), ("walk", (390, 265, 990, 455)), ("run", (20, 545, 1005, 735)), ("actions", (25, 790, 990, 965))],
    },
    "turtle": {
        "file": "image (6).png",
        "regions": [("idle", (60, 70, 920, 255)), ("walk", (20, 320, 1005, 520)), ("run", (20, 525, 1005, 745)), ("swim", (20, 800, 1005, 985))],
    },
    "wind_bird": {
        "file": "image (7).png",
        "regions": [("idle", (330, 70, 980, 260)), ("walk", (25, 405, 1005, 565)), ("run", (25, 640, 1005, 775)), ("fly", (25, 820, 1005, 985))],
    },
}


def fit_frame(frame: Image.Image, box: tuple[int, int]) -> Image.Image:
    img = frame.copy()
    img.thumbnail(box, Image.Resampling.NEAREST)
    return img


def make_action_gif(name: str, action: str, frames: list[Image.Image]) -> Path:
    canvas_size = (260, 220)
    rendered = []
    for frame in frames:
        canvas = Image.new("RGBA", canvas_size, (240, 235, 215, 255))
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((68, 168, 192, 190), fill=(92, 71, 52, 60))
        f = fit_frame(frame, (220, 180))
        canvas.alpha_composite(f, ((canvas_size[0] - f.width) // 2, 178 - f.height))
        rendered.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE))
    path = OUT_DIR / f"{name}_{action}.gif"
    rendered[0].save(path, save_all=True, append_images=rendered[1:], duration=115, loop=0, disposal=2)
    return path


def make_showcase(sprite_frames: dict[str, dict[str, list[Image.Image]]]) -> Path:
    width, height = 1280, 720
    bg = Image.new("RGBA", (width, height), (166, 218, 247, 255))
    draw = ImageDraw.Draw(bg)
    draw.rectangle((0, 280, width, height), fill=(138, 205, 115, 255))
    draw.ellipse((80, 390, 1180, 650), fill=(230, 204, 118, 255))
    draw.ellipse((150, 435, 1110, 625), fill=(126, 198, 106, 255))
    draw.rectangle((0, 610, width, height), fill=(94, 193, 204, 255))
    for x in range(0, width, 38):
        draw.line((x, 610, x + 18, height), fill=(132, 219, 219, 120), width=8)
    draw.text((34, 26), "Sprite animation effect preview", fill=(36, 48, 42, 255))

    actors = [
        ("hero", "run", (260, 350), (190, 190)),
        ("dragon", "fly", (500, 285), (180, 160)),
        ("fire_fox", "run", (730, 360), (180, 160)),
        ("turtle", "swim", (525, 560), (170, 135)),
        ("wind_bird", "fly", (925, 275), (155, 130)),
    ]

    frame_count = 36
    pages = []
    for i in range(frame_count):
        canvas = bg.copy()
        for actor, action, pos, max_size in actors:
            frames = sprite_frames[actor][action]
            frame = frames[i % len(frames)]
            f = fit_frame(frame, max_size)
            x, y = pos
            bob = 0
            if action == "fly":
                bob = -10 if i % 12 < 6 else 0
            canvas.alpha_composite(f, (x - f.width // 2, y - f.height + bob))
            ImageDraw.Draw(canvas).text((x - 42, y + 8), f"{actor}:{action}", fill=(34, 52, 38, 255))
        pages.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE))

    path = OUT_DIR / "sprite_showcase_loop.gif"
    pages[0].save(path, save_all=True, append_images=pages[1:], duration=100, loop=0, disposal=2)
    return path


def make_contact(sprite_frames: dict[str, dict[str, list[Image.Image]]]) -> Path:
    width = 1500
    row_h = 160
    height = 70 + sum(len(actions) for actions in sprite_frames.values()) * row_h
    canvas = Image.new("RGBA", (width, height), (246, 242, 225, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 20), "extracted action frames for Unity import", fill=(36, 48, 42, 255))
    y = 70
    for sprite, actions in sprite_frames.items():
        for action, frames in actions.items():
            draw.text((24, y + 58), f"{sprite} / {action} ({len(frames)} frames)", fill=(36, 48, 42, 255))
            x = 240
            for frame in frames:
                f = fit_frame(frame, (112, 130))
                canvas.alpha_composite(f, (x + (118 - f.width) // 2, y + 132 - f.height))
                x += 120
            y += row_h
    path = OUT_DIR / "sprite_contact_sheet.png"
    canvas.save(path)
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_frames: dict[str, dict[str, list[Image.Image]]] = {}
    for sprite, spec in SPRITES.items():
        sheet = Image.open(SOURCE_DIR / spec["file"])
        frames = crop_frames(sheet, spec["regions"])
        frames = {action: imgs for action, imgs in frames.items() if imgs}
        all_frames[sprite] = frames
        for action, imgs in frames.items():
            make_action_gif(sprite, action, imgs)
    make_contact(all_frames)
    make_showcase(all_frames)


if __name__ == "__main__":
    main()
