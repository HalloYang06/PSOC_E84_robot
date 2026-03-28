from __future__ import annotations

import argparse
import json
from pathlib import Path

from vla_system.services.vla_bridge_service import VLABridgeService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve a VLA task from a JSON payload.")
    parser.add_argument("--input", required=True, help="Path to the input JSON payload.")
    parser.add_argument(
        "--output",
        help="Optional path to write the resolved task JSON. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    resolved = VLABridgeService().resolve(payload).to_dict()
    text = json.dumps(resolved, ensure_ascii=False, indent=2 if args.pretty else None)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())