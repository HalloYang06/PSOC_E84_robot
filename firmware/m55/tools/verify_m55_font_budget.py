#!/usr/bin/env python3
"""Verify that the common CJK font stays inside M55 Flash budgets."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_TEXT = 1_718_900
BASELINE_METADATA_PATH = ROOT / "docs/M55常用中文字库预算基线.env"
NVM_START = 0x60580000
NVM_LIMIT = 0x60D80000
MAX_TEXT_DELTA = 1_572_864
MIN_HEADROOM = 1_048_576


def parse_text_size(output: str) -> int:
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 6 and fields[0].isdigit():
            return int(fields[0])
    raise ValueError("arm-none-eabi-size output has no size row")


def parse_nvm_load_end(output: str) -> int:
    pattern = re.compile(
        r"^\s*\d+\s+\S+\s+([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+"
        r"([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+\S+\s*\n\s*([^\n]+)",
        re.MULTILINE,
    )
    ends: list[int] = []
    for match in pattern.finditer(output):
        size = int(match.group(1), 16)
        lma = int(match.group(2), 16)
        flags = match.group(3)
        if (
            NVM_START <= lma < NVM_LIMIT
            and all(flag in flags for flag in ("CONTENTS", "ALLOC", "LOAD"))
        ):
            ends.append(lma + size)
    if not ends:
        raise ValueError("objdump output has no loadable M55 NVM section")
    return max(ends)


def evaluate_budget(
    baseline_text: int, current_text: int, load_end: int
) -> dict[str, int]:
    text_delta = current_text - baseline_text
    headroom = NVM_LIMIT - load_end
    if text_delta < 0 or text_delta > MAX_TEXT_DELTA:
        raise ValueError(f"text delta {text_delta} exceeds {MAX_TEXT_DELTA}")
    if headroom < MIN_HEADROOM:
        raise ValueError(f"Flash headroom {headroom} is below {MIN_HEADROOM}")
    return {"text_delta": text_delta, "load_end": load_end, "headroom": headroom}


def read_baseline_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"invalid baseline metadata line: {line}")
        metadata[key.strip()] = value.strip()
    return metadata


def baseline_binding(root: Path, metadata: dict[str, str]) -> tuple[bool, str]:
    required = {"baseline_commit", "baseline_text", "config_path", "config_sha256"}
    if not required <= metadata.keys():
        return False, "metadata_incomplete"
    if not re.fullmatch(r"[0-9a-f]{40}", metadata["baseline_commit"]):
        return False, "baseline_commit_invalid"
    config_path = root / metadata["config_path"]
    if not config_path.is_file():
        return False, "config_missing"
    actual_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    if actual_hash != metadata["config_sha256"]:
        return False, "config_sha256_mismatch"
    try:
        int(metadata["baseline_text"])
    except ValueError:
        return False, "baseline_text_invalid"
    return True, "bound"


def evaluate_headroom(load_end: int) -> int:
    headroom = NVM_LIMIT - load_end
    if headroom < MIN_HEADROOM:
        raise ValueError(f"Flash headroom {headroom} is below {MIN_HEADROOM}")
    return headroom


def _tool(name: str, tool_dir: Path | None) -> str:
    executable = f"arm-none-eabi-{name}.exe" if os.name == "nt" else f"arm-none-eabi-{name}"
    if tool_dir is not None:
        candidate = tool_dir / executable
        if candidate.is_file():
            return str(candidate)
    resolved = shutil.which(executable)
    if resolved is None:
        raise SystemExit(f"tool not found: {executable}; pass --tool-dir")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, default=ROOT / "rt-thread.elf")
    parser.add_argument("--tool-dir", type=Path)
    parser.add_argument("--baseline-metadata", type=Path, default=BASELINE_METADATA_PATH)
    args = parser.parse_args()

    size_output = subprocess.check_output(
        [_tool("size", args.tool_dir), str(args.elf)], text=True
    )
    sections_output = subprocess.check_output(
        [_tool("objdump", args.tool_dir), "-h", str(args.elf)], text=True
    )
    current_text = parse_text_size(size_output)
    load_end = parse_nvm_load_end(sections_output)
    headroom = evaluate_headroom(load_end)
    if args.baseline_metadata.is_file():
        metadata = read_baseline_metadata(args.baseline_metadata)
        bound, reason = baseline_binding(ROOT, metadata)
    else:
        metadata = {}
        bound, reason = False, "metadata_missing"
    baseline_text = int(metadata["baseline_text"]) if metadata.get("baseline_text", "").isdigit() else 0
    text_delta = current_text - baseline_text if baseline_text else 0
    if bound:
        evaluate_budget(baseline_text, current_text, load_end)
        print(
            f"baseline_unbound=0 commit={metadata['baseline_commit']} "
            f"config_sha256={metadata['config_sha256']}"
        )
        print(f"font_text_delta={text_delta} limit={MAX_TEXT_DELTA}")
    else:
        print(f"baseline_unbound=1 reason={reason} text_delta_informational={text_delta}")
    print(f"nvm_load_end=0x{load_end:08X} limit=0x{NVM_LIMIT:08X}")
    print(f"nvm_headroom={headroom} ({headroom / 1048576:.2f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
