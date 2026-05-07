from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_ID = "10f6a858-f3e4-467c-87f5-726caa3cc2be"
LATE_ACK_SECONDS = 60 * 60
STATE_STALE_SECONDS = 30 * 60


def parse_stamp(value: str | None) -> datetime | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    candidate = cleaned.replace("Z", "+00:00")
    for parser in (
        lambda item: datetime.fromisoformat(item),
        lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S"),
        lambda item: datetime.strptime(item, "%Y-%m-%dT%H:%M:%S"),
    ):
        try:
            parsed = parser(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def seconds_between(later: str | None, earlier: str | None) -> int | None:
    later_dt = parse_stamp(later)
    earlier_dt = parse_stamp(earlier)
    if later_dt is None or earlier_dt is None:
        return None
    return max(0, int((later_dt - earlier_dt).total_seconds()))


def epoch_to_iso(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return ""
    if numeric > 10_000_000_000:
        numeric = numeric / 1000
    return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit local consumer bridge health for live NPC seats.")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--seats", nargs="+", default=["NPC1", "NPC2", "NPC3"])
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def seat_slug(seat: str) -> str:
    return seat.strip().lower()


def normalize_slug(value: str, fallback: str = "codex-seat") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or fallback


def wrapper_path(root: Path, seat: str) -> Path:
    return root / "scripts" / f"{seat_slug(seat)}-thread-consumer.py"


def state_path(root: Path, seat: str) -> Path:
    return root / "scripts" / f".{wrapper_path(root, seat).stem}-state.json"


def codex_home_root() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def parse_toml_value(raw: str) -> str | int:
    value = raw.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_automation_toml(contents: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for line in contents.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*(.+)$", trimmed)
        if not match:
            continue
        parsed[match.group(1)] = parse_toml_value(match.group(2))
    return parsed


def read_automation_catalog() -> list[dict[str, Any]]:
    automations_root = codex_home_root() / "automations"
    if not automations_root.exists():
        return []
    records: list[dict[str, Any]] = []
    for entry in automations_root.iterdir():
        if not entry.is_dir():
            continue
        file_path = entry / "automation.toml"
        if not file_path.exists():
            continue
        try:
            parsed = parse_automation_toml(file_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        records.append(
            {
                "id": str(parsed.get("id") or entry.name),
                "name": str(parsed.get("name") or entry.name),
                "status": str(parsed.get("status") or "UNKNOWN"),
                "prompt": str(parsed.get("prompt") or ""),
                "target_thread_id": str(parsed.get("target_thread_id") or ""),
                "updated_at": int(parsed["updated_at"]) if isinstance(parsed.get("updated_at"), int) else None,
            }
        )
    return records


def derive_codex_thread_id(source_workstation_id: str) -> str:
    raw = source_workstation_id.strip()
    if raw.lower().startswith("codex-session-"):
        return raw[len("codex-session-") :].strip()
    return raw


def build_heartbeat_automation_id(seat: str) -> str:
    return f"{normalize_slug(seat)}-coop-loop"


def pick_matching_automation(automations: list[dict[str, Any]], seat: str, source_workstation_id: str) -> dict[str, Any] | None:
    thread_id = derive_codex_thread_id(source_workstation_id)
    expected_id = build_heartbeat_automation_id(seat)
    matches = [
        item
        for item in automations
        if item.get("target_thread_id") == thread_id
        or source_workstation_id in str(item.get("prompt") or "")
        or item.get("id") == expected_id
    ]
    matches.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
    return matches[0] if matches else None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def wrapper_defaults(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    id_match = re.search(r'DEFAULT_WORKSTATION_ID\s*=\s*"([^"]+)"', text)
    name_match = re.search(r'DEFAULT_WORKSTATION_NAME\s*=\s*"([^"]+)"', text)
    return {
        "workstation_id": id_match.group(1).strip() if id_match else "",
        "workstation_name": name_match.group(1).strip() if name_match else "",
    }


def live_requirement_snapshot(root: Path, project_id: str, seats: list[str]) -> list[dict[str, Any]]:
    command = [
        sys.executable,
        str(root / "scripts" / "verify-live-npc-requirements.py"),
        "--project-id",
        project_id,
        "--json",
        "--seats",
        *seats,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=str(root),
        check=True,
        capture_output=True,
        text=False,
        env=env,
    )
    return json.loads(completed.stdout.decode("utf-8", errors="replace"))


def posted_statuses_for_requirement(workstation_state: dict[str, Any], requirement_id: str) -> list[dict[str, str]]:
    posted = workstation_state.get("posted") or {}
    results: list[dict[str, str]] = []
    for dedupe_id, payload in posted.items():
        if not isinstance(payload, dict):
            continue
        for status_name, status_payload in payload.items():
            if not isinstance(status_payload, dict):
                continue
            if str(status_payload.get("requirement_id") or "").strip() != requirement_id:
                continue
            results.append(
                {
                    "dedupe_id": str(dedupe_id),
                    "status": str(status_name),
                    "at": str(status_payload.get("at") or ""),
                }
            )
    results.sort(key=lambda item: (item["at"], item["status"]))
    return results


def summarize_bridge(root: Path, seat_result: dict[str, Any]) -> dict[str, Any]:
    seat = str(seat_result.get("seat") or "").strip()
    wrapper = wrapper_path(root, seat)
    state_file = state_path(root, seat)
    defaults = wrapper_defaults(wrapper)
    automations = read_automation_catalog()

    state_payload: dict[str, Any] = {}
    if state_file.exists():
        try:
            state_payload = read_json(state_file)
        except Exception:
            state_payload = {}

    requirement = seat_result.get("requirement") or {}
    signals = seat_result.get("signals") or {}
    current_workstation_id = str(requirement.get("to_agent") or "").strip()
    workstations = (state_payload.get("workstations") or {}) if isinstance(state_payload, dict) else {}
    workstation_state = {}
    if current_workstation_id and current_workstation_id in workstations:
        workstation_state = workstations.get(current_workstation_id) or {}
    elif defaults.get("workstation_id") and defaults["workstation_id"] in workstations:
        workstation_state = workstations.get(defaults["workstation_id"]) or {}
    elif isinstance(workstations, dict) and len(workstations) == 1:
        workstation_state = next(iter(workstations.values())) or {}

    last_selected = workstation_state.get("last_selected") or {}
    current_requirement_id = str(requirement.get("id") or "").strip()
    current_posted = posted_statuses_for_requirement(workstation_state, current_requirement_id) if current_requirement_id else []
    latest_messages = seat_result.get("latest_messages") or {}
    dispatch_message = latest_messages.get("dispatch") or {}
    last_selected_requirement_id = str(last_selected.get("requirement_id") or "")
    selection_lag_seconds = seconds_between(
        str(last_selected.get("at") or ""),
        str(dispatch_message.get("created_at") or ""),
    )
    ack_times = [item["at"] for item in current_posted if item.get("status") == "in_progress"]
    ack_lag_seconds = seconds_between(ack_times[0], str(dispatch_message.get("created_at") or "")) if ack_times else None
    state_updated_at = (
        datetime.fromtimestamp(state_file.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if state_file.exists()
        else ""
    )
    state_age_seconds = seconds_between(datetime.now(timezone.utc).isoformat(), state_updated_at) if state_updated_at else None
    state_stale = state_age_seconds is not None and state_age_seconds >= STATE_STALE_SECONDS
    automation = pick_matching_automation(automations, seat, current_workstation_id) if current_workstation_id else None
    heartbeat_status = str((automation or {}).get("status") or "")
    heartbeat_missing = bool(current_workstation_id and not automation)
    heartbeat_updated_at = (
        epoch_to_iso(automation["updated_at"])
        if automation and automation.get("updated_at")
        else ""
    )
    needs_fresh_state = bool(current_requirement_id and not bool(signals.get("final_done")))
    selection_matches_current_requirement = bool(
        current_requirement_id
        and last_selected_requirement_id
        and current_requirement_id == last_selected_requirement_id
    )
    selection_recovered = bool(
        selection_matches_current_requirement
        and current_posted
        and not state_stale
        and not heartbeat_missing
        and (not heartbeat_status or heartbeat_status == "ACTIVE")
    )
    warnings = list(signals.get("warnings") or [])
    if (
        selection_lag_seconds is not None
        and selection_lag_seconds >= LATE_ACK_SECONDS
        and not selection_recovered
        and "late_selection" not in warnings
    ):
        warnings.append("late_selection")
    if ack_lag_seconds is not None and ack_lag_seconds >= LATE_ACK_SECONDS and "late_bridge_ack" not in warnings:
        warnings.append("late_bridge_ack")
    if heartbeat_missing and "missing_heartbeat" not in warnings:
        warnings.append("missing_heartbeat")
    if heartbeat_status and heartbeat_status != "ACTIVE" and "inactive_heartbeat" not in warnings:
        warnings.append("inactive_heartbeat")
    if needs_fresh_state and not state_file.exists() and "missing_state" not in warnings:
        warnings.append("missing_state")
    if needs_fresh_state and state_stale and "stale_state" not in warnings:
        warnings.append("stale_state")

    return {
        "seat": seat,
        "wrapper_exists": wrapper.exists(),
        "state_exists": state_file.exists(),
        "wrapper_path": str(wrapper),
        "state_path": str(state_file),
        "wrapper_workstation_id": defaults.get("workstation_id", ""),
        "wrapper_workstation_name": defaults.get("workstation_name", ""),
        "live_workstation_id": current_workstation_id,
        "bridge_matches_live": bool(current_workstation_id and defaults.get("workstation_id") == current_workstation_id),
        "heartbeat_id": str((automation or {}).get("id") or ""),
        "heartbeat_status": heartbeat_status,
        "heartbeat_missing": heartbeat_missing,
        "heartbeat_updated_at": heartbeat_updated_at,
        "requirement_id": current_requirement_id,
        "requirement_title": str(requirement.get("display_title") or requirement.get("title") or ""),
        "requirement_status": str(requirement.get("status") or seat_result.get("state") or ""),
        "last_selected_requirement_id": last_selected_requirement_id,
        "last_selected_at": str(last_selected.get("at") or ""),
        "current_requirement_seen": bool(current_posted),
        "selection_matches_current_requirement": selection_matches_current_requirement,
        "selection_recovered": selection_recovered,
        "current_requirement_statuses": current_posted,
        "live_progress_signal": str(signals.get("progress_signal") or ""),
        "live_final_done": bool(signals.get("final_done")),
        "selection_lag_seconds": selection_lag_seconds,
        "ack_lag_seconds": ack_lag_seconds,
        "state_updated_at": state_updated_at,
        "state_age_seconds": state_age_seconds,
        "state_stale": state_stale,
        "live_health": str(signals.get("health") or ""),
        "title_dirty": bool(requirement.get("title_dirty")),
        "warnings": warnings,
    }


def recovery_hint_for_bridge(bridge: dict[str, Any]) -> str:
    seat = str(bridge.get("seat") or "当前 NPC")
    heartbeat_status = str(bridge.get("heartbeat_status") or "")
    requirement_status = str(bridge.get("requirement_status") or "").lower()
    if bridge.get("live_final_done") or requirement_status in {"done", "completed", "closed", "resolved"}:
        return "当前桥接链路没有额外恢复动作。"
    if bridge.get("heartbeat_missing"):
        return f"补 {seat} 的 heartbeat，或重新校准自治桥。"
    if heartbeat_status and heartbeat_status != "ACTIVE":
        return f"把 {seat} 的 heartbeat 恢复为 ACTIVE。"
    if not bridge.get("wrapper_exists"):
        return f"补 {seat} 的 consumer wrapper。"
    if bridge.get("requirement_id") and not bridge.get("state_exists"):
        return f"让 {seat} 跑一轮本地 consumer，先生成首个 state 文件。"
    if bridge.get("requirement_id") and bridge.get("state_stale"):
        return f"唤醒 {seat} 所在线程或重跑本地 consumer，刷新本地 state。"
    if bridge.get("requirement_id") and not bridge.get("current_requirement_seen"):
        return f"确认 {seat} 已选中当前 requirement，并补最小回执。"
    if bridge.get("requirement_id") and not bridge.get("live_final_done"):
        return f"继续推进 {seat} 当前 requirement，直到最终回复回平台。"
    return "当前桥接链路没有额外恢复动作。"


def print_human(requirements: list[dict[str, Any]], bridges: list[dict[str, Any]]) -> None:
    bridge_by_seat = {item["seat"]: item for item in bridges}
    print("Live NPC bridge audit")
    print("")
    for seat_result in requirements:
        seat = str(seat_result.get("seat") or "")
        bridge = bridge_by_seat.get(seat, {})
        print(f"[{seat}]")
        print(
            "  bridge: "
            f"wrapper={'yes' if bridge.get('wrapper_exists') else 'no'}, "
            f"state={'yes' if bridge.get('state_exists') else 'no'}, "
            f"matches_live={'yes' if bridge.get('bridge_matches_live') else 'no'}, "
            f"heartbeat={bridge.get('heartbeat_status') or ('missing' if bridge.get('heartbeat_missing') else '-')}"
        )
        print(
            "  live: "
            f"{bridge.get('requirement_id') or '-'} | {bridge.get('requirement_status') or seat_result.get('state')} | "
            f"{bridge.get('requirement_title') or '-'}"
        )
        print(
            "  consumer: "
            f"last_selected={bridge.get('last_selected_requirement_id') or '-'} @ {bridge.get('last_selected_at') or '-'}"
        )
        print(
            "  state: "
            f"updated={bridge.get('state_updated_at') or '-'}, "
            f"age_s={bridge.get('state_age_seconds') if bridge.get('state_age_seconds') is not None else '-'}, "
            f"stale={'yes' if bridge.get('state_stale') else 'no'}"
        )
        statuses = bridge.get("current_requirement_statuses") or []
        compact = ", ".join(f"{item['status']}@{item['at']}" for item in statuses) if statuses else "-"
        print(
            "  current_requirement: "
            f"seen={'yes' if bridge.get('current_requirement_seen') else 'no'}, posted={compact}"
        )
        print(
            "  live_signals: "
            f"progress={bridge.get('live_progress_signal') or '-'}, "
            f"final_done={'yes' if bridge.get('live_final_done') else 'no'}"
        )
        print(
            "  health: "
            f"{bridge.get('live_health') or '-'}, "
            f"title_dirty={'yes' if bridge.get('title_dirty') else 'no'}, "
            f"selection_lag_s={bridge.get('selection_lag_seconds') if bridge.get('selection_lag_seconds') is not None else '-'}, "
            f"ack_lag_s={bridge.get('ack_lag_seconds') if bridge.get('ack_lag_seconds') is not None else '-'}"
        )
        print(f"  warnings: {', '.join(bridge.get('warnings') or []) or '-'}")
        print(f"  next_step: {recovery_hint_for_bridge(bridge)}")
        print("")


def main() -> int:
    args = parse_args()
    root = repo_root()
    requirements = live_requirement_snapshot(root, args.project_id, args.seats)
    bridges = [summarize_bridge(root, item) for item in requirements]
    if args.json:
        print(json.dumps(bridges, ensure_ascii=False, indent=2))
    else:
        print_human(requirements, bridges)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
