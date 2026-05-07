from pathlib import Path

from PIL import Image, ImageDraw


SOURCE = Path("D:/\u6e38\u620f\u7d20\u6750")
OUT = Path.cwd() / "art" / "unity-sprite-demo" / "clean-grid-frames"


SHEETS = [
    {
        "file": "image (17).png",
        "name": "ember_pup",
        "rows": [("idle", 4), ("walk", 6), ("run", 6), ("fly", 6)],
    },
    {
        "file": "image (18).png",
        "name": "shadow_cat",
        "rows": [("idle", 3), ("walk", 6), ("run", 6), ("stealth", 6)],
    },
    {
        "file": "image (19).png",
        "name": "field_mouse",
        "rows": [("idle", 4), ("walk", 5), ("run", 4), ("stealth", 4)],
    },
    {
        "file": "image (21).png",
        "name": "frost_wolf",
        "rows": [("idle", 6), ("walk", 6), ("run", 6), ("stealth", 5)],
    },
    {
        "file": "image (22).png",
        "name": "aqua_drake",
        "rows": [("idle", 4), ("walk", 6), ("run", 6), ("swim", 6)],
    },
    {
        "file": "image (23).png",
        "name": "pond_frog",
        "rows": [("idle", 4), ("jump", 4), ("walk", 6), ("swim", 6)],
    },
    {
        "file": "image (24).png",
        "name": "sun_tiger",
        "rows": [("idle", 4), ("walk", 6), ("run", 6)],
    },
    {
        "file": "image (25).png",
        "name": "forest_guardian",
        "rows": [("idle", 4), ("walk", 4), ("run", 4)],
    },
    {
        "file": "image (26).png",
        "name": "bamboo_panda",
        "rows": [("idle", 5), ("walk", 5), ("run", 5)],
    },
    {
        "file": "image (27).png",
        "name": "camp_dog",
        "rows": [("idle", 4), ("walk", 6), ("run", 6)],
    },
    {
        "file": "image (28).png",
        "name": "cloud_mage",
        "rows": [("idle", 6), ("walk", 6), ("run", 6)],
    },
]


def foreground_mask(image, dark_sheet):
    rgb = image.convert("RGB")
    pixels = rgb.load()
    w, h = rgb.size
    mask = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            if dark_sheet:
                # Dark presentation sheets: keep saturated/light pixels, drop near-black backdrop.
                mask[y][x] = max(r, g, b) > 42 and (max(r, g, b) - min(r, g, b) > 10 or max(r, g, b) > 95)
            else:
                # White/checker presentation sheets: keep colored/dark pixels, drop pale checkerboard.
                mask[y][x] = not (r > 218 and g > 218 and b > 218)
    return mask


def bands_from_density(density, min_value, gap=10):
    bands = []
    start = None
    last = None
    for i, value in enumerate(density):
        if value >= min_value:
            if start is None:
                start = i
            last = i
        elif start is not None and i - last > gap:
            bands.append((start, last))
            start = None
            last = None
    if start is not None:
        bands.append((start, last))
    return bands


def trim_rect(mask, rect, pad=10):
    x0, y0, x1, y1 = rect
    xs = []
    ys = []
    for y in range(max(0, y0), min(len(mask), y1)):
        row = mask[y]
        for x in range(max(0, x0), min(len(row), x1)):
            if row[x]:
                xs.append(x)
                ys.append(y)
    if not xs:
        return rect
    w = len(mask[0])
    h = len(mask)
    return (
        max(0, min(xs) - pad),
        max(0, min(ys) - pad),
        min(w, max(xs) + pad + 1),
        min(h, max(ys) + pad + 1),
    )


def transparent_crop(image, mask, rect):
    x0, y0, x1, y1 = rect
    crop = image.convert("RGBA").crop(rect)
    out = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    src = crop.load()
    dst = out.load()
    for y in range(crop.height):
        for x in range(crop.width):
            if mask[y0 + y][x0 + x]:
                dst[x, y] = src[x, y]
    return out


def extract_sheet(config):
    path = SOURCE / config["file"]
    image = Image.open(path).convert("RGBA")
    dark_sheet = config["file"] in {"image (21).png"} or Image.open(path).convert("RGB").getpixel((10, 10))[0] < 80
    mask = foreground_mask(image, dark_sheet)
    w, h = image.size

    # These sheets are presentation-style grids: action rows are evenly spaced,
    # while per-frame spacing varies. Discovering rows by density can accidentally
    # catch labels or title cards, so use broad row lanes and trim inside each lane.
    scan_x0 = 120
    top = 90
    bottom = 910
    lane_h = (bottom - top) / len(config["rows"])
    row_bands = []
    for i in range(len(config["rows"])):
        y0 = int(top + i * lane_h)
        y1 = int(top + (i + 1) * lane_h)
        row_bands.append((max(0, y0), min(h - 1, y1)))

    summary = []
    for (action, count), (y0, y1) in zip(config["rows"], row_bands):
        xs = [
            x
            for x in range(scan_x0, w - 20)
            if sum(1 for y in range(y0, y1 + 1) if mask[y][x]) > 5
        ]
        if xs:
            row_x0 = max(scan_x0, min(xs) - 10)
            row_x1 = min(w - 20, max(xs) + 10)
        else:
            row_x0 = scan_x0
            row_x1 = w - 20

        cell_w = (row_x1 - row_x0) / count
        cols = [
            (int(row_x0 + i * cell_w), int(row_x0 + (i + 1) * cell_w))
            for i in range(count)
        ]
        action_dir = OUT / config["name"] / action
        action_dir.mkdir(parents=True, exist_ok=True)

        for index, (x0, x1) in enumerate(cols, start=1):
            rect = trim_rect(mask, (x0, y0, x1 + 1, y1 + 1), pad=12)
            frame = transparent_crop(image, mask, rect)
            # Use a fixed padded cell per action to avoid animation jitter.
            cell = Image.new("RGBA", (150, 130), (0, 0, 0, 0))
            scale = min(128 / max(1, frame.width), 112 / max(1, frame.height), 1.0)
            if scale < 1.0:
                frame = frame.resize((int(frame.width * scale), int(frame.height * scale)), Image.Resampling.LANCZOS)
            cell.paste(frame, ((cell.width - frame.width) // 2, cell.height - frame.height - 8), frame)
            frame_path = action_dir / f"{config['name']}_{action}_{index:02d}.png"
            cell.save(frame_path)
            summary.append(frame_path)
    return summary


def build_contact_sheet(paths):
    thumbs = []
    for p in paths:
        im = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", (166, 154), (244, 240, 218, 255))
        bg.paste(im, ((166 - im.width) // 2, 6), im)
        thumbs.append((p, bg.convert("RGB")))
    cols = 8
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 166, rows * 184), (232, 228, 205))
    draw = ImageDraw.Draw(sheet)
    for i, (path, thumb) in enumerate(thumbs):
        x = (i % cols) * 166
        y = (i // cols) * 184
        sheet.paste(thumb, (x, y))
        label = f"{path.parent.parent.name}/{path.parent.name}/{path.stem[-2:]}"
        draw.text((x + 4, y + 160), label, fill=(46, 46, 38))
    sheet.save(OUT / "_contact_sheet.png")


def main():
    all_paths = []
    for config in SHEETS:
        all_paths.extend(extract_sheet(config))
    build_contact_sheet(all_paths)
    print(f"extracted {len(all_paths)} frames to {OUT}")


if __name__ == "__main__":
    main()
