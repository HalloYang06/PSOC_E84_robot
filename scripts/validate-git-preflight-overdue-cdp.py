from __future__ import annotations

import argparse
import base64
import importlib.util
from io import BytesIO
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CDP_SCRIPT = SCRIPT_DIR / "capture-auth-screenshot-cdp.py"
spec = importlib.util.spec_from_file_location("capture_auth_screenshot_cdp", CDP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CDP helpers from {CDP_SCRIPT}")
cdp_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp_helpers)

FIXTURE_NAME_PREFIX = "CODEx-GIT-PREFLIGHT-FIXTURE-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a temporary project, validate overdue Git preflight UI in a real browser, then clean it up."
    )
    parser.add_argument("--web-base", default="http://127.0.0.1:3000")
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--login-email", default="3245056131@qq.com")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--database", default=str(REPO_ROOT / "apps" / "api" / "ai_collab.db"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts"))
    parser.add_argument("--viewport-width", type=int, default=2048)
    parser.add_argument("--viewport-height", type=int, default=1152)
    parser.add_argument("--overdue-minutes", type=int, default=20)
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
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=45) as response:
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


def create_fixture_project(api_base: str, token: str) -> dict[str, object]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    runner_id = f"runner-git-overdue-fixture-{stamp}"
    node_id = f"node-git-overdue-fixture-{stamp}"
    payload = {
        "name": f"{FIXTURE_NAME_PREFIX}{stamp}",
        "description": "临时验收项目：验证 Git 预检待接单会进入首页推荐动作和 Git 面板，脚本结束会清理。",
        "project_type": "validation",
        "github_url": "https://github.com/example/ai-collab-fixture.git",
        "default_branch": "main",
        "develop_branch": "develop",
        "collaboration_config": {
            "ai_providers": [
                {
                    "id": "codex-fixture",
                    "label": "Codex 验收模型",
                    "kind": "codex",
                    "enabled": True,
                    "model": "gpt-5.4",
                }
            ],
            "computer_nodes": [
                {
                    "id": node_id,
                    "label": "Git 预检验收电脑",
                    "status": "online",
                    "runner_id": runner_id,
                    "connection_kind": "runner",
                    "metadata": {"fixture": True},
                }
            ],
            "thread_workstations": [],
        },
    }
    response = request_json(f"{api_base.rstrip('/')}/api/projects", method="POST", payload=payload, token=token)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError(f"Project create response did not include id: {response}")
    data["_fixture_runner_id"] = runner_id
    data["_fixture_node_id"] = node_id
    return data


def insert_overdue_preflight_message(
    database: Path,
    *,
    project_id: str,
    sender_id: str | None,
    runner_id: str,
    overdue_minutes: int,
) -> str:
    message_id = f"fixture-git-preflight-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    stamp = (datetime.now() - timedelta(minutes=max(1, overdue_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    body = json.dumps(
        {
            "kind": "git.preflight",
            "action": "sync",
            "dry_run": True,
            "repository_url": "https://github.com/example/ai-collab-fixture.git",
            "branch": "main",
            "credential_source": "runner_env",
            "credential_ref": "GITHUB_TOKEN_FIXTURE",
            "checks": ["git_version", "remote_read", "credential_presence", "safe_operation"],
            "fixture": True,
        },
        ensure_ascii=False,
        indent=2,
    )
    conn = sqlite3.connect(database, timeout=30)
    try:
        conn.execute(
            """
            INSERT INTO collaboration_messages (
                id, project_id, task_id, approval_id, handoff_id, requirement_id, agent_id,
                message_type, title, body, sender_type, sender_id, recipient_type, recipient_id,
                status, created_at, updated_at, dispatch_id, dedupe_key
            )
            VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                message_id,
                project_id,
                "runner_command",
                "Git 同步只读预检 / 临时验收夹具",
                body,
                "human",
                sender_id,
                "runner",
                runner_id,
                "pending",
                stamp,
                stamp,
                f"fixture:{message_id}",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return message_id


def cleanup_fixture_project(database: Path, project_id: str | None) -> dict[str, int]:
    if not project_id:
        return {}
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    deleted: dict[str, int] = {}
    try:
        row = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return {}
        project_name = str(row["name"] or "")
        if not project_name.startswith(FIXTURE_NAME_PREFIX):
            raise RuntimeError(f"Refusing to clean non-fixture project {project_id}: {project_name}")
        conn.execute("PRAGMA foreign_keys=OFF")
        tables = [
            str(item[0])
            for item in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            columns = [str(item[1]) for item in conn.execute(f'PRAGMA table_info("{table}")')]
            if "project_id" not in columns:
                continue
            cursor = conn.execute(f'DELETE FROM "{table}" WHERE project_id = ?', (project_id,))
            deleted[table] = int(cursor.rowcount if cursor.rowcount is not None else 0)
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        deleted["projects"] = int(cursor.rowcount if cursor.rowcount is not None else 0)
        conn.commit()
        return {key: value for key, value in deleted.items() if value}
    finally:
        conn.close()


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


def wait_for(cdp: object, expression: str, *, timeout_seconds: float = 60, interval_seconds: float = 0.3) -> object:
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


def wait_for_embedded_map_paint(
    cdp: object,
    *,
    timeout_seconds: float = 75,
    interval_seconds: float = 0.5,
) -> dict[str, object]:
    """Wait until the embedded farm iframe is visible in the screenshot.

    Phaser may render through WebGL, so reading a 2D canvas context is not a
    reliable readiness check. Instead, verify iframe/canvas presence, then sample
    the actual browser screenshot region the user would see.
    """
    expression = r"""
    (() => {
      const frames = Array.from(document.querySelectorAll('iframe'));
      const frame = frames.find((item) => {
        const title = item.getAttribute('title') || '';
        const src = item.getAttribute('src') || '';
        return title.includes('农场地图') || src.includes('/harvest-moon-phaser3-game/');
      });
      if (!frame) return { ready: false, reason: 'iframe_missing', frameCount: frames.length };
      const rect = frame.getBoundingClientRect();
      if (rect.width < 240 || rect.height < 180) {
        return {
          ready: false,
          reason: 'iframe_not_visible',
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      }

      let doc = null;
      try {
        doc = frame.contentDocument || (frame.contentWindow ? frame.contentWindow.document : null);
      } catch (error) {
        return { ready: false, reason: 'iframe_inaccessible', error: String(error) };
      }
      if (!doc) return { ready: false, reason: 'iframe_doc_missing' };
      if (doc.readyState !== 'complete') {
        return { ready: false, reason: 'iframe_loading', readyState: doc.readyState };
      }

      const canvases = Array.from(doc.querySelectorAll('canvas'));
      const canvas = canvases.find((item) => item.width >= 240 && item.height >= 180) || canvases[0];
      if (!canvas) return { ready: false, reason: 'canvas_missing', canvasCount: canvases.length };

      return {
        ready: true,
        reason: 'canvas_present',
        rect: {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
        },
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        iframeWidth: Math.round(rect.width),
        iframeHeight: Math.round(rect.height),
      };
    })()
    """
    deadline = time.time() + timeout_seconds
    last: object = None
    while time.time() < deadline:
        value = cdp_eval(cdp, expression)
        if isinstance(value, dict) and value.get("ready"):
            stats = analyze_embedded_map_screenshot(cdp, value)
            merged = {**value, "screenshot_sample": stats}
            if bool(stats.get("ready")):
                return merged
            last = merged
        else:
            last = value
        time.sleep(interval_seconds)
    raise RuntimeError(f"Timed out waiting for embedded farm map paint; last={last}")


def capture_screenshot_bytes(cdp: object) -> bytes:
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = str(shot.get("data") or "")
    if not data:
        raise RuntimeError("CDP returned empty screenshot")
    return base64.b64decode(data)


def analyze_embedded_map_screenshot(cdp: object, map_state: dict[str, object]) -> dict[str, object]:
    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "reason": f"pillow_unavailable:{exc}"}

    rect = map_state.get("rect") if isinstance(map_state, dict) else None
    if not isinstance(rect, dict):
        return {"ready": False, "reason": "iframe_rect_missing"}

    image = Image.open(BytesIO(capture_screenshot_bytes(cdp))).convert("RGB")
    x = float(rect.get("x") or 0)
    y = float(rect.get("y") or 0)
    width = float(rect.get("width") or image.width)
    height = float(rect.get("height") or image.height)
    left = max(0, min(image.width - 1, int(x + width * 0.18)))
    right = max(left + 1, min(image.width, int(x + width * 0.82)))
    top = max(0, min(image.height - 1, int(y + height * 0.18)))
    # Avoid the bottom focus rail when it is intentionally open.
    bottom = max(top + 1, min(image.height, int(y + height * 0.58)))
    crop = image.crop((left, top, right, bottom))
    if hasattr(crop, "get_flattened_data"):
        pixels = list(crop.get_flattened_data())
    else:
        pixels = list(crop.getdata())
    if not pixels:
        return {"ready": False, "reason": "empty_sample_region", "region": [left, top, right, bottom]}

    step = max(1, len(pixels) // 8000)
    sampled = pixels[::step]
    brightness_values = [sum(pixel) / 3 for pixel in sampled]
    mean_brightness = sum(brightness_values) / len(brightness_values)
    dark_ratio = sum(1 for value in brightness_values if value < 18) / len(brightness_values)
    bright_ratio = sum(1 for value in brightness_values if value > 45) / len(brightness_values)
    colorful_ratio = (
        sum(1 for red, green, blue in sampled if max(red, green, blue) - min(red, green, blue) > 18)
        / len(sampled)
    )
    ready = mean_brightness > 24 and bright_ratio > 0.08 and colorful_ratio > 0.04 and dark_ratio < 0.85
    return {
        "ready": ready,
        "reason": "painted" if ready else "sample_region_too_dark",
        "region": [left, top, right, bottom],
        "imageWidth": image.width,
        "imageHeight": image.height,
        "sampledPixels": len(sampled),
        "meanBrightness": round(mean_brightness, 2),
        "darkRatio": round(dark_ratio, 4),
        "brightRatio": round(bright_ratio, 4),
        "colorfulRatio": round(colorful_ratio, 4),
    }


def screenshot(cdp: object, output: Path) -> None:
    output.write_bytes(capture_screenshot_bytes(cdp))


def capture_debug(cdp: object, output_dir: Path, label: str, stamp: str) -> tuple[Path, Path]:
    shot = output_dir / f"git-preflight-overdue-debug-{label}-{stamp}.png"
    text_path = output_dir / f"git-preflight-overdue-debug-{label}-{stamp}.txt"
    try:
        screenshot(cdp, shot)
    except Exception as exc:  # noqa: BLE001
        text_path.write_text(f"screenshot failed: {exc}\n", encoding="utf-8")
    body_text = str(cdp_eval(cdp, "document.body ? document.body.innerText : ''") or "")
    text_path.write_text(body_text, encoding="utf-8")
    return shot, text_path


def main() -> int:
    args = parse_args()
    database = Path(args.database).resolve()
    if not database.exists():
        raise RuntimeError(f"SQLite database not found: {database}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    screenshots: list[str] = []
    map_paint_report: dict[str, object] = {}
    project_id: str | None = None
    cleanup_report: dict[str, int] = {}

    token, user = api_login(args.api_base, args.login_email, args.login_password)
    fixture_project = create_fixture_project(args.api_base, token)
    project_id = str(fixture_project["id"])
    runner_id = str(fixture_project["_fixture_runner_id"])
    message_id = insert_overdue_preflight_message(
        database,
        project_id=project_id,
        sender_id=str(user.get("id") or "").strip() or None,
        runner_id=runner_id,
        overdue_minutes=args.overdue_minutes,
    )
    cookie_domain = urlparse(args.web_base).hostname or "127.0.0.1"
    port = cdp_helpers.find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-git-preflight-overdue-"))
    edge_process = None
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
                "--disable-background-networking",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            cdp_helpers.request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = cdp_helpers.wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page"), None)
        if not isinstance(page_target, dict) or not page_target.get("webSocketDebuggerUrl"):
            raise RuntimeError("No CDP page target available")

        cdp = cdp_helpers.CdpSocket(str(page_target["webSocketDebuggerUrl"]))
        cdp.sock.settimeout(90)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.viewport_width,
                "height": args.viewport_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        cdp.send("Page.navigate", {"url": f"{args.web_base.rstrip('/')}/login"})
        wait_for(cdp, "document.readyState === 'complete' && !!document.body")
        for cookie in (
            {"name": "farm_access_token", "value": token},
            {"name": "farm_user", "value": json.dumps(user, ensure_ascii=True)},
        ):
            cdp.send(
                "Network.setCookie",
                {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie_domain,
                    "path": "/",
                    "httpOnly": False,
                    "secure": False,
                },
            )

        project_url = f"{args.web_base.rstrip('/')}/projects/{project_id}?validation=git-preflight-overdue"
        cdp.send("Page.navigate", {"url": project_url})
        wait_for(cdp, "document.readyState === 'complete' && !!document.body", timeout_seconds=75)
        try:
            wait_for(
                cdp,
                """
                document.readyState === 'complete' &&
                document.body.innerText.includes('隐藏协作焦点') &&
                document.body.innerText.includes('当前推荐动作') &&
                document.body.innerText.includes('Git 预检待接单') &&
                document.body.innerText.includes('Git 预检验收电脑')
                """,
                timeout_seconds=75,
            )
        except Exception as exc:  # noqa: BLE001
            debug_shot, debug_text = capture_debug(cdp, output_dir, "home", run_stamp)
            screenshots.append(str(debug_shot))
            raise RuntimeError(f"Home validation failed; debug text: {debug_text}") from exc
        home_text = str(cdp_eval(cdp, "document.body.innerText || ''") or "")
        for required in ("当前推荐动作", "Git 预检待接单", "Git 预检验收电脑"):
            if required not in home_text:
                raise RuntimeError(f"Project home did not include expected text: {required}")
        map_paint_report = wait_for_embedded_map_paint(cdp)
        home_shot = output_dir / f"git-preflight-overdue-home-{run_stamp}.png"
        screenshot(cdp, home_shot)
        screenshots.append(str(home_shot))

        git_url = f"{args.web_base.rstrip('/')}/projects/{project_id}?panel=team&tab=git&validation=git-preflight-overdue"
        cdp.send("Page.navigate", {"url": git_url})
        try:
            wait_for(
                cdp,
                """
                document.readyState === 'complete' &&
                !!document.querySelector('[data-git-preflight-card="1"]') &&
                document.body.innerText.includes('电脑 Git 预检回执') &&
                document.body.innerText.includes('需要马上处理') &&
                document.body.innerText.includes('超时')
                """,
                timeout_seconds=75,
            )
        except Exception as exc:  # noqa: BLE001
            debug_shot, debug_text = capture_debug(cdp, output_dir, "panel", run_stamp)
            screenshots.append(str(debug_shot))
            raise RuntimeError(f"Git panel validation failed; debug text: {debug_text}") from exc
        cdp_eval(
            cdp,
            """
            (() => {
              const card = document.querySelector('[data-git-preflight-card="1"]');
              if (!card) return false;
              card.scrollIntoView({ block: 'center', inline: 'nearest' });
              return true;
            })()
            """,
        )
        time.sleep(0.5)
        git_shot = output_dir / f"git-preflight-overdue-panel-{run_stamp}.png"
        screenshot(cdp, git_shot)
        screenshots.append(str(git_shot))
    finally:
        if cdp is not None:
            cdp.close()
        if edge_process is not None:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
        cleanup_report = cleanup_fixture_project(database, project_id)

    report = {
        "validated_at": datetime.now().astimezone().isoformat(),
        "project_id": project_id,
        "fixture_message_id": message_id,
        "map_paint": map_paint_report,
        "screenshots": screenshots,
        "cleanup": cleanup_report,
    }
    report_path = output_dir / f"git-preflight-overdue-validation-report-{run_stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
