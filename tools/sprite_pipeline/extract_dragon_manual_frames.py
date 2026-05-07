from pathlib import Path

from PIL import Image, ImageDraw


SOURCE = Path("D:/\u6e38\u620f\u7d20\u6750/image (4).png")
OUT = Path.cwd() / "art" / "unity-sprite-demo" / "dragon-manual-frames"


ROWS = {
    "idle": {"y": (60, 250), "centers": [130, 375, 620, 865]},
    "walk": {"y": (330, 490), "centers": [88, 258, 430, 600, 770, 940]},
    "run": {"y": (570, 720), "centers": [82, 254, 425, 600, 770, 940]},
    "fly": {"y": (805, 985), "centers": [82, 250, 420, 595, 770, 940]},
}


def is_foreground(pixel):
    r, g, b = pixel[:3]
    # Dark navy sheet background. Row crops already avoid labels/separators,
    # so keep all non-background colors, including dragon purple and shadows.
    if r < 45 and g < 48 and b < 68:
        return False
    return True


def make_alpha(crop):
    crop = crop.convert("RGBA")
    pix = crop.load()
    xs = []
    ys = []
    for y in range(crop.height):
        for x in range(crop.width):
            if is_foreground(pix[x, y]):
                xs.append(x)
                ys.append(y)
            else:
                pix[x, y] = (0, 0, 0, 0)

    if not xs:
        return crop

    x0 = max(0, min(xs) - 8)
    y0 = max(0, min(ys) - 8)
    x1 = min(crop.width, max(xs) + 9)
    y1 = min(crop.height, max(ys) + 9)
    return crop.crop((x0, y0, x1, y1))


def paste_to_cell(frame):
    # Fixed cell prevents animation jitter and leaves room for tail/wing extents.
    cell = Image.new("RGBA", (260, 210), (0, 0, 0, 0))
    scale = min(240 / max(1, frame.width), 180 / max(1, frame.height), 1.0)
    if scale < 1.0:
        frame = frame.resize((int(frame.width * scale), int(frame.height * scale)), Image.Resampling.LANCZOS)
    x = (cell.width - frame.width) // 2
    y = cell.height - frame.height - 12
    cell.paste(frame, (x, y), frame)
    return cell


def boundaries(centers):
    values = [0]
    for left, right in zip(centers, centers[1:]):
        values.append((left + right) // 2)
    values.append(1024)
    return values


def main():
    src = Image.open(SOURCE).convert("RGBA")
    all_frames = []
    for action, spec in ROWS.items():
        y0, y1 = spec["y"]
        xs = boundaries(spec["centers"])
        action_dir = OUT / action
        action_dir.mkdir(parents=True, exist_ok=True)
        for i in range(len(spec["centers"])):
            x0 = max(0, xs[i] + 4)
            x1 = min(1024, xs[i + 1] - 4)
            frame = make_alpha(src.crop((x0, y0, x1, y1)))
            cell = paste_to_cell(frame)
            out_path = action_dir / f"dragon_{action}_{i + 1:02d}.png"
            cell.save(out_path)
            all_frames.append(out_path)

    cols = 6
    thumb_w, thumb_h = 280, 250
    rows = (len(all_frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * thumb_h), (240, 236, 216))
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(all_frames):
        im = Image.open(path).convert("RGBA")
        x = (i % cols) * thumb_w
        y = (i // cols) * thumb_h
        sheet.paste(im, (x + (thumb_w - im.width) // 2, y + 8), im)
        draw.text((x + 10, y + 220), f"{path.parent.name}/{path.stem[-2:]}", fill=(42, 42, 36))
    sheet.save(OUT / "_contact_sheet.png")
    print(f"wrote {len(all_frames)} frames to {OUT}")


if __name__ == "__main__":
    main()
