from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DUAL_HELPER_PATH = SCRIPT_DIR / "validate-dual-account-invite-collab-cdp.py"

spec = importlib.util.spec_from_file_location("dual_helper", DUAL_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load helper module: {DUAL_HELPER_PATH}")
dual_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dual_helper)

api_login = dual_helper.api_login
request_json = dual_helper.request_json


FRONT_C_SEATS = [
    {
        "seat_id": "front-c-7",
        "row_id": "d975546d-6850-40ef-985c-e67369bf46b7",
        "name": "前端 C 7号",
        "thread_id": "019e8121-ee19-77d2-b391-200ffbc6dad5",
        "thread_workstation_id": "codex-session-019e8121-ee19-77d2-b391-200ffbc6dad5",
    },
    {
        "seat_id": "front-c-8",
        "row_id": "2b1f53c1-d759-4905-93d2-5648b2324c5c",
        "name": "前端 C 8号",
        "thread_id": "019e8122-6868-7222-9a71-c2eab2483dd7",
        "thread_workstation_id": "codex-session-019e8122-6868-7222-9a71-c2eab2483dd7",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Front C 7/8 cloud-to-Codex Desktop sync evidence without sending new work.",
    )
    parser.add_argument("--web-base", default="http://106.55.62.122:3001")
    parser.add_argument("--api-base", default="http://106.55.62.122:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--runner-id", default="runner-front-c-local")
    parser.add_argument("--computer-node-id", default="front-c-local-pc")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "front-c-sync-qa"))
    parser.add_argument("--skip-browser", action="store_true")
    return parser.parse_args()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def request_runner_inbox(api_base: str, runner_id: str, *, limit: int = 100) -> list[dict[str, object]]:
    url = f"{api_base.rstrip('/')}/api/runners/{quote(runner_id)}/inbox?limit={limit}"
    req = Request(url, headers={"Accept": "application/json", "X-Runner-Id": runner_id}, method="GET")
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    data = payload.get("data") if isinstance(payload, dict) else []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def browser_preview(
    *,
    web_base: str,
    project_id: str,
    computer_node_id: str,
    token: str,
    output_dir: Path,
    stamp: str,
) -> dict[str, object]:
    screenshot_path = output_dir / f"front-c-machine-room-{stamp}.png"
    node_code = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch({{ headless: true }});
  const context = await browser.newContext({{ viewport: {{ width: 1440, height: 1000 }} }});
  await context.addCookies([{{
    name: 'farm_access_token',
    value: {json.dumps(token)},
    url: {json.dumps(web_base.rstrip('/') + '/')},
    sameSite: 'Lax'
  }}]);
  const page = await context.newPage();
  const url = `${{ {json.dumps(web_base.rstrip('/'))} }}/projects/${{ {json.dumps(project_id)} }}/2d-upgrade?panel=machine-room&action=thread-list&computer=${{ {json.dumps(computer_node_id)} }}`;
  await page.goto(url, {{ waitUntil: 'networkidle', timeout: 45000 }}).catch(async () => {{
    await page.goto(url, {{ waitUntil: 'domcontentloaded', timeout: 45000 }});
  }});
  await page.waitForTimeout(1800);
    const result = await page.evaluate((computerId) => {{
    const root = document.scrollingElement || document.documentElement;
    const section = document.querySelector(`[data-computer-thread-preview-for="${{computerId}}"]`);
    const text = section ? section.innerText : document.body.innerText.slice(0, 2000);
    const links = Array.from(section?.querySelectorAll('a[href]') || []).map((anchor) => anchor.getAttribute('href') || '');
    return {{
      url: location.href,
      sectionFound: Boolean(section),
      text,
      links,
      hasFrontC7Thread: text.includes('设置为7号') || links.some((href) => href.includes('019e8121-ee19-77d2-b391-200ffbc6dad5')),
      hasFrontC8Thread: text.includes('标记为8号') || links.some((href) => href.includes('019e8122-6868-7222-9a71-c2eab2483dd7')),
      renderedCount: section ? section.querySelectorAll('[data-computer-thread-item]').length : 0,
      overflowX: Math.max(0, root.scrollWidth - root.clientWidth),
    }};
  }}, {json.dumps(computer_node_id)});
  await page.screenshot({{ path: {json.dumps(str(screenshot_path))}, fullPage: true }});
  await browser.close();
  result.screenshot = {json.dumps(str(screenshot_path))};
  console.log(JSON.stringify(result));
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    completed = subprocess.run(
        ["node", "-e", node_code],
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=80,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "").strip())
    return json.loads(completed.stdout.strip().splitlines()[-1])


def normalize_metadata(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def find_seat(items: list[dict[str, object]], seat: dict[str, str]) -> dict[str, object] | None:
    wanted = {
        seat["seat_id"],
        seat["row_id"],
        seat["name"],
    }
    for item in items:
        values = {
            str(item.get("id") or ""),
            str(item.get("config_id") or ""),
            str(item.get("row_id") or ""),
            str(item.get("name") or ""),
            str(item.get("title") or ""),
        }
        if wanted & values:
            return item
    return None


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    web_base = args.web_base.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    token, _user = api_login(api_base, args.login_email, args.login_password)

    report: dict[str, object] = {
        "verdict": "failed",
        "stamp": stamp,
        "project_id": args.project_id,
        "api_base": api_base,
        "web_base": web_base,
        "runner_id": args.runner_id,
        "computer_node_id": args.computer_node_id,
        "issues": [],
        "seats": [],
    }
    issues: list[str] = []

    workstations_payload = request_json(
        f"{api_base}/api/collaboration/projects/{args.project_id}/thread-workstations",
        headers=auth_headers(token),
    )
    workstations_data = workstations_payload.get("data") if isinstance(workstations_payload, dict) else []
    workstations = [item for item in workstations_data if isinstance(item, dict)] if isinstance(workstations_data, list) else []

    nodes_payload = request_json(
        f"{api_base}/api/collaboration/projects/{args.project_id}/computer-nodes",
        headers=auth_headers(token),
    )
    nodes_data = nodes_payload.get("data") if isinstance(nodes_payload, dict) else []
    nodes = [item for item in nodes_data if isinstance(item, dict)] if isinstance(nodes_data, list) else []
    node = next(
        (
            item
            for item in nodes
            if str(item.get("id") or item.get("config_id") or "").strip() == args.computer_node_id
        ),
        None,
    )
    if not node:
        issues.append(f"computer node missing: {args.computer_node_id}")
    else:
        report["computer_node"] = {
            "id": node.get("id") or node.get("config_id"),
            "label": node.get("label") or node.get("name"),
            "status": node.get("status"),
            "runner_id": node.get("runner_id") or normalize_metadata(node.get("metadata")).get("runner_id"),
        }

    try:
        runner_inbox = request_runner_inbox(api_base, args.runner_id)
    except Exception as exc:  # noqa: BLE001
        runner_inbox = []
        issues.append(f"runner inbox unavailable: {exc}")
    report["runner_inbox"] = {
        "count": len(runner_inbox),
        "open_front_c_commands": [],
    }

    open_commands: list[dict[str, object]] = []
    for message in runner_inbox:
        metadata = normalize_metadata(message.get("extra_data") or message.get("metadata"))
        target = str(message.get("agent_id") or metadata.get("target_workstation_id") or metadata.get("target_seat_id") or "")
        if target in {"front-c-7", "front-c-8", FRONT_C_SEATS[0]["row_id"], FRONT_C_SEATS[1]["row_id"]}:
            open_commands.append(
                {
                    "id": message.get("id"),
                    "title": message.get("title"),
                    "status": message.get("status"),
                    "target": target,
                    "created_at": message.get("created_at"),
                    "updated_at": message.get("updated_at"),
                }
            )
    report["runner_inbox"]["open_front_c_commands"] = open_commands
    if open_commands:
        issues.append(f"runner has {len(open_commands)} open Front C command(s); inspect before claiming idle")

    for expected in FRONT_C_SEATS:
        seat = find_seat(workstations, expected)
        if not seat:
            issues.append(f"seat missing: {expected['name']}")
            report["seats"].append({"expected": expected, "found": False})
            continue
        metadata = normalize_metadata(seat.get("metadata") or seat.get("extra_data"))
        seat_id = str(seat.get("id") or seat.get("config_id") or expected["seat_id"])
        config_payload = request_json(
            f"{api_base}/api/collaboration/projects/{args.project_id}/thread-workstations/{quote(seat_id, safe='')}/adapter-config",
            headers=auth_headers(token),
        )
        adapter = config_payload.get("data") if isinstance(config_payload, dict) and isinstance(config_payload.get("data"), dict) else {}
        queues_payload = request_json(
            f"{api_base}/api/collaboration/projects/{args.project_id}/thread-workstations/{quote(seat_id, safe='')}/queues?limit=20",
            headers=auth_headers(token),
        )
        queues = queues_payload.get("data") if isinstance(queues_payload, dict) else {}
        inbox_payload = request_json(
            f"{api_base}/api/collaboration/projects/{args.project_id}/thread-workstations/{quote(seat_id, safe='')}/inbox?limit=20",
            headers=auth_headers(token),
        )
        inbox_data = inbox_payload.get("data") if isinstance(inbox_payload, dict) else []
        inbox = [item for item in inbox_data if isinstance(item, dict)] if isinstance(inbox_data, list) else []

        automation_thread = str(
            adapter.get("automation_thread_id")
            or metadata.get("automation_thread_id")
            or metadata.get("source_workstation_id")
            or ""
        )
        thread_url = str(adapter.get("desktop_thread_url") or "")
        checks = {
            "computer_node_match": str(adapter.get("computer_node_id") or seat.get("computer_node_id") or "") == args.computer_node_id,
            "provider_codex": str(adapter.get("provider_id") or "").lower() == "codex",
            "automation_enabled": bool(adapter.get("automation_enabled")),
            "desktop_mode": str(adapter.get("desktop_delivery_mode") or "") == "codex_desktop_ui",
            "desktop_visible": bool(adapter.get("desktop_visible")),
            "desktop_bridge_connected": bool(adapter.get("desktop_bridge_connected")),
            "thread_url_match": thread_url == f"codex://threads/{expected['thread_id']}",
            "automation_thread_match": expected["thread_id"] in automation_thread,
        }
        for key, value in checks.items():
            if not value:
                issues.append(f"{expected['name']} failed {key}")

        report["seats"].append(
            {
                "expected": expected,
                "found": True,
                "seat_id": seat_id,
                "row_id": seat.get("row_id"),
                "name": seat.get("name") or seat.get("title"),
                "metadata_thread": metadata.get("source_workstation_id") or metadata.get("automation_thread_id"),
                "adapter": {
                    "provider_id": adapter.get("provider_id"),
                    "provider_label": adapter.get("provider_label"),
                    "computer_node_id": adapter.get("computer_node_id"),
                    "automation_enabled": adapter.get("automation_enabled"),
                    "automation_thread_id": adapter.get("automation_thread_id"),
                    "desktop_delivery_mode": adapter.get("desktop_delivery_mode"),
                    "delivery_mode": adapter.get("delivery_mode"),
                    "delivery_label": adapter.get("delivery_label"),
                    "desktop_visible": adapter.get("desktop_visible"),
                    "desktop_bridge_connected": adapter.get("desktop_bridge_connected"),
                    "desktop_thread_url": adapter.get("desktop_thread_url"),
                    "delivery_warning": adapter.get("delivery_warning"),
                },
                "checks": checks,
                "recent_inbox": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "status": item.get("status"),
                        "message_type": item.get("message_type"),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                        "progress_state": normalize_metadata(item.get("extra_data") or item.get("metadata")).get("progress_state"),
                    }
                    for item in inbox[:8]
                ],
                "queue_keys": sorted(list(queues.keys())) if isinstance(queues, dict) else [],
            }
        )

    if not args.skip_browser:
        try:
            preview = browser_preview(
                web_base=web_base,
                project_id=args.project_id,
                computer_node_id=args.computer_node_id,
                token=token,
                output_dir=output_dir,
                stamp=stamp,
            )
            report["machine_room_preview"] = preview
            if not preview.get("sectionFound"):
                issues.append("machine room focused computer thread preview missing")
            if not preview.get("hasFrontC7Thread"):
                issues.append("machine room preview missing Front C 7 thread id")
            if not preview.get("hasFrontC8Thread"):
                issues.append("machine room preview missing Front C 8 thread id")
            if int(preview.get("overflowX") or 0) > 2:
                issues.append(f"machine room horizontal overflow {preview.get('overflowX')}")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"machine room browser preview failed: {exc}")

    report["issues"] = issues
    report["verdict"] = "passed" if not issues else "failed"
    report_path = output_dir / f"front-c-desktop-sync-evidence-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": not issues, "report": str(report_path), "issues": issues}, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
