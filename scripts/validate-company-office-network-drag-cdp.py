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


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate draggable NPC office network on company page.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/company-office-network-qa")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1050)
    return parser.parse_args()


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 20, interval_seconds: float = 0.25) -> object:
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
    shot_data = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}).get("data")
    if not shot_data:
        raise RuntimeError("CDP returned empty screenshot")
    output.write_bytes(base64.b64decode(str(shot_data)))


def run_alignment_precheck(args: argparse.Namespace) -> dict[str, object]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_web_api_alignment.py"),
        "--web-base",
        args.web_base,
        "--api-base",
        args.api_base,
        "--project-id",
        args.project_id,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    body = completed.stdout.strip() or completed.stderr.strip()
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"ok": False, "issues": [body or "alignment probe returned no output"]}
    data["exit_code"] = completed.returncode
    return data


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    alignment = run_alignment_precheck(args)
    if not alignment.get("ok"):
      raise RuntimeError(f"Alignment precheck failed: {json.dumps(alignment, ensure_ascii=False)[:2000]}")

    token, user_json = cdp_helpers.authenticate(args)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-office-network-cdp-"))
    edge_process = None
    cdp = None
    report: dict[str, object] = {
        "verdict": "passed",
        "project_id": args.project_id,
        "alignment": alignment,
        "screenshots": [],
    }
    try:
        port = cdp_helpers.find_free_port()
        edge_process = subprocess.Popen(
            [
                str(cdp_helpers.find_edge()),
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next(
            (item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")),
            None,
        )
        if not isinstance(page_target, dict):
            raise RuntimeError("No page target available")

        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        origin = args.web_base.rstrip("/")
        cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
        url = f"{origin}/projects/{args.project_id}/company"
        cdp.send("Page.navigate", {"url": url})

        wait_for(
            cdp,
            """
            (() => {
              const text = document.body?.innerText || '';
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              return text.includes('NPC 办公网')
                && !!section
                && section.querySelectorAll('button[data-edge-id]').length > 0
                && section.querySelectorAll('a[href*="seat="]').length > 0;
            })()
            """,
        )
        time.sleep(1.0)
        cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              section?.scrollIntoView({ block: 'center', inline: 'nearest' });
              return true;
            })()
            """,
        )
        time.sleep(0.4)
        before = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const nodes = Array.from(section?.querySelectorAll('[class*="officeNodeLayer"] a[class*="officeNode"][href*="seat="]') || []);
              const node = nodes
                .map((item) => {
                  const rect = item.getBoundingClientRect();
                  return {
                    item,
                    rect,
                    room: Math.min(rect.left, window.innerWidth - rect.right) + Math.min(rect.top, window.innerHeight - rect.bottom),
                  };
                })
                .sort((left, right) => right.room - left.room)[0]?.item;
              const lines = Array.from(section?.querySelectorAll('svg [data-kind] line[stroke-width]') || []);
              const root = document.scrollingElement || document.documentElement;
              if (!section || !node || lines.length === 0) return null;
              const rect = node.getBoundingClientRect();
              return {
                href: node.getAttribute('href') || '',
                node: { left: rect.left, top: rect.top, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
                lines: lines.map((line) => ({ x1: line.getAttribute('x1'), y1: line.getAttribute('y1'), x2: line.getAttribute('x2'), y2: line.getAttribute('y2') })),
                overflow: Math.max(0, root.scrollWidth - root.clientWidth),
              };
            })()
            """,
        )
        if not isinstance(before, dict):
            raise RuntimeError("Office network nodes or lines were not available")
        if int(before.get("overflow") or 0) > 2:
            raise RuntimeError(f"Company page has horizontal overflow before drag: {before['overflow']}")

        before_shot = output_dir / f"office-network-before-drag-{stamp}.png"
        screenshot(cdp, before_shot)
        report["screenshots"].append(str(before_shot))

        start_x = float(before["node"]["x"])
        start_y = float(before["node"]["y"])
        drag_vector = cdp_eval(
            cdp,
            """
            (() => {
              const width = window.innerWidth || document.documentElement.clientWidth || 1440;
              const height = window.innerHeight || document.documentElement.clientHeight || 900;
              const href = %s;
              const node = Array.from(document.querySelectorAll('section[aria-label="NPC 办公网"] [class*="officeNodeLayer"] a[class*="officeNode"][href*="seat="]'))
                .find((item) => item.getAttribute('href') === href);
              const rect = node?.getBoundingClientRect();
              const centerX = rect ? rect.left + rect.width / 2 : width / 2;
              const centerY = rect ? rect.top + rect.height / 2 : height / 2;
              return {
                dx: centerX > width * 0.52 ? -132 : 132,
                dy: centerY > height * 0.55 ? -62 : 62,
              };
            })()
            """ % json.dumps(before.get("href") or ""),
        )
        drag_dx = float(drag_vector.get("dx", 96) if isinstance(drag_vector, dict) else 96)
        drag_dy = float(drag_vector.get("dy", 44) if isinstance(drag_vector, dict) else 44)
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": start_x, "y": start_y, "button": "none"})
        cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": start_x, "y": start_y, "button": "left", "buttons": 1, "clickCount": 1})
        time.sleep(0.08)
        for step in range(1, 9):
            progress = step / 8
            cdp.send(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseMoved",
                    "x": start_x + drag_dx * progress,
                    "y": start_y + drag_dy * progress,
                    "button": "left",
                    "buttons": 1,
                },
            )
            time.sleep(0.05)
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": start_x + drag_dx, "y": start_y + drag_dy, "button": "left", "clickCount": 1})
        time.sleep(0.8)

        after = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const href = %s;
              const node = Array.from(section?.querySelectorAll('[class*="officeNodeLayer"] a[class*="officeNode"][href*="seat="]') || [])
                .find((item) => item.getAttribute('href') === href);
              const lines = Array.from(section?.querySelectorAll('svg [data-kind] line[stroke-width]') || []);
              const root = document.scrollingElement || document.documentElement;
              if (!section || !node || lines.length === 0) return null;
              const rect = node.getBoundingClientRect();
              return {
                node: { left: rect.left, top: rect.top, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
                lines: lines.map((line) => ({ x1: line.getAttribute('x1'), y1: line.getAttribute('y1'), x2: line.getAttribute('x2'), y2: line.getAttribute('y2') })),
                overflow: Math.max(0, root.scrollWidth - root.clientWidth),
              };
            })()
            """ % json.dumps(before.get("href") or ""),
        )
        if not isinstance(after, dict):
            raise RuntimeError("Office network disappeared after drag")
        node_moved = abs(float(after["node"]["x"]) - start_x) > 24 or abs(float(after["node"]["y"]) - start_y) > 24
        line_changed = json.dumps(before.get("lines"), sort_keys=True) != json.dumps(after.get("lines"), sort_keys=True)
        if not node_moved:
            raise RuntimeError(f"NPC node did not move enough: before={before['node']} after={after['node']}")
        if not line_changed:
            raise RuntimeError(f"Office network line did not follow drag: before={before.get('lines')} after={after.get('lines')}")
        if int(after.get("overflow") or 0) > 2:
            raise RuntimeError(f"Company page has horizontal overflow after drag: {after['overflow']}")

        click_target = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const target = Array.from(section?.querySelectorAll('button[data-edge-id]') || []).find((candidate) => {
                const rect = candidate.getBoundingClientRect();
                const x = rect.left + rect.width / 2;
                const y = rect.top + rect.height / 2;
                return document.elementFromPoint(x, y) === candidate;
              });
              if (!target) return null;
              const rect = target.getBoundingClientRect();
              return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
              };
            })()
            """,
        )
        if not isinstance(click_target, dict):
            raise RuntimeError(f"Could not find an office network line to click: {click_target}")
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": float(click_target["x"]), "y": float(click_target["y"]), "button": "none"})
        cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": float(click_target["x"]), "y": float(click_target["y"]), "button": "left", "clickCount": 1})
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": float(click_target["x"]), "y": float(click_target["y"]), "button": "left", "clickCount": 1})
        time.sleep(0.5)
        detail = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const drawer = section.querySelector('[aria-label="协作线详情"]');
              const detailLink = drawer?.querySelector('a[href*="/workbench"]');
              const knowledgeLink = drawer?.querySelector('a[href*="/skill-forge"][href*="tab=knowledge"]');
              const skillLink = drawer?.querySelector('a[href*="/skill-forge"][href*="tab=skills"]');
              return {
                drawerText: (drawer?.textContent || '').trim(),
                detailHref: detailLink?.getAttribute('href') || '',
                knowledgeHref: knowledgeLink?.getAttribute('href') || '',
                skillHref: skillLink?.getAttribute('href') || '',
                selected: section.querySelectorAll('svg [data-selected="1"]').length,
              };
            })()
            """,
        )
        if not isinstance(detail, dict) or not detail.get("drawerText") or not detail.get("detailHref"):
            raise RuntimeError(f"Clicking a collaboration line did not open details: {detail}")
        detail_text = str(detail.get("drawerText") or "")
        for expected_text in ["需求", "产出", "承接任务", "最新回执", "闭环沉淀", "下一步"]:
            if expected_text not in detail_text:
                raise RuntimeError(f"Collaboration detail is missing {expected_text}: {detail}")
        if "沉淀知识" not in detail_text and "补充知识" not in detail_text:
            raise RuntimeError(f"Collaboration detail is missing the knowledge closure action: {detail}")
        if "沉淀 Skill" not in detail_text and "完善 Skill" not in detail_text:
            raise RuntimeError(f"Collaboration detail is missing the Skill closure action: {detail}")
        if not detail.get("knowledgeHref") or not detail.get("skillHref"):
            raise RuntimeError(f"Knowledge/Skill closure links are not tab-specific: {detail}")
        if int(detail.get("selected") or 0) < 1:
            raise RuntimeError(f"Clicked line was not visually selected: {detail}")

        cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const button = Array.from(section?.querySelectorAll('button') || []).find((item) => item.textContent?.trim() === '真实');
              button?.click();
              return Boolean(button);
            })()
            """,
        )
        time.sleep(0.4)
        filtered = cdp_eval(
            cdp,
            """
            (() => {
              const section = document.querySelector('section[aria-label="NPC 办公网"]');
              const button = Array.from(section?.querySelectorAll('button') || []).find((item) => item.textContent?.trim() === '真实');
              const edgeCount = section?.querySelectorAll('svg [data-kind="collaboration"]').length || 0;
              const dimmedNodes = section?.querySelectorAll('a[data-dimmed="1"]').length || 0;
              return {
                edgeCount,
                dimmedNodes,
                activeText: button?.getAttribute('data-active') || '',
              };
            })()
            """,
        )
        if not isinstance(filtered, dict) or filtered.get("activeText") != "1":
            raise RuntimeError(f"Office network filter did not activate: {filtered}")

        after_shot = output_dir / f"office-network-after-drag-{stamp}.png"
        screenshot(cdp, after_shot)
        report["screenshots"].append(str(after_shot))
        knowledge_href = str(detail.get("knowledgeHref") or "")
        knowledge_url = knowledge_href if knowledge_href.startswith("http") else f"{origin}{knowledge_href}"
        cdp.send("Page.navigate", {"url": knowledge_url})
        wait_for(
            cdp,
            """
            (() => {
              const text = document.body?.innerText || '';
              return text.includes('能力工坊') && text.includes('来自公司协作线');
            })()
            """,
            timeout_seconds=30,
        )
        forge = cdp_eval(
            cdp,
            """
            (() => {
              const bodyText = document.body?.innerText || '';
              const activeKnowledgeTab = Array.from(document.querySelectorAll('button[data-active="1"]')).some((button) => button.textContent?.includes('知识库配置'));
              const seedCard = document.querySelector('[aria-label="协作沉淀建议"]');
              const titleInput = document.querySelector('input[name="title"]');
              const summaryInput = document.querySelector('textarea[name="summary"]');
              const oneClickKnowledge = Array.from(seedCard?.querySelectorAll('button') || []).some((button) => button.textContent?.includes('一键保存知识'));
              const skillDraft = Array.from(seedCard?.querySelectorAll('button') || []).some((button) => button.textContent?.includes('生成 Skill 草稿'));
              const closureSourceInputs = Array.from(seedCard?.querySelectorAll('input[name="closure_source"]') || []).map((input) => input.value);
              const rawIdVisible = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(seedCard?.textContent || '');
              return {
                activeKnowledgeTab,
                seedText: (seedCard?.textContent || '').trim(),
                hasPrefilledTitle: Boolean(titleInput?.value),
                hasPrefilledSummary: Boolean(summaryInput?.value),
                oneClickKnowledge,
                skillDraft,
                closureSourceInputs,
                rawIdVisible,
                overflow: Math.max(0, (document.scrollingElement || document.documentElement).scrollWidth - document.documentElement.clientWidth),
                bodyHasSeed: bodyText.includes('来自公司协作线'),
              };
            })()
            """,
        )
        if not isinstance(forge, dict) or not forge.get("activeKnowledgeTab") or not forge.get("seedText"):
            raise RuntimeError(f"Skill forge did not open the collaboration seed in knowledge tab: {forge}")
        if not forge.get("hasPrefilledTitle") or not forge.get("hasPrefilledSummary"):
            raise RuntimeError(f"Skill forge deposit form was not prefilled from the collaboration line: {forge}")
        if not forge.get("oneClickKnowledge") or not forge.get("skillDraft"):
            raise RuntimeError(f"Skill forge collaboration seed is missing one-click closure actions: {forge}")
        if "company_collaboration" not in (forge.get("closureSourceInputs") or []):
            raise RuntimeError(f"Skill forge one-click actions are not traceable to company collaboration: {forge}")
        if forge.get("rawIdVisible"):
            raise RuntimeError(f"Skill forge collaboration seed exposed raw record ids: {forge}")
        if int(forge.get("overflow") or 0) > 2:
            raise RuntimeError(f"Skill forge collaboration seed caused horizontal overflow: {forge}")
        forge_shot = output_dir / f"skill-forge-collaboration-seed-{stamp}.png"
        screenshot(cdp, forge_shot)
        report["screenshots"].append(str(forge_shot))
        report["before"] = before
        report["after"] = after
        report["detail"] = detail
        report["filtered"] = filtered
        report["forge"] = forge
        report["url"] = url
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)

    report_path = output_dir / f"office-network-drag-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
