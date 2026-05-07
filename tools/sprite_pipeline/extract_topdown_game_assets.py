from pathlib import Path

from PIL import Image, ImageDraw


SRC = Path("D:/\u6e38\u620f\u7d20\u6750")
OUT = Path.cwd() / "art" / "unity-sprite-demo" / "topdown-assets"


ASSETS = {
    "image.png": [
        ("tree_house", (0, 0, 345, 390)),
        ("cottage", (350, 90, 560, 350)),
        ("floating_island", (560, 100, 800, 360)),
        ("ancient_tree", (805, 120, 1015, 365)),
        ("grass_plateau_wide", (10, 405, 245, 520)),
        ("grass_plateau_square", (260, 410, 380, 510)),
        ("sand_patch", (405, 410, 545, 500)),
        ("stone_patch", (570, 420, 725, 505)),
        ("rocks_large", (740, 405, 855, 500)),
        ("market_stall", (795, 540, 1015, 665)),
        ("sign_post", (20, 555, 130, 650)),
        ("fence", (170, 555, 285, 650)),
        ("lamp_post", (310, 540, 410, 650)),
        ("wood_chest", (455, 545, 555, 635)),
        ("barrel", (590, 545, 665, 635)),
        ("crate", (695, 545, 790, 635)),
        ("pine_tree", (20, 670, 100, 815)),
        ("round_tree", (230, 690, 325, 795)),
        ("pink_tree", (455, 670, 550, 790)),
        ("stump", (620, 700, 700, 790)),
        ("red_mushroom", (760, 710, 830, 790)),
        ("blue_crystal", (315, 830, 385, 910)),
        ("purple_crystal", (410, 830, 485, 910)),
        ("green_crystal", (505, 830, 575, 910)),
        ("blue_flower", (790, 855, 845, 925)),
        ("apple_icon", (870, 955, 905, 995)),
        ("coin_icon", (930, 955, 970, 995)),
        ("gem_icon", (980, 955, 1020, 995)),
    ],
    "image (30).png": [
        ("house_yellow", (15, 80, 240, 310)),
        ("house_blue", (270, 80, 500, 310)),
        ("house_red", (520, 80, 750, 310)),
        ("house_purple", (760, 80, 1010, 330)),
        ("log_cabin", (20, 360, 245, 600)),
        ("villa", (270, 360, 510, 600)),
        ("snow_cabin", (535, 340, 755, 600)),
        ("dojo", (775, 340, 1015, 600)),
        ("mushroom_house", (20, 650, 250, 915)),
        ("desert_house", (280, 660, 500, 915)),
        ("haunted_house", (535, 645, 755, 915)),
        ("manor", (770, 640, 1015, 915)),
    ],
    "image (31).png": [
        ("broadleaf_tree", (25, 50, 280, 335)),
        ("fir_tree_big", (385, 30, 610, 335)),
        ("birch_tree", (735, 35, 960, 335)),
        ("cherry_tree_big", (35, 385, 290, 630)),
        ("orange_tree_big", (400, 385, 625, 630)),
        ("willow_tree", (730, 375, 1000, 635)),
        ("palm_tree", (50, 690, 250, 990)),
        ("baobab_tree", (420, 690, 610, 990)),
        ("magic_tree", (720, 690, 1005, 990)),
    ],
    "image (33).png": [
        ("chest_closed", (45, 45, 240, 220)),
        ("chest_half", (295, 45, 490, 220)),
        ("chest_open", (550, 45, 745, 220)),
        ("chest_glow", (790, 45, 1005, 240)),
        ("blue_chest_closed", (45, 315, 245, 490)),
        ("blue_chest_glow", (790, 315, 1005, 500)),
        ("gold_chest_glow", (790, 555, 1005, 755)),
    ],
    "image (34).png": [
        ("hero_knight_icon", (0, 790, 70, 850)),
        ("hero_ranger_icon", (75, 790, 145, 850)),
        ("hero_mage_icon", (150, 790, 220, 850)),
        ("hero_worker_icon", (450, 790, 520, 850)),
        ("campfire_icon", (850, 865, 930, 935)),
        ("well_icon", (935, 865, 1015, 940)),
        ("sword_icon", (0, 5, 55, 65)),
        ("potion_red", (0, 185, 60, 245)),
        ("potion_blue", (70, 185, 130, 245)),
        ("wood_log", (0, 370, 60, 420)),
        ("stone_ore", (145, 370, 205, 425)),
        ("crystal_small", (425, 370, 480, 425)),
        ("heart_ui", (0, 565, 60, 625)),
        ("energy_ui", (140, 565, 200, 625)),
    ],
    "image (35).png": [
        ("hud_panel", (20, 370, 230, 500)),
        ("quest_panel", (505, 370, 730, 500)),
        ("reward_panel", (760, 610, 1010, 735)),
        ("bottom_buttons", (15, 890, 1010, 1015)),
    ],
}


def is_background(pixel):
    r, g, b = pixel[:3]
    if r > 244 and g > 244 and b > 238:
        return True
    # Fake transparency checkerboard in the source sheets.
    if abs(r - g) <= 4 and abs(g - b) <= 4 and r >= 216:
        return True
    return False


def crop_asset(sheet, box):
    crop = sheet.crop(box).convert("RGBA")
    pix = crop.load()
    xs = []
    ys = []
    for y in range(crop.height):
        for x in range(crop.width):
            if is_background(pix[x, y]):
                pix[x, y] = (0, 0, 0, 0)
            elif pix[x, y][3] > 0:
                xs.append(x)
                ys.append(y)
    if not xs:
        return crop
    pad = 4
    x0 = max(0, min(xs) - pad)
    y0 = max(0, min(ys) - pad)
    x1 = min(crop.width, max(xs) + pad + 1)
    y1 = min(crop.height, max(ys) + pad + 1)
    return crop.crop((x0, y0, x1, y1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for file_name, entries in ASSETS.items():
        sheet = Image.open(SRC / file_name).convert("RGBA")
        for name, box in entries:
            asset = crop_asset(sheet, box)
            path = OUT / f"{name}.png"
            asset.save(path)
            written.append(path)

    cols = 8
    cell = (180, 170)
    rows = (len(written) + cols - 1) // cols
    contact = Image.new("RGB", (cols * cell[0], rows * cell[1]), (236, 232, 210))
    draw = ImageDraw.Draw(contact)
    for i, path in enumerate(written):
        im = Image.open(path).convert("RGBA")
        scale = min(150 / max(1, im.width), 120 / max(1, im.height), 1)
        if scale < 1:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.Resampling.LANCZOS)
        x = (i % cols) * cell[0]
        y = (i // cols) * cell[1]
        contact.paste(im, (x + (cell[0] - im.width) // 2, y + 6), im)
        draw.text((x + 6, y + 140), path.stem[:24], fill=(45, 44, 36))
    contact.save(OUT / "_topdown_contact_sheet.png")
    print(f"wrote {len(written)} assets to {OUT}")


if __name__ == "__main__":
    main()
