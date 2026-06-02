from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


FORBIDDEN_TERMS = [
    "adapter",
    "bridge",
    "session JSONL",
    "local path",
    "source_thread",
    "canonical",
    "requested id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate company focus queue archive state with isolated test data in a real browser.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts/company-focus-archive-state")
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str | None = None,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def api_login(api_base: str, email: str, password: str) -> tuple[str, dict[str, object]]:
    payload = request_json(
        f"{api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": email, "password": password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("API login response did not include access_token")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    return str(data["access_token"]), user


def api_data(response: dict[str, object]) -> dict[str, object]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"API response did not include object data: {response}")
    return data


def create_project(api_base: str, token: str) -> dict[str, object]:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return api_data(
        request_json(
            f"{api_base.rstrip('/')}/api/projects",
            method="POST",
            token=token,
            payload={
                "name": f"QA Archive Focus {stamp}",
                "project_type": "software",
                "github_url": "https://github.com/example/qa-archive-focus.git",
                "local_git_url": "",
                "default_branch": "main",
                "develop_branch": "main",
            },
        ),
    )


def create_task(api_base: str, token: str, project_id: str, *, title: str, status: str) -> dict[str, object]:
    return api_data(
        request_json(
            f"{api_base.rstrip('/')}/api/tasks",
            method="POST",
            token=token,
            payload={
                "project_id": project_id,
                "title": title,
                "description": "QA isolated queue item; no dispatch is created.",
                "module": "company-focus-qa",
                "priority": "P2",
                "status": status,
                "branch": "qa/company-focus-archive",
                "assignee_agent_id": "qa-agent",
                "reviewers": ["human"],
                "acceptance_criteria": ["Company focus page shows the correct queue state."],
            },
        ),
    )


def create_requirement(api_base: str, token: str, project_id: str, *, title: str, status: str) -> dict[str, object]:
    return api_data(
        request_json(
            f"{api_base.rstrip('/')}/api/requirements",
            method="POST",
            token=token,
            payload={
                "project_id": project_id,
                "title": title,
                "requirement_type": "thread_request",
                "module": "company-focus-qa",
                "priority": "medium",
                "status": status,
                "from_agent": "qa-requester",
                "to_agent": "qa-reviewer",
                "context_summary": "QA isolated need; no dispatch is created.",
                "expected_output": "Company focus page hides archived needs.",
                "related_files": [],
                "max_response_tokens": 3000,
                "opening_message": "Validate archive focus filtering.",
            },
        ),
    )


def seed_archive_state(api_base: str, token: str, user: dict[str, object]) -> dict[str, object]:
    project = create_project(api_base, token)
    project_id = str(project["id"])
    actor_id = str(user.get("id") or user.get("email") or "qa-human")

    open_task = create_task(api_base, token, project_id, title="QA Open Focus Task", status="ready")
    done_task = create_task(api_base, token, project_id, title="QA Archived Focus Task", status="running")
    done_task_id = str(done_task["id"])
    request_json(
        f"{api_base.rstrip('/')}/api/tasks/{done_task_id}/transition",
        method="POST",
        token=token,
        payload={"status": "done", "actor_type": "human", "actor_id": actor_id, "message": "QA done evidence"},
    )
    archived_task = api_data(
        request_json(
            f"{api_base.rstrip('/')}/api/tasks/{done_task_id}/archive",
            method="POST",
            token=token,
            payload={"actor_type": "human", "actor_id": actor_id, "note": "QA archive current queue only"},
        ),
    )

    open_need = create_requirement(api_base, token, project_id, title="QA Open Focus Need", status="waiting_response")
    closable_need = create_requirement(api_base, token, project_id, title="QA Archived Focus Need", status="waiting_response")
    closable_need_id = str(closable_need["id"])
    request_json(
        f"{api_base.rstrip('/')}/api/requirements/{closable_need_id}/close",
        method="POST",
        token=token,
        payload={"actor_type": "human", "actor_id": actor_id, "note": "QA satisfied evidence"},
    )
    archived_need = api_data(
        request_json(
            f"{api_base.rstrip('/')}/api/requirements/{closable_need_id}/archive",
            method="POST",
            token=token,
            payload={"actor_type": "human", "actor_id": actor_id, "note": "QA archive current queue only"},
        ),
    )
    blocked_archive = None
    try:
        request_json(
            f"{api_base.rstrip('/')}/api/requirements/{open_need['id']}/archive",
            method="POST",
            token=token,
            payload={"actor_type": "human", "actor_id": actor_id, "note": "QA should fail"},
        )
    except Exception as exc:  # noqa: BLE001
        blocked_archive = str(exc)

    if str(archived_task.get("status", "")).lower() != "archived":
        raise RuntimeError(f"Task did not archive: {archived_task}")
    if str(archived_need.get("status", "")).lower() != "archived":
        raise RuntimeError(f"Need did not archive: {archived_need}")
    if not blocked_archive:
        raise RuntimeError("Open need archive unexpectedly succeeded")

    return {
        "project": project,
        "open_task": open_task,
        "archived_task": archived_task,
        "open_need": open_need,
        "archived_need": archived_need,
        "blocked_archive_error": blocked_archive,
    }


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "userGesture": True,
        },
    )
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    value = result.get("result", {})
    return value.get("value") if isinstance(value, dict) else None


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 40, interval_seconds: float = 0.25) -> object:
    deadline = time.time() + timeout_seconds
    last: object = None
    while time.time() < deadline:
        try:
            value = cdp_eval(cdp, expression)
            if value:
                return value
            last = value
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(interval_seconds)
    raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def new_cdp() -> tuple[object, subprocess.Popen[bytes], Path]:
    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-company-archive-cdp-"))
    edge_process = subprocess.Popen(
        [
            str(cdp_helper.find_edge()),
            "--headless=new",
            "--disable-gpu",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
    if not isinstance(targets, list) or not targets:
        cdp_helper.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
    page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
    if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
        raise RuntimeError("No CDP page target available")
    cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
    cdp.sock.settimeout(60)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    return cdp, edge_process, profile_dir


def validate_company_page(
    *,
    cdp: object,
    web_base: str,
    token: str,
    user: dict[str, object],
    project_id: str,
    queue: str,
    output_dir: Path,
) -> dict[str, object]:
    origin = web_base.rstrip("/")
    user_json = json.dumps(user or {}, ensure_ascii=True)
    for name, value in (("farm_access_token", token), ("farm_user", user_json)):
        result = cdp.send(
            "Network.setCookie",
            {"name": name, "value": value, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
        )
        if not result.get("success"):
            raise RuntimeError(f"Failed to set auth cookie {name}")
    query = urlencode({"focus": "skill-forge-index", "queue": queue, "item": "0", "tab": "knowledge"})
    url = f"{origin}/projects/{project_id}/company?{query}"
    cdp.send("Page.navigate", {"url": url})
    wait_for(cdp, "document.body && document.body.innerText.includes('验收详情')", timeout_seconds=45)
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const text = document.body ? document.body.innerText || '' : '';
          const focusText = Array.from(document.querySelectorAll('[aria-label="本次先看条目"] a'))
            .map((item) => item.innerText || item.textContent || '')
            .join('\\n');
          const lower = text.toLowerCase();
          return {{
            url: location.href,
            blank: text.trim().length < 40,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 ||
              document.body.scrollWidth > document.documentElement.clientWidth + 1,
            focusText,
            hasOpenNeed: focusText.includes('QA Open Focus Need'),
            hasArchivedNeed: focusText.includes('QA Archived Focus Need'),
            hasOpenTask: focusText.includes('QA Open Focus Task'),
            hasArchivedTask: focusText.includes('QA Archived Focus Task'),
            hasReadOnlyArchiveHint: text.includes('完成后可归档，当前只查看验收线索'),
            hasArchiveButton: text.includes('归档当前条目'),
            forbiddenHits: {json.dumps(FORBIDDEN_TERMS)}.filter((term) => lower.includes(term.toLowerCase())),
            rawUuidHits: Array.from(text.matchAll(/[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}/ig)).map((match) => match[0]).slice(0, 8),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError("Could not read company page state")
    shot = output_dir / f"company-focus-{queue}.png"
    screenshot(cdp, shot)
    state["screenshot"] = str(shot)
    return state


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    token, user = api_login(args.api_base, args.login_email, args.login_password)
    seeded = seed_archive_state(args.api_base, token, user)
    project_id = str(seeded["project"]["id"])

    cdp = None
    edge_process = None
    profile_dir = None
    try:
        cdp, edge_process, profile_dir = new_cdp()
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False},
        )
        needs = validate_company_page(
            cdp=cdp,
            web_base=args.web_base,
            token=token,
            user=user,
            project_id=project_id,
            queue="needs",
            output_dir=output_dir,
        )
        tasks = validate_company_page(
            cdp=cdp,
            web_base=args.web_base,
            token=token,
            user=user,
            project_id=project_id,
            queue="tasks",
            output_dir=output_dir,
        )
    finally:
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        if edge_process is not None:
            try:
                edge_process.terminate()
                edge_process.wait(timeout=10)
            except Exception:
                edge_process.kill()
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)

    pass_checks = bool(
        needs.get("hasOpenNeed")
        and not needs.get("hasArchivedNeed")
        and needs.get("hasReadOnlyArchiveHint")
        and not needs.get("hasArchiveButton")
        and tasks.get("hasOpenTask")
        and not tasks.get("hasArchivedTask")
        and tasks.get("hasReadOnlyArchiveHint")
        and not tasks.get("hasArchiveButton")
        and not needs.get("blank")
        and not tasks.get("blank")
        and not needs.get("hasHorizontalOverflow")
        and not tasks.get("hasHorizontalOverflow")
        and not needs.get("forbiddenHits")
        and not tasks.get("forbiddenHits")
        and not needs.get("rawUuidHits")
        and not tasks.get("rawUuidHits")
    )
    report = {
        "ok": pass_checks,
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "web_base": args.web_base,
        "api_base": args.api_base,
        "project_id": project_id,
        "seeded": seeded,
        "needs": needs,
        "tasks": tasks,
    }
    report_path = output_dir / "company-focus-archive-state-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": pass_checks,
                "project_id": project_id,
                "report": str(report_path),
                "screenshots": {
                    "needs": needs.get("screenshot"),
                    "tasks": tasks.get("screenshot"),
                },
            },
            ensure_ascii=False,
        ),
    )
    return 0 if pass_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
