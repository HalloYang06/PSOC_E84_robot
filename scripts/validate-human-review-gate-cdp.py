from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CDP_HELPER_PATH = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"

spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helper: {CDP_HELPER_PATH}")
cdp_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helper)


CN_REVIEW_TITLE_PREFIX = "\u4eba\u5de5\u5ba1\u6838\uff1a"
CN_ORIGINAL_TITLE = "\u539f\u59cb\u6807\u9898"
CN_ORIGINAL_TARGET = "\u539f\u59cb\u76ee\u6807"
CN_TARGET_TYPE = "\u76ee\u6807\u7c7b\u578b"
CN_TARGET_AI = "\u76ee\u6807 AI"
CN_PROJECT_PROFILE = "\u9879\u76ee\u89c6\u89d2"
CN_RISK_LEVEL = "\u98ce\u9669\u7b49\u7ea7"
CN_ESTIMATED_TOKENS = "\u9884\u8ba1 token"
CN_EXECUTION_BOUNDARY = "\u6267\u884c\u8fb9\u754c"
CN_READONLY_PROBE = "\u53ea\u8bfb\u63a2\u9488"
CN_SIMULATION_FIRST = "\u4eff\u771f\u4f18\u5148"
CN_GOVERNANCE_NOTE = "\u6cbb\u7406\u63d0\u9192"
CN_ORIGINAL_INSTRUCTION = "\u539f\u59cb\u6307\u4ee4"
CN_REVIEW_SUGGESTION = "\u4eba\u5de5\u5ba1\u6838\u52a8\u4f5c\u5efa\u8bae"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the human-review collaboration gate through the real browser.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--sqlite-db", default=str(REPO_ROOT / "apps" / "api" / "ai_collab.db"))
    parser.add_argument(
        "--decision",
        choices=["reject", "readonly_probe", "simulation", "formal_execute"],
        default="reject",
        help="Which human-review decision button to validate.",
    )
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1000)
    parser.add_argument(
        "--temporary-github-url",
        default="",
        help="Temporarily bind this GitHub repository before approval, then restore the project.",
    )
    parser.add_argument(
        "--temporary-github-account",
        default="",
        help="Temporarily bind this GitHub account before approval, then restore the project.",
    )
    return parser.parse_args()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {body[:1200]}") from exc


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


def read_project(api_base: str, project_id: str, token: str) -> dict[str, object]:
    payload = request_json(f"{api_base.rstrip('/')}/api/projects/{quote(project_id)}", token=token)
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and isinstance(data.get("project"), dict):
        return data["project"]  # type: ignore[return-value]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Project response did not include a project object: {payload}")


def collaboration_config(project: dict[str, object]) -> dict[str, object]:
    value = project.get("collaboration_config")
    return dict(value) if isinstance(value, dict) else {}


def patch_project(api_base: str, project_id: str, token: str, payload: dict[str, object]) -> None:
    request_json(
        f"{api_base.rstrip('/')}/api/projects/{quote(project_id)}",
        method="PATCH",
        token=token,
        payload=payload,
    )


def restore_project(api_base: str, project_id: str, token: str, original_project: dict[str, object]) -> None:
    patch_project(
        api_base,
        project_id,
        token,
        {
            "github_url": original_project.get("github_url"),
            "local_git_url": original_project.get("local_git_url"),
            "default_branch": original_project.get("default_branch") or original_project.get("defaultBranch") or "main",
            "develop_branch": original_project.get("develop_branch") or original_project.get("developBranch") or "develop",
            "collaboration_config": collaboration_config(original_project),
        },
    )


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 45, interval_seconds: float = 0.25) -> object:
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
    raise RuntimeError(f"Timed out waiting for expression: {expression[:240]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            break
        except TimeoutError as exc:
            last_error = exc
            time.sleep(1.5 + attempt)
    else:
        raise RuntimeError(f"CDP screenshot timed out after retries: {last_error}") from last_error
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def click_selector(cdp: object, selector: str) -> None:
    point = wait_for(
        cdp,
        f"""
        (() => {{
          const el = document.querySelector({json.dumps(selector)});
          if (!el || el.disabled) return null;
          el.scrollIntoView({{ block: 'center', inline: 'center' }});
          const rect = el.getBoundingClientRect();
          return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
        }})()
        """,
    )
    if not isinstance(point, dict):
        raise RuntimeError(f"Could not click selector: {selector}")
    x = float(point["x"])
    y = float(point["y"])
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def cleanup_messages(sqlite_db: Path, message_ids: list[str]) -> int:
    ids = [message_id for message_id in dict.fromkeys(message_ids) if message_id]
    if not sqlite_db.exists() or not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with sqlite3.connect(sqlite_db) as conn:
        cursor = conn.cursor()
        deleted = 0
        for table in ("audit_logs", "collaboration_messages"):
            try:
                if table == "audit_logs":
                    cursor.execute(f"DELETE FROM {table} WHERE resource_id IN ({placeholders})", ids)
                else:
                    cursor.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", ids)
                deleted += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            except sqlite3.DatabaseError:
                continue
        conn.commit()
    return deleted


def decision_expectation(decision: str) -> dict[str, str | bool]:
    if decision == "readonly_probe":
        return {
            "status": "approved_readonly",
            "button": "readonly_probe",
            "prefix": "\u53ea\u8bfb\u63a2\u9488\uff1a",
            "creates_command": True,
        }
    if decision == "simulation":
        return {
            "status": "approved_simulation",
            "button": "simulation",
            "prefix": "\u4eff\u771f\u9a8c\u8bc1\uff1a",
            "creates_command": True,
        }
    if decision == "formal_execute":
        return {
            "status": "approved_formal",
            "button": "formal_execute",
            "prefix": "\u4eba\u5de5\u901a\u8fc7\uff1a",
            "creates_command": True,
        }
    return {
        "status": "rejected",
        "button": "reject",
        "prefix": "",
        "creates_command": False,
    }


def build_review_body(original_title: str, target_id: str) -> str:
    review_meta = {
        "schema": "ai_collab_human_review_v1",
        "original_title": original_title,
        "original_target": target_id,
        "target_type": "workstation",
        "target_ai": "CDP validation target",
        "provider": "Codex",
        "risk_level": "high",
        "estimated_tokens": 256,
        "execution_boundary": "human review required",
        "readonly_first": True,
        "simulation_first": True,
        "original_instruction": "Validate the serial flashing rollback plan, but do not touch real hardware.",
    }
    return "\n".join(
        [
            "This validation request is injected by CDP and must not be dispatched before a human decision.",
            "AI_REVIEW_META_JSON:",
            json.dumps(review_meta, ensure_ascii=False, separators=(",", ":")),
            "AI_REVIEW_META_JSON_END",
            "",
            f"{CN_ORIGINAL_TITLE}: {original_title}",
            f"{CN_ORIGINAL_TARGET}: {target_id}",
            f"{CN_TARGET_TYPE}: workstation",
            f"{CN_TARGET_AI}: CDP validation target",
            "Provider: Codex",
            f"{CN_PROJECT_PROFILE}: embedded / hardware",
            f"{CN_RISK_LEVEL}: high",
            f"{CN_ESTIMATED_TOKENS}: 256",
            f"{CN_EXECUTION_BOUNDARY}: human review required",
            f"{CN_READONLY_PROBE}: \u662f",
            f"{CN_SIMULATION_FIRST}: \u662f",
            "",
            f"{CN_GOVERNANCE_NOTE}:",
            "1. This is a high-risk command and should be narrowed before execution.",
            "",
            f"{CN_ORIGINAL_INSTRUCTION}:",
            "Validate the serial flashing rollback plan, but do not touch real hardware.",
            "",
            f"{CN_REVIEW_SUGGESTION}:",
            "1. If this is only research, approve as readonly probe.",
            "2. If hardware is involved, approve simulation first or reject.",
            "3. Do not let the target NPC continue autonomously before review.",
        ]
    )


def first_workstation_id(api_base: str, project_id: str, token: str) -> str:
    workstations_payload = request_json(
        f"{api_base}/api/collaboration/projects/{quote(project_id)}/thread-workstations",
        token=token,
    )
    workstations = workstations_payload.get("data") if isinstance(workstations_payload, dict) else []
    if not isinstance(workstations, list) or not workstations:
        raise RuntimeError("Project has no workstation target for the human-review validation")
    target = next((item for item in workstations if isinstance(item, dict)), None)
    if not isinstance(target, dict):
        raise RuntimeError("No valid workstation target found")
    target_id = str(target.get("id") or target.get("workstation_id") or target.get("config_id") or "").strip()
    if not target_id:
        raise RuntimeError("Workstation target has no id")
    return target_id


def fetch_matching_decisions(api_base: str, project_id: str, token: str, review_id: str, review_title: str) -> list[str]:
    decision_payload = request_json(
        f"{api_base}/api/collaboration/messages?project_id={quote(project_id)}&message_type=human_review_decision&limit=200",
        token=token,
    )
    decision_items = decision_payload.get("data") if isinstance(decision_payload, dict) else []
    decision_ids: list[str] = []
    for item in decision_items if isinstance(decision_items, list) else []:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "")
        title = str(item.get("title") or "")
        if review_id in body or review_title in title:
            decision_ids.append(str(item.get("id")))
    return decision_ids


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    api_base = args.api_base.rstrip("/")
    web_base = args.web_base.rstrip("/")
    token, user = api_login(api_base, args.login_email, args.login_password)
    original_project: dict[str, object] | None = None
    if args.temporary_github_url or args.temporary_github_account:
        original_project = read_project(api_base, args.project_id, token)
        config = collaboration_config(original_project)
        if args.temporary_github_account:
            config["github_account_binding"] = {
                "account_login": args.temporary_github_account,
                "account_type": "bot",
                "profile_url": f"https://github.com/{args.temporary_github_account}",
                "credential_source": "runner_env",
                "credential_ref": "GITHUB_TOKEN_TEST_ONLY",
                "default_clone_protocol": "https",
                "permission_scopes": ["repo", "workflow"],
                "secret_storage": "not_stored_in_project_config",
                "updated_at": datetime.now().astimezone().isoformat(),
            }
        patch_project(
            api_base,
            args.project_id,
            token,
            {
                "github_url": args.temporary_github_url or original_project.get("github_url"),
                "local_git_url": original_project.get("local_git_url"),
                "default_branch": original_project.get("default_branch") or original_project.get("defaultBranch") or "main",
                "develop_branch": "develop",
                "collaboration_config": config,
            },
        )
    target_id = first_workstation_id(api_base, args.project_id, token)

    expectation = decision_expectation(args.decision)
    review_title = f"{CN_REVIEW_TITLE_PREFIX}CDP human-review gate {args.decision} {stamp}"
    original_title = f"CDP human-review gate {args.decision} {stamp}"
    review_payload = request_json(
        f"{api_base}/api/collaboration/messages",
        method="POST",
        token=token,
        payload={
            "project_id": args.project_id,
            "message_type": "human_review_request",
            "title": review_title,
            "body": build_review_body(original_title, target_id),
            "recipient_type": "project",
            "recipient_id": args.project_id,
            "status": "pending_human_review",
        },
    )
    review = review_payload.get("data") if isinstance(review_payload, dict) else None
    if not isinstance(review, dict) or not review.get("id"):
        raise RuntimeError("Could not create validation human-review request")
    review_id = str(review["id"])

    cleanup_ids = [review_id]
    cleanup_done = False
    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-human-review-edge-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    screenshots: list[str] = []
    decision_ids: list[str] = []
    command_ids: list[str] = []
    try:
        edge_process = subprocess.Popen(
            [
                str(cdp_helper.find_edge()),
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helper.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helper.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next(
            (item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")),
            None,
        )
        if not isinstance(page_target, dict):
            raise RuntimeError("No Edge page target available")
        cdp = cdp_helper.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.sock.settimeout(90)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": args.viewport_width, "height": args.viewport_height, "deviceScaleFactor": 1, "mobile": False},
        )
        origin = web_base
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        cdp.send(
            "Network.setCookie",
            {
                "name": "farm_user",
                "value": json.dumps(user, ensure_ascii=True),
                "url": f"{origin}/",
                "path": "/",
                "sameSite": "Lax",
            },
        )
        url = f"{web_base}/projects/{quote(args.project_id)}?panel=team&tab=exchange"
        cdp.send("Page.navigate", {"url": url})
        button_value = str(expectation["button"])
        wait_for(cdp, f"!!document.querySelector('[data-human-review-message=\"{review_id}\"] button[value=\"{button_value}\"]')")
        first_shot = output_dir / f"human-review-gate-01-pending-{args.decision}-{stamp}.png"
        screenshot(cdp, first_shot)
        screenshots.append(str(first_shot))

        click_selector(cdp, f'[data-human-review-message="{review_id}"] button[value="{button_value}"]')
        wait_for(cdp, f"!document.querySelector('[data-human-review-message=\"{review_id}\"]')", timeout_seconds=60)
        second_shot = output_dir / f"human-review-gate-02-processed-{args.decision}-{stamp}.png"
        screenshot(cdp, second_shot)
        screenshots.append(str(second_shot))
        visible_text_after_decision = str(
            cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "",
        )
        if "AI_REQUIRED_REQUIREMENT_LEDGER_V1" in visible_text_after_decision:
            raise RuntimeError("Required ledger protocol leaked into the visible collaboration UI")
        if "AI_REVIEW_META_JSON" in visible_text_after_decision:
            raise RuntimeError("Human-review machine metadata leaked into the visible collaboration UI")

        review_after_payload = request_json(
            f"{api_base}/api/collaboration/messages?project_id={quote(args.project_id)}&message_type=human_review_request&limit=200",
            token=token,
        )
        review_after_items = review_after_payload.get("data") if isinstance(review_after_payload, dict) else []
        review_after = next((item for item in review_after_items if isinstance(item, dict) and str(item.get("id")) == review_id), None)
        if not isinstance(review_after, dict) or review_after.get("status") != expectation["status"]:
            raise RuntimeError(f"Human-review request did not reach expected status {expectation['status']}: {review_after}")

        command_payload = request_json(
            f"{api_base}/api/collaboration/messages?project_id={quote(args.project_id)}&message_type=agent_command&limit=200",
            token=token,
        )
        command_items = command_payload.get("data") if isinstance(command_payload, dict) else []
        matching_commands = [
            item
            for item in command_items
            if isinstance(item, dict)
            and original_title in str(item.get("title") or "")
            and str(item.get("recipient_id") or "") == target_id
        ] if isinstance(command_items, list) else []
        if expectation["creates_command"]:
            if not matching_commands:
                raise RuntimeError(f"Expected a narrowed agent_command after {args.decision}, but none was created")
            expected_prefix = str(expectation["prefix"])
            for command in matching_commands:
                command_ids.append(str(command.get("id")))
                title = str(command.get("title") or "")
                body = str(command.get("body") or "")
                if expected_prefix and not title.startswith(expected_prefix):
                    raise RuntimeError(f"Command title did not use expected prefix {expected_prefix!r}: {title!r}")
                if "AI_REQUIRED_REQUIREMENT_LEDGER_V1" not in body:
                    raise RuntimeError(f"Approved command did not include the required AI requirement ledger block: {command.get('id')}")
                if "docs/ai-requirements/ai-required-requirements-ledger.md" not in body:
                    raise RuntimeError(f"Approved command did not include the required ledger path: {command.get('id')}")
                for required_fragment in ("代码协作:", "GitHub 身份:", "GitHub 凭据:", "本地路径规则:", "Git 人审边界:"):
                    if required_fragment not in body:
                        raise RuntimeError(f"Approved command missed GitHub collaboration fragment {required_fragment!r}: {command.get('id')}")
                if args.temporary_github_url and args.temporary_github_url not in body:
                    raise RuntimeError(f"Approved command did not include temporary GitHub repository: {command.get('id')}")
                if args.temporary_github_account and args.temporary_github_account not in body:
                    raise RuntimeError(f"Approved command did not include temporary GitHub account: {command.get('id')}")
                if "ghp_" in body or "github_pat_" in body:
                    raise RuntimeError(f"Approved command leaked a raw-looking GitHub token: {command.get('id')}")
            cleanup_ids.extend(command_ids)
            inbox_payload = request_json(
                f"{api_base}/api/collaboration/projects/{quote(args.project_id)}/thread-workstations/{quote(target_id)}/inbox",
                extra_headers={"X-Workstation-Id": target_id},
            )
            inbox_items = inbox_payload.get("data") if isinstance(inbox_payload, dict) else []
            inbox_ids = {str(item.get("id")) for item in inbox_items if isinstance(item, dict)}
            missing_from_inbox = [command_id for command_id in command_ids if command_id not in inbox_ids]
            if missing_from_inbox:
                raise RuntimeError(f"Approved commands were not visible in workstation inbox: {missing_from_inbox}")
        elif matching_commands:
            command_ids.extend(str(command.get("id")) for command in matching_commands if isinstance(command, dict))
            cleanup_ids.extend(command_ids)
            raise RuntimeError(f"Reject decision unexpectedly created agent_command: {command_ids}")

        decision_ids = fetch_matching_decisions(api_base, args.project_id, token, review_id, review_title)
        cleanup_ids.extend(decision_ids)
        deleted_rows = cleanup_messages(Path(args.sqlite_db), cleanup_ids)
        cleanup_done = True
        report = {
            "validated_at": datetime.now().astimezone().isoformat(),
            "project_id": args.project_id,
            "decision": args.decision,
            "temporary_github_url": args.temporary_github_url or None,
            "temporary_github_account": args.temporary_github_account or None,
            "asserted_git_fragments": [
                "代码协作:",
                "GitHub 身份:",
                "GitHub 凭据:",
                "本地路径规则:",
                "Git 人审边界:",
            ],
            "review_id": review_id,
            "decision_ids": decision_ids,
            "command_ids": command_ids,
            "cleanup_ids": list(dict.fromkeys(cleanup_ids)),
            "deleted_rows": deleted_rows,
            "screenshots": screenshots,
        }
        report_path = output_dir / f"human-review-gate-report-{args.decision}-{stamp}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        if not cleanup_done:
            cleanup_messages(Path(args.sqlite_db), cleanup_ids)
        if original_project is not None:
            restore_project(api_base, args.project_id, token, original_project)
        if cdp is not None:
            cdp.close()
        if edge_process is not None and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
