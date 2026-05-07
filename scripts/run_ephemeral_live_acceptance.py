from __future__ import annotations

import argparse
import json
import locale
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bring up API/web temporarily, capture proof, then shut everything down.")
    parser.add_argument("--api-port", type=int, default=8010)
    parser.add_argument("--web-port", type=int, default=3124)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--login-email", default="codex-platform-npc@local.dev")
    parser.add_argument("--login-password", default="password")
    parser.add_argument("--skip-capture", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_ascii_path(path: Path) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def find_ascii_workspace_alias(root: Path) -> Path:
    resolved_root = root.resolve()
    if is_ascii_path(resolved_root):
        return resolved_root
    parent = resolved_root.parent
    try:
        candidates = list(parent.iterdir())
    except Exception:  # noqa: BLE001
        return resolved_root
    for candidate in candidates:
        if not candidate.name.isascii():
            continue
        try:
            if candidate.resolve() == resolved_root:
                return candidate
        except Exception:  # noqa: BLE001
            continue
    return resolved_root


def find_edge() -> Path:
    for candidate in EDGE_PATHS:
        if candidate.exists():
            return candidate
    raise RuntimeError("Microsoft Edge not found")


def start_process(
    command: list[str],
    cwd: Path | None,
    stdout_path: Path,
    stderr_path: Path,
    env_overrides: dict[str, str] | None = None,
) -> tuple[subprocess.Popen[str], object, object]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd is not None else None,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        env=env,
    )
    return process, stdout_handle, stderr_handle


def wait_for_http(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, url: str, payload: dict[str, object] | None = None, headers: dict[str, str] | None = None) -> dict[str, object]:
    body = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method.upper())
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_authenticated_html(api_port: int, web_port: int, path_with_query: str, login_email: str, login_password: str) -> str:
    auth_payload = http_json(
        "POST",
        f"http://127.0.0.1:{api_port}/api/auth/session",
        payload={"email": login_email, "password": login_password},
    )
    data = auth_payload["data"]
    access_token = str(data["access_token"])
    user_cookie = json.dumps(data["user"], ensure_ascii=True)
    request = Request(
        f"http://127.0.0.1:{web_port}{path_with_query}",
        headers={"Cookie": f"farm_access_token={access_token}; farm_user={user_cookie}"},
    )
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_authenticated_project_html(api_port: int, web_port: int, project_id: str, login_email: str, login_password: str) -> str:
    return fetch_authenticated_html(api_port, web_port, f"/projects/{project_id}", login_email, login_password)


def analyze_recovery_html(html: str, recovery_seat: str, seat_aliases: dict[str, str] | None = None) -> dict[str, object]:
    alias_map = {str(key).strip(): str(value).strip() for key, value in (seat_aliases or {}).items() if str(key).strip() and str(value).strip()}
    seat_blocks: list[tuple[str, str]] = []
    for match in re.finditer(r'data-seat-card="(?P<seat>[^"]+)"', html):
        seat = match.group("seat")
        start = match.start()
        next_match = re.search(r'data-seat-card="[^"]+"', html[match.end() :])
        end = match.end() + next_match.start() if next_match else len(html)
        seat_blocks.append((seat, html[start:end]))

    seat_cards = [seat for seat, _block in seat_blocks]
    raw_next_step_seat = ""
    normalized_target = recovery_seat.strip().lower()
    for seat, block in seat_blocks:
        resolved_seat = alias_map.get(seat, seat)
        if normalized_target and normalized_target in resolved_seat.lower() and "涓嬩竴姝ワ細" in block:
            raw_next_step_seat = seat
            break
    if not raw_next_step_seat:
        for seat, block in seat_blocks:
            if "涓嬩竴姝ワ細" in block:
                raw_next_step_seat = seat
                break

    resolved_seat_cards = [alias_map.get(card, card) for card in seat_cards]
    next_step_seat = alias_map.get(raw_next_step_seat, raw_next_step_seat)
    return {
        "seat_cards": resolved_seat_cards,
        "target_visible": any(normalized_target and normalized_target in card.lower() for card in resolved_seat_cards),
        "next_step_seat": next_step_seat,
    }


def load_bridge_audit(root: Path) -> list[dict[str, object]]:
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "verify-live-npc-bridges.py"), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def pick_recovery_capture_target(bridges: list[dict[str, object]]) -> dict[str, object] | None:
    def score(item: dict[str, object]) -> tuple[int, int, int]:
        requirement_status = str(item.get("requirement_status") or "").lower()
        live_final_done = bool(item.get("live_final_done"))
        warnings = [str(value) for value in item.get("warnings") or []]
        if live_final_done or requirement_status in {"done", "completed", "closed", "resolved"}:
            return (-1, -1, -1)
        heartbeat_missing = 1 if bool(item.get("heartbeat_missing")) else 0
        stale_state = 1 if "stale_state" in warnings else 0
        warning_count = len(warnings)
        return (heartbeat_missing, stale_state, warning_count)

    ranked = sorted(bridges, key=score, reverse=True)
    candidate = ranked[0] if ranked and score(ranked[0]) > (0, 0, 0) else None
    return candidate


def capabilities_cache_path(root: Path) -> Path:
    return root / ".codex-runtime" / "acceptance-capabilities.json"


def load_acceptance_capabilities(root: Path, max_age_seconds: int = 6 * 60 * 60) -> dict[str, object] | None:
    cache_path = capabilities_cache_path(root)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    checked_at = float(payload.get("checked_at", 0))
    if time.time() - checked_at > max_age_seconds:
        return None
    return payload


def save_acceptance_capabilities(root: Path, payload: dict[str, object]) -> None:
    cache_path = capabilities_cache_path(root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def probe_headless_edge_screenshot(root: Path) -> tuple[bool, str]:
    smoke_dir = Path(tempfile.mkdtemp(prefix="codex-edge-shot-smoke-"))
    try:
        html_path = smoke_dir / "smoke.html"
        shot_path = smoke_dir / "shot.png"
        user_data_dir = smoke_dir / "profile"
        html_path.write_text(
            "<!doctype html><html><body style='background:#7cc96f;font-family:sans-serif;'><h1>edge screenshot smoke</h1></body></html>",
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [
                str(find_edge()),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={user_data_dir}",
                "--window-size=1280,720",
                "--virtual-time-budget=3000",
                f"--screenshot={shot_path}",
                html_path.as_uri(),
            ],
            cwd=None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.time() + 8
        while time.time() < deadline:
            if shot_path.exists():
                return True, "Headless Edge created a local smoke screenshot."
            if process.poll() is not None:
                break
            time.sleep(0.25)
        return False, "Headless Edge did not create a local smoke screenshot within 8s."
    except Exception as exc:  # noqa: BLE001
        return False, f"Headless Edge smoke probe failed: {exc}"
    finally:
        try:
            if "process" in locals() and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(smoke_dir, ignore_errors=True)


def probe_node_cdp_access(root: Path, edge_workspace_root: Path) -> tuple[bool, str]:
    smoke_dir = edge_workspace_root / ".codex-runtime" / f"edge-cdp-smoke-{int(time.time() * 1000)}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    edge_process: subprocess.Popen[str] | None = None
    try:
        debug_port = find_free_port()
        profile_dir = smoke_dir / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        edge_process = subprocess.Popen(
            [
                str(find_edge()),
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            cwd=None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        wait_for_http(f"http://127.0.0.1:{debug_port}/json/version", timeout_seconds=10)
        probe = subprocess.run(
            [
                "node",
                "-e",
                (
                    "const http=require('http');"
                    f"http.get('http://127.0.0.1:{debug_port}/json/version',res=>process.exit(res.statusCode===200?0:2))"
                    ".on('error',err=>{console.error(err.message);process.exit(1);});"
                ),
            ],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if probe.returncode == 0:
            return True, "Node can reach external Edge DevTools localhost endpoint."
        stderr = (probe.stderr or probe.stdout or "").strip()
        return False, f"Node cannot reach external Edge DevTools localhost endpoint: {stderr or f'code {probe.returncode}'}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Node-to-CDP smoke probe failed: {exc}"
    finally:
        stop_process(edge_process)
        shutil.rmtree(smoke_dir, ignore_errors=True)


def get_acceptance_capabilities(root: Path, edge_workspace_root: Path) -> dict[str, object]:
    cached = load_acceptance_capabilities(root)
    if cached is not None:
        return cached
    farm_ok, farm_note = probe_headless_edge_screenshot(root)
    project_ok, project_note = probe_node_cdp_access(root, edge_workspace_root)
    payload = {
        "checked_at": time.time(),
        "farm_headless_edge": farm_ok,
        "farm_headless_edge_note": farm_note,
        "project_edge_cdp_from_node": project_ok,
        "project_edge_cdp_from_node_note": project_note,
    }
    save_acceptance_capabilities(root, payload)
    return payload


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


def run_capture(command: list[str], *, cwd: Path, timeout_seconds: int | None = None) -> tuple[bool, str]:
    def decode_stream(payload: bytes | str | None) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        encodings = [locale.getpreferredencoding(False), "utf-8", "gbk"]
        seen: set[str] = set()
        for encoding in encodings:
            if not encoding or encoding.lower() in seen:
                continue
            seen.add(encoding.lower())
            try:
                return payload.decode(encoding)
            except Exception:  # noqa: BLE001
                continue
        return payload.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace")

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=False,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = decode_stream(exc.stdout).strip()
        stderr = decode_stream(exc.stderr).strip()
        combined = "\n".join(part for part in (stdout, stderr, f"Timed out after {timeout_seconds}s") if part).strip()
        return False, combined
    stdout = decode_stream(completed.stdout).strip()
    stderr = decode_stream(completed.stderr).strip()
    combined = "\n".join(part for part in (stdout, stderr) if part).strip()
    return completed.returncode == 0, combined


def main() -> int:
    args = parse_args()
    root = repo_root()
    edge_workspace_root = find_ascii_workspace_alias(root)
    api_root = root / "apps" / "api"
    web_root = root / "apps" / "web"
    artifacts_root = root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d-%H%M%S")

    api_process = None
    web_process = None
    edge_process = None
    api_out = api_err = web_out = web_err = edge_out = edge_err = None
    edge_runtime_dir: Path | None = None

    try:
        api_process, api_out, api_err = start_process(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
            api_root,
            root / f"api-ephemeral-{timestamp}.out.log",
            root / f"api-ephemeral-{timestamp}.err.log",
        )
        web_process, web_out, web_err = start_process(
            ["node", str(root / "node_modules" / "next" / "dist" / "bin" / "next"), "start", "--port", str(args.web_port)],
            web_root,
            web_root / f"web-ephemeral-{timestamp}.out.log",
            web_root / f"web-ephemeral-{timestamp}.err.log",
            env_overrides={"NEXT_PUBLIC_API_BASE_URL": f"http://127.0.0.1:{args.api_port}"},
        )

        wait_for_http(f"http://127.0.0.1:{args.api_port}/api/health")
        wait_for_http(f"http://127.0.0.1:{args.web_port}/")

        if args.skip_capture:
            print(f"API_READY=http://127.0.0.1:{args.api_port}/api/health")
            print(f"WEB_READY=http://127.0.0.1:{args.web_port}/")
            return 0

        project_base = artifacts_root / f"project-live-{args.web_port}-ephemeral-{timestamp}"
        farm_base = artifacts_root / f"farm-live-{args.web_port}-ephemeral-{timestamp}"
        recovery_target = pick_recovery_capture_target(load_bridge_audit(root))
        recovery_base: Path | None = None
        recovery_path = ""
        recovery_seat = ""
        recovery_dom_audit: dict[str, object] | None = None
        recovery_focus_text = ""
        if recovery_target:
            recovery_seat = str(recovery_target.get("seat") or "").strip()
            recovery_workstation_id = str(recovery_target.get("live_workstation_id") or "").strip()
            if recovery_seat and recovery_workstation_id:
                recovery_slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in recovery_seat).strip("-") or "seat"
                recovery_base = artifacts_root / f"project-seat-{recovery_slug}-{args.web_port}-ephemeral-{timestamp}"
                recovery_path = (
                    f"/projects/{args.project_id}?panel=team&tab=npc-create&npc_view=seats&seat={quote(recovery_workstation_id, safe='')}"
                )
                recovery_focus_text = f"涓嬩竴姝ワ細"
        project_html = fetch_authenticated_project_html(
            args.api_port,
            args.web_port,
            args.project_id,
            args.login_email,
            args.login_password,
        )
        project_base.with_suffix(".html").write_text(project_html, encoding="utf-8")
        if recovery_base and recovery_path:
            seat_aliases = {
                str(item.get("live_workstation_id") or "").strip(): str(item.get("seat") or "").strip()
                for item in load_bridge_audit(root)
            }
            recovery_html = fetch_authenticated_html(
                args.api_port,
                args.web_port,
                recovery_path,
                args.login_email,
                args.login_password,
            )
            recovery_base.with_suffix(".html").write_text(recovery_html, encoding="utf-8")
            recovery_dom_audit = analyze_recovery_html(recovery_html, recovery_seat, seat_aliases)

        acceptance_capabilities = get_acceptance_capabilities(root, edge_workspace_root)
        edge_debug_port = find_free_port()
        edge_debug_ready = False
        edge_debug_log = ""
        if acceptance_capabilities.get("project_edge_cdp_from_node"):
            try:
                edge_runtime_dir = edge_workspace_root / ".codex-runtime" / f"edge-auth-capture-{timestamp}"
                edge_runtime_dir.mkdir(parents=True, exist_ok=True)
                edge_debug_profile = edge_runtime_dir / "profile"
                edge_debug_profile.mkdir(parents=True, exist_ok=True)
                edge_process, edge_out, edge_err = start_process(
                    [
                        str(find_edge()),
                        "--headless=new",
                        "--disable-gpu",
                        f"--remote-debugging-port={edge_debug_port}",
                        f"--user-data-dir={edge_debug_profile}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "about:blank",
                    ],
                    None,
                    root / f"edge-auth-{timestamp}.out.log",
                    root / f"edge-auth-{timestamp}.err.log",
                )
                wait_for_http(f"http://127.0.0.1:{edge_debug_port}/json/version", timeout_seconds=20)
                edge_debug_ready = True
            except Exception as exc:
                edge_debug_log = (
                    f"External Edge debug bootstrap failed: {exc}\n"
                    f"Edge workspace root: {edge_workspace_root}"
                )
                acceptance_capabilities["project_edge_cdp_from_node"] = False
                acceptance_capabilities["project_edge_cdp_from_node_note"] = edge_debug_log
                acceptance_capabilities["checked_at"] = time.time()
                save_acceptance_capabilities(root, acceptance_capabilities)
                stop_process(edge_process)
                edge_process = None
        else:
            capability_note = str(acceptance_capabilities.get("project_edge_cdp_from_node_note", "")).strip()
            edge_debug_log = (
                "Skipped primary Edge auth capture because cached capability probe marked external Edge bootstrap unavailable."
                + (f"\n{capability_note}" if capability_note else "")
            ).strip()

        project_capture = [
            sys.executable,
            str(root / "scripts" / "capture-auth-screenshot-cdp.py"),
            "--url",
            f"http://127.0.0.1:{args.web_port}/projects/{args.project_id}",
            "--output",
            str(project_base.with_suffix(".png")),
            "--api-base",
            f"http://127.0.0.1:{args.api_port}",
            "--login-email",
            args.login_email,
            "--login-password",
            args.login_password,
            "--wait-ms",
            "1800",
            "--prime-wait-ms",
            "1200",
            "--markers",
            "显示协作焦点|打开背包|已锁定：AI 合作平台项目入口",
            "--html-dump",
            str(project_base.with_suffix(".html")),
        ]
        project_capture_ok, project_capture_log = run_capture(project_capture, cwd=root, timeout_seconds=45)
        if not project_capture_ok:
            project_capture_fallback = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "scripts" / "capture-webbrowser-screenshot.ps1"),
                "-Url",
                f"http://127.0.0.1:{args.web_port}/projects/{args.project_id}",
                "-Output",
                str(project_base.with_suffix(".png")),
                "-WaitMs",
                "12000",
            ]
            fallback_ok, fallback_log = run_capture(project_capture_fallback, cwd=root, timeout_seconds=45)
            if not fallback_ok:
                raise RuntimeError(
                    "Project screenshot capture failed via Python CDP capture and WebBrowser fallback.\n"
                    f"Python CDP capture:\n{project_capture_log}\n\nFallback:\n{fallback_log}"
                )
            project_capture_log = (
                "Primary Python CDP auth capture failed; fell back to WebBrowser screenshot.\n"
                f"{project_capture_log}\n\nFallback:\n{fallback_log}"
            ).strip()

        recovery_capture_log = ""
        if recovery_base and recovery_path:
            recovery_url = f"http://127.0.0.1:{args.web_port}{recovery_path}"
            recovery_capture = [
                sys.executable,
                str(root / "scripts" / "capture-auth-screenshot-cdp.py"),
                "--url",
                recovery_url,
                "--output",
                str(recovery_base.with_suffix(".png")),
                "--api-base",
                f"http://127.0.0.1:{args.api_port}",
                "--login-email",
                args.login_email,
                "--login-password",
                args.login_password,
                "--wait-ms",
                "2200",
                "--prime-wait-ms",
                "1200",
                "--markers",
                "涓嬩竴姝ワ細|鑷不妗ワ細|鏈€灏忓洖鎵э細",
                "--html-dump",
                str(recovery_base.with_suffix(".html")),
            ]
            if recovery_focus_text:
                recovery_capture.extend(["--focus-text", recovery_focus_text])
            recovery_capture_ok, recovery_capture_log = run_capture(recovery_capture, cwd=root, timeout_seconds=45)
            if not recovery_capture_ok:
                recovery_capture_fallback = [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "scripts" / "capture-webbrowser-screenshot.ps1"),
                    "-Url",
                    recovery_url,
                    "-Output",
                    str(recovery_base.with_suffix(".png")),
                    "-WaitMs",
                    "12000",
                ]
                fallback_ok, fallback_log = run_capture(recovery_capture_fallback, cwd=root, timeout_seconds=45)
                if not fallback_ok:
                    raise RuntimeError(
                        "Recovery seat screenshot capture failed via Python CDP capture and WebBrowser fallback.\n"
                        f"Python CDP capture:\n{recovery_capture_log}\n\nFallback:\n{fallback_log}"
                    )
                recovery_capture_log = (
                    "Primary recovery Python CDP capture failed; fell back to WebBrowser screenshot.\n"
                    f"{recovery_capture_log}\n\nFallback:\n{fallback_log}"
                ).strip()

        farm_url = (
            f"http://127.0.0.1:{args.web_port}/harvest-moon-phaser3-game/index.html"
            f"?project={args.project_id}&embed=project-shell"
        )
        farm_capture = [
            sys.executable,
            str(root / "scripts" / "capture-auth-screenshot-cdp.py"),
            "--url",
            farm_url,
            "--output",
            str(farm_base.with_suffix(".png")),
            "--wait-ms",
            "2600",
            "--markers",
            "map-farm",
            "--html-dump",
            str(farm_base.with_suffix(".html")),
            "--no-auth",
        ]
        farm_capture_ok, farm_capture_log = run_capture(farm_capture, cwd=root, timeout_seconds=45)
        if not farm_capture_ok:
            farm_capture_fallback = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "scripts" / "capture-desktop-edge-window.ps1"),
                "-Url",
                farm_url,
                "-Output",
                str(farm_base.with_suffix(".png")),
                "-TitleHint",
                "Harvest Moon Phaser 3 Game",
                "-WaitSeconds",
                "12",
            ]
            fallback_ok, fallback_log = run_capture(farm_capture_fallback, cwd=root, timeout_seconds=45)
            if not fallback_ok:
                raise RuntimeError(
                    "Farm screenshot capture failed via Python CDP and desktop fallback.\n"
                    f"Python CDP:\n{farm_capture_log}\n\nFallback:\n{fallback_log}"
                )
            farm_capture_log = (
                "Primary farm Python CDP capture failed; fell back to desktop window capture.\n"
                f"{farm_capture_log}\n\nFallback:\n{fallback_log}"
            ).strip()
        if farm_capture_log:
            print(f"FARM_CAPTURE_LOG={farm_capture_log}")

        print(f"PROJECT_PNG={project_base.with_suffix('.png')}")
        print(f"PROJECT_HTML={project_base.with_suffix('.html')}")
        if recovery_base and recovery_path:
            print(f"RECOVERY_SEAT={recovery_seat}")
            print(f"RECOVERY_PNG={recovery_base.with_suffix('.png')}")
            print(f"RECOVERY_HTML={recovery_base.with_suffix('.html')}")
            if recovery_dom_audit is not None:
                print(f"RECOVERY_DOM_SEATS={json.dumps(recovery_dom_audit.get('seat_cards', []), ensure_ascii=False)}")
                print(f"RECOVERY_DOM_TARGET_VISIBLE={str(bool(recovery_dom_audit.get('target_visible'))).lower()}")
                print(f"RECOVERY_DOM_NEXT_STEP_SEAT={recovery_dom_audit.get('next_step_seat', '')}")
        print(f"FARM_PNG={farm_base.with_suffix('.png')}")
        print(f"FARM_HTML={farm_base.with_suffix('.html')}")
        if project_capture_log:
            print(f"PROJECT_CAPTURE_LOG={project_capture_log}")
        if recovery_capture_log:
            print(f"RECOVERY_CAPTURE_LOG={recovery_capture_log}")
        return 0
    finally:
        stop_process(edge_process)
        stop_process(web_process)
        stop_process(api_process)
        for handle in (edge_out, edge_err, web_out, web_err, api_out, api_err):
            if handle is not None:
                handle.close()
        if edge_runtime_dir is not None:
            try:
                shutil.rmtree(edge_runtime_dir, ignore_errors=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
