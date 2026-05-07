from __future__ import annotations

import argparse
from pathlib import Path


def collect_matches(root: Path, pattern: str) -> list[Path]:
    return sorted((path for path in root.glob(pattern) if path.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)


def prune_group(root: Path, pattern: str, keep: int, dry_run: bool) -> tuple[list[Path], list[Path]]:
    matches = collect_matches(root, pattern)
    stale = matches[keep:]
    removed: list[Path] = []
    skipped: list[Path] = []
    for path in stale:
        if not dry_run:
            try:
                path.unlink(missing_ok=True)
                removed.append(path)
            except PermissionError:
                skipped.append(path)
                continue
        else:
            removed.append(path)
    return removed, skipped


def remove_all(root: Path, pattern: str, dry_run: bool) -> tuple[list[Path], list[Path]]:
    matches = collect_matches(root, pattern)
    removed: list[Path] = []
    skipped: list[Path] = []
    for path in matches:
        if not dry_run:
            try:
                path.unlink(missing_ok=True)
                removed.append(path)
            except PermissionError:
                skipped.append(path)
                continue
        else:
            removed.append(path)
    return removed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean temporary live-validation artifacts while keeping the newest proof set.")
    parser.add_argument("--keep", type=int, default=1, help="How many newest files to keep per ephemeral proof/log pattern.")
    parser.add_argument("--dry-run", action="store_true", help="List files without deleting them.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    web_root = repo_root / "apps" / "web"
    artifacts_root = repo_root / "artifacts"

    ephemeral_groups = [
        (repo_root, "api-ephemeral-*.out.log"),
        (repo_root, "api-ephemeral-*.err.log"),
        (web_root, "web-ephemeral-*.out.log"),
        (web_root, "web-ephemeral-*.err.log"),
        (artifacts_root, "project-live-*-ephemeral-*.html"),
        (artifacts_root, "project-live-*-ephemeral-*.png"),
        (artifacts_root, "farm-live-*-ephemeral-*.html"),
        (artifacts_root, "farm-live-*-ephemeral-*.png"),
    ]
    debug_scraps = [
        (artifacts_root, "os-startfile-test.cmd"),
        (artifacts_root, "project-live-3000-noauth-*.html"),
        (artifacts_root, "project-live-3000-noauth-*.txt"),
        (artifacts_root, "project-live-3000-auth-*.html"),
        (artifacts_root, "project-live-3000-webbrowser-*.png"),
        (artifacts_root, "farm-edge-window-3000-*.png"),
        (web_root, "live3000-start.err.log"),
        (web_root, "live3000-start.out.log"),
        (web_root, "web-heartbeat-3000.err.log"),
        (web_root, "web-heartbeat-3000.out.log"),
    ]

    removed: list[Path] = []
    skipped: list[Path] = []
    for root, pattern in ephemeral_groups:
        group_removed, group_skipped = prune_group(root, pattern, keep=max(args.keep, 0), dry_run=args.dry_run)
        removed.extend(group_removed)
        skipped.extend(group_skipped)
    for root, pattern in debug_scraps:
        group_removed, group_skipped = remove_all(root, pattern, dry_run=args.dry_run)
        removed.extend(group_removed)
        skipped.extend(group_skipped)

    label = "Would remove" if args.dry_run else "Removed"
    if removed:
        for path in removed:
            print(f"{label}: {path}")
    else:
        print("Nothing to clean.")
    if skipped:
        for path in skipped:
            print(f"Skipped (in use): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
