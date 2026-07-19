#!/usr/bin/env python3
"""Audit fixed M55 LCD text against the committed LVGL font coverage."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_SUPPLEMENT = (
    "主动模式助力模式抗阻模式被动模式急停安全停止关节肩肘腕"
    "轨迹电流力矩角度速度限幅故障恢复设备配对绑定蓝牙康复训练"
)
MANIFEST_PATH = Path("docs/LVGL固定界面中文字形清单.txt")
REVIEWED_SOURCES_PATH = Path("docs/LVGL中文字库审查源码清单.txt")
PRIMARY_FONT_PATH = Path("applications/rehab_wifi_font.c")
COMMON_FONT_PATH = Path("applications/rehab_cjk_common_font.c")
SIMSUN_FONT_PATH = Path(
    "libraries/components/lvgl_9.2.0/src/font/lv_font_simsun_16_cjk.c"
)
EXPECTED_FONT_CHAIN = (
    "rehab_wifi_font",
    "rehab_cjk_common_font",
    "lv_font_simsun_16_cjk",
)
_SOURCE_EXTENSIONS = {".c", ".cc", ".cpp", ".h", ".hpp"}
_EXCLUDED_SOURCE_DIRS = {"ifx_deepcraft"}
_DISPLAY_CALL_RE = re.compile(
    r"\blv_(?:label_set_text(?:_fmt|_static)?|textarea_set_placeholder_text|"
    r"checkbox_set_text)\s*\("
)

_ARRAY_RE = re.compile(
    r"static\s+const\s+uint(?:8|16)_t\s+(?P<name>\w+)\[\]\s*=\s*"
    r"\{(?P<body>.*?)\};",
    re.DOTALL,
)
_CMAPS_RE = re.compile(
    r"static\s+const\s+lv_font_fmt_txt_cmap_t\s+cmaps\[\]\s*=\s*"
    r"\{(?P<body>.*?)\n\};",
    re.DOTALL,
)
_C_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')


def is_cjk(codepoint: int) -> bool:
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def extract_cjk(text: str) -> str:
    return "".join(sorted({char for char in text if is_cjk(ord(char))}, key=ord))


def build_manifest(source_texts: list[str], supplement: str) -> str:
    display_literals = "".join(
        literal
        for source_text in source_texts
        for literal in _C_STRING_RE.findall(source_text)
    )
    return extract_cjk(display_literals + supplement)


def common_font_target(manifest: str) -> str:
    characters: list[str] = []
    for lead in range(0xB0, 0xD8):
        final_trail = 0xF9 if lead == 0xD7 else 0xFE
        for trail in range(0xA1, final_trail + 1):
            characters.append(bytes((lead, trail)).decode("gb2312"))
    return "".join(sorted(set(characters + list(manifest)), key=ord))


def validate_exact_coverage(
    actual: set[int], expected_characters: str
) -> tuple[set[int], set[int]]:
    expected = set(map(ord, expected_characters))
    return expected - actual, actual - expected


def _font_fallback(source: str) -> str | None:
    targets = re.findall(r"\.fallback\s*=\s*&(\w+)\s*,", source)
    if len(targets) > 1:
        raise ValueError("font has multiple fallback pointers")
    return targets[0] if targets else None


def validate_fallback_chain(font_sources: dict[str, str]) -> tuple[str, ...]:
    current = EXPECTED_FONT_CHAIN[0]
    chain: list[str] = []
    seen: set[str] = set()
    while current is not None:
        if current in seen:
            raise ValueError(f"fallback cycle at {current}")
        if current not in font_sources:
            raise ValueError(f"fallback target source missing: {current}")
        seen.add(current)
        chain.append(current)
        target = _font_fallback(font_sources[current])
        if target is not None:
            declaration = f"LV_FONT_DECLARE({target});"
            if declaration not in font_sources[current]:
                raise ValueError(f"fallback target is not declared: {target}")
        current = target
    actual = tuple(chain)
    if actual != EXPECTED_FONT_CHAIN:
        raise ValueError(f"fallback chain {actual} != {EXPECTED_FONT_CHAIN}")
    return actual


def load_reviewed_sources(root: Path) -> tuple[Path, ...]:
    lines = (root / REVIEWED_SOURCES_PATH).read_text(encoding="utf-8").splitlines()
    reviewed: list[Path] = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            reviewed.append(Path(line))
    return tuple(reviewed)


def discover_display_sources(root: Path) -> tuple[set[Path], int]:
    applications = root / "applications"
    discovered: set[Path] = set()
    scanned = 0
    for path in sorted(applications.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or path.suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        if any(part in _EXCLUDED_SOURCE_DIRS for part in relative.parts):
            continue
        if path.name.endswith("_font.c"):
            continue
        scanned += 1
        source = path.read_text(encoding="utf-8", errors="replace")
        if _DISPLAY_CALL_RE.search(source):
            discovered.add(relative)
    return discovered, scanned


def unreviewed_display_sources(
    discovered: set[Path], reviewed: tuple[Path, ...]
) -> set[Path]:
    return discovered - set(reviewed)


def _parse_int(body: str, field: str) -> int:
    match = re.search(rf"\.{field}\s*=\s*(0[xX][0-9a-fA-F]+|\d+)", body)
    if match is None:
        raise ValueError(f"cmap has no {field}")
    return int(match.group(1), 0)


def parse_lvgl_font_coverage(font_source: str) -> set[int]:
    arrays: dict[str, list[int]] = {}
    for match in _ARRAY_RE.finditer(font_source):
        arrays[match.group("name")] = [
            int(token, 0)
            for token in re.findall(r"0[xX][0-9a-fA-F]+|\d+", match.group("body"))
        ]

    cmaps_match = _CMAPS_RE.search(font_source)
    if cmaps_match is None:
        raise ValueError("LVGL cmaps array not found")

    coverage: set[int] = set()
    for block in re.findall(r"\{(.*?)\}", cmaps_match.group("body"), re.DOTALL):
        if ".range_start" not in block:
            continue
        start = _parse_int(block, "range_start")
        length = _parse_int(block, "range_length")
        cmap_type = re.search(r"\.type\s*=\s*(LV_FONT_FMT_TXT_CMAP_\w+)", block)
        if cmap_type is None:
            raise ValueError("cmap has no type")
        cmap_type_name = cmap_type.group(1)

        list_match = re.search(r"\.unicode_list\s*=\s*(\w+)", block)
        list_name = list_match.group(1) if list_match else "NULL"
        if "SPARSE" in cmap_type_name:
            if list_name == "NULL" or list_name not in arrays:
                raise ValueError(f"sparse cmap references unknown list {list_name}")
            list_length = _parse_int(block, "list_length")
            coverage.update(start + offset for offset in arrays[list_name][:list_length])
            continue

        if "FORMAT0_FULL" in cmap_type_name:
            offset_match = re.search(r"\.glyph_id_ofs_list\s*=\s*(\w+)", block)
            offset_name = offset_match.group(1) if offset_match else "NULL"
            offsets = arrays.get(offset_name, [])
            coverage.update(
                start + index
                for index, glyph_offset in enumerate(offsets[:length])
                if index == 0 or glyph_offset != 0
            )
            continue

        coverage.update(range(start, start + length))

    return coverage


def missing_characters(manifest: str, coverage: set[int]) -> str:
    return "".join(char for char in manifest if ord(char) not in coverage)


def check_exit_code(drift: bool, missing: str, audit_errors: bool = False) -> int:
    if drift:
        return 2
    if audit_errors:
        return 4
    if missing:
        return 3
    return 0


def _load_manifest_inputs(root: Path, source_files: tuple[Path, ...]) -> str:
    texts = [(root / path).read_text(encoding="utf-8") for path in source_files]
    return build_manifest(texts, BUSINESS_SUPPLEMENT)


def _read_font_coverage(root: Path, path: Path) -> set[int]:
    return parse_lvgl_font_coverage((root / path).read_text(encoding="utf-8"))


def _print_report(
    manifest: str, primary: set[int], common: set[int], simsun: set[int]
) -> str:
    combined = primary | common | simsun
    missing = missing_characters(manifest, combined)
    primary_cjk = sum(is_cjk(codepoint) for codepoint in primary)
    common_cjk = sum(is_cjk(codepoint) for codepoint in common)
    simsun_cjk = sum(is_cjk(codepoint) for codepoint in simsun)
    delta_low = len(missing) * 96
    delta_high = len(missing) * 160
    print(f"fixed_ui_cjk={len(manifest)}")
    print(
        f"primary_cjk={primary_cjk} common_cjk={common_cjk} "
        f"simsun_cjk={simsun_cjk}"
    )
    print(f"missing_fixed_ui={len(missing)} chars={missing or '-'}")
    print(
        "estimated_next_font_delta="
        f"{delta_low / 1024:.1f}-{delta_high / 1024:.1f} KiB "
        "(96-160 bytes per added 18px 2bpp glyph heuristic)"
    )
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="update the committed manifest")
    mode.add_argument("--check", action="store_true", help="fail on drift or missing coverage")
    args = parser.parse_args(argv)

    reviewed = load_reviewed_sources(ROOT)
    discovered, scanned = discover_display_sources(ROOT)
    unreviewed = unreviewed_display_sources(discovered, reviewed)
    missing_reviewed = {path for path in reviewed if not (ROOT / path).is_file()}
    source_drift = bool(unreviewed or missing_reviewed)
    print(
        f"first_party_sources_scanned={scanned} reviewed_sources={len(reviewed)} "
        f"likely_display_sources={len(discovered)}"
    )
    print(
        "source_review_drift="
        f"{int(source_drift)} unreviewed={','.join(map(str, sorted(unreviewed))) or '-'} "
        f"missing={','.join(map(str, sorted(missing_reviewed))) or '-'}"
    )

    manifest = _load_manifest_inputs(ROOT, reviewed)
    manifest_path = ROOT / MANIFEST_PATH
    if args.write:
        manifest_path.write_text(manifest + "\n", encoding="utf-8", newline="\n")

    committed = manifest_path.read_text(encoding="utf-8").strip() if manifest_path.exists() else ""
    drift = committed != manifest
    if drift:
        print(
            f"manifest_drift=1 expected={len(manifest)} committed={len(committed)}; "
            "run with --write",
            file=sys.stderr,
        )
    else:
        print("manifest_drift=0")

    primary = _read_font_coverage(ROOT, PRIMARY_FONT_PATH)
    common = _read_font_coverage(ROOT, COMMON_FONT_PATH)
    simsun = _read_font_coverage(ROOT, SIMSUN_FONT_PATH)
    expected_common = common_font_target(manifest)
    common_missing, common_extra = validate_exact_coverage(common, expected_common)
    common_drift = bool(common_missing or common_extra)
    print(
        f"common_target={len(expected_common)} actual={len(common)} "
        f"missing={len(common_missing)} extra={len(common_extra)}"
    )

    font_sources = {
        "rehab_wifi_font": (ROOT / PRIMARY_FONT_PATH).read_text(encoding="utf-8"),
        "rehab_cjk_common_font": (ROOT / COMMON_FONT_PATH).read_text(encoding="utf-8"),
        "lv_font_simsun_16_cjk": (ROOT / SIMSUN_FONT_PATH).read_text(encoding="utf-8"),
    }
    chain_error = False
    try:
        chain = validate_fallback_chain(font_sources)
        print(f"fallback_chain={'->'.join(chain)}")
    except ValueError as exc:
        chain_error = True
        print(f"fallback_chain_error={exc}", file=sys.stderr)

    missing = _print_report(manifest, primary, common, simsun)
    audit_errors = source_drift or common_drift or chain_error

    if args.check:
        return check_exit_code(drift, missing, audit_errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
