"""End-to-end acceptance walk through the platform from a real user's POV.

Logs in, visits each main surface, and screenshots them. Also exercises the
specific fixes from this session (token result card, watch command, scorecard,
handoff preview).

Outputs:
  artifacts/acceptance-<ts>/<step>.png + summary.json + report.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DUAL_HELPER_PATH = SCRIPT_DIR / "validate-dual-account-invite-collab-cdp.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_module("acceptance_helper", DUAL_HELPER_PATH)


def _run(flow, args, web_base: str, api_base: str, out_root: Path, findings: list[dict]) -> int:
    def add(step: str, status: str, detail: str = "", screenshot: str = ""):
        findings.append({"step": step, "status": status, "detail": detail, "screenshot": screenshot})
        prefix = {"ok": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]", "info": "[INFO]"}.get(status, "[??]")
        print(f"{prefix} {step} :: {detail}")

    # --- Step 1: login --------------------------------------------------
    try:
        shot1 = out_root / "01-login-page.png"
        flow.navigate(f"{web_base}/login")
        time.sleep(1.0)
        flow.screenshot(shot1)
        helper.login_via_ui(flow, web_base, email=args.login_email, password=args.login_password)
        add("登录", "ok", f"以 {args.login_email} 登录成功", shot1.name)
    except Exception as exc:
        add("登录", "fail", f"login_via_ui 抛错: {exc}")
        return 1

    # --- Step 2: projects list -----------------------------------------
    try:
        flow.navigate(f"{web_base}/projects")
        flow.wait_for_text("项目", timeout_seconds=15)
        time.sleep(1.5)
        shot2 = out_root / "02-projects-list.png"
        flow.screenshot(shot2)
        add("项目列表页", "ok", "项目列表渲染", shot2.name)
    except Exception as exc:
        add("项目列表页", "fail", f"{exc}")

    # --- Step 3: project main shell ------------------------------------
    try:
        flow.navigate(f"{web_base}/projects/{args.project_id}")
        time.sleep(2.5)
        shot3 = out_root / "03-project-shell-default.png"
        flow.screenshot(shot3)
        page_text = flow.text()[:600]
        add("项目主壳进入", "ok", f"页面文本前 200 字: {page_text[:200]!r}", shot3.name)
    except Exception as exc:
        add("项目主壳进入", "fail", f"{exc}")

    # --- Step 4: open computer panel ------------------------------------
    try:
        flow.navigate(f"{web_base}/projects/{args.project_id}?panel=team&tab=computers")
        time.sleep(2.5)
        shot4 = out_root / "04-computers-panel.png"
        flow.screenshot(shot4)
        txt = flow.text()
        has_register = "登记电脑" in txt or "新电脑" in txt or "电脑接入" in txt
        add("电脑接入面板", "ok" if has_register else "warn", "电脑面板已加载" if has_register else "未找到登记电脑入口", shot4.name)
    except Exception as exc:
        add("电脑接入面板", "fail", f"{exc}")

    # --- Step 5: pairing token via API redirect simulation -------------
    try:
        token, _user = helper.api_login(api_base, args.login_email, args.login_password)
        auth_headers = {"Authorization": f"Bearer {token}"}
        nodes_resp = helper.request_json(
            f"{api_base}/api/collaboration/projects/{args.project_id}/computer-nodes",
            method="GET",
            headers=auth_headers,
        )
        nodes = nodes_resp.get("data", []) if isinstance(nodes_resp, dict) else []
        if not nodes:
            helper.request_json(
                f"{api_base}/api/collaboration/projects/{args.project_id}/computer-nodes",
                method="POST",
                headers=auth_headers,
                payload={"id": "acceptance-pc", "label": "Acceptance PC"},
            )
            nodes_resp = helper.request_json(
                f"{api_base}/api/collaboration/projects/{args.project_id}/computer-nodes",
                method="GET",
                headers=auth_headers,
            )
            nodes = nodes_resp.get("data", []) if isinstance(nodes_resp, dict) else []
        target_node = nodes[0] if nodes else None
        if target_node:
            node_id = target_node.get("id") or target_node.get("node_id") or "acceptance-pc"
            resp = helper.request_json(
                f"{api_base}/api/collaboration/projects/{args.project_id}/computer-nodes/{node_id}/pairing-token",
                method="POST",
                headers=auth_headers,
                payload={},
            )
            tk = (resp or {}).get("data", {}).get("token", "") if isinstance(resp, dict) else ""
            flow.navigate(
                f"{web_base}/projects/{args.project_id}?panel=team&tab=computers"
                f"&pairing_node={node_id}&pairing_token={tk}&team_notice=已生成 {node_id} 的配对令牌"
            )
            time.sleep(3.0)
            shot5 = out_root / "05-token-result-card.png"
            flow.screenshot(shot5)
            txt = flow.text()
            has_token = tk in txt if tk else False
            has_command = "powershell" in txt.lower() or "invoke-webrequest" in txt.lower()
            has_watch = "持续协作" in txt or "-Watch" in txt
            if has_token and has_command and has_watch:
                add("Token 结果卡(主壳)", "ok", f"token({tk[:8]}…)/命令/持续协作命令 都展示", shot5.name)
            else:
                add("Token 结果卡(主壳)", "warn", f"token={has_token} command={has_command} watchCmd={has_watch}", shot5.name)
        else:
            add("Token 结果卡(主壳)", "warn", "无电脑节点可签发令牌")
    except Exception as exc:
        add("Token 结果卡(主壳)", "fail", f"{exc}")

    # --- Step 6: 2d-upgrade dashboard -----------------------------------
    try:
        flow.navigate(f"{web_base}/projects/{args.project_id}/2d-upgrade")
        time.sleep(4.0)
        shot6 = out_root / "06-2d-upgrade-dashboard.png"
        flow.screenshot(shot6)
        txt = flow.text()
        has_grade = "合格性" in txt
        add("2d-upgrade 驾驶舱", "ok" if has_grade else "warn", f"合格性 chip 展示={has_grade}", shot6.name)
    except Exception as exc:
        add("2d-upgrade 驾驶舱", "fail", f"{exc}")

    # --- Step 7: scorecard panel (open) --------------------------------
    try:
        flow.eval(
            """
            (() => {
              const btns = Array.from(document.querySelectorAll('button'));
              const target = btns.find((b) => (b.innerText || '').includes('合格性'));
              if (target) target.click();
              return target ? 'clicked' : 'not-found';
            })()
            """,
        )
        time.sleep(1.5)
        shot7 = out_root / "07-scorecard-open.png"
        flow.screenshot(shot7)
        txt = flow.text()
        indicators_ok = sum(
            1 for word in ("本机线程调用", "NPC 换手", "人工审核", "硬件红线", "协作消息密度", "token 花费")
            if word in txt
        )
        add("合格性看板展开", "ok" if indicators_ok >= 4 else "warn", f"识别到 {indicators_ok}/6 条指标文字", shot7.name)
    except Exception as exc:
        add("合格性看板展开", "fail", f"{exc}")

    # --- Step 8: NPC handoff bar (locate in 2d-upgrade dashboard) ----
    try:
        # 滚到底部，让 NPC bar 可见
        flow.eval("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.0)
        shot8 = out_root / "08-2d-upgrade-scrolled.png"
        flow.screenshot(shot8)
        txt_full = flow.text()
        # 接手 bar 上的按钮文字模式："复制 XXX 的接手 prompt"
        has_handoff_button = "接手 prompt" in txt_full or "复制接手" in txt_full
        add("NPC 接手 bar 存在性", "ok" if has_handoff_button else "warn",
            f"页面包含 '接手 prompt' 按钮文字 = {has_handoff_button}", shot8.name)
    except Exception as exc:
        add("NPC 接手 bar 存在性", "fail", f"{exc}")

    # --- Step 9: team_notice toast + URL cleanup ----------------------
    try:
        flow.navigate(f"{web_base}/projects/{args.project_id}?team_notice=测试自动刷新提示")
        time.sleep(2.5)
        shot9 = out_root / "09-team-notice-toast.png"
        flow.screenshot(shot9)
        url = flow.url()
        has_notice_in_url = "team_notice" in url
        add("team_notice toast", "ok" if not has_notice_in_url else "warn",
            ("URL 已清掉 team_notice ✓" if not has_notice_in_url else f"URL 还残留 team_notice: {url[-120:]}"),
            shot9.name)
    except Exception as exc:
        add("team_notice toast", "fail", f"{exc}")

    fails = [f for f in findings if f["status"] == "fail"]
    return 1 if fails else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--project-id", default="proj_rehab_arm")
    parser.add_argument("--login-email", default="lead@example.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=900)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    args = parser.parse_args()

    web_base = args.web_base.rstrip("/")
    api_base = args.api_base.rstrip("/")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.output_dir) / f"acceptance-{timestamp}"
    out_root.mkdir(parents=True, exist_ok=True)
    profile_root = out_root / "browser-profile"
    print(f"[acceptance] output dir: {out_root}")

    findings: list[dict] = []
    profile = helper.new_browser_profile(profile_root, "acceptance")
    runtime = helper.BrowserRuntime(
        port=helper.find_free_port(),
        profile_dir=profile,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
    )

    rc = 1
    try:
        with runtime as flow:
            rc = _run(flow, args, web_base, api_base, out_root, findings)
    except Exception as exc:
        findings.append({"step": "browser-runtime", "status": "fail", "detail": str(exc), "screenshot": ""})
        print(f"[FAIL] browser-runtime :: {exc}")

    summary = {
        "timestamp": timestamp,
        "web_base": web_base,
        "api_base": api_base,
        "project_id": args.project_id,
        "results": findings,
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = ["# Acceptance walk", f"- 时间: {timestamp}", f"- web: {web_base}", f"- api: {api_base}", ""]
    for f in findings:
        emoji = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}.get(f["status"], "?")
        lines.append(f"## {emoji} {f['step']}")
        lines.append(f"- {f['detail']}")
        if f.get("screenshot"):
            lines.append(f"- 截图: `{f['screenshot']}`")
        lines.append("")
    (out_root / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
