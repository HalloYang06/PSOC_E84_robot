from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from public_deployment_lib import build_preflight_report, env_file_from_default, print_report, repo_root_from_script


def main() -> int:
    repo_root = repo_root_from_script(__file__)
    parser = argparse.ArgumentParser(description="Run the formal public deployment stack after a preflight check.")
    parser.add_argument("--env-file", default=str(env_file_from_default(repo_root)))
    parser.add_argument("--compose-file", default=str(repo_root / "infra" / "docker-compose.public.yml"))
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    args = parser.parse_args()

    env_file = Path(args.env_file).resolve()
    compose_file = Path(args.compose_file).resolve()

    if not args.skip_preflight:
        report = build_preflight_report(
            env_file=env_file,
            compose_file=compose_file,
            require_docker=True,
        )
        print_report(report)
        if not report["ready"]:
            print("public deployment preflight failed; refusing to run docker compose", file=sys.stderr)
            return 1

    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "up",
        "--build",
    ]
    if not args.foreground:
        command.append("-d")

    completed = subprocess.run(command, cwd=repo_root, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
