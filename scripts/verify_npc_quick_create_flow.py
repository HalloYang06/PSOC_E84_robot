from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests


DEFAULT_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
DEFAULT_PROVIDER = "claude"
DEFAULT_EMAIL = "codex-platform-npc@local.dev"
DEFAULT_PASSWORD = "password"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify NPC quick-create flow with cleanup.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["claude", "codex"])
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--login-email", default=DEFAULT_EMAIL)
    parser.add_argument("--login-password", default=DEFAULT_PASSWORD)
    parser.add_argument("--keep-seat", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def artifacts_dir() -> Path:
    directory = repo_root() / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def auth_session(api_base: str, email: str, password: str) -> tuple[requests.Session, dict[str, Any]]:
    session = requests.Session()
    response = session.post(
        f"{api_base}/api/auth/session",
        json={"email": email, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()["data"]
    session.cookies.set("farm_access_token", str(payload["access_token"]), path="/")
    return session, payload


def get_html(session: requests.Session, url: str) -> str:
    response = session.get(url, headers={"Accept": "text/html"}, timeout=30)
    response.raise_for_status()
    return response.text


def get_public_html(url: str) -> str:
    response = requests.get(url, headers={"Accept": "text/html"}, timeout=30)
    response.raise_for_status()
    return response.text


def extract_quick_create_form(html_text: str, provider_id: str) -> dict[str, str]:
    forms = re.findall(r"<form\b.*?</form>", html_text, re.S | re.I)
    for form in forms:
        if f'name="ai_provider_id" value="{provider_id}"' not in form:
            continue
        if 'name="source_workstation_id"' not in form:
            continue
        inputs: dict[str, str] = {}
        for name, value in re.findall(r'<input[^>]*name="([^"]+)"(?:[^>]*value="([^"]*)")?[^>]*>', form, re.I):
            inputs[name] = html.unescape(value or "")
        if not any(key.startswith("$ACTION_REF_") for key in inputs):
            continue
        return inputs
    raise RuntimeError(f"Could not find provider={provider_id} quick-create form")


def resolve_quick_create_form(session: requests.Session, url: str, provider_id: str) -> tuple[str, dict[str, str], str]:
    auth_html = get_html(session, url)
    try:
        return auth_html, extract_quick_create_form(auth_html, provider_id), "auth-html"
    except RuntimeError:
        public_html = get_public_html(url)
        return auth_html, extract_quick_create_form(public_html, provider_id), "public-html-fallback"


def extract_delete_form(html_text: str, seat_name: str) -> dict[str, str]:
    forms = re.findall(r"<form\b.*?</form>", html_text, re.S | re.I)
    for form in forms:
        if seat_name not in form:
            continue
        if "删除 NPC 席位" not in form:
            continue
        inputs: dict[str, str] = {}
        for name, value in re.findall(r'<input[^>]*name="([^"]+)"(?:[^>]*value="([^"]*)")?[^>]*>', form, re.I):
            inputs[name] = html.unescape(value or "")
        if any(key.startswith("$ACTION_REF_") for key in inputs):
            return inputs
    raise RuntimeError("Could not find delete NPC form for created seat")


def build_multipart_fields(fields: dict[str, str]) -> list[tuple[str, tuple[None, str]]]:
    return [(key, (None, value)) for key, value in fields.items()]


def fetch_workstations(
    session: requests.Session,
    api_base: str,
    project_id: str,
    access_token: str,
) -> list[dict[str, Any]]:
    response = session.get(
        f"{api_base}/api/collaboration/projects/{project_id}/thread-workstations",
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", payload)
    return data if isinstance(data, list) else []


def delete_workstation(
    session: requests.Session,
    api_base: str,
    project_id: str,
    access_token: str,
    workstation_id: str,
) -> bool:
    response = session.delete(
        f"{api_base}/api/collaboration/projects/{project_id}/thread-workstations/{workstation_id}",
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    return response.ok


def workstation_lookup_keys(item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    extra_data = item.get("extra_data") if isinstance(item.get("extra_data"), dict) else {}
    candidates = [
        item.get("id"),
        item.get("workstation_id"),
        item.get("config_id"),
        item.get("row_id"),
        item.get("source_workstation_id"),
        metadata.get("source_workstation_id"),
        extra_data.get("source_workstation_id"),
    ]
    return [str(candidate).strip() for candidate in candidates if str(candidate or "").strip()]


def cleanup_claude_registry(repo: Path, seat_name: str, source_workstation_id: str | None) -> bool:
    registry = repo / "artifacts" / "claude-seat-registry.json"
    if not registry.exists():
        return False
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except Exception:
        return False
    seats = payload.get("seats", [])
    if not isinstance(seats, list):
        return False
    session_id = None
    if source_workstation_id and source_workstation_id.startswith("claude-session-"):
        session_id = source_workstation_id[len("claude-session-") :]
    next_seats = []
    removed = False
    for item in seats:
        if not isinstance(item, dict):
            next_seats.append(item)
            continue
        same_seat = str(item.get("seat_name") or "").strip() == seat_name
        same_session = bool(session_id) and str(item.get("session_id") or "").strip() == session_id
        if same_seat or same_session:
            removed = True
            continue
        next_seats.append(item)
    if not removed:
        return False
    payload["updated_at"] = datetime.now().astimezone().isoformat()
    payload["seats"] = next_seats
    registry.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def normalize_codex_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "codex-seat"


def cleanup_codex_artifacts(repo: Path, seat_name: str) -> bool:
    slug = normalize_codex_slug(seat_name)
    consumer_name = f"{slug}-thread-consumer.py" if re.fullmatch(r"npc\\d+", slug) else f"codex-seat-{slug}-thread-consumer.py"
    script_path = repo / "scripts" / consumer_name
    state_path = repo / "scripts" / f".{consumer_name[:-3]}-state.json"
    automation_dir = Path.home() / ".codex" / "automations" / f"{slug}-coop-loop"
    removed = False
    for target in (script_path, state_path):
        if target.exists():
            target.unlink()
            removed = True
    if automation_dir.exists():
        for child in sorted(automation_dir.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        automation_dir.rmdir()
        removed = True
    return removed


def cleanup_handoff_doc(repo: Path, handoff_path: str | None) -> bool:
    if not handoff_path:
        return False
    target = repo / handoff_path.replace("/", "\\")
    if not target.exists():
        return False
    target.unlink()
    return True


def claude_registry_contains(repo: Path, seat_name: str, source_workstation_id: str | None) -> bool:
    registry = repo / "artifacts" / "claude-seat-registry.json"
    if not registry.exists():
        return False
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except Exception:
        return False
    seats = payload.get("seats", [])
    if not isinstance(seats, list):
        return False
    session_id = None
    if source_workstation_id and source_workstation_id.startswith("claude-session-"):
        session_id = source_workstation_id[len("claude-session-") :]
    for item in seats:
        if not isinstance(item, dict):
            continue
        if str(item.get("seat_name") or "").strip() == seat_name:
            return True
        if session_id and str(item.get("session_id") or "").strip() == session_id:
            return True
    return False


def codex_artifacts_exist(repo: Path, seat_name: str) -> bool:
    slug = normalize_codex_slug(seat_name)
    consumer_name = f"{slug}-thread-consumer.py" if re.fullmatch(r"npc\\d+", slug) else f"codex-seat-{slug}-thread-consumer.py"
    script_path = repo / "scripts" / consumer_name
    state_path = repo / "scripts" / f".{consumer_name[:-3]}-state.json"
    automation_dir = Path.home() / ".codex" / "automations" / f"{slug}-coop-loop"
    return script_path.exists() or state_path.exists() or automation_dir.exists()


def run_capture(
    web_url: str,
    access_token: str,
    user_payload: dict[str, Any],
    output_png: Path,
    output_html: Path,
    focus_text: str,
) -> None:
    command = [
        "node",
        str(repo_root() / "scripts" / "capture-auth-screenshot.mjs"),
        "--url",
        web_url,
        "--token",
        access_token,
        "--userjson",
        json.dumps(user_payload, ensure_ascii=True),
        "--output",
        str(output_png),
        "--html-dump",
        str(output_html),
        "--focus-text",
        focus_text,
        "--wait-ms",
        "2200",
        "--viewport-width",
        "1600",
        "--viewport-height",
        "1200",
    ]
    subprocess.run(command, cwd=str(repo_root()), check=True, timeout=120)


def safe_write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def main() -> None:
    args = parse_args()
    repo = repo_root()
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    temp_name = f"Temp {args.provider.title()} NPC {stamp}"
    project_path = f"/projects/{args.project_id}?panel=team&tab=npc-create"
    bound_return_path = f"{project_path}&npc_view=bound"
    project_url = f"{args.web_base}{project_path}"

    session, auth_payload = auth_session(args.api_base, args.login_email, args.login_password)
    html_text, form_fields, form_source = resolve_quick_create_form(session, project_url, args.provider)
    source_workstation_id = form_fields.get("source_workstation_id")
    form_fields["name"] = temp_name
    form_fields["return_to"] = bound_return_path

    final_url = ""
    final_html = ""
    created_seat_id = ""
    notice = ""
    handoff_path = None
    access_token = str(auth_payload["access_token"])
    screenshot_png = artifacts_dir() / f"npc-quick-create-{args.provider}-{stamp}.png"
    screenshot_html = artifacts_dir() / f"npc-quick-create-{args.provider}-{stamp}.html"
    capture_mode = "not-run"
    capture_error = ""
    delete_mode = "keep-seat"
    delete_notice = ""
    registry_cleaned = False
    codex_artifacts_cleaned = False
    handoff_doc_cleaned = False

    try:
        create_response = session.post(
            project_url,
            files=build_multipart_fields(form_fields),
            allow_redirects=False,
            timeout=60,
        )
        if create_response.status_code not in {302, 303}:
            raise RuntimeError(
                f"Create NPC returned unexpected status: {create_response.status_code} {create_response.text[:240]}"
            )

        location = create_response.headers.get("Location", "")
        if not location:
            raise RuntimeError("Create NPC did not return a redirect location")
        if "team_error=" in location:
            raise RuntimeError(f"Create NPC redirected to error path: {location}")
        if "team_notice=" not in location:
            raise RuntimeError(f"Create NPC redirect did not include success notice: {location}")

        final_url = urljoin(args.web_base, location)
        parsed_location = urlparse(location)
        location_query = parse_qs(parsed_location.query)
        created_seat_id = (location_query.get("seat") or [""])[0]
        notice = html.unescape((location_query.get("team_notice") or [""])[0])

        final_html = get_html(session, final_url)
        if temp_name not in final_html:
            raise RuntimeError("Created NPC name was not present on the redirected page")

        workstations = fetch_workstations(session, args.api_base, args.project_id, access_token)
        created_seat = next(
            (
                item
                for item in workstations
                if str(item.get("name") or item.get("workstation_name") or "").strip() == temp_name
                or created_seat_id in workstation_lookup_keys(item)
            ),
            None,
        )
        if not created_seat:
            raise RuntimeError("Created NPC was not present in the collaboration API")

        created_seat_id = str(
            created_seat.get("id")
            or created_seat.get("config_id")
            or created_seat.get("row_id")
            or created_seat_id
        ).strip()
        created_metadata = created_seat.get("metadata") if isinstance(created_seat.get("metadata"), dict) else {}
        created_knowledge = created_metadata.get("npc_knowledge") if isinstance(created_metadata.get("npc_knowledge"), dict) else {}
        handoff_path = str(created_knowledge.get("handoff_path") or "").strip() or None

        try:
            run_capture(
                web_url=final_url,
                access_token=access_token,
                user_payload=auth_payload["user"],
                output_png=screenshot_png,
                output_html=screenshot_html,
                focus_text=temp_name,
            )
            capture_mode = "screenshot"
        except subprocess.CalledProcessError as error:
            capture_mode = "html-fallback"
            capture_error = str(error)
            safe_write_text(screenshot_html, final_html)
        except Exception as error:  # noqa: BLE001
            capture_mode = "html-fallback"
            capture_error = str(error)
            safe_write_text(screenshot_html, final_html)
    finally:
        if not args.keep_seat and final_url and final_html:
            try:
                delete_form = extract_delete_form(final_html, temp_name)
                delete_response = session.post(
                    final_url,
                    files=build_multipart_fields(delete_form),
                    allow_redirects=False,
                    timeout=60,
                )
                if delete_response.status_code not in {302, 303}:
                    raise RuntimeError(
                        f"Delete NPC returned unexpected status: {delete_response.status_code} {delete_response.text[:240]}"
                    )
                delete_location = delete_response.headers.get("Location", "")
                if not delete_location:
                    raise RuntimeError("Delete NPC did not return a redirect location")
                if "team_error=" in delete_location:
                    raise RuntimeError(f"Delete NPC redirected to error path: {delete_location}")
                delete_query = parse_qs(urlparse(delete_location).query)
                delete_notice = html.unescape((delete_query.get("team_notice") or [""])[0])
                delete_mode = "ui-form-delete"
            except Exception:  # noqa: BLE001
                delete_mode = "cleanup-fallback"

        if not args.keep_seat:
            if created_seat_id:
                deleted_via_api = delete_workstation(
                    session,
                    args.api_base,
                    args.project_id,
                    access_token,
                    created_seat_id,
                )
                if deleted_via_api:
                    delete_mode = f"{delete_mode}+api-delete" if delete_mode else "api-delete"
            registry_cleaned = not claude_registry_contains(repo, temp_name, source_workstation_id)
            codex_artifacts_cleaned = not codex_artifacts_exist(repo, temp_name)
            handoff_doc_cleaned = not handoff_path or not (repo / handoff_path.replace("/", "\\")).exists()

            if args.provider == "claude" and not registry_cleaned:
                registry_cleaned = cleanup_claude_registry(repo, temp_name, source_workstation_id)
                delete_mode = f"{delete_mode}+registry-fallback" if delete_mode else "registry-fallback"
            if args.provider == "codex" and not codex_artifacts_cleaned:
                codex_artifacts_cleaned = cleanup_codex_artifacts(repo, temp_name)
                delete_mode = f"{delete_mode}+bridge-fallback" if delete_mode else "bridge-fallback"
            if not handoff_doc_cleaned:
                handoff_doc_cleaned = cleanup_handoff_doc(repo, handoff_path)
                delete_mode = f"{delete_mode}+handoff-fallback" if delete_mode else "handoff-fallback"

    remaining_workstations = fetch_workstations(session, args.api_base, args.project_id, access_token)
    remaining = [
        item
        for item in remaining_workstations
        if created_seat_id and created_seat_id in workstation_lookup_keys(item)
        or str(item.get("name") or item.get("workstation_name") or "").strip() == temp_name
    ]
    if not args.keep_seat and remaining:
        raise RuntimeError("Temporary NPC still exists after cleanup")

    summary = {
        "project_id": args.project_id,
        "provider": args.provider,
        "temp_name": temp_name,
        "source_workstation_id": source_workstation_id,
        "created_seat_id": created_seat_id,
        "team_notice": notice,
        "final_url": final_url,
        "form_source": form_source,
        "capture_mode": capture_mode,
        "capture_error": capture_error,
        "screenshot_png": str(screenshot_png),
        "screenshot_html": str(screenshot_html),
        "delete_mode": delete_mode,
        "delete_notice": delete_notice,
        "registry_cleaned": registry_cleaned,
        "codex_artifacts_cleaned": codex_artifacts_cleaned,
        "handoff_doc_cleaned": handoff_doc_cleaned,
    }
    summary_path = artifacts_dir() / f"npc-quick-create-{args.provider}-{stamp}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
