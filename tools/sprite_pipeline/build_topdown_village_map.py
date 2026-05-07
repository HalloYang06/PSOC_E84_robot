from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps


ROOT = Path.cwd()
ASSET_DIR = ROOT / "art" / "unity-sprite-demo" / "topdown-assets"
OUT_DIR = ROOT / "art" / "unity-sprite-demo" / "topdown-map"
WIDTH, HEIGHT = 1920, 1080


def load_asset(name: str) -> Image.Image:
    return Image.open(ASSET_DIR / f"{name}.png").convert("RGBA")


def paste_scaled(base: Image.Image, name: str, center: tuple[int, int], scale: float = 1.0, shadow: bool = True) -> tuple[int, int, int, int]:
    asset = load_asset(name)
    size = (max(1, int(asset.width * scale)), max(1, int(asset.height * scale)))
    asset = asset.resize(size, Image.Resampling.LANCZOS)
    x = int(center[0] - asset.width / 2)
    y = int(center[1] - asset.height)
    if shadow:
        shadow_w = int(asset.width * 0.62)
        shadow_h = max(12, int(asset.height * 0.13))
        shadow_img = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(shadow_img)
        d.ellipse((0, 0, shadow_w, shadow_h), fill=(19, 40, 22, 82))
        shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(4))
        base.alpha_composite(shadow_img, (center[0] - shadow_w // 2, center[1] - shadow_h // 2))
    base.alpha_composite(asset, (x, y))
    return (x, y, x + asset.width, y + asset.height)


def rounded_poly_mask(points: list[tuple[int, int]], blur: int = 8) -> Image.Image:
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(mask)
    d.line(points, fill=255, width=120, joint="curve")
    for x, y in points:
        d.ellipse((x - 60, y - 60, x + 60, y + 60), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def add_texture(base: Image.Image, seed: int = 7) -> None:
    rnd = random.Random(seed)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for _ in range(1200):
        x = rnd.randrange(30, WIDTH - 30)
        y = rnd.randrange(20, HEIGHT - 20)
        r = rnd.randrange(1, 4)
        color = rnd.choice([(91, 145, 56, 22), (218, 239, 139, 22), (58, 117, 58, 16)])
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)
    for _ in range(140):
        x = rnd.randrange(60, WIDTH - 60)
        y = rnd.randrange(40, HEIGHT - 120)
        w = rnd.randrange(10, 28)
        h = rnd.randrange(3, 8)
        d.ellipse((x, y, x + w, y + h), fill=(62, 132, 61, 26))
    base.alpha_composite(overlay)


def add_path(base: Image.Image, points: list[tuple[int, int]], width: int) -> None:
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    dmask = ImageDraw.Draw(mask)
    dmask.line(points, fill=255, width=width, joint="curve")
    for x, y in points:
        dmask.ellipse((x - width // 2, y - width // 2, x + width // 2, y + width // 2), fill=255)
    edge = mask.filter(ImageFilter.GaussianBlur(9))
    inner = mask.filter(ImageFilter.GaussianBlur(2))

    edge_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    edge_layer.putalpha(edge.point(lambda p: int(p * 0.50)))
    edge_color = Image.new("RGBA", (WIDTH, HEIGHT), (128, 103, 50, 255))
    base.alpha_composite(Image.composite(edge_color, edge_layer, edge_layer.split()[-1]))

    path_layer = Image.new("RGBA", (WIDTH, HEIGHT), (218, 174, 88, 0))
    path_layer.putalpha(inner.point(lambda p: int(p * 0.88)))
    base.alpha_composite(path_layer)

    hi = Image.new("RGBA", (WIDTH, HEIGHT), (247, 213, 124, 0))
    hi_mask = mask.filter(ImageFilter.GaussianBlur(4)).point(lambda p: int(p * 0.18))
    hi.putalpha(hi_mask)
    base.alpha_composite(hi)


def add_river(base: Image.Image) -> None:
    river = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(river)
    points = [(0, 885), (300, 858), (650, 888), (960, 858), (1310, 890), (1920, 850)]
    d.line(points, fill=(58, 169, 202, 255), width=270, joint="curve")
    for x, y in points:
        d.ellipse((x - 135, y - 135, x + 135, y + 135), fill=(58, 169, 202, 255))
    river = river.filter(ImageFilter.GaussianBlur(1))
    base.alpha_composite(river)

    waves = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    dw = ImageDraw.Draw(waves)
    for i in range(16):
        x = 120 + i * 120
        y = 840 + int(math.sin(i * 0.8) * 24)
        dw.arc((x, y, x + 84, y + 30), 195, 345, fill=(181, 236, 242, 105), width=4)
    base.alpha_composite(waves)


def add_farm(base: Image.Image) -> None:
    farm = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(farm)
    d.rounded_rectangle((1225, 260, 1605, 525), radius=38, fill=(157, 113, 54, 230), outline=(221, 180, 92, 170), width=9)
    for y in [310, 365, 420, 475]:
        d.rounded_rectangle((1260, y, 1568, y + 28), radius=14, fill=(130, 88, 45, 180))
        for x in range(1280, 1550, 54):
            d.ellipse((x, y - 10, x + 20, y + 10), fill=(121, 189, 65, 235))
            d.ellipse((x + 12, y - 14, x + 32, y + 10), fill=(93, 156, 55, 235))
    base.alpha_composite(farm)


def add_plaza(base: Image.Image) -> None:
    plaza = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(plaza)
    d.ellipse((790, 465, 1125, 655), fill=(232, 190, 95, 210), outline=(248, 220, 130, 150), width=8)
    d.ellipse((853, 505, 1060, 625), fill=(210, 164, 78, 80))
    base.alpha_composite(plaza)


def add_label(base: Image.Image, text: str, xy: tuple[int, int]) -> None:
    d = ImageDraw.Draw(base)
    x, y = xy
    d.rounded_rectangle((x - 58, y - 17, x + 58, y + 17), radius=12, fill=(255, 241, 174, 220), outline=(126, 113, 62, 60), width=2)
    d.text((x - len(text) * 3.2, y - 7), text, fill=(52, 58, 35))


def add_hotspot(base: Image.Image, center: tuple[int, int]) -> None:
    glow = Image.new("RGBA", (88, 28), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((0, 0, 88, 28), fill=(255, 225, 72, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(3))
    base.alpha_composite(glow, (center[0] - 44, center[1] - 14))


def build(include_labels: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGBA", (WIDTH, HEIGHT), (148, 203, 91, 255))
    add_texture(base)
    add_river(base)

    add_path(base, [(160, 600), (520, 600), (860, 610), (1160, 590), (1740, 600)], 90)
    add_path(base, [(925, 900), (930, 650), (900, 440), (915, 180)], 88)
    add_path(base, [(500, 455), (660, 405), (820, 390)], 72)
    add_path(base, [(1070, 392), (1290, 365), (1540, 385)], 70)
    add_plaza(base)
    add_farm(base)

    hotspots = []
    placements = [
        ("broadleaf_tree", (165, 235), 0.60, False, None),
        ("fir_tree_big", (255, 515), 0.50, False, None),
        ("tree_house", (500, 455), 0.66, True, "HOME"),
        ("cottage", (760, 440), 0.64, True, "CRAFT"),
        ("market_stall", (1090, 405), 0.58, True, "SHOP"),
        ("floating_island", (1455, 430), 0.54, True, "EXPLORE"),
        ("house_yellow", (430, 680), 0.62, True, "LODGE"),
        ("house_blue", (770, 675), 0.62, True, "LAB"),
        ("mushroom_house", (1140, 680), 0.66, True, "PET"),
        ("dojo", (1460, 682), 0.58, True, "TRAIN"),
        ("blue_chest_glow", (1365, 825), 0.50, True, "RARE"),
        ("wood_chest", (1265, 815), 0.45, True, None),
        ("sign_post", (936, 525), 0.42, True, "QUEST"),
        ("lamp_post", (1038, 570), 0.45, False, None),
        ("cherry_tree_big", (1698, 258), 0.44, False, None),
        ("orange_tree_big", (1760, 505), 0.44, False, None),
        ("magic_tree", (1690, 835), 0.48, False, None),
        ("willow_tree", (1810, 880), 0.48, False, None),
        ("palm_tree", (310, 920), 0.42, False, None),
        ("ancient_tree", (900, 935), 0.42, False, None),
    ]

    for name, center, scale, interactive, label in placements:
        if interactive:
            add_hotspot(base, (center[0], center[1] + 8))
        bbox = paste_scaled(base, name, center, scale, shadow=True)
        if include_labels and label:
            add_label(base, label, (center[0], center[1] + 28))
        if interactive:
            hotspots.append({"id": name, "label": label or name, "center": center, "bounds": bbox})

    for name, center, scale in [
        ("blue_crystal", (1318, 365), 0.34),
        ("purple_crystal", (1375, 360), 0.34),
        ("green_crystal", (1510, 348), 0.34),
        ("red_mushroom", (315, 620), 0.33),
        ("blue_flower", (1605, 515), 0.32),
        ("crate", (1212, 805), 0.38),
        ("barrel", (1498, 820), 0.40),
    ]:
        add_hotspot(base, (center[0], center[1] + 2))
        bbox = paste_scaled(base, name, center, scale, shadow=True)
        hotspots.append({"id": name, "label": name, "center": center, "bounds": bbox})

    # Foreground framing for depth.
    paste_scaled(base, "broadleaf_tree", (115, 1000), 0.48, shadow=True)
    paste_scaled(base, "magic_tree", (1580, 1030), 0.52, shadow=True)
    paste_scaled(base, "willow_tree", (1765, 1000), 0.52, shadow=True)

    if include_labels:
        panel = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(panel)
        d.rounded_rectangle((54, 42, 520, 126), radius=24, fill=(255, 243, 188, 232), outline=(146, 134, 80, 65), width=3)
        d.text((82, 62), "Top-down Village Prototype", fill=(42, 49, 31))
        d.text((82, 92), "Farm  Build  Train  Explore  Collect", fill=(70, 86, 45))
        base.alpha_composite(panel)

    out = OUT_DIR / ("village_map_labeled.png" if include_labels else "village_map_explore.png")
    base.convert("RGBA").save(out)
    (OUT_DIR / "village_hotspots.json").write_text(json.dumps(hotspots, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    build()
