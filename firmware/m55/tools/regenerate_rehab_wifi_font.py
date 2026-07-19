#!/usr/bin/env python3
"""Regenerate the fixed M55 LCD font from its committed CJK manifest."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from audit_lvgl_cjk_manifest import is_cjk


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/LVGL固定界面中文字形清单.txt"
OUTPUT_PATH = ROOT / "applications/rehab_wifi_font.c"
DEFAULT_FONT_PATH = Path(r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf")
EXPECTED_FONT_SHA256 = "a2b93e6c2db05d6bbbf6f27d413ec73269735b7b679019c8a5aa9670ff0ffbf2"
FONT_CONV_VERSION = "1.5.3"
PRESERVED_RANGE = "0x20-0x7E,0xB0,0x2022,0x3000-0x303F,0xFF00-0xFFEF"
LEGACY_PRIMARY_CJK = "你准械段离臂误错阶"


def validate_manifest(manifest: str) -> None:
    expected = "".join(sorted(set(manifest), key=ord))
    if manifest != expected:
        raise ValueError("manifest must be sorted and contain unique codepoints")
    if not manifest or any(not is_cjk(ord(char)) for char in manifest):
        raise ValueError("manifest must contain CJK codepoints only")


def generation_symbols(manifest: str) -> str:
    return "".join(sorted(set(manifest + LEGACY_PRIMARY_CJK), key=ord))


def build_command(font_path: Path, manifest: str, output_path: Path) -> list[str]:
    return [
        "npx",
        "--yes",
        f"lv_font_conv@{FONT_CONV_VERSION}",
        "--font",
        str(font_path),
        "--range",
        PRESERVED_RANGE,
        "--symbols",
        manifest,
        "--size",
        "18",
        "--format",
        "lvgl",
        "--bpp",
        "4",
        "--no-compress",
        "--lv-font-name",
        "rehab_wifi_font",
        "--lv-include",
        "lvgl.h",
        "-o",
        str(output_path),
    ]


def patch_font_fallback(generated: str, fallback_font: str) -> str:
    include = '#include "lvgl.h"\n'
    declaration = f"\nLV_FONT_DECLARE({fallback_font});\n"
    generated = re.sub(
        r'#ifdef LV_LVGL_H_INCLUDE_SIMPLE\s*#include "lvgl\.h"\s*'
        r'#else\s*#include "lvgl\.h"\s*#endif',
        include.rstrip(),
        generated,
        count=1,
    )
    if declaration.strip() not in generated:
        if include not in generated:
            raise ValueError("generated font has no LVGL include")
        generated = generated.replace(include, include + declaration, 1)

    user_data = "    .user_data = NULL,\n"
    fallback = (
        "#if LV_VERSION_CHECK(8, 2, 0) || LVGL_VERSION_MAJOR >= 9\n"
        f"    .fallback = &{fallback_font},\n"
        "#endif\n"
    )
    null_fallback = (
        "#if LV_VERSION_CHECK(8, 2, 0) || LVGL_VERSION_MAJOR >= 9\n"
        "    .fallback = NULL,\n"
        "#endif\n"
    )
    if f".fallback = &{fallback_font}," not in generated:
        if null_fallback in generated:
            generated = generated.replace(null_fallback, fallback, 1)
        elif user_data not in generated:
            raise ValueError("generated font has no user_data initializer")
        else:
            generated = generated.replace(user_data, fallback + user_data, 1)
    return generated


def patch_simsun_fallback(generated: str) -> str:
    return patch_font_fallback(generated, "lv_font_simsun_16_cjk")


def patch_common_fallback(generated: str) -> str:
    return patch_font_fallback(generated, "rehab_cjk_common_font")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT_PATH)
    args = parser.parse_args()

    if not args.font.is_file():
        raise SystemExit(f"font not found: {args.font}")
    actual_hash = _sha256(args.font)
    if actual_hash != EXPECTED_FONT_SHA256:
        raise SystemExit(
            f"font SHA-256 mismatch: expected {EXPECTED_FONT_SHA256}, got {actual_hash}"
        )

    manifest = MANIFEST_PATH.read_text(encoding="utf-8").strip()
    validate_manifest(manifest)
    temporary_path = Path("applications/rehab_wifi_font.generated.c")
    command = build_command(args.font, generation_symbols(manifest), temporary_path)
    if os.name == "nt":
        command[0] = shutil.which("npx.cmd") or "npx.cmd"
    subprocess.run(command, cwd=ROOT, check=True)

    generated_path = ROOT / temporary_path
    try:
        generated = generated_path.read_text(encoding="utf-8")
        generated = generated.replace(str(temporary_path), "applications/rehab_wifi_font.c")
        OUTPUT_PATH.write_text(
            patch_common_fallback(generated), encoding="utf-8", newline="\n"
        )
    finally:
        generated_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
