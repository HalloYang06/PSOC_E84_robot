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
from urllib.parse import quote, urlencode
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


FIXTURE_ROOT = "docs/qa/npc-deposit-idempotency"
FIXTURE_PATHS = {
    "knowledge": f"{FIXTURE_ROOT}/knowledge/qa-knowledge.md",
    "skill": f"{FIXTURE_ROOT}/skills/qa-skill/SKILL.md",
    "need": f"{FIXTURE_ROOT}/needs/qa-need.md",
    "task": f"{FIXTURE_ROOT}/tasks/qa-task-receipt.md",
}
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
        description="Validate Skill Forge NPC deposit indexing idempotency through the real cloud page.",
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--output-dir", default="artifacts/skill-forge-index-idempotency")
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


def api_data(response: dict[str, object]) -> object:
    return response.get("data")


def object_data(response: dict[str, object]) -> dict[str, object]:
    data = api_data(response)
    if not isinstance(data, dict):
        raise RuntimeError(f"API response did not include object data: {response}")
    return data


def as_list(response: dict[str, object]) -> list[dict[str, object]]:
    data = api_data(response)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]  # type: ignore[unreachable]
    return []


def text(value: object, fallback: str = "") -> str:
    next_value = str(value or "").strip()
    return next_value or fallback


def create_project(api_base: str, token: str) -> dict[str, object]:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return object_data(
        request_json(
            f"{api_base.rstrip('/')}/api/projects",
            method="POST",
            token=token,
            payload={
                "name": f"QA Skill Forge Idempotency {stamp}",
                "project_type": "software",
                "github_url": "https://github.com/wenjunyong666/ai-.git",
                "local_git_url": "",
                "default_branch": "ai/game-loop-core",
                "develop_branch": "ai/game-loop-core",
            },
        ),
    )


def create_qa_seat(api_base: str, token: str, project_id: str) -> dict[str, object]:
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    seat_id = f"qa-skill-forge-idem-{stamp}"
    return object_data(
        request_json(
            f"{api_base.rstrip('/')}/api/collaboration/projects/{quote(project_id)}/thread-workstations",
            method="POST",
            token=token,
            payload={
                "id": seat_id,
                "name": f"QA 幂等 NPC {stamp}",
                "agent_id": seat_id,
                "ai_provider_id": "codex",
                "responsibility": "验证能力工坊索引幂等性",
                "permission_level": "qa-readonly",
                "status": "idle",
                "metadata": {
                    "seat_type": "codex",
                    "source": "qa_skill_forge_idempotency",
                    "npc_identity_key": seat_id,
                    "responsibility": "验证能力工坊索引幂等性",
                    "npc_knowledge": {
                        "slug": "qa-npc-deposit-idempotency",
                        "summary": "QA fixture for idempotent NPC deposit indexing.",
                        "knowledge_deposit_path": f"{FIXTURE_ROOT}/knowledge/",
                        "skill_deposit_path": f"{FIXTURE_ROOT}/skills/",
                        "need_deposit_path": f"{FIXTURE_ROOT}/needs/",
                        "task_deposit_path": f"{FIXTURE_ROOT}/tasks/",
                        "tags": ["qa", "skill-forge", "idempotency"],
                    },
                },
            },
        ),
    )


def list_project_items(api_base: str, token: str, project_id: str) -> dict[str, list[dict[str, object]]]:
    return {
        "documents": as_list(request_json(f"{api_base.rstrip('/')}/api/knowledge/projects/{quote(project_id)}/documents", token=token)),
        "skills": as_list(request_json(f"{api_base.rstrip('/')}/api/knowledge/projects/{quote(project_id)}/skills", token=token)),
        "requirements": as_list(request_json(f"{api_base.rstrip('/')}/api/requirements?project_id={quote(project_id)}", token=token)),
        "tasks": as_list(request_json(f"{api_base.rstrip('/')}/api/tasks?project_id={quote(project_id)}&page_size=100", token=token)),
    }


def get_seat_queues(api_base: str, token: str, project_id: str, seat_id: str) -> dict[str, object]:
    return object_data(
        request_json(
            f"{api_base.rstrip('/')}/api/collaboration/projects/{quote(project_id)}/thread-workstations/{quote(seat_id)}/queues?limit=100",
            token=token,
        ),
    )


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [text(item) for item in value if text(item)]
    raw = text(value)
    return [raw] if raw else []


def normalized_path(value: object) -> str:
    return text(value).replace("\\", "/").strip("/")


def has_evidence_line(description: str, repo_path: str) -> bool:
    expected = normalized_path(repo_path).lower()
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if ":" not in line and "：" not in line:
            continue
        label, _, value = line.replace("：", ":").partition(":")
        if label.strip().lower() in {"证据路径", "evidence path", "repo path"}:
            if normalized_path(value).lower() == expected:
                return True
    return False


def count_indexed(items: dict[str, list[dict[str, object]]]) -> dict[str, int]:
    knowledge_path = FIXTURE_PATHS["knowledge"]
    skill_path = FIXTURE_PATHS["skill"]
    need_path = FIXTURE_PATHS["need"]
    task_path = FIXTURE_PATHS["task"]
    return {
        "knowledge": sum(
            1
            for item in items["documents"]
            if normalized_path(item.get("repo_relative_path") or item.get("repoRelativePath") or item.get("path")).lower()
            == knowledge_path.lower()
        ),
        "skills": sum(
            1
            for item in items["skills"]
            if normalized_path(item.get("repo_relative_path") or item.get("repoRelativePath") or item.get("path")).lower()
            == skill_path.lower()
        ),
        "needs": sum(
            1
            for item in items["requirements"]
            if need_path in string_list(item.get("related_files") or item.get("relatedFiles"))
            or has_evidence_line(text(item.get("context_summary") or item.get("contextSummary")), need_path)
        ),
        "tasks": sum(
            1
            for item in items["tasks"]
            if normalized_path(item.get("related_issue") or item.get("relatedIssue")).lower() == task_path.lower()
            or has_evidence_line(text(item.get("description")), task_path)
        ),
    }


def indexed_records(items: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    need_path = FIXTURE_PATHS["need"]
    task_path = FIXTURE_PATHS["task"]
    return {
        "needs": [
            item
            for item in items["requirements"]
            if need_path in string_list(item.get("related_files") or item.get("relatedFiles"))
            or has_evidence_line(text(item.get("context_summary") or item.get("contextSummary")), need_path)
        ],
        "tasks": [
            item
            for item in items["tasks"]
            if normalized_path(item.get("related_issue") or item.get("relatedIssue")).lower() == task_path.lower()
            or has_evidence_line(text(item.get("description")), task_path)
        ],
    }


def archive_indexed_queue_items(api_base: str, token: str, user: dict[str, object], project_id: str) -> dict[str, object]:
    items = list_project_items(api_base, token, project_id)
    records = indexed_records(items)
    actor_id = text(user.get("id") or user.get("email"), "qa-human")
    archived: dict[str, object] = {"needs": [], "tasks": []}
    for task in records["tasks"]:
        task_id = text(task.get("id"))
        if not task_id:
            continue
        archived_task = object_data(
            request_json(
                f"{api_base.rstrip('/')}/api/tasks/{quote(task_id)}/archive",
                method="POST",
                token=token,
                payload={"actor_type": "human", "actor_id": actor_id, "message": "QA archive indexed task receipt"},
            ),
        )
        archived["tasks"].append(archived_task)  # type: ignore[union-attr]
    for need in records["needs"]:
        need_id = text(need.get("id"))
        if not need_id:
            continue
        request_json(
            f"{api_base.rstrip('/')}/api/requirements/{quote(need_id)}/close",
            method="POST",
            token=token,
            payload={"actor_type": "human", "actor_id": actor_id, "note": "QA close indexed need before archive"},
        )
        archived_need = object_data(
            request_json(
                f"{api_base.rstrip('/')}/api/requirements/{quote(need_id)}/archive",
                method="POST",
                token=token,
                payload={"actor_type": "human", "actor_id": actor_id, "note": "QA archive indexed need"},
            ),
        )
        archived["needs"].append(archived_need)  # type: ignore[union-attr]
    return archived


def list_task_dispatches(api_base: str, token: str, task_id: str) -> list[dict[str, object]]:
    return as_list(
        request_json(
            f"{api_base.rstrip('/')}/api/tasks/{quote(task_id)}/dispatches",
            token=token,
        ),
    )


def validate_route_preview_readonly(
    *,
    api_base: str,
    token: str,
    project_id: str,
    seat: dict[str, object],
    items_before: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    records = indexed_records(items_before)
    needs = records["needs"]
    task_ids = [text(item.get("id")) for item in records["tasks"] if text(item.get("id"))]
    if len(needs) != 1:
        return {
            "ok": False,
            "reason": f"Expected exactly one indexed Need before route preview, got {len(needs)}",
            "need_count": len(needs),
            "task_ids": task_ids,
        }
    need_id = text(needs[0].get("id"))
    if not need_id:
        return {"ok": False, "reason": "Indexed Need is missing id", "task_ids": task_ids}

    need_before = object_data(
        request_json(
            f"{api_base.rstrip('/')}/api/requirements/{quote(need_id)}",
            token=token,
        ),
    )
    dispatch_counts_before = {
        task_id: len(list_task_dispatches(api_base, token, task_id))
        for task_id in task_ids
    }
    preview = object_data(
        request_json(
            f"{api_base.rstrip('/')}/api/requirements/{quote(need_id)}/route-preview",
            token=token,
        ),
    )
    need_after = object_data(
        request_json(
            f"{api_base.rstrip('/')}/api/requirements/{quote(need_id)}",
            token=token,
        ),
    )
    items_after = list_project_items(api_base, token, project_id)
    dispatch_counts_after = {
        task_id: len(list_task_dispatches(api_base, token, task_id))
        for task_id in task_ids
    }
    before_task_count = len(items_before["tasks"])
    after_task_count = len(items_after["tasks"])
    before_task_id = text(need_before.get("task_id") or need_before.get("taskId"))
    after_task_id = text(need_after.get("task_id") or need_after.get("taskId"))
    seat_row_id = text(seat.get("id") or seat.get("row_id") or seat.get("rowId"))
    seat_config_id = text(seat.get("config_id") or seat.get("configId"))
    seat_agent_id = text(seat.get("agent_id") or seat.get("agentId"))
    queue = get_seat_queues(api_base, token, project_id, seat_row_id or seat_config_id or seat_agent_id)
    queue_seat = queue.get("seat") if isinstance(queue.get("seat"), dict) else {}
    seat_identities = {
        value
        for value in (
            seat_row_id,
            seat_config_id,
            seat_agent_id,
            text(queue_seat.get("id") or queue_seat.get("row_id") or queue_seat.get("rowId")),
            text(queue_seat.get("config_id") or queue_seat.get("configId")),
            text(queue_seat.get("agent_id") or queue_seat.get("agentId")),
        )
        if value
    }
    preview_requester_id = text(preview.get("requester_seat_id") or preview.get("requesterSeatId"))
    alternatives = preview.get("alternatives")
    will_create_tasks = preview.get("will_create_tasks") or preview.get("willCreateTasks")
    blocked_reason = text(preview.get("blocked_reason") or preview.get("blockedReason"))
    review_reason = text(preview.get("review_reason") or preview.get("reviewReason"))
    preview_task_items = will_create_tasks if isinstance(will_create_tasks, list) else []
    planned_source_need_ids = {
        text(item.get("source_need_id") or item.get("sourceNeedId"))
        for item in preview_task_items
        if isinstance(item, dict)
    }
    readonly_ok = (
        before_task_count == after_task_count
        and not before_task_id
        and not after_task_id
        and dispatch_counts_before == dispatch_counts_after
    )
    shape_ok = (
        text(preview.get("need_id") or preview.get("needId")) == need_id
        and preview_requester_id in seat_identities
        and isinstance(alternatives, list)
        and bool(blocked_reason or review_reason)
        and all(source_id in {"", need_id} for source_id in planned_source_need_ids)
    )
    return {
        "ok": readonly_ok and shape_ok,
        "readonly_ok": readonly_ok,
        "shape_ok": shape_ok,
        "need_id": need_id,
        "task_ids": task_ids,
        "before_task_count": before_task_count,
        "after_task_count": after_task_count,
        "before_need_task_id": before_task_id or None,
        "after_need_task_id": after_task_id or None,
        "seat_identities": sorted(seat_identities),
        "dispatch_counts_before": dispatch_counts_before,
        "dispatch_counts_after": dispatch_counts_after,
        "preview": preview,
        "checks": {
            "need_id_matches": text(preview.get("need_id") or preview.get("needId")) == need_id,
            "requester_matches_seat": preview_requester_id in seat_identities,
            "alternatives_is_list": isinstance(alternatives, list),
            "has_user_readable_reason": bool(blocked_reason or review_reason),
            "preview_tasks_reference_need": all(source_id in {"", need_id} for source_id in planned_source_need_ids),
            "task_count_unchanged": before_task_count == after_task_count,
            "need_task_id_unchanged_empty": not before_task_id and not after_task_id,
            "dispatch_count_unchanged": dispatch_counts_before == dispatch_counts_after,
        },
    }


def queue_items(queue: dict[str, object], key: str) -> list[dict[str, object]]:
    section = queue.get(key)
    if not isinstance(section, dict):
        return []
    items = section.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def validate_index_ownership(
    *,
    items: dict[str, list[dict[str, object]]],
    seat_queue: dict[str, object],
    seat: dict[str, object],
) -> dict[str, object]:
    records = indexed_records(items)
    queue_seat = seat_queue.get("seat") if isinstance(seat_queue.get("seat"), dict) else {}
    seat_row_id = text(seat.get("id") or seat.get("row_id") or seat.get("rowId"))
    seat_config_id = text(seat.get("config_id") or seat.get("configId"))
    seat_agent_id = text(seat.get("agent_id") or seat.get("agentId"))
    queue_seat_row_id = text(queue_seat.get("id") or queue_seat.get("row_id") or queue_seat.get("rowId"))
    queue_seat_config_id = text(queue_seat.get("config_id") or queue_seat.get("configId"))
    queue_seat_agent_id = text(queue_seat.get("agent_id") or queue_seat.get("agentId"))
    seat_identities = {
        value
        for value in (
            seat_row_id,
            seat_config_id,
            seat_agent_id,
            queue_seat_row_id,
            queue_seat_config_id,
            queue_seat_agent_id,
        )
        if value
    }
    my_needs = queue_items(seat_queue, "my_needs")
    requirement_inbox = queue_items(seat_queue, "requirement_inbox")
    my_tasks = queue_items(seat_queue, "my_tasks")
    indexed_need_ids = {text(item.get("id")) for item in records["needs"] if text(item.get("id"))}
    indexed_task_ids = {text(item.get("id")) for item in records["tasks"] if text(item.get("id"))}
    need_from_agents = {text(item.get("from_agent") or item.get("fromAgent")) for item in records["needs"]}
    task_assignees = {text(item.get("assignee_agent_id") or item.get("assigneeAgentId")) for item in records["tasks"]}
    return {
        "seat_identity": {
            "row_id": seat_row_id,
            "config_id": seat_config_id,
            "agent_id": seat_agent_id,
            "queue_row_id": queue_seat_row_id,
            "queue_config_id": queue_seat_config_id,
            "queue_agent_id": queue_seat_agent_id,
        },
        "indexed_need_ids": sorted(indexed_need_ids),
        "indexed_task_ids": sorted(indexed_task_ids),
        "need_from_agents": sorted(value for value in need_from_agents if value),
        "task_assignees": sorted(value for value in task_assignees if value),
        "my_needs_count": len(my_needs),
        "my_tasks_count": len(my_tasks),
        "requirement_inbox_count": len(requirement_inbox),
        "need_in_my_needs": bool(indexed_need_ids & {text(item.get("id")) for item in my_needs}),
        "need_not_in_requirement_inbox": not bool(indexed_need_ids & {text(item.get("id")) for item in requirement_inbox}),
        "need_owner_matches_seat": bool(need_from_agents) and all(owner in seat_identities for owner in need_from_agents if owner),
        "task_assignee_matches_seat": bool(task_assignees) and all(assignee in seat_identities for assignee in task_assignees if assignee),
        "done_receipt_not_in_my_open_tasks": not bool(indexed_task_ids & {text(item.get("id")) for item in my_tasks}),
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
    raise RuntimeError(f"Timed out waiting for expression: {expression[:220]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(data))


def new_cdp() -> tuple[object, subprocess.Popen[bytes], Path]:
    port = cdp_helper.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-collab-skill-forge-idem-cdp-"))
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


def authenticate_browser(cdp: object, *, web_base: str, token: str, user: dict[str, object]) -> None:
    origin = web_base.rstrip("/")
    user_json = json.dumps(user or {}, ensure_ascii=True)
    for name, value in (("farm_access_token", token), ("farm_user", user_json)):
        result = cdp.send(
            "Network.setCookie",
            {"name": name, "value": value, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
        )
        if not result.get("success"):
            raise RuntimeError(f"Failed to set auth cookie {name}")


def read_page_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const text = document.body ? document.body.innerText || '' : '';
          const lower = text.toLowerCase();
          const auditText = Array.from(document.querySelectorAll('[aria-label="最近一次沉淀索引结果"], [aria-label="沉淀索引摘要"]'))
            .map((item) => item.innerText || item.textContent || '')
            .join('\\n');
          return {{
            url: location.href,
            blank: text.trim().length < 40,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 ||
              document.body.scrollWidth > document.documentElement.clientWidth + 1,
            hasSeat: text.includes('QA 幂等 NPC'),
            hasIndexButton: text.includes('索引该 NPC 沉淀'),
            hasRecentIndex: text.includes('最近索引'),
            auditText,
            forbiddenHits: {json.dumps(FORBIDDEN_TERMS)}.filter((term) => lower.includes(term.toLowerCase())),
            rawUuidHits: Array.from(text.matchAll(/[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}/ig)).map((match) => match[0]).slice(0, 8),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError("Could not read page state")
    return state


def click_index_button(cdp: object) -> None:
    point = wait_for(
        cdp,
        """
        (() => {
          const buttons = Array.from(document.querySelectorAll('button'));
          const button = buttons.find((item) => (item.innerText || item.textContent || '').includes('索引该 NPC 沉淀'));
          if (!button) return false;
          button.scrollIntoView({ block: 'center', inline: 'center' });
          const rect = button.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        })()
        """,
        timeout_seconds=30,
    )
    if not isinstance(point, dict):
        raise RuntimeError("Could not find index button")
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": float(point["x"]), "y": float(point["y"])})
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": float(point["x"]), "y": float(point["y"]), "button": "left", "clickCount": 1})
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": float(point["x"]), "y": float(point["y"]), "button": "left", "clickCount": 1})


def run_index_round(cdp: object, *, output_dir: Path, label: str) -> dict[str, object]:
    click_index_button(cdp)
    wait_for(cdp, "document.body && document.body.innerText.includes('最近索引')", timeout_seconds=60)
    time.sleep(0.5)
    state = read_page_state(cdp)
    shot = output_dir / f"{label}.png"
    screenshot(cdp, shot)
    state["screenshot"] = str(shot)
    return state


def audit_shows_all_skipped(value: object) -> bool:
    audit_text = text(value)
    return (
        "新增 0" in audit_text
        and (
            "跳过 4" in audit_text
            or all(f"{kind} 新增 0 / 跳过 1" in audit_text for kind in ("知识", "Skill 草稿", "需求", "任务回执"))
        )
    )


def validate_company_archive_hidden(
    cdp: object,
    *,
    web_base: str,
    project_id: str,
    queue: str,
    output_dir: Path,
) -> dict[str, object]:
    query = urlencode({"focus": "skill-forge-index", "queue": queue, "item": "0", "tab": "knowledge"})
    url = f"{web_base.rstrip('/')}/projects/{project_id}/company?{query}"
    cdp.send("Page.navigate", {"url": url})
    wait_for(cdp, "document.body && (document.body.innerText.includes('验收详情') || document.body.innerText.includes('当前没有可验收条目'))", timeout_seconds=60)
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const text = document.body ? document.body.innerText || '' : '';
          const lower = text.toLowerCase();
          return {{
            url: location.href,
            blank: text.trim().length < 40,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 ||
              document.body.scrollWidth > document.documentElement.clientWidth + 1,
            hasEmptyReviewState: text.includes('当前没有可验收条目'),
            hasNeedTitle: text.includes('QA NPC 结构化需求'),
            hasTaskTitle: text.includes('QA NPC 任务回执'),
            hasArchiveAction: text.includes('归档当前条目'),
            forbiddenHits: {json.dumps(FORBIDDEN_TERMS)}.filter((term) => lower.includes(term.toLowerCase())),
            rawUuidHits: Array.from(text.matchAll(/[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}/ig)).map((match) => match[0]).slice(0, 8),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError("Could not read company archive state")
    shot = output_dir / f"company-after-archive-{queue}.png"
    screenshot(cdp, shot)
    state["screenshot"] = str(shot)
    return state


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    project = create_project(args.api_base, token)
    project_id = text(project.get("id"))
    seat = create_qa_seat(args.api_base, token, project_id)
    seat_id = text(seat.get("id") or seat.get("row_id") or seat.get("config_id"))
    if not project_id or not seat_id:
        raise RuntimeError(f"Could not seed QA project/seat: project={project} seat={seat}")

    cdp = None
    edge_process = None
    profile_dir = None
    try:
        cdp, edge_process, profile_dir = new_cdp()
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False},
        )
        authenticate_browser(cdp, web_base=args.web_base, token=token, user=user)
        query = urlencode({"resources": f"seat:{seat_id}", "tab": "knowledge"})
        url = f"{args.web_base.rstrip('/')}/projects/{project_id}/skill-forge?{query}"
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.body && document.body.innerText.includes('索引该 NPC 沉淀')", timeout_seconds=60)
        initial_state = read_page_state(cdp)
        screenshot(cdp, output_dir / "initial-skill-forge.png")

        first_state = run_index_round(cdp, output_dir=output_dir, label="after-first-index")
        first_counts = count_indexed(list_project_items(args.api_base, token, project_id))
        second_state = run_index_round(cdp, output_dir=output_dir, label="after-second-index")
        second_items = list_project_items(args.api_base, token, project_id)
        second_counts = count_indexed(second_items)
        ownership_before_archive = validate_index_ownership(
            items=second_items,
            seat_queue=get_seat_queues(args.api_base, token, project_id, seat_id),
            seat=seat,
        )
        route_preview_readonly = validate_route_preview_readonly(
            api_base=args.api_base,
            token=token,
            project_id=project_id,
            seat=seat,
            items_before=second_items,
        )
        archived_items = archive_indexed_queue_items(args.api_base, token, user, project_id)
        archived_counts = count_indexed(list_project_items(args.api_base, token, project_id))
        company_needs_state = validate_company_archive_hidden(
            cdp,
            web_base=args.web_base,
            project_id=project_id,
            queue="needs",
            output_dir=output_dir,
        )
        company_tasks_state = validate_company_archive_hidden(
            cdp,
            web_base=args.web_base,
            project_id=project_id,
            queue="tasks",
            output_dir=output_dir,
        )
        cdp.send("Page.navigate", {"url": url})
        wait_for(cdp, "document.body && document.body.innerText.includes('索引该 NPC 沉淀')", timeout_seconds=60)
        third_state = run_index_round(cdp, output_dir=output_dir, label="after-archive-third-index")
        third_counts = count_indexed(list_project_items(args.api_base, token, project_id))
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

    expected_first = {"knowledge": 1, "skills": 1, "needs": 1, "tasks": 1}
    pass_checks = bool(
        first_counts == expected_first
        and second_counts == first_counts
        and archived_counts == second_counts
        and third_counts == second_counts
        and ownership_before_archive.get("need_in_my_needs")
        and ownership_before_archive.get("need_not_in_requirement_inbox")
        and ownership_before_archive.get("need_owner_matches_seat")
        and ownership_before_archive.get("task_assignee_matches_seat")
        and ownership_before_archive.get("done_receipt_not_in_my_open_tasks")
        and route_preview_readonly.get("ok")
        and "新增 4" in text(first_state.get("auditText"))
        and audit_shows_all_skipped(second_state.get("auditText"))
        and audit_shows_all_skipped(third_state.get("auditText"))
        and not company_needs_state.get("hasNeedTitle")
        and not company_tasks_state.get("hasTaskTitle")
        and company_needs_state.get("hasEmptyReviewState")
        and company_tasks_state.get("hasEmptyReviewState")
        and not initial_state.get("blank")
        and not first_state.get("blank")
        and not second_state.get("blank")
        and not third_state.get("blank")
        and not company_needs_state.get("blank")
        and not company_tasks_state.get("blank")
        and not initial_state.get("hasHorizontalOverflow")
        and not first_state.get("hasHorizontalOverflow")
        and not second_state.get("hasHorizontalOverflow")
        and not third_state.get("hasHorizontalOverflow")
        and not company_needs_state.get("hasHorizontalOverflow")
        and not company_tasks_state.get("hasHorizontalOverflow")
        and not initial_state.get("forbiddenHits")
        and not first_state.get("forbiddenHits")
        and not second_state.get("forbiddenHits")
        and not third_state.get("forbiddenHits")
        and not company_needs_state.get("forbiddenHits")
        and not company_tasks_state.get("forbiddenHits")
        and not initial_state.get("rawUuidHits")
        and not first_state.get("rawUuidHits")
        and not second_state.get("rawUuidHits")
        and not third_state.get("rawUuidHits")
        and not company_needs_state.get("rawUuidHits")
        and not company_tasks_state.get("rawUuidHits")
    )
    report = {
        "ok": pass_checks,
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "web_base": args.web_base,
        "api_base": args.api_base,
        "project_id": project_id,
        "seat_id": seat_id,
        "fixture_paths": FIXTURE_PATHS,
        "initial_state": initial_state,
        "first_state": first_state,
        "second_state": second_state,
        "ownership_before_archive": ownership_before_archive,
        "route_preview_readonly": route_preview_readonly,
        "archived_items": archived_items,
        "company_after_archive": {
            "needs": company_needs_state,
            "tasks": company_tasks_state,
        },
        "third_state": third_state,
        "first_counts": first_counts,
        "second_counts": second_counts,
        "archived_counts": archived_counts,
        "third_counts": third_counts,
        "screenshots": {
            "initial": str(output_dir / "initial-skill-forge.png"),
            "first": first_state.get("screenshot"),
            "second": second_state.get("screenshot"),
            "company_needs_after_archive": company_needs_state.get("screenshot"),
            "company_tasks_after_archive": company_tasks_state.get("screenshot"),
            "third": third_state.get("screenshot"),
        },
    }
    report_path = output_dir / "skill-forge-index-idempotency-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": pass_checks,
                "project_id": project_id,
                "seat_id": seat_id,
                "report": str(report_path),
                "screenshots": report["screenshots"],
                "first_counts": first_counts,
                "second_counts": second_counts,
                "archived_counts": archived_counts,
                "third_counts": third_counts,
                "ownership": ownership_before_archive,
                "route_preview_readonly": route_preview_readonly,
            },
            ensure_ascii=False,
        ),
    )
    return 0 if pass_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
