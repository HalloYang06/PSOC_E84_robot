#!/usr/bin/env python3
"""Generate the Flash-resident 18px GB2312 level-1 LVGL fallback font."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import regenerate_rehab_wifi_font as fixed_font


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "applications/rehab_cjk_common_font.c"


def gb2312_level1_characters() -> str:
    characters: list[str] = []
    for lead in range(0xB0, 0xD8):
        final_trail = 0xF9 if lead == 0xD7 else 0xFE
        for trail in range(0xA1, final_trail + 1):
            characters.append(bytes((lead, trail)).decode("gb2312"))
    return "".join(sorted(characters, key=ord))


def build_command(font_path: Path, symbols: str, output_path: Path) -> list[str]:
    return [
        "npx",
        "--yes",
        f"lv_font_conv@{fixed_font.FONT_CONV_VERSION}",
        "--font",
        str(font_path),
        "--symbols",
        symbols,
        "--size",
        "18",
        "--format",
        "lvgl",
        "--bpp",
        "2",
        "--no-compress",
        "--lv-font-name",
        "rehab_cjk_common_font",
        "--lv-include",
        "lvgl.h",
        "-o",
        str(output_path),
    ]


def patch_simsun_fallback(generated: str) -> str:
    return fixed_font.patch_simsun_fallback(generated)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, default=fixed_font.DEFAULT_FONT_PATH)
    args = parser.parse_args()

    if not args.font.is_file():
        raise SystemExit(f"font not found: {args.font}")
    actual_hash = fixed_font._sha256(args.font)
    if actual_hash != fixed_font.EXPECTED_FONT_SHA256:
        raise SystemExit(
            "font SHA-256 mismatch: expected "
            f"{fixed_font.EXPECTED_FONT_SHA256}, got {actual_hash}"
        )

    symbols = gb2312_level1_characters()
    manifest = (ROOT / "docs/LVGL固定界面中文字形清单.txt").read_text(
        encoding="utf-8"
    ).strip()
    if not set(manifest) <= set(symbols):
        symbols = "".join(sorted(set(symbols + manifest), key=ord))

    temporary_path = Path("applications/rehab_cjk_common_font.generated.c")
    command = build_command(args.font, symbols, temporary_path)
    if os.name == "nt":
        command[0] = shutil.which("npx.cmd") or "npx.cmd"
    subprocess.run(command, cwd=ROOT, check=True)

    generated_path = ROOT / temporary_path
    try:
        generated = generated_path.read_text(encoding="utf-8")
        generated = generated.replace(
            str(temporary_path), "applications/rehab_cjk_common_font.c"
        )
        OUTPUT_PATH.write_text(
            patch_simsun_fallback(generated), encoding="utf-8", newline="\n"
        )
    finally:
        generated_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
