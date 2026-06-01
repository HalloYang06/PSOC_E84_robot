from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_FILES = (
    "BUILD_ID",
    "package.json",
    "build-manifest.json",
    "prerender-manifest.json",
    "react-loadable-manifest.json",
    "required-server-files.json",
    "routes-manifest.json",
    "server/middleware-manifest.json",
)

SERVER_ROUTE_MANIFESTS = (
    "server/app-paths-manifest.json",
    "server/pages-manifest.json",
)


def verify_next_build(next_dir: Path) -> dict[str, object]:
    missing = [relative for relative in REQUIRED_FILES if not (next_dir / relative).is_file()]
    has_route_manifest = any((next_dir / relative).is_file() for relative in SERVER_ROUTE_MANIFESTS)
    if not has_route_manifest:
        missing.append("server/app-paths-manifest.json or server/pages-manifest.json")

    build_id = ""
    build_id_path = next_dir / "BUILD_ID"
    if build_id_path.is_file():
        build_id = build_id_path.read_text(encoding="utf-8", errors="replace").strip()
        if not build_id:
            missing.append("BUILD_ID is empty")

    return {
        "ok": not missing,
        "next_dir": str(next_dir),
        "build_id": build_id,
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that a Next.js production build directory is complete enough to start.")
    parser.add_argument(
        "--next-dir",
        default="apps/web/.next",
        help="Path to the Next.js build directory, relative to cwd unless absolute.",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON report instead of a short human message.")
    args = parser.parse_args()

    next_dir = Path(args.next_dir).resolve()
    report = verify_next_build(next_dir)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif report["ok"]:
        print(f"Next build artifacts verified: {next_dir}")
    else:
        print(f"Next build artifacts incomplete: {next_dir}")
        for item in report["missing"]:
            print(f"- missing {item}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
