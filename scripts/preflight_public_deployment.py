from __future__ import annotations

import argparse
import sys
from pathlib import Path

from public_deployment_lib import build_preflight_report, env_file_from_default, print_report, repo_root_from_script


def main() -> int:
    repo_root = repo_root_from_script(__file__)
    parser = argparse.ArgumentParser(description="Validate the formal public deployment configuration before running it.")
    parser.add_argument("--env-file", default=str(env_file_from_default(repo_root)))
    parser.add_argument("--compose-file", default=str(repo_root / "infra" / "docker-compose.public.yml"))
    parser.add_argument("--skip-docker-check", action="store_true")
    args = parser.parse_args()

    env_file = Path(args.env_file).resolve()
    compose_file = Path(args.compose_file).resolve()

    if not env_file.exists():
        print(f"env file not found: {env_file}", file=sys.stderr)
        return 2
    if not compose_file.exists():
        print(f"compose file not found: {compose_file}", file=sys.stderr)
        return 2

    report = build_preflight_report(
        env_file=env_file,
        compose_file=compose_file,
        require_docker=not args.skip_docker_check,
    )
    print_report(report)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
