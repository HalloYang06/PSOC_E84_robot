from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)
CDP_SOCKET_TIMEOUT_SECONDS = 30

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture an authenticated page through Edge CDP without Node websockets.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-base", default="")
    parser.add_argument("--login-email", default="")
    parser.add_argument("--login-password", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--userjson", default="")
    parser.add_argument("--markers", default="")
    parser.add_argument("--html-dump", default="")
    parser.add_argument("--text-dump", default="")
    parser.add_argument("--focus-text", default="")
    parser.add_argument("--scroll-y", type=int, default=0)
    parser.add_argument("--viewport-width", type=int, default=1600)
    parser.add_argument("--viewport-height", type=int, default=1200)
    parser.add_argument("--wait-ms", type=int, default=2500)
    parser.add_argument("--prime-wait-ms", type=int, default=0)
    parser.add_argument("--expected-url-contains", default="")
    parser.add_argument("--no-auth", action="store_true")
    return parser.parse_args()


def find_edge() -> Path:
    for candidate in EDGE_PATHS:
        if candidate.exists():
            return candidate
    raise RuntimeError("Microsoft Edge not found")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None, headers: dict[str, str] | None = None) -> dict[str, object]:
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def wait_for_json(url: str, timeout_seconds: int = 20) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return request_json(url)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def read_exact(sock: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("WebSocket closed while reading")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class CdpSocket:
    def __init__(self, websocket_url: str):
        parsed = urlparse(websocket_url)
        if parsed.scheme != "ws":
            raise RuntimeError(f"Unsupported websocket scheme: {parsed.scheme}")
        self.sock = socket.create_connection(
            (parsed.hostname or "127.0.0.1", parsed.port or 80),
            timeout=CDP_SOCKET_TIMEOUT_SECONDS,
        )
        self.sock.settimeout(CDP_SOCKET_TIMEOUT_SECONDS)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        self.sock.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.sock.recv(4096)
            if len(response) > 65536:
                raise RuntimeError("WebSocket handshake response too large")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket handshake failed: {response[:240]!r}")
        self.next_id = 0

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:  # noqa: BLE001
            pass

    def _send_frame(self, payload: bytes) -> None:
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self) -> str:
        first, second = read_exact(self.sock, 2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", read_exact(self.sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", read_exact(self.sock, 8))[0]
        mask = read_exact(self.sock, 4) if masked else b""
        payload = read_exact(self.sock, length)
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            raise RuntimeError("WebSocket closed by remote")
        if opcode not in (0x1, 0x0):
            return ""
        return payload.decode("utf-8", errors="replace")

    def send(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.next_id += 1
        message_id = self.next_id
        self._send_frame(json.dumps({"id": message_id, "method": method, "params": params or {}}).encode("utf-8"))
        while True:
            raw = self._recv_frame()
            if not raw:
                continue
            payload = json.loads(raw)
            if payload.get("id") != message_id:
                continue
            if "error" in payload:
                raise RuntimeError(f"CDP {method} failed: {payload['error']}")
            result = payload.get("result")
            return result if isinstance(result, dict) else {}


def authenticate(args: argparse.Namespace) -> tuple[str, str]:
    if args.no_auth:
        return "", ""
    if args.token:
        return args.token, args.userjson
    if not args.api_base or not args.login_email or not args.login_password:
        raise RuntimeError("Authenticated capture needs --token or --api-base with --login-email/--login-password")
    payload = request_json(
        f"{args.api_base.rstrip('/')}/api/auth/session",
        method="POST",
        payload={"email": args.login_email, "password": args.login_password},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise RuntimeError("Auth response did not include access_token")
    return str(data["access_token"]), json.dumps(data.get("user") or {}, ensure_ascii=True)


def wait_for_markers(cdp: CdpSocket, markers: list[str], timeout_seconds: int = 15) -> str:
    deadline = time.time() + timeout_seconds
    last_text = ""
    while time.time() < deadline:
        result = cdp.send("Runtime.evaluate", {"expression": "document.body ? document.body.innerText : ''", "returnByValue": True})
        value = result.get("result", {}).get("value", "")
        last_text = str(value)
        if all(marker in last_text for marker in markers):
            return last_text
        time.sleep(0.3)
    missing = [marker for marker in markers if marker not in last_text]
    raise RuntimeError(f"Markers not found: {', '.join(missing)}")


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.html_dump:
        Path(args.html_dump).parent.mkdir(parents=True, exist_ok=True)
    if args.text_dump:
        Path(args.text_dump).parent.mkdir(parents=True, exist_ok=True)

    token, user_json = authenticate(args)
    port = find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="codex-edge-python-cdp-"))
    edge_process: subprocess.Popen[bytes] | None = None
    cdp: CdpSocket | None = None
    try:
        edge_process = subprocess.Popen(
            [
                str(find_edge()),
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
        targets = wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        if not isinstance(targets, list) or not targets:
            request_json(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
            targets = wait_for_json(f"http://127.0.0.1:{port}/json/list", timeout_seconds=20)
        page_target = next((item for item in targets if isinstance(item, dict) and item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
        if not isinstance(page_target, dict):
            raise RuntimeError("No page target available")
        cdp = CdpSocket(str(page_target["webSocketDebuggerUrl"]))
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
        origin = f"{urlparse(args.url).scheme}://{urlparse(args.url).netloc}"
        if token:
            result = cdp.send(
                "Network.setCookie",
                {"name": "farm_access_token", "value": token, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
            )
            if not result.get("success"):
                raise RuntimeError("Failed to set farm_access_token")
            if user_json:
                cdp.send(
                    "Network.setCookie",
                    {"name": "farm_user", "value": user_json, "url": f"{origin}/", "path": "/", "sameSite": "Lax"},
                )
        cdp.send("Page.navigate", {"url": args.url})
        markers = [item.strip() for item in args.markers.split("|") if item.strip()]
        if markers:
            wait_for_markers(cdp, markers)
        time.sleep(max(args.wait_ms, 0) / 1000)
        if args.scroll_y > 0:
            cdp.send("Runtime.evaluate", {"expression": f"window.scrollTo({{ top: {args.scroll_y}, behavior: 'instant' }});", "returnByValue": True})
            time.sleep(0.4)
        if args.focus_text:
            cdp.send(
                "Runtime.evaluate",
                {
                    "expression": f"""
                    (() => {{
                      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                      let node = walker.nextNode();
                      while (node) {{
                        if ((node.textContent || '').includes({json.dumps(args.focus_text)})) {{
                          node.parentElement?.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
                          return true;
                        }}
                        node = walker.nextNode();
                      }}
                      return false;
                    }})()
                    """,
                    "returnByValue": True,
                },
            )
            time.sleep(0.4)
        if args.html_dump:
            html_result = cdp.send("Runtime.evaluate", {"expression": "document.documentElement ? document.documentElement.outerHTML : ''", "returnByValue": True})
            Path(args.html_dump).write_text(str(html_result.get("result", {}).get("value", "")), encoding="utf-8")
        if args.text_dump:
            text_result = cdp.send("Runtime.evaluate", {"expression": "document.body ? document.body.innerText : ''", "returnByValue": True})
            Path(args.text_dump).write_text(str(text_result.get("result", {}).get("value", "")), encoding="utf-8")
        shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        data = str(shot.get("data") or "")
        if not data:
            raise RuntimeError("CDP returned empty screenshot")
        output.write_bytes(base64.b64decode(data))
        print(f"CAPTURE_METHOD=python-cdp")
        print(str(output))
        return 0
    finally:
        if cdp:
            cdp.close()
        if edge_process and edge_process.poll() is None:
            edge_process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
