from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
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


SURFACES = [
    {
        "key": "cockpit",
        "path": "cockpit",
        "markers": ["驾驶舱 / 今日决策", "待我处理", "电脑状态", "下一步建议"],
    },
    {
        "key": "company",
        "path": "company",
        "markers": ["公司层 / 员工表", "工位列表", "NPC 员工表", "审核策略", "组织变更"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate cockpit and company cloud workbenches with screenshots.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/cockpit-company-workbench-cdp")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1000)
    return parser.parse_args()


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 18, interval_seconds: float = 0.25) -> object:
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


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    alignment = run_alignment_precheck(args)
    if not alignment.get("ok"):
        raise RuntimeError(f"Alignment precheck failed: {json.dumps(alignment, ensure_ascii=False)[:2000]}")

    token, user_json = cdp_helpers.authenticate(args)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {
        "verdict": "passed",
        "project_id": args.project_id,
        "alignment": alignment,
        "screenshots": [],
        "surfaces": {},
        "issues": [],
    }

    for surface in SURFACES:
        url = f"{args.web_base.rstrip('/')}/projects/{args.project_id}/{surface['path']}"
        profile_dir = cdp_helpers.Path(cdp_helpers.tempfile.mkdtemp(prefix="codex-cockpit-company-cdp-"))
        edge_process = None
        cdp = None
        try:
            port = cdp_helpers.find_free_port()
            edge_process = cdp_helpers.subprocess.Popen(
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
                stdout=cdp_helpers.subprocess.DEVNULL,
                stderr=cdp_helpers.subprocess.DEVNULL,
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
            cdp.send("Page.navigate", {"url": url})

            marker_expression = " && ".join(
                [f"(document.body?.innerText || '').includes({json.dumps(marker, ensure_ascii=False)})" for marker in surface["markers"]]
            )
            wait_for(cdp, f"Boolean(document.body) && {marker_expression}")
            time.sleep(1.2)

            overflow = cdp_eval(
                cdp,
                """
                (() => {
                  const root = document.scrollingElement || document.documentElement;
                  const horizontal = Math.max(0, root.scrollWidth - root.clientWidth);
                  const offenders = Array.from(document.querySelectorAll('body *')).filter((el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.right > window.innerWidth + 2;
                  }).slice(0, 8).map((el) => ({
                    tag: el.tagName,
                    text: (el.textContent || '').trim().slice(0, 80),
                    right: Math.round(el.getBoundingClientRect().right),
                  }));
                  return { horizontal, offenders };
                })()
                """,
            )
            if isinstance(overflow, dict) and int(overflow.get("horizontal") or 0) > 2:
                raise RuntimeError(f"{surface['key']} has horizontal overflow: {json.dumps(overflow, ensure_ascii=False)}")

            shot = output_dir / f"{surface['key']}-{stamp}.png"
            shot_data = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}).get("data")
            if not shot_data:
                raise RuntimeError("CDP returned empty screenshot")
            shot.write_bytes(cdp_helpers.base64.b64decode(str(shot_data)))
            report["screenshots"].append(str(shot))
            report["surfaces"][surface["key"]] = {"url": url, "markers": surface["markers"], "overflow": overflow, "screenshot": str(shot)}
        finally:
            if cdp:
                cdp.close()
            if edge_process and edge_process.poll() is None:
                edge_process.kill()
            cdp_helpers.shutil.rmtree(profile_dir, ignore_errors=True)

    report_path = output_dir / f"cockpit-company-workbench-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": "passed", "report_path": str(report_path), "screenshots": report["screenshots"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
