from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml


REQUIRED_ENV_KEYS = [
    "PUBLIC_APP_DOMAIN",
    "ACME_EMAIL",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "SECRET_KEY",
    "TOKEN_ENCRYPTION_KEY",
    "RUNNER_REGISTRATION_TOKEN",
    "AUTH_PROVIDER",
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"(^|[-_])change-me($|[-_])", re.IGNORECASE),
    re.compile(r"replace-with", re.IGNORECASE),
    re.compile(r"example\.com", re.IGNORECASE),
]


def parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().lstrip("\ufeff")
        values[normalized_key] = value.strip()
    return values


def looks_like_placeholder(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return True
    return any(pattern.search(candidate) for pattern in PLACEHOLDER_PATTERNS)


def validate_domain(value: str) -> bool:
    domain = value.strip().lower()
    if not domain or "://" in domain or "/" in domain:
        return False
    return "." in domain and " " not in domain


def validate_email(value: str) -> bool:
    email = value.strip()
    return "@" in email and "." in email.split("@", 1)[-1]


def check_docker_available() -> tuple[bool, str]:
    docker_path = shutil.which("docker")
    if not docker_path:
        return False, "docker command not found"
    try:
        completed = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, f"docker compose version failed to launch: {exc}"
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        return False, f"docker compose version failed: {stderr}"
    return True, completed.stdout.strip()


def validate_compose_file(compose_file: Path) -> dict[str, Any]:
    payload = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = payload.get("services", {}) if isinstance(payload, dict) else {}
    return {
        "service_names": sorted(services.keys()),
        "has_expected_services": sorted(services.keys()) == ["api", "caddy", "postgres", "redis", "web"],
    }


def build_preflight_report(env_file: Path, compose_file: Path, require_docker: bool) -> dict[str, Any]:
    env_values = parse_env_file(env_file)
    missing = [key for key in REQUIRED_ENV_KEYS if not env_values.get(key, "").strip()]
    placeholders = [
        key
        for key, value in env_values.items()
        if key in REQUIRED_ENV_KEYS and looks_like_placeholder(value)
    ]
    issues: list[str] = []
    warnings: list[str] = []

    if missing:
        issues.append(f"missing required environment keys: {', '.join(missing)}")
    if placeholders:
        issues.append(f"placeholder values still present: {', '.join(placeholders)}")

    if not validate_domain(env_values.get("PUBLIC_APP_DOMAIN", "")):
        issues.append("PUBLIC_APP_DOMAIN must be a real hostname without scheme or path")

    if not validate_email(env_values.get("ACME_EMAIL", "")):
        issues.append("ACME_EMAIL must be a valid email address")

    auth_provider = env_values.get("AUTH_PROVIDER", "").strip().lower()
    if auth_provider == "supertokens":
        if not env_values.get("SUPERTOKENS_CONNECTION_URI", "").strip():
            issues.append("SUPERTOKENS_CONNECTION_URI is required when AUTH_PROVIDER=supertokens")
        if not env_values.get("SUPERTOKENS_SMTP_HOST", "").strip():
            warnings.append("SUPERTOKENS_SMTP_HOST is empty; email delivery will not work")
        if not env_values.get("SUPERTOKENS_SMTP_FROM_EMAIL", "").strip():
            warnings.append("SUPERTOKENS_SMTP_FROM_EMAIL is empty; email delivery will not work")

    docker_ok = None
    docker_detail = "not checked"
    if require_docker:
        docker_ok, docker_detail = check_docker_available()
        if not docker_ok:
            issues.append(docker_detail)

    compose_summary = validate_compose_file(compose_file)
    if not compose_summary["has_expected_services"]:
        issues.append("compose file does not expose the expected services: api, caddy, postgres, redis, web")

    return {
        "env_file": str(env_file),
        "compose_file": str(compose_file),
        "required_keys_checked": REQUIRED_ENV_KEYS,
        "missing_keys": missing,
        "placeholder_keys": placeholders,
        "issues": issues,
        "warnings": warnings,
        "docker_checked": require_docker,
        "docker_ok": docker_ok,
        "docker_detail": docker_detail,
        "compose_summary": compose_summary,
        "ready": not issues,
    }


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False))


def repo_root_from_script(script_file: str) -> Path:
    return Path(script_file).resolve().parent.parent


def env_file_from_default(repo_root: Path) -> Path:
    override = os.environ.get("AI_COLLAB_PUBLIC_ENV_FILE", "").strip()
    if override:
        return Path(override).resolve()
    return repo_root / "infra" / ".env.public"
