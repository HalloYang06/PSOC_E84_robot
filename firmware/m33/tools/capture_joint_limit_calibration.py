from __future__ import annotations

import argparse
import csv
import json
import math
import re
import threading
import time
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "tmp"
PRIVATE_POSITION_PERIOD_RAD = 25.14
JOINT4_GEAR_RATIO = 7.1844

_MOTOR_FB_RE = re.compile(
    r"MOTOR\[(?P<joint>\d+)\]:.*?pos_mrad=(?P<pos>-?\d+)"
    r".*?vel_mrad_s=(?P<vel>-?\d+).*?tor_mNm=(?P<torque>-?\d+)"
    r".*?tick=(?P<tick>\d+)"
)


class FeedbackSample(NamedTuple):
    tick: int
    raw_rad: float
    velocity_rad_s: float
    torque_nm: float


def parse_fresh_feedback(text: str, *, joint: int) -> list[FeedbackSample]:
    samples: list[FeedbackSample] = []
    seen_ticks: set[int] = set()
    for match in _MOTOR_FB_RE.finditer(text):
        if int(match.group("joint")) != joint:
            continue
        tick = int(match.group("tick"))
        if tick == 0 or tick in seen_ticks:
            continue
        seen_ticks.add(tick)
        samples.append(
            FeedbackSample(
                tick=tick,
                raw_rad=int(match.group("pos")) / 1000.0,
                velocity_rad_s=int(match.group("vel")) / 1000.0,
                torque_nm=int(match.group("torque")) / 1000.0,
            )
        )
    return samples


class FeedbackStreamParser:
    def __init__(self, *, joint: int) -> None:
        self.joint = joint
        self.buffer = ""

    def feed(self, text: str) -> list[FeedbackSample]:
        self.buffer += text
        lines = self.buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self.buffer = lines.pop()
        else:
            self.buffer = ""
        if len(self.buffer) > 4096:
            self.buffer = self.buffer[-4096:]
        return parse_fresh_feedback("".join(lines), joint=self.joint)


def unwrap_positions(raw_positions: list[float], *, period_rad: float) -> list[float]:
    if not raw_positions:
        return []
    if period_rad <= 0.0:
        raise ValueError("period_rad must be positive")

    half_period = period_rad / 2.0
    unwrapped = [raw_positions[0]]
    previous_raw = raw_positions[0]
    for raw in raw_positions[1:]:
        delta = raw - previous_raw
        if delta > half_period:
            delta -= period_rad
        elif delta < -half_period:
            delta += period_rad
        unwrapped.append(unwrapped[-1] + delta)
        previous_raw = raw
    return unwrapped


def build_limit_summary(
    *,
    lower_start_rad: float,
    upper_rad: float,
    lower_return_rad: float,
    gear_ratio: float,
    repeat_tolerance_motor_rad: float,
) -> dict[str, float | bool | str]:
    if gear_ratio <= 0.0:
        raise ValueError("gear_ratio must be positive")
    repeat_error = abs(lower_return_rad - lower_start_rad)
    repeatable = repeat_error <= repeat_tolerance_motor_rad
    validation_error = ""
    if not repeatable:
        validation_error = (
            "lower-limit repeat error "
            f"{repeat_error:.6f} rad exceeds {repeat_tolerance_motor_rad:.6f} rad"
        )
    motor_travel = abs(upper_rad - lower_start_rad)
    return {
        "lower_start_motor_rad": lower_start_rad,
        "upper_motor_rad": upper_rad,
        "lower_return_motor_rad": lower_return_rad,
        "lower_repeat_error_motor_rad": repeat_error,
        "motor_travel_rad": motor_travel,
        "joint_travel_rad": motor_travel / gear_ratio,
        "joint_travel_deg": math.degrees(motor_travel / gear_ratio),
        "repeatable": repeatable,
        "validation_error": validation_error,
    }


def select_endpoint_position(
    positions: list[float],
    velocities: list[float],
    *,
    bounds: tuple[int, int],
    max_abs_velocity_rad_s: float,
    edge: str = "last",
) -> float:
    start, end = bounds
    if start < 0 or end > len(positions) or end > len(velocities) or start >= end:
        raise ValueError("endpoint sample bounds are invalid")
    if edge not in ("first", "last"):
        raise ValueError("endpoint edge must be first or last")
    endpoint_index = start if edge == "first" else end - 1
    endpoint_velocity = velocities[endpoint_index]
    if abs(endpoint_velocity) > max_abs_velocity_rad_s:
        raise ValueError(
            "endpoint velocity "
            f"{endpoint_velocity:.6f} rad/s exceeds {max_abs_velocity_rad_s:.6f} rad/s"
        )
    return positions[endpoint_index]


def validate_stage_sample_count(*, stage: str, count: int) -> None:
    if count < 1:
        raise RuntimeError(
            f"no new feedback event for {stage}; move the joint during this stage "
            "before pressing Enter"
        )


class SerialFeedbackCollector:
    def __init__(
        self,
        *,
        port_name: str,
        baud: int,
        joint: int,
        poll_interval_sec: float,
        stale_timeout_sec: float,
    ) -> None:
        import serial  # type: ignore[import-untyped]

        self.joint = joint
        self.poll_interval_sec = poll_interval_sec
        self.stale_timeout_sec = stale_timeout_sec
        self.port = serial.Serial(
            port_name,
            baudrate=baud,
            timeout=0.05,
            write_timeout=0.5,
        )
        self.last_tick: int | None = None
        self.last_fresh_monotonic = time.monotonic()
        self.last_rearm_monotonic = 0.0
        self.rows: list[dict[str, float | int | str]] = []
        self.started_monotonic = time.monotonic()
        self.feedback_parser = FeedbackStreamParser(joint=joint)

        time.sleep(0.3)
        self.port.read_all()
        self._send("rehab stop")
        time.sleep(0.2)
        self.port.read_all()
        self._rearm_report()

    def close(self) -> None:
        self.port.close()

    def _send(self, command: str) -> None:
        self.port.write((command + "\n").encode("ascii"))

    def _rearm_report(self) -> None:
        self._send(f"cmd_motor_report {self.joint} 1")
        self.last_rearm_monotonic = time.monotonic()

    def poll(self, *, stage: str) -> int:
        self._send(f"cmd_motor_fb {self.joint}")
        time.sleep(self.poll_interval_sec)
        text = self.port.read_all().decode("utf-8", errors="replace")
        accepted = 0
        for sample in self.feedback_parser.feed(text):
            if sample.tick == self.last_tick:
                continue
            self.last_tick = sample.tick
            self.last_fresh_monotonic = time.monotonic()
            self.rows.append(
                {
                    "host_ms": int(
                        (self.last_fresh_monotonic - self.started_monotonic) * 1000.0
                    ),
                    "stage": stage,
                    "tick": sample.tick,
                    "raw_rad": sample.raw_rad,
                    "velocity_rad_s": sample.velocity_rad_s,
                    "torque_nm": sample.torque_nm,
                }
            )
            accepted += 1

        now = time.monotonic()
        stale_age = now - self.last_fresh_monotonic
        if stale_age > 0.5 and (now - self.last_rearm_monotonic) > 0.5:
            self._rearm_report()
        return accepted

    def prime(self) -> None:
        deadline = time.monotonic() + self.stale_timeout_sec
        while self.last_tick is None and time.monotonic() < deadline:
            self.poll(stage="priming")
        if self.last_tick is None:
            raise RuntimeError(
                f"joint {self.joint} has no cached feedback to establish a tick baseline"
            )

    def capture_until_enter(
        self, *, stage: str, prompt: str, timeout_sec: float
    ) -> tuple[int, int]:
        start = len(self.rows)
        done = threading.Event()

        def wait_for_enter() -> None:
            input(prompt)
            done.set()

        threading.Thread(target=wait_for_enter, daemon=True).start()
        deadline = time.monotonic() + timeout_sec
        while not done.is_set():
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{stage} timed out after {timeout_sec:.1f}s")
            self.poll(stage=stage)
        for _ in range(3):
            self.poll(stage=stage)
        end = len(self.rows)
        validate_stage_sample_count(stage=stage, count=end - start)
        stale_age = time.monotonic() - self.last_fresh_monotonic
        if stale_age > self.stale_timeout_sec:
            raise RuntimeError(
                f"joint {self.joint} feedback was already stale for {stale_age:.2f}s "
                f"when {stage} was marked"
            )
        return start, end


def _write_outputs(
    *,
    output_dir: Path,
    joint: int,
    rows: list[dict[str, float | int | str]],
    summary: dict[str, object],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"joint{joint}_limit_calibration_{stamp}.csv"
    json_path = output_dir / f"joint{joint}_limit_calibration_{stamp}.json"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return csv_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only interactive joint limit calibration. Sends stop/report/feedback "
            "commands only and rejects stale or non-repeatable captures."
        )
    )
    parser.add_argument("--joint", type=int, default=4)
    parser.add_argument("--port", default="COM16")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--gear-ratio", type=float, default=JOINT4_GEAR_RATIO)
    parser.add_argument("--period-rad", type=float, default=PRIVATE_POSITION_PERIOD_RAD)
    parser.add_argument("--poll-ms", type=float, default=80.0)
    parser.add_argument("--motion-timeout-sec", type=float, default=120.0)
    parser.add_argument("--stale-timeout-sec", type=float, default=2.0)
    parser.add_argument("--repeat-tolerance-rad", type=float, default=0.20)
    parser.add_argument("--endpoint-max-velocity-rad-s", type=float, default=0.20)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    collector = SerialFeedbackCollector(
        port_name=args.port,
        baud=args.baud,
        joint=args.joint,
        poll_interval_sec=args.poll_ms / 1000.0,
        stale_timeout_sec=args.stale_timeout_sec,
    )
    try:
        collector.prime()
        lower_start_bounds = collector.capture_until_enter(
            stage="lower_start",
            prompt="Place the joint at the lower limit, hold it still, then press Enter: ",
            timeout_sec=args.motion_timeout_sec,
        )
        upper_bounds = collector.capture_until_enter(
            stage="moving_to_upper",
            prompt="Move slowly to the upper limit, hold it, then press Enter: ",
            timeout_sec=args.motion_timeout_sec,
        )
        lower_return_bounds = collector.capture_until_enter(
            stage="returning_to_lower",
            prompt="Move slowly back to the lower limit, hold it, then press Enter: ",
            timeout_sec=args.motion_timeout_sec,
        )
    finally:
        collector.close()

    raw_positions = [float(row["raw_rad"]) for row in collector.rows]
    unwrapped = unwrap_positions(raw_positions, period_rad=args.period_rad)
    for row, unwrapped_rad in zip(collector.rows, unwrapped):
        row["unwrapped_rad"] = round(unwrapped_rad, 6)

    velocities = [float(row["velocity_rad_s"]) for row in collector.rows]
    lower_start = select_endpoint_position(
        unwrapped,
        velocities,
        bounds=lower_start_bounds,
        max_abs_velocity_rad_s=args.endpoint_max_velocity_rad_s,
        edge="first",
    )
    upper = select_endpoint_position(
        unwrapped,
        velocities,
        bounds=upper_bounds,
        max_abs_velocity_rad_s=args.endpoint_max_velocity_rad_s,
    )
    lower_return = select_endpoint_position(
        unwrapped,
        velocities,
        bounds=lower_return_bounds,
        max_abs_velocity_rad_s=args.endpoint_max_velocity_rad_s,
    )
    summary: dict[str, object] = {
        "schema_version": "m33_joint_limit_calibration_v1",
        "joint": args.joint,
        "sample_count": len(collector.rows),
        "position_period_rad": args.period_rad,
        "gear_ratio": args.gear_ratio,
        "control_boundary": "read_only_no_motor_actuation",
    }
    summary.update(
        build_limit_summary(
            lower_start_rad=lower_start,
            upper_rad=upper,
            lower_return_rad=lower_return,
            gear_ratio=args.gear_ratio,
            repeat_tolerance_motor_rad=args.repeat_tolerance_rad,
        )
    )
    csv_path, json_path = _write_outputs(
        output_dir=args.output_dir,
        joint=args.joint,
        rows=collector.rows,
        summary=summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"csv={csv_path}")
    print(f"json={json_path}")
    if not bool(summary["repeatable"]):
        print(f"INVALID: {summary['validation_error']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
