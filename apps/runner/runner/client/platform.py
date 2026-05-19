from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


def _encode_header_value(value: str) -> tuple[str, bool]:
    """Return (header_value, was_encoded). urllib encodes header values as latin-1
    so non-ASCII identifiers (e.g. 中文 workstation_id) explode at request time.
    Percent-encode the value when it has non-ASCII bytes; receiver decodes back."""
    if not value:
        return "", False
    try:
        value.encode("ascii")
        return value, False
    except UnicodeEncodeError:
        return urllib.parse.quote(value, safe=""), True


@dataclass(frozen=True)
class PlatformClient:
    base_url: str
    runner_id: str
    runner_token: str = ""

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout_s: int = 10) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        runner_id_value, runner_id_encoded = _encode_header_value(self.runner_id)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Runner-Id": runner_id_value,
        }
        if runner_id_encoded:
            headers["X-Runner-Id-Encoding"] = "percent"
        if self.runner_token and self.runner_token != "change-me":
            headers["X-Runner-Registration-Token"] = self.runner_token
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {raw}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error {method} {path}: {e}") from e

    def register(self, runner_id: str, runner_name: str, capabilities: list[str], hardware_access: bool) -> Any:
        return self._request(
            "POST",
            "/api/runners/register",
            {
                "runner_id": runner_id,
                "runner_name": runner_name,
                "capabilities": capabilities,
                "hardware_access": hardware_access,
            },
        )

    def heartbeat(self, runner_id: str) -> Any:
        return self._request("POST", "/api/runners/heartbeat", {"runner_id": runner_id})

    def sync_device_interfaces(
        self,
        runner_id: str,
        *,
        project_id: str,
        computer_node_id: str,
        scan: dict[str, Any],
    ) -> Any:
        payload = {
            **scan,
            "project_id": project_id,
            "computer_node_id": computer_node_id,
        }
        return self._request(
            "POST",
            f"/api/runners/{runner_id}/device-interfaces/sync",
            payload,
            timeout_s=20,
        )

    def fetch_next_task(self, runner_id: str) -> dict[str, Any] | None:
        # First-version placeholder endpoint. Backend may not implement this yet.
        # Return None if not found / not supported.
        try:
            resp = self._request("GET", f"/api/runners/{runner_id}/next-task", None)
        except RuntimeError as e:
            msg = str(e)
            if "HTTP 404" in msg or "HTTP 405" in msg:
                return None
            return None
        if not resp:
            return None
        # Expect { "data": { ...task... } } or { ...task... }
        if isinstance(resp, dict) and "data" in resp and isinstance(resp["data"], dict):
            return resp["data"]
        if isinstance(resp, dict):
            return resp
        return None

    def fetch_runner_inbox(self, runner_id: str, *, status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        path = f"/api/runners/{runner_id}/inbox?limit={max(1, min(limit, 50))}"
        if status:
            path += f"&status={status}"
        try:
            resp = self._request("GET", path, None, timeout_s=10)
        except RuntimeError as e:
            msg = str(e)
            if "HTTP 404" in msg or "HTTP 405" in msg:
                return []
            return []
        if isinstance(resp, dict) and isinstance(resp.get("data"), list):
            return [item for item in resp["data"] if isinstance(item, dict)]
        if isinstance(resp, list):
            return [item for item in resp if isinstance(item, dict)]
        return []

    def ack_runner_message(self, runner_id: str, message_id: str, note: str | None = None) -> Any:
        return self._request(
            "POST",
            f"/api/runners/{runner_id}/messages/{message_id}/ack",
            {"note": note},
            timeout_s=10,
        )

    def complete_runner_message(
        self,
        runner_id: str,
        message_id: str,
        *,
        result_status: str,
        note: str | None = None,
    ) -> Any:
        return self._request(
            "POST",
            f"/api/runners/{runner_id}/messages/{message_id}/complete",
            {"result_status": result_status, "note": note},
            timeout_s=20,
        )

    def post_task_log(self, task_id: str, level: str, message: str) -> None:
        # Best-effort. If backend doesn't support yet, ignore.
        try:
            self._request(
                "POST",
                f"/api/tasks/{task_id}/logs",
                {"level": level, "message": message},
                timeout_s=10,
            )
        except Exception:
            return

    def post_task_result(self, task_id: str, result: dict[str, Any]) -> None:
        try:
            self._request("POST", f"/api/tasks/{task_id}/result", {"result": result}, timeout_s=20)
        except Exception:
            return
