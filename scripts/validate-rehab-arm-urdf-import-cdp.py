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
from urllib.parse import quote, urlparse


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)


FORBIDDEN_RE = r"adapter|bridge|session JSONL|local path|source_thread|canonical|requested id|raw UUID|camera_keyframe|\bJSONL\b|source=rehab-arm-control"
DEFAULT_URDF_ZIP = Path(r"C:\Users\18312\xwechat_files\wxid_4anyq9um43fg22_7053\msg\file\2026-06\medical_arm.zip")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate rehab-arm URDF zip import and readonly joint pose preview from the user view.")
    parser.add_argument("--web-base", default="http://127.0.0.1:3001")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--urdf-zip", default=str(DEFAULT_URDF_ZIP))
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/validation/rehab-arm-urdf-import")
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=980)
    return parser.parse_args()


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def cdp_eval(cdp: object, expression: str) -> object:
    result = cdp.send("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True})
    if "exceptionDetails" in result:
        raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False)[:1600])
    payload = result.get("result", {})
    return payload.get("value") if isinstance(payload, dict) else None


def wait_for(cdp: object, expression: str, timeout_seconds: float = 45) -> object:
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
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {expression[:180]} last={last}")


def screenshot(cdp: object, output: Path) -> None:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    output.write_bytes(base64.b64decode(str(shot.get("data") or "")))


def set_viewport(cdp: object, width: int, height: int) -> None:
    cdp.send("Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": width < 700,
    })


def query_object_id(cdp: object, selector: str) -> str:
    result = cdp.send(
        "Runtime.evaluate",
        {
            "expression": f"document.querySelector({js(selector)})",
            "objectGroup": "rehab-urdf-upload",
            "returnByValue": False,
        },
    )
    object_id = result.get("result", {}).get("objectId")
    if not object_id:
        raise RuntimeError(f"Cannot find node: {selector}")
    return str(object_id)


def page_state(cdp: object) -> dict[str, object]:
    state = cdp_eval(
        cdp,
        f"""
        (() => {{
          const body = document.body?.innerText || '';
          const forbidden = Array.from(new Set(body.match(new RegExp({js(FORBIDDEN_RE)}, 'ig')) || []));
          const mappingRows = Array.from(document.querySelectorAll('[data-testid="rehab-pose-mapping"] [class*="mappingRow"]'));
          const matchLine = Array.from(document.querySelectorAll('[class*="poseStatus"] strong')).map((item) => item.textContent || '').find((text) => text.includes('匹配')) || '';
          const meshLine = Array.from(document.querySelectorAll('[class*="poseStatus"] span')).map((item) => item.textContent || '').find((text) => text.includes('模型资源已加载')) || '';
          const previewLines = Array.from(document.querySelectorAll('[class*="armLegend"] span')).map((item) => item.textContent || '');
          const canvas = document.querySelector('canvas[aria-label="机械臂 Three.js 总览"], [aria-label="机械臂 Three.js 总览"] canvas');
          return {{
            href: location.href,
            title: document.title,
            hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
            forbidden,
            hasReadonlyBoundary: body.includes('只读预览') && body.includes('不下发任何运动控制') && body.includes('不发 CAN'),
            hasImportedUrdf: body.includes('已导入 medical_arm.zip') && body.includes('medical_arm/urdf/medical_arm.urdf'),
            hasSavedModel: body.includes('已保存到当前设备档案') || body.includes('已从当前设备档案恢复模型包'),
            hasRestoredModel: body.includes('已从当前设备档案恢复模型包'),
            hasPoseMapping: body.includes('姿态映射') && mappingRows.length > 0,
            mappingRowCount: mappingRows.length,
            matchLine,
            meshLine,
            hasRestoredMeshes: meshLine.includes('模型资源已加载 7 个，未加载 0 个'),
            previewLines: previewLines.slice(0, 12),
            hasCanvas: Boolean(canvas),
            bodySample: body.slice(0, 2600),
          }};
        }})()
        """,
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"invalid page state: {state!r}")
    return state


def main() -> int:
    args = parse_args()
    web_base = args.web_base.rstrip("/")
    urdf_zip = Path(args.urdf_zip)
    if not urdf_zip.exists():
        raise RuntimeError(f"URDF zip not found: {urdf_zip}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report: dict[str, object] = {
        "project_id": args.project_id,
        "web_base": web_base,
        "urdf_zip_name": urdf_zip.name,
        "pages": [],
        "failures": [],
    }

    token, user_json = cdp_helpers.authenticate(args)
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="rehab-urdf-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp = None
    try:
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
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not page_target:
            raise RuntimeError("No browser page target")
        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.sock.settimeout(60)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("DOM.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        set_viewport(cdp, args.viewport_width, args.viewport_height)
        origin = f"{urlparse(web_base).scheme}://{urlparse(web_base).netloc}"
        if token:
            cdp.send("Network.setCookie", {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})
            if user_json:
                cdp.send("Network.setCookie", {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"})

        href = f"{web_base}/projects/{quote(args.project_id, safe='')}/rehab-arm-control"
        cdp.send("Page.navigate", {"url": href})
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              return location.pathname.endsWith('/rehab-arm-control')
                && body.includes('康复机械臂专项总控')
                && Boolean(document.querySelector('[data-testid="rehab-urdf-file"]'));
            })()
            """,
            timeout_seconds=45,
        )
        input_node = query_object_id(cdp, '[data-testid="rehab-urdf-file"]')
        cdp.send("DOM.setFileInputFiles", {"objectId": input_node, "files": [str(urdf_zip.resolve())]})
        cdp_eval(
            cdp,
            """
            (() => {
              const input = document.querySelector('[data-testid="rehab-urdf-file"]');
              if (!input) return false;
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
              return true;
            })()
            """,
        )
        wait_for(
            cdp,
            """
            (() => {
              const labels = Array.from(document.querySelectorAll('strong, summary, span')).map((item) => item.textContent || '');
              const loaded = labels.some((text) => text.includes('已导入 medical_arm.zip'))
                && labels.some((text) => text.includes('姿态映射'))
                && Boolean(document.querySelector('[data-testid="rehab-pose-mapping"]'));
              const failed = labels.some((text) => text.includes('URDF 未能完整加载'));
              return loaded || failed;
            })()
            """,
            timeout_seconds=60,
        )
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              return body.includes('已保存到当前设备档案') || body.includes('已从当前设备档案恢复模型包');
            })()
            """,
            timeout_seconds=30,
        )
        cdp.send("Page.reload", {"ignoreCache": True})
        wait_for(
            cdp,
            """
            (() => {
              const body = document.body?.innerText || '';
              return body.includes('已从当前设备档案恢复模型包')
                && body.includes('已导入 medical_arm.zip')
                && body.includes('匹配 6/6')
                && body.includes('模型资源已加载 7 个，未加载 0 个');
            })()
            """,
            timeout_seconds=60,
        )
        time.sleep(1.0)
        state = page_state(cdp)
        shot = output_dir / f"rehab-arm-urdf-import-{args.viewport_width}x{args.viewport_height}-{stamp}.png"
        screenshot(cdp, shot)
        state["screenshot"] = str(shot)
        state["ok"] = (
            state["hasImportedUrdf"]
            and state["hasPoseMapping"]
            and state["hasCanvas"]
            and state["hasReadonlyBoundary"]
            and state["hasSavedModel"]
            and state["hasRestoredModel"]
            and state["hasRestoredMeshes"]
            and not state["hasHorizontalOverflow"]
            and not state["forbidden"]
        )
        report["pages"].append(state)  # type: ignore[union-attr]
        if not state["ok"]:
            report["failures"].append("rehab-arm-urdf-import")  # type: ignore[union-attr]
        report["verdict"] = "passed" if not report["failures"] else "failed"
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "passed" else 1
    except Exception as exc:  # noqa: BLE001
        report["verdict"] = "failed"
        report["error"] = str(exc)
        if cdp:
            try:
                state = page_state(cdp)
                shot = output_dir / f"rehab-arm-urdf-import-failed-{stamp}.png"
                screenshot(cdp, shot)
                state["screenshot"] = str(shot)
                report["pages"].append(state)  # type: ignore[union-attr]
            except Exception as state_exc:  # noqa: BLE001
                report["state_error"] = str(state_exc)
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
