from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from typing import Any


GIT_PREFLIGHT_KINDS = {"git.preflight"}
MAX_COMPLETION_NOTE_CHARS = 3800
MAX_GIT_FIELD_CHARS = 800
RAW_GITHUB_SECRET_PATTERNS = (
    re.compile(r"^(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}$", re.IGNORECASE),
    re.compile(r"^github_pat_[A-Za-z0-9_]{40,}$", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def is_git_preflight_command(payload: dict[str, Any] | None) -> bool:
    return str((payload or {}).get("kind") or "").strip() in GIT_PREFLIGHT_KINDS


def execute_git_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "").strip()
    if kind not in GIT_PREFLIGHT_KINDS:
        return {
            "handled": False,
            "result_status": "failed",
            "note": "",
            "result": {"ok": False, "error": f"unsupported git command kind: {kind or '<empty>'}"},
        }

    result = build_git_preflight_result(payload)
    return {
        "handled": True,
        "result_status": "completed" if result.get("ok") else "failed",
        "note": _format_completion_note("Git 协作预检结果", result),
        "result": result,
    }


def build_git_preflight_result(payload: dict[str, Any]) -> dict[str, Any]:
    action = _bounded_text(payload.get("action"), "status").lower()
    repository_url = _bounded_text(payload.get("repository_url") or payload.get("repo_url"), "")
    branch = _bounded_text(payload.get("branch") or payload.get("target_branch"), "")
    target_ref = _bounded_text(payload.get("target_ref"), "")
    credential_source = _normalize_credential_source(payload.get("credential_source"))
    raw_credential_ref = _bounded_text(payload.get("credential_ref"), "")
    credential_ref = _safe_credential_ref(raw_credential_ref)
    dry_run = _truthy(payload.get("dry_run"), True)
    warnings: list[str] = []
    blockers: list[str] = []

    if action not in {"status", "sync", "rollback", "clone_prepare", "read_only"}:
        blockers.append(f"Unsupported git preflight action: {action}")
    if not repository_url:
        blockers.append("Repository URL is missing. Bind the project GitHub repository before cross-computer execution.")
    elif _looks_like_raw_secret(repository_url):
        blockers.append("Repository URL looks like it contains a secret. Replace it with a normal HTTPS/SSH repository URL.")
        repository_url = "<hidden-secret-like-url>"
    elif "github.com" not in repository_url.lower():
        warnings.append("Repository URL is not a GitHub URL. The platform can record it, but GitHub account binding may not apply.")

    if not dry_run:
        blockers.append("Runner git.preflight is read-only. Destructive or write execution must go through human review first.")
    if _looks_like_raw_secret(raw_credential_ref):
        blockers.append("Credential reference looks like a raw GitHub token/private key. Store it in an environment variable or SSH Agent.")
        credential_ref = "<hidden-secret-like-ref>"

    git_version = _probe_git_version()
    if not git_version["ok"]:
        blockers.append(str(git_version.get("error") or "git executable was not found"))

    credential_check = _check_credential_source(credential_source, credential_ref)
    warnings.extend(str(item) for item in credential_check.get("warnings", []) if item)
    blockers.extend(str(item) for item in credential_check.get("blockers", []) if item)

    result = {
        "ok": not blockers,
        "kind": "git.preflight",
        "action": action,
        "dry_run": dry_run,
        "host_os": platform.platform(),
        "repository_url": repository_url,
        "branch": branch,
        "target_ref": target_ref,
        "credential_source": credential_source,
        "credential_ref": credential_ref,
        "credential_check": credential_check,
        "git_version": git_version,
        "local_path_policy": _bounded_text(
            payload.get("local_path_policy"),
            "Each computer must choose its own local clone path. Do not reuse another computer's absolute path.",
        ),
        "human_review_boundary": _bounded_text(
            payload.get("human_review_boundary"),
            "clone/status/diff/read-only can be preflighted; push/pull/reset/revert/delete/release require human review.",
        ),
        "allowed_now": ["git --version", "credential-source-presence-check", "read-only planning"],
        "blocked_now": ["clone", "pull", "push", "reset", "revert", "delete", "release"],
        "warnings": warnings,
        "blockers": blockers,
    }
    return result


def _probe_git_version() -> dict[str, Any]:
    git = shutil.which("git")
    if not git:
        return {"ok": False, "error": "git executable was not found in PATH"}
    try:
        completed = subprocess.run(
            [git, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _check_credential_source(source: str, credential_ref: str) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    detail: dict[str, Any] = {"source": source, "credential_ref": credential_ref}
    if source == "runner_env":
        env_name = _credential_ref_env_name(credential_ref)
        detail["env_name"] = env_name
        if not env_name:
            warnings.append("Runner environment credential source was selected, but no env var name was provided.")
        else:
            detail["env_present"] = env_name in os.environ and bool(os.environ.get(env_name))
            if not detail["env_present"]:
                warnings.append(f"Environment variable {env_name} is not set on this runner.")
    elif source == "ssh_agent":
        ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
        detail["ssh_auth_sock_present"] = bool(ssh_auth_sock)
        if not ssh_auth_sock:
            warnings.append("SSH Agent was selected, but SSH_AUTH_SOCK is not set on this runner.")
    elif source in {"github_app", "oauth"}:
        warnings.append(f"{source} credential flow is recorded, but this runner only performs read-only preflight today.")
    elif source == "manual_review":
        warnings.append("Credential source requires manual review; runner will not attempt code sync.")
    else:
        blockers.append(f"Unsupported credential source: {source}")
    return {"ok": not blockers, "warnings": warnings, "blockers": blockers, **detail}


def _credential_ref_env_name(value: str) -> str:
    raw = _bounded_text(value, "").strip()
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1].strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", raw):
        return raw
    return ""


def _normalize_credential_source(value: Any) -> str:
    source = _bounded_text(value, "runner_env").lower()
    return source if source in {"github_app", "oauth", "runner_env", "ssh_agent", "manual_review"} else "runner_env"


def _safe_credential_ref(value: Any) -> str:
    raw = _bounded_text(value, "")
    return "<hidden-secret-like-ref>" if _looks_like_raw_secret(raw) else raw


def _looks_like_raw_secret(value: Any) -> bool:
    raw = _bounded_text(value, "")
    if not raw:
        return False
    return any(pattern.search(raw) for pattern in RAW_GITHUB_SECRET_PATTERNS)


def _bounded_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    if len(text) <= MAX_GIT_FIELD_CHARS:
        return text
    return f"{text[:MAX_GIT_FIELD_CHARS - 20].rstrip()}...<truncated>"


def _truthy(value: Any, fallback: bool) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return fallback
    return normalized not in {"false", "0", "off", "no"}


def _format_completion_note(title: str, result: dict[str, Any]) -> str:
    raw = json.dumps(result, ensure_ascii=False, indent=2)
    note = f"{title}\n\n```json\n{raw}\n```"
    if len(note) <= MAX_COMPLETION_NOTE_CHARS:
        return note
    trimmed = note[: MAX_COMPLETION_NOTE_CHARS - 80].rstrip()
    return f"{trimmed}\n...\n```"
