#!/usr/bin/env python3
"""Collect STM32F103/C8T6 sensor CAN data into CSV files.

The legacy firmware path uses standard CAN frames:
  0x7C0 M33/host -> F103 control
  0x7C1 F103 -> M33/host ACK
  0x7C2 F103 -> M33/host sensor data
  0x7C3 F103 -> M33/host health data

The emg3-motor protocol keeps 0x7C1/0x7C3 unchanged and interprets 0x7C2
as four raw ADC channels. The first three are the EMG model inputs
(biceps/triceps/anterior deltoid); adc3 is retained for debug and is unused
when the fourth electrode input is not connected. It also records M33 motor
telemetry from 0x330..0x337 and the training-only 0x340/0x341 slot-pair frames.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import math
import queue
import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Iterable, Iterator, List, Optional, Sequence, TextIO, Tuple


PROTOCOL_LEGACY = "legacy"
PROTOCOL_EMG3_MOTOR = "emg3-motor"

F103_CTRL_ID = 0x7C0
F103_ACK_ID = 0x7C1
F103_SENSOR_ID = 0x7C2
F103_HEALTH_ID = 0x7C3

F103_CMD_SET_RATE = 0x01
F103_CMD_START_STREAM = 0x03
F103_CMD_STOP_STREAM = 0x04
F103_RATE_TARGET_CAN_TX = 0x02

M33_MOTOR_STATUS_BASE = 0x330
M33_MOTOR_STATUS_COUNT = 8
M33_MOTOR_STATUS_MARKER = 0xB3
M33_MOTOR_STATUS_FLAG_FAULT = 0x02
M33_MOTOR_STATUS_FLAG_LIMITED = 0x04
M33_MOTOR_STATUS_FLAG_STALE = 0x10

M33_TRAINING_KIN_BASE = 0x340
M33_TRAINING_EFFORT_BASE = 0x341
M33_TRAINING_SLOT_COUNT = 5
M33_TRAINING_KIN_MARKER = 0xD0
M33_TRAINING_EFFORT_MARKER = 0xD1
M33_TRAINING_FLAG_FRESH = 0x01
M33_TRAINING_FLAG_FAULT = 0x02
M33_TRAINING_FLAG_SATURATED = 0x08
M33_TRAINING_FLAG_STALE = 0x10

DEFAULT_EMG3_LABELS = ("rest", "elbow_flex", "elbow_extend", "shoulder_flex")
MANUAL_LABEL_SHORTCUTS = {
    "1": "rest",
    "2": "elbow_flex",
    "3": "elbow_extend",
    "4": "shoulder_flex",
}
DEFAULT_EMG3_SAMPLE_HZ = 50
DEFAULT_EMG3_WINDOW_MS = 300
DEFAULT_EMG3_STEP_MS = 100
DEFAULT_EMG3_STALE_AFTER_MS = 250
SERIAL_PORT_AUTO = "auto"
INFINEON_SERIAL_KEYWORDS = (
    ("kitprog3", 900),
    ("kitprog", 800),
    ("cypress", 400),
    ("infineon", 400),
    ("cmsis-dap", 200),
    ("daplink", 200),
)
INFINEON_SERIAL_VIDPID_MARKERS = ("04b4:f155", "vid:pid=04b4:f155", "vid_04b4&pid_f155")

DEFAULT_SLOT_PREFIXES = {
    0: "shoulder",
    1: "elbow",
}

RAW_COLUMNS = [
    "timestamp",
    "timestamp_iso",
    "rel_ms",
    "channel",
    "can_id",
    "source",
    "m33_ms",
    "kind",
    "session_id",
    "subject_id",
    "trial_id",
    "trial_index",
    "label",
    "raw_hex",
    "emg_raw",
    "emg_filt",
    "emg_abs",
    "hr_raw",
    "hr_bpm",
    "flags",
    "adc0",
    "adc1",
    "adc2",
    "adc3",
    "emg_biceps",
    "emg_triceps",
    "emg_ant_deltoid",
    "emg_flags",
    "emg_seq",
    "node_state",
    "node_err_cnt",
    "node_q_fill",
    "ack_cmd",
    "ack_seq",
    "ack_status",
    "motor_slot",
    "ros_slot",
    "m33_joint_id",
    "motor_id",
    "motor_seq",
    "motor_flags",
    "motor_fresh",
    "motor_fault",
    "motor_saturated",
    "motor_pos_mrad",
    "motor_vel_mrad_s",
    "motor_torque_mNm",
    "motor_temp_c",
    "output_current_cmd_a",
    "limit_current_a",
    "shoulder_pos_mrad",
    "shoulder_vel_mrad_s",
    "shoulder_torque_mNm",
    "shoulder_temp_c",
    "shoulder_output_current_cmd_a",
    "shoulder_limit_current_a",
    "shoulder_saturated",
    "shoulder_fresh",
    "shoulder_fault",
    "shoulder_stale",
    "elbow_pos_mrad",
    "elbow_vel_mrad_s",
    "elbow_torque_mNm",
    "elbow_temp_c",
    "elbow_output_current_cmd_a",
    "elbow_limit_current_a",
    "elbow_saturated",
    "elbow_fresh",
    "elbow_fault",
    "elbow_stale",
    "target_shoulder_output_current_cmd_a",
    "target_shoulder_vel_mrad_s",
    "target_shoulder_pos_mrad",
    "target_elbow_output_current_cmd_a",
    "target_elbow_vel_mrad_s",
    "target_elbow_pos_mrad",
]

WINDOW_COLUMNS = [
    "session_id",
    "subject_id",
    "trial_id",
    "label",
    "window_index",
    "window_start_ms",
    "window_end_ms",
    "sample_count",
    "emg_raw_mean",
    "emg_filt_mean",
    "emg_abs_mean",
    "emg_rms",
    "hr_raw_mean",
    "hr_bpm_mean",
    "flags_or",
    "emg_biceps_mean",
    "emg_biceps_std",
    "emg_biceps_min",
    "emg_biceps_max",
    "emg_biceps_mav",
    "emg_biceps_rms",
    "emg_triceps_mean",
    "emg_triceps_std",
    "emg_triceps_min",
    "emg_triceps_max",
    "emg_triceps_mav",
    "emg_triceps_rms",
    "emg_ant_deltoid_mean",
    "emg_ant_deltoid_std",
    "emg_ant_deltoid_min",
    "emg_ant_deltoid_max",
    "emg_ant_deltoid_mav",
    "emg_ant_deltoid_rms",
    "shoulder_pos_mrad_mean",
    "shoulder_vel_mrad_s_mean",
    "shoulder_torque_mNm_mean",
    "shoulder_temp_c_mean",
    "shoulder_output_current_cmd_a_mean",
    "shoulder_limit_current_a_mean",
    "elbow_pos_mrad_mean",
    "elbow_vel_mrad_s_mean",
    "elbow_torque_mNm_mean",
    "elbow_temp_c_mean",
    "elbow_output_current_cmd_a_mean",
    "elbow_limit_current_a_mean",
    "target_shoulder_output_current_cmd_a_mean",
    "target_shoulder_vel_mrad_s_mean",
    "target_shoulder_pos_mrad_mean",
    "target_elbow_output_current_cmd_a_mean",
    "target_elbow_vel_mrad_s_mean",
    "target_elbow_pos_mrad_mean",
    "stale_count",
    "fault_count",
    "saturated_count",
]

TRIAL_COLUMNS = [
    "session_id",
    "subject_id",
    "trial_index",
    "trial_id",
    "label",
    "label_trial_index",
    "prepare_s",
    "record_s",
    "rest_s",
    "expected_samples",
]

_CANDUMP_LOG_RE = re.compile(
    r"^\((?P<timestamp>\d+(?:\.\d+)?)\)\s+"
    r"(?P<channel>\S+)\s+"
    r"(?P<can_id>[0-9A-Fa-f]+)#(?P<data>[0-9A-Fa-f]*)"
)

_CANDUMP_TEXT_RE = re.compile(
    r"^(?P<channel>\S+)\s+"
    r"(?P<can_id>[0-9A-Fa-f]+)\s+"
    r"\[(?P<len>\d+)\]\s+"
    r"(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)"
)


@dataclass(frozen=True)
class CanFrame:
    timestamp: float
    channel: str
    arbitration_id: int
    data: bytes


@dataclass(frozen=True)
class GuidedTrial:
    trial_index: int
    label: str
    label_trial_index: int
    prepare_s: float
    record_s: float
    rest_s: float
    expected_samples: int

    @property
    def trial_id(self) -> str:
        return f"{self.trial_index:03d}_{self.label}_{self.label_trial_index:02d}"


@dataclass(frozen=True)
class GuidedTrialPlan:
    labels: Tuple[str, ...]
    trials: Tuple[GuidedTrial, ...]
    prepare_s: float
    record_s: float
    rest_s: float
    sample_hz: int
    window_ms: int
    step_ms: int
    expected_raw_samples: int


class ManualTrialState:
    def __init__(self) -> None:
        self._next_trial_index = 1
        self._label_counts: Dict[str, int] = {}

    def start_trial(self, label: str) -> GuidedTrial:
        clean_label = _resolve_manual_label(label)
        if not clean_label:
            raise ValueError("label must not be empty")

        label_trial_index = self._label_counts.get(clean_label, 0) + 1
        self._label_counts[clean_label] = label_trial_index
        trial = GuidedTrial(
            trial_index=self._next_trial_index,
            label=clean_label,
            label_trial_index=label_trial_index,
            prepare_s=0.0,
            record_s=0.0,
            rest_s=0.0,
            expected_samples=0,
        )
        self._next_trial_index += 1
        return trial


class ManualDataSourceStopped(RuntimeError):
    pass


class CsvRowWriter:
    def __init__(self, output: TextIO, columns: List[str]):
        self._columns = columns
        self._writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        self._writer.writeheader()
        self._output = output

    def write(self, row: Dict[str, object]) -> None:
        stable_row = {column: row.get(column, "") for column in self._columns}
        self._writer.writerow(stable_row)
        self._output.flush()


def _resolve_manual_label(label: str) -> str:
    clean_label = label.strip()
    return MANUAL_LABEL_SHORTCUTS.get(clean_label, clean_label)


class WindowAggregator:
    def __init__(self, window_ms: int, step_ms: int):
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        if step_ms <= 0:
            raise ValueError("step_ms must be positive")

        self.window_ms = window_ms
        self.step_ms = step_ms
        self._samples: Deque[Dict[str, object]] = deque()
        self._next_start_ms: Optional[int] = None
        self._window_index = 0

    def add_sensor_row(self, row: Dict[str, object]) -> List[Dict[str, object]]:
        rel_ms = int(row["rel_ms"])
        if self._next_start_ms is None:
            self._next_start_ms = (rel_ms // self.step_ms) * self.step_ms

        self._samples.append(row)
        emitted: List[Dict[str, object]] = []

        assert self._next_start_ms is not None
        while rel_ms >= self._next_start_ms + self.window_ms:
            start_ms = self._next_start_ms
            end_ms = start_ms + self.window_ms
            window_samples = [
                sample
                for sample in self._samples
                if start_ms <= int(sample["rel_ms"]) < end_ms
            ]
            if window_samples:
                emitted.append(self._build_window(start_ms, end_ms, window_samples))

            self._next_start_ms += self.step_ms
            while self._samples and int(self._samples[0]["rel_ms"]) < self._next_start_ms:
                self._samples.popleft()

        return emitted

    def _build_window(
        self,
        start_ms: int,
        end_ms: int,
        samples: List[Dict[str, object]],
    ) -> Dict[str, object]:
        emg_raw_values = [_as_float(sample.get("emg_raw")) for sample in samples]
        emg_filt_values = [_as_float(sample.get("emg_filt")) for sample in samples]
        hr_raw_values = [_as_float(sample.get("hr_raw")) for sample in samples]
        hr_bpm_values = [_as_float(sample.get("hr_bpm")) for sample in samples]
        flags_or = 0
        for sample in samples:
            flags_or |= int(sample.get("flags") or 0)

        row = {
            "session_id": samples[0].get("session_id", ""),
            "subject_id": samples[0].get("subject_id", ""),
            "trial_id": samples[0].get("trial_id", ""),
            "label": samples[0].get("label", ""),
            "window_index": self._window_index,
            "window_start_ms": start_ms,
            "window_end_ms": end_ms,
            "sample_count": len(samples),
            "emg_raw_mean": _mean(emg_raw_values),
            "emg_filt_mean": _mean(emg_filt_values),
            "emg_abs_mean": _mean([abs(value) for value in emg_filt_values]),
            "emg_rms": math.sqrt(_mean([value * value for value in emg_filt_values])),
            "hr_raw_mean": _mean(hr_raw_values),
            "hr_bpm_mean": _mean(hr_bpm_values),
            "flags_or": flags_or,
        }
        self._window_index += 1
        return row


class Emg3MotorAligner:
    def __init__(
        self,
        stale_after_ms: int = DEFAULT_EMG3_STALE_AFTER_MS,
        slot_prefixes: Optional[Dict[int, str]] = None,
    ):
        self.stale_after_ms = stale_after_ms
        self.slot_prefixes = dict(slot_prefixes or DEFAULT_SLOT_PREFIXES)
        self._states: Dict[int, Dict[str, object]] = {}

    def observe(self, row: Dict[str, object]) -> None:
        kind = str(row.get("kind", ""))
        if not kind.startswith("motor_"):
            return

        slot = _row_slot(row)
        if slot is None:
            return

        state = self._states.setdefault(slot, {})
        rel_ms = row.get("rel_ms")
        if rel_ms not in (None, ""):
            state["last_rel_ms"] = int(rel_ms)

        for field in (
            "motor_pos_mrad",
            "motor_vel_mrad_s",
            "motor_torque_mNm",
            "motor_temp_c",
            "output_current_cmd_a",
            "limit_current_a",
            "motor_saturated",
            "motor_fresh",
            "motor_fault",
            "motor_flags",
            "m33_joint_id",
            "motor_id",
        ):
            if field in row and row[field] != "":
                state[field] = row[field]

    def align_sensor_row(self, row: Dict[str, object]) -> Dict[str, object]:
        aligned = dict(row)
        rel_ms = int(row.get("rel_ms") or 0)

        for slot, prefix in self.slot_prefixes.items():
            state = self._states.get(slot)
            stale = True
            fresh = False
            if state is not None and "last_rel_ms" in state:
                age_ms = rel_ms - int(state["last_rel_ms"])
                stale = age_ms > self.stale_after_ms
                fresh = bool(state.get("motor_fresh", True)) and not stale

            aligned[f"{prefix}_pos_mrad"] = _state_value(state, "motor_pos_mrad")
            aligned[f"{prefix}_vel_mrad_s"] = _state_value(state, "motor_vel_mrad_s")
            aligned[f"{prefix}_torque_mNm"] = _state_value(state, "motor_torque_mNm")
            aligned[f"{prefix}_temp_c"] = _state_value(state, "motor_temp_c")
            aligned[f"{prefix}_output_current_cmd_a"] = _state_value(state, "output_current_cmd_a")
            aligned[f"{prefix}_limit_current_a"] = _state_value(state, "limit_current_a")
            aligned[f"{prefix}_saturated"] = bool(_state_value(state, "motor_saturated") or False)
            aligned[f"{prefix}_fault"] = bool(_state_value(state, "motor_fault") or False)
            aligned[f"{prefix}_stale"] = stale
            aligned[f"{prefix}_fresh"] = fresh

        _add_target_aliases(aligned)
        return aligned


class Emg3MotorWindowAggregator:
    def __init__(self, window_ms: int, step_ms: int):
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        if step_ms <= 0:
            raise ValueError("step_ms must be positive")

        self.window_ms = window_ms
        self.step_ms = step_ms
        self._samples: Deque[Dict[str, object]] = deque()
        self._next_start_ms: Optional[int] = None
        self._window_index = 0

    def add_sensor_row(self, row: Dict[str, object]) -> List[Dict[str, object]]:
        rel_ms = int(row["rel_ms"])
        if self._next_start_ms is None:
            self._next_start_ms = (rel_ms // self.step_ms) * self.step_ms

        self._samples.append(row)
        emitted: List[Dict[str, object]] = []

        assert self._next_start_ms is not None
        while rel_ms >= self._next_start_ms + self.window_ms:
            start_ms = self._next_start_ms
            end_ms = start_ms + self.window_ms
            window_samples = [
                sample
                for sample in self._samples
                if start_ms <= int(sample["rel_ms"]) < end_ms
            ]
            if window_samples:
                emitted.append(self._build_window(start_ms, end_ms, window_samples))

            self._next_start_ms += self.step_ms
            while self._samples and int(self._samples[0]["rel_ms"]) < self._next_start_ms:
                self._samples.popleft()

        return emitted

    def _build_window(
        self,
        start_ms: int,
        end_ms: int,
        samples: List[Dict[str, object]],
    ) -> Dict[str, object]:
        flags_or = 0
        for sample in samples:
            flags_or |= int(sample.get("emg_flags") or 0)

        row = {
            "session_id": samples[0].get("session_id", ""),
            "subject_id": samples[0].get("subject_id", ""),
            "trial_id": samples[0].get("trial_id", ""),
            "label": samples[0].get("label", ""),
            "window_index": self._window_index,
            "window_start_ms": start_ms,
            "window_end_ms": end_ms,
            "sample_count": len(samples),
            "flags_or": flags_or,
            "stale_count": _count_any_flag(samples, ("shoulder_stale", "elbow_stale")),
            "fault_count": _count_any_flag(samples, ("shoulder_fault", "elbow_fault")),
            "saturated_count": _count_any_flag(samples, ("shoulder_saturated", "elbow_saturated")),
        }

        for field in ("emg_biceps", "emg_triceps", "emg_ant_deltoid"):
            values = _numeric_values(samples, field)
            row[f"{field}_mean"] = _mean(values)
            row[f"{field}_std"] = _std(values)
            row[f"{field}_min"] = min(values) if values else 0.0
            row[f"{field}_max"] = max(values) if values else 0.0
            row[f"{field}_mav"] = _mean([abs(value) for value in values])
            row[f"{field}_rms"] = math.sqrt(_mean([value * value for value in values]))

        for prefix in ("shoulder", "elbow"):
            for metric in (
                "pos_mrad",
                "vel_mrad_s",
                "torque_mNm",
                "temp_c",
                "output_current_cmd_a",
                "limit_current_a",
            ):
                field = f"{prefix}_{metric}"
                row[f"{field}_mean"] = _mean(_numeric_values(samples, field))

        for field in (
            "target_shoulder_output_current_cmd_a",
            "target_shoulder_vel_mrad_s",
            "target_shoulder_pos_mrad",
            "target_elbow_output_current_cmd_a",
            "target_elbow_vel_mrad_s",
            "target_elbow_pos_mrad",
        ):
            row[f"{field}_mean"] = _mean(_numeric_values(samples, field))

        self._window_index += 1
        return row


def build_guided_trial_plan(
    trials_per_label: int,
    record_s: float,
    sample_hz: int,
    labels: Sequence[str] = DEFAULT_EMG3_LABELS,
    prepare_s: float = 3.0,
    rest_s: float = 3.0,
    window_ms: int = DEFAULT_EMG3_WINDOW_MS,
    step_ms: int = DEFAULT_EMG3_STEP_MS,
) -> GuidedTrialPlan:
    if trials_per_label <= 0:
        raise ValueError("trials_per_label must be positive")
    if record_s <= 0:
        raise ValueError("record_s must be positive")
    if sample_hz <= 0:
        raise ValueError("sample_hz must be positive")

    clean_labels = tuple(label.strip() for label in labels if label.strip())
    if not clean_labels:
        raise ValueError("at least one label is required")

    trials: List[GuidedTrial] = []
    expected_per_trial = int(round(record_s * sample_hz))
    for label in clean_labels:
        for label_trial_index in range(1, trials_per_label + 1):
            trials.append(
                GuidedTrial(
                    trial_index=len(trials) + 1,
                    label=label,
                    label_trial_index=label_trial_index,
                    prepare_s=prepare_s,
                    record_s=record_s,
                    rest_s=rest_s,
                    expected_samples=expected_per_trial,
                )
            )

    return GuidedTrialPlan(
        labels=clean_labels,
        trials=tuple(trials),
        prepare_s=prepare_s,
        record_s=record_s,
        rest_s=rest_s,
        sample_hz=sample_hz,
        window_ms=window_ms,
        step_ms=step_ms,
        expected_raw_samples=expected_per_trial * len(trials),
    )


def parse_candump_line(line: str) -> Optional[CanFrame]:
    line = _strip_line_prefix_noise(line.strip())
    if not line:
        return None

    match = _CANDUMP_LOG_RE.match(line)
    if match:
        data_hex = match.group("data")
        return CanFrame(
            timestamp=float(match.group("timestamp")),
            channel=match.group("channel"),
            arbitration_id=int(match.group("can_id"), 16),
            data=bytes.fromhex(data_hex),
        )

    match = _CANDUMP_TEXT_RE.match(line)
    if match:
        data_hex = "".join(match.group("data").split())
        return CanFrame(
            timestamp=time.time(),
            channel=match.group("channel"),
            arbitration_id=int(match.group("can_id"), 16),
            data=bytes.fromhex(data_hex),
        )

    return None


def parse_emg3_motor_serial_line(line: str) -> Optional[Dict[str, object]]:
    line = line.strip()
    if not line.startswith("EMG3MOTOR,"):
        return None

    parts = [part.strip() for part in line.split(",")]
    if len(parts) == 21:
        adc3: object = ""
        flags_index = 5
        seq_index = 6
        shoulder_offset = 7
        elbow_offset = 14
    elif len(parts) == 22:
        adc3 = int(parts[5], 0)
        flags_index = 6
        seq_index = 7
        shoulder_offset = 8
        elbow_offset = 15
    else:
        raise ValueError("EMG3MOTOR line must contain 21 or 22 comma-separated fields")

    adc0 = int(parts[2], 0)
    adc1 = int(parts[3], 0)
    adc2 = int(parts[4], 0)

    row: Dict[str, object] = {
        "kind": "sensor",
        "source": "serial",
        "m33_ms": int(parts[1], 0),
        "adc0": adc0,
        "adc1": adc1,
        "adc2": adc2,
        "adc3": adc3,
        "emg_biceps": adc0,
        "emg_triceps": adc1,
        "emg_ant_deltoid": adc2,
        "emg_flags": int(parts[flags_index], 0),
        "emg_seq": int(parts[seq_index], 0),
    }

    _parse_serial_joint_fields(row, "shoulder", parts, shoulder_offset)
    _parse_serial_joint_fields(row, "elbow", parts, elbow_offset)
    _add_target_aliases(row)
    return row


def _strip_line_prefix_noise(line: str) -> str:
    line = line.lstrip("\ufeff")
    timestamp_pos = line.find("(")
    if 0 < timestamp_pos <= 4:
        return line[timestamp_pos:]
    return line


def decode_frame(
    frame: CanFrame,
    first_timestamp: float,
    protocol: str = PROTOCOL_LEGACY,
) -> Dict[str, object]:
    if protocol not in (PROTOCOL_LEGACY, PROTOCOL_EMG3_MOTOR):
        raise ValueError(f"unsupported protocol: {protocol}")

    row: Dict[str, object] = {
        "timestamp": f"{frame.timestamp:.6f}",
        "timestamp_iso": _format_timestamp(frame.timestamp),
        "rel_ms": int(round((frame.timestamp - first_timestamp) * 1000.0)),
        "channel": frame.channel,
        "can_id": f"0x{frame.arbitration_id:03X}",
        "source": "can",
        "kind": "other",
        "raw_hex": frame.data.hex().upper(),
    }

    if frame.arbitration_id == F103_SENSOR_ID:
        row["kind"] = "sensor"
        if len(frame.data) >= 8:
            if protocol == PROTOCOL_EMG3_MOTOR:
                _decode_emg3_sensor(row, frame.data)
            else:
                _decode_legacy_sensor(row, frame.data)
    elif frame.arbitration_id == F103_HEALTH_ID:
        row["kind"] = "health"
        if len(frame.data) >= 4:
            row.update(
                {
                    "node_state": frame.data[0],
                    "node_err_cnt": _u16_le(frame.data, 1),
                    "node_q_fill": frame.data[3],
                }
            )
    elif frame.arbitration_id == F103_ACK_ID:
        row["kind"] = "ack"
        if len(frame.data) >= 3:
            row.update(
                {
                    "ack_cmd": frame.data[0],
                    "ack_seq": frame.data[1],
                    "ack_status": frame.data[2],
                }
            )
    elif protocol == PROTOCOL_EMG3_MOTOR:
        _decode_emg3_motor_frame(row, frame)

    return row


def iter_candump_file(path: Optional[Path]) -> Iterator[CanFrame]:
    source = sys.stdin if path is None else path.open("r", encoding="utf-8", errors="replace")
    try:
        for line in source:
            frame = parse_candump_line(line)
            if frame is not None:
                yield frame
    finally:
        if path is not None:
            source.close()


def resolve_serial_port(port: str, ports: Optional[Sequence[object]] = None) -> str:
    requested = (port or SERIAL_PORT_AUTO).strip()
    if requested.lower() != SERIAL_PORT_AUTO:
        return requested

    available_ports = tuple(ports) if ports is not None else _list_serial_ports()
    detected = detect_infineon_serial_port(available_ports)
    if detected:
        return detected

    available = ", ".join(_serial_port_device(item) for item in available_ports) or "none"
    raise SystemExit(
        "could not auto-detect Infineon/KitProg3 serial port; "
        f"available ports: {available}. Pass --serial-port COMx explicitly."
    )


def detect_infineon_serial_port(ports: Optional[Sequence[object]] = None) -> Optional[str]:
    available_ports = tuple(ports) if ports is not None else _list_serial_ports()
    candidates: List[Tuple[int, str]] = []
    for port in available_ports:
        device = _serial_port_device(port)
        score = _infineon_serial_port_score(port)
        if device and score > 0:
            candidates.append((score, device))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], _serial_port_sort_key(item[1])))
    return candidates[0][1]


def _list_serial_ports() -> Tuple[object, ...]:
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "pyserial is not installed. Install it with `python -m pip install pyserial`, "
            "or pass CAN data with --source python-can/candump/file/stdin."
        ) from exc

    return tuple(list_ports.comports())


def _infineon_serial_port_score(port: object) -> int:
    text = _serial_port_text(port)
    score = 0
    for marker in INFINEON_SERIAL_VIDPID_MARKERS:
        if marker in text:
            score += 1000
    for keyword, weight in INFINEON_SERIAL_KEYWORDS:
        if keyword in text:
            score += weight
    return score


def _serial_port_text(port: object) -> str:
    fields = ("device", "name", "description", "manufacturer", "hwid", "interface", "product")
    return " ".join(str(getattr(port, field, "") or "") for field in fields).lower()


def _serial_port_device(port: object) -> str:
    return str(getattr(port, "device", "") or getattr(port, "name", "") or "")


def _serial_port_sort_key(port: str) -> Tuple[int, str]:
    match = re.fullmatch(r"COM(\d+)", port.upper())
    if match:
        return (0, f"{int(match.group(1)):08d}")
    return (1, port)


def iter_serial_rows(
    port: str,
    baudrate: int,
    timeout_s: float,
    start_command: str = "",
    stop_command: str = "",
) -> Iterator[Dict[str, object]]:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "pyserial is not installed. Install it with `python -m pip install pyserial`, "
            "or use --source python-can/candump/file/stdin."
        ) from exc

    resolved_port = resolve_serial_port(port)

    first_m33_ms: Optional[int] = None
    print(f"serial_port={resolved_port}")
    with serial.Serial(port=resolved_port, baudrate=baudrate, timeout=timeout_s) as ser:
        if start_command:
            ser.write(_serial_command_bytes(start_command))
        try:
            while True:
                raw_line = ser.readline()
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                row = parse_emg3_motor_serial_line(line)
                if row is None:
                    diagnostic_error = _serial_diagnostic_error(line)
                    if diagnostic_error is not None:
                        raise diagnostic_error
                    continue

                m33_ms = int(row["m33_ms"])
                if first_m33_ms is None:
                    first_m33_ms = m33_ms

                now = time.time()
                row.update(
                    {
                        "timestamp": f"{now:.6f}",
                        "timestamp_iso": _format_timestamp(now),
                        "rel_ms": m33_ms - first_m33_ms,
                        "channel": resolved_port,
                        "can_id": "",
                        "raw_hex": line.strip(),
                    }
                )
                yield row
        finally:
            if stop_command:
                ser.write(_serial_command_bytes(stop_command))


def iter_can_decoded_rows(
    frames: Iterable[CanFrame],
    protocol: str,
) -> Iterator[Dict[str, object]]:
    first_timestamp: Optional[float] = None
    for frame in frames:
        if first_timestamp is None:
            first_timestamp = frame.timestamp
        yield decode_frame(frame, first_timestamp, protocol=protocol)


def iter_candump_process(channel: str, protocol: str = PROTOCOL_LEGACY) -> Iterator[CanFrame]:
    return iter_candump_command(["candump", "-L", _candump_channel_arg(channel, protocol)])


def iter_ssh_candump_process(
    ssh_target: str,
    channel: str,
    protocol: str = PROTOCOL_LEGACY,
) -> Iterator[CanFrame]:
    remote_cmd = f"candump -L {_candump_channel_arg(channel, protocol)!r}"
    return iter_candump_command(
        [
            "ssh",
            "-o",
            "ServerAliveInterval=2",
            "-o",
            "ServerAliveCountMax=2",
            ssh_target,
            remote_cmd,
        ]
    )


def _candump_channel_arg(channel: str, protocol: str) -> str:
    filters = [
        f"{F103_ACK_ID:03X}:7FF",
        f"{F103_SENSOR_ID:03X}:7FF",
        f"{F103_HEALTH_ID:03X}:7FF",
    ]
    if protocol == PROTOCOL_EMG3_MOTOR:
        filters.extend(
            [
                f"{M33_MOTOR_STATUS_BASE:03X}:7F8",
                f"{M33_TRAINING_KIN_BASE:03X}:7F0",
            ]
        )

    return f"{channel},{','.join(filters)}"


def iter_candump_command(cmd: Sequence[str]) -> Iterator[CanFrame]:
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8") as proc:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                frame = parse_candump_line(line)
                if frame is not None:
                    yield frame
            return_code = proc.wait(timeout=1.0)
            if return_code:
                raise RuntimeError(
                    f"candump source stopped with exit code {return_code}: {' '.join(cmd)}"
                )
        finally:
            if proc.poll() is None:
                proc.terminate()


def iter_python_can(
    interface: str,
    channel: str,
    bitrate: Optional[int],
    start_stream: bool,
    stop_on_exit: bool,
    period_ms: int,
    protocol: str = PROTOCOL_LEGACY,
) -> Iterator[CanFrame]:
    try:
        import can  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "python-can is not installed. Install it with `python -m pip install python-can`, "
            "or use --source candump/--source stdin."
        ) from exc

    kwargs = {"interface": interface, "channel": channel}
    if bitrate:
        kwargs["bitrate"] = bitrate

    bus = can.Bus(**kwargs)
    allowed_ids = _allowed_can_ids(protocol)
    try:
        try:
            bus.set_filters(
                [
                    {"can_id": can_id, "can_mask": 0x7FF, "extended": False}
                    for can_id in sorted(allowed_ids)
                ]
            )
        except NotImplementedError:
            pass

        if start_stream:
            send_stream_control(bus, period_ms=period_ms, enable=True)

        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue
            if msg.arbitration_id not in allowed_ids:
                continue
            yield CanFrame(
                timestamp=float(msg.timestamp or time.time()),
                channel=channel,
                arbitration_id=int(msg.arbitration_id),
                data=bytes(msg.data),
            )
    finally:
        if stop_on_exit:
            send_stream_control(bus, period_ms=period_ms, enable=False)
        bus.shutdown()


def send_stream_control(bus: object, period_ms: int, enable: bool) -> None:
    try:
        import can  # type: ignore
    except ImportError:
        return

    period_ms = period_ms if period_ms > 0 else 20
    rate_hz = max(1, 1000 // period_ms)

    set_rate_payload = bytes(
        [
            F103_CMD_SET_RATE,
            1,
            F103_RATE_TARGET_CAN_TX,
            rate_hz & 0xFF,
            (rate_hz >> 8) & 0xFF,
            0,
            0,
            0,
        ]
    )
    stream_payload = bytes(
        [
            F103_CMD_START_STREAM if enable else F103_CMD_STOP_STREAM,
            2,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    bus.send(can.Message(arbitration_id=F103_CTRL_ID, data=set_rate_payload, is_extended_id=False))
    bus.send(can.Message(arbitration_id=F103_CTRL_ID, data=stream_payload, is_extended_id=False))


def collect(args: argparse.Namespace) -> None:
    if args.manual:
        collect_manual(args)
        return
    if args.guided:
        collect_guided(args)
        return

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = args.session_id or _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = output_dir / f"{session_id}_raw.csv"
    window_path = output_dir / f"{session_id}_windows.csv"

    deadline = time.monotonic() + args.duration_s if args.duration_s else None
    frame_count = 0
    sensor_count = 0
    aggregator = _build_window_aggregator(args.protocol, args.window_ms, args.step_ms)
    aligner = _build_aligner(args)

    row_iter = build_row_iterator(args)

    with raw_path.open("w", newline="", encoding="utf-8") as raw_file:
        raw_writer = CsvRowWriter(raw_file, RAW_COLUMNS)
        window_file = None
        window_writer = None
        try:
            if aggregator is not None:
                window_file = window_path.open("w", newline="", encoding="utf-8")
                window_writer = CsvRowWriter(window_file, WINDOW_COLUMNS)

            for row in row_iter:
                if deadline is not None and time.monotonic() >= deadline:
                    break

                _attach_capture_fields(row, args, session_id, args.label, "")
                row = _observe_and_align(row, aligner)

                raw_writer.write(row)
                frame_count += 1

                if row["kind"] == "sensor":
                    sensor_count += 1
                    _write_windows(aggregator, window_writer, row)

                if args.max_frames and frame_count >= args.max_frames:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            if window_file is not None:
                window_file.close()

    print(f"raw_csv={raw_path}")
    if aggregator is not None:
        print(f"window_csv={window_path}")
    print(f"frames={frame_count} sensor_frames={sensor_count}")


def collect_manual(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = args.session_id or _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = output_dir / f"{session_id}_raw.csv"
    window_path = output_dir / f"{session_id}_windows.csv"
    trials_path = output_dir / f"{session_id}_trials.csv"

    row_queue: "queue.Queue[object]" = queue.Queue()
    stop_event = threading.Event()
    recording_event = threading.Event()
    pump_thread = threading.Thread(
        target=_pump_rows_for_manual,
        args=(args, row_queue, stop_event, recording_event),
        daemon=True,
    )
    pump_thread.start()

    state = ManualTrialState()
    frame_count = 0
    sensor_count = 0
    aggregator = _build_window_aggregator(args.protocol, args.window_ms, args.step_ms)
    aligner = _build_aligner(args)

    print(f"raw_csv={raw_path}")
    if aggregator is not None:
        print(f"window_csv={window_path}")
    print(f"trial_plan_csv={trials_path}")
    print("manual labels: 1=rest 2=elbow_flex 3=elbow_extend 4=shoulder_flex")
    print("type 1/2/3/4 or a label to start, press Enter/Space/S once to stop, type q to quit")

    with raw_path.open("w", newline="", encoding="utf-8") as raw_file, \
            trials_path.open("w", newline="", encoding="utf-8") as trials_file:
        raw_writer = CsvRowWriter(raw_file, RAW_COLUMNS)
        trial_writer = CsvRowWriter(trials_file, TRIAL_COLUMNS)
        window_file = None
        window_writer = None
        try:
            if aggregator is not None:
                window_file = window_path.open("w", newline="", encoding="utf-8")
                window_writer = CsvRowWriter(window_file, WINDOW_COLUMNS)

            while True:
                label = input("label> ").strip()
                if label.lower() in ("q", "quit", "exit"):
                    break
                if not label:
                    continue

                try:
                    trial = state.start_trial(label)
                except ValueError as exc:
                    print(exc)
                    continue

                _drain_queue_or_raise(row_queue)
                started = time.monotonic()
                recording_event.set()
                print(
                    f"[trial {trial.trial_index}] label={trial.label} recording... "
                    "press Enter/Space/S once to stop"
                )
                _wait_for_manual_stop()
                recording_event.clear()
                stopped = time.monotonic()

                rows = _drain_queue_or_raise(row_queue)
                written = 0
                for queued in rows:
                    row = queued
                    assert isinstance(row, dict)
                    _attach_capture_fields(row, args, session_id, trial.label, trial.trial_id)
                    row["trial_index"] = trial.trial_index
                    row = _observe_and_align(row, aligner)

                    raw_writer.write(row)
                    frame_count += 1
                    written += 1

                    if row["kind"] == "sensor":
                        sensor_count += 1
                        _write_windows(aggregator, window_writer, row)

                _write_trial_row(
                    trial_writer,
                    session_id=session_id,
                    subject_id=args.subject_id,
                    trial=GuidedTrial(
                        trial_index=trial.trial_index,
                        label=trial.label,
                        label_trial_index=trial.label_trial_index,
                        prepare_s=0.0,
                        record_s=stopped - started,
                        rest_s=0.0,
                        expected_samples=written,
                    ),
                )
                print(f"[trial {trial.trial_index}] saved rows={written} seconds={stopped - started:.2f}")
        except KeyboardInterrupt:
            pass
        finally:
            recording_event.clear()
            stop_event.set()
            pump_thread.join(timeout=2.0)
            if window_file is not None:
                window_file.close()

    print(f"frames={frame_count} sensor_frames={sensor_count}")


def collect_guided(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = args.session_id or _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = output_dir / f"{session_id}_raw.csv"
    window_path = output_dir / f"{session_id}_windows.csv"
    trials_path = output_dir / f"{session_id}_trials.csv"

    labels = _parse_labels(args.labels)
    plan = build_guided_trial_plan(
        trials_per_label=args.trials_per_label,
        labels=labels,
        prepare_s=args.prepare_s,
        record_s=args.record_s,
        rest_s=args.rest_s,
        sample_hz=args.sample_hz,
        window_ms=args.window_ms,
        step_ms=args.step_ms,
    )
    _write_trials_csv(trials_path, plan, session_id, args.subject_id)

    print(f"trial_plan_csv={trials_path}")
    print(f"expected_raw_samples={plan.expected_raw_samples}")

    row_iter = iter(build_row_iterator(args))
    frame_count = 0
    sensor_count = 0
    aggregator = _build_window_aggregator(args.protocol, args.window_ms, args.step_ms)
    aligner = _build_aligner(args)

    with raw_path.open("w", newline="", encoding="utf-8") as raw_file:
        raw_writer = CsvRowWriter(raw_file, RAW_COLUMNS)
        window_file = None
        window_writer = None
        try:
            if aggregator is not None:
                window_file = window_path.open("w", newline="", encoding="utf-8")
                window_writer = CsvRowWriter(window_file, WINDOW_COLUMNS)

            for trial in plan.trials:
                print(
                    f"[trial {trial.trial_index}/{len(plan.trials)}] "
                    f"label={trial.label} prepare={trial.prepare_s}s"
                )
                _sleep_if_live(args, trial.prepare_s)
                print(f"[trial {trial.trial_index}/{len(plan.trials)}] record={trial.record_s}s")

                trial_deadline = time.monotonic() + trial.record_s
                while time.monotonic() < trial_deadline:
                    try:
                        row = next(row_iter)
                    except StopIteration:
                        return

                    _attach_capture_fields(row, args, session_id, trial.label, trial.trial_id)
                    row["trial_index"] = trial.trial_index
                    row = _observe_and_align(row, aligner)

                    raw_writer.write(row)
                    frame_count += 1

                    if row["kind"] == "sensor":
                        sensor_count += 1
                        _write_windows(aggregator, window_writer, row)

                    if args.max_frames and frame_count >= args.max_frames:
                        return

                print(f"[trial {trial.trial_index}/{len(plan.trials)}] rest={trial.rest_s}s")
                _sleep_if_live(args, trial.rest_s)
        except KeyboardInterrupt:
            pass
        finally:
            if window_file is not None:
                window_file.close()

    print(f"raw_csv={raw_path}")
    if aggregator is not None:
        print(f"window_csv={window_path}")
    print(f"frames={frame_count} sensor_frames={sensor_count}")


def build_row_iterator(args: argparse.Namespace) -> Iterable[Dict[str, object]]:
    if args.source == "serial":
        return iter_serial_rows(
            port=args.serial_port,
            baudrate=args.serial_baudrate,
            timeout_s=args.serial_timeout_s,
            start_command=args.serial_start_command,
            stop_command=args.serial_stop_command,
        )
    return iter_can_decoded_rows(build_frame_iterator(args), args.protocol)


def _pump_rows_for_manual(
    args: argparse.Namespace,
    row_queue: "queue.Queue[object]",
    stop_event: threading.Event,
    recording_event: threading.Event,
) -> None:
    iterator = iter(build_row_iterator(args))
    try:
        while not stop_event.is_set():
            try:
                row = next(iterator)
            except StopIteration:
                raise ManualDataSourceStopped("data source stopped; restart collection after CAN/SSH is back")
            if recording_event.is_set():
                row_queue.put(dict(row))
    except BaseException as exc:
        row_queue.put(exc)
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()


def _drain_queue(row_queue: "queue.Queue[object]") -> List[object]:
    rows: List[object] = []
    while True:
        try:
            rows.append(row_queue.get_nowait())
        except queue.Empty:
            return rows


def _drain_queue_or_raise(row_queue: "queue.Queue[object]") -> List[object]:
    rows = _drain_queue(row_queue)
    for row in rows:
        if isinstance(row, BaseException):
            raise row
    return rows


def _wait_for_manual_stop() -> None:
    if sys.platform.startswith("win"):
        import msvcrt

        while True:
            key = msvcrt.getwch()
            if key in ("\r", "\n", " ", "s", "S"):
                while msvcrt.kbhit():
                    msvcrt.getwch()
                return

    input()


def build_frame_iterator(args: argparse.Namespace) -> Iterable[CanFrame]:
    if args.source == "python-can":
        return iter_python_can(
            interface=args.interface,
            channel=args.channel,
            bitrate=args.bitrate,
            start_stream=args.start_stream,
            stop_on_exit=args.stop_on_exit,
            period_ms=args.period_ms,
            protocol=args.protocol,
        )
    if args.source == "candump":
        return iter_candump_process(args.channel, protocol=args.protocol)
    if args.source == "ssh-candump":
        return iter_ssh_candump_process(args.ssh_target, args.channel, protocol=args.protocol)
    if args.source == "stdin":
        return iter_candump_file(None)
    if args.source == "file":
        if args.input_file is None:
            raise SystemExit("--input-file is required when --source file")
        return iter_candump_file(args.input_file)
    if args.source == "serial":
        raise SystemExit("--source serial does not produce CAN frames; use build_row_iterator")
    raise SystemExit(f"unsupported source: {args.source}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect F103/C8T6 EMG and M33 motor CAN data to CSV."
    )
    parser.add_argument(
        "--source",
        choices=("python-can", "candump", "ssh-candump", "stdin", "file", "serial"),
        default="python-can",
        help="live python-can, live candump, SSH candump, stdin/file candump log, or M33 serial text",
    )
    parser.add_argument(
        "--protocol",
        choices=(PROTOCOL_LEGACY, PROTOCOL_EMG3_MOTOR),
        default=PROTOCOL_LEGACY,
        help="legacy 0x7C2 layout or three-EMG plus motor telemetry layout",
    )
    parser.add_argument("--interface", default="socketcan", help="python-can interface")
    parser.add_argument("--channel", default="can0", help="CAN channel, e.g. can0 or PCAN_USBBUS1")
    parser.add_argument("--bitrate", type=int, default=None, help="CAN bitrate for adapters that need it")
    parser.add_argument("--input-file", type=Path, default=None, help="candump -L log file")
    parser.add_argument("--ssh-target", default="pi@192.168.3.36", help="SSH target used by --source ssh-candump")
    parser.add_argument(
        "--serial-port",
        default=SERIAL_PORT_AUTO,
        help="M33 serial port; default auto-detects KitProg3/Infineon, e.g. COM20",
    )
    parser.add_argument("--serial-baudrate", type=int, default=115200, help="M33 serial baudrate")
    parser.add_argument("--serial-timeout-s", type=float, default=1.0, help="serial read timeout")
    parser.add_argument(
        "--serial-start-command",
        default="",
        help="optional RT-Thread shell command(s) sent after opening serial; separate multiple commands with ';' or newlines",
    )
    parser.add_argument(
        "--serial-stop-command",
        default="",
        help="optional RT-Thread shell command(s) sent before closing serial; separate multiple commands with ';' or newlines",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "sensor_capture")
    parser.add_argument("--session-id", default="", help="file prefix; defaults to current timestamp")
    parser.add_argument("--subject-id", default="", help="subject/person identifier saved with rows")
    parser.add_argument("--label", default="", help="optional activity/class label saved with each row")
    parser.add_argument("--duration-s", type=float, default=0.0, help="capture duration; 0 means until Ctrl+C")
    parser.add_argument("--max-frames", type=int, default=0, help="stop after this many decoded frames")
    parser.add_argument("--period-ms", type=int, default=20, help="F103 stream period when --start-stream is used")
    parser.add_argument("--start-stream", action="store_true", help="send SET_RATE and START_STREAM first")
    parser.add_argument("--stop-on-exit", action="store_true", help="send STOP_STREAM before exiting")
    parser.add_argument("--window-ms", type=int, default=DEFAULT_EMG3_WINDOW_MS, help="rolling feature window; 0 disables")
    parser.add_argument("--step-ms", type=int, default=DEFAULT_EMG3_STEP_MS, help="rolling feature step")
    parser.add_argument("--stale-after-ms", type=int, default=DEFAULT_EMG3_STALE_AFTER_MS)
    parser.add_argument("--manual", action="store_true", help="keyboard-controlled trial labels and start/stop")
    parser.add_argument("--guided", action="store_true", help="run fixed-label guided trial collection")
    parser.add_argument("--labels", default=",".join(DEFAULT_EMG3_LABELS), help="comma-separated guided labels")
    parser.add_argument("--trials-per-label", type=int, default=30)
    parser.add_argument("--prepare-s", type=float, default=3.0)
    parser.add_argument("--record-s", type=float, default=8.0)
    parser.add_argument("--rest-s", type=float, default=3.0)
    parser.add_argument("--sample-hz", type=int, default=DEFAULT_EMG3_SAMPLE_HZ)
    return parser


def _decode_legacy_sensor(row: Dict[str, object], data: bytes) -> None:
    emg_raw = _u16_le(data, 0)
    emg_filt = _s16_le(data, 2)
    hr_raw = _u16_le(data, 4)
    hr_bpm = data[6]
    flags = data[7]
    row.update(
        {
            "emg_raw": emg_raw,
            "emg_filt": emg_filt,
            "emg_abs": abs(emg_filt),
            "hr_raw": hr_raw,
            "hr_bpm": hr_bpm,
            "flags": flags,
            "adc0": _u16_le(data, 0),
            "adc1": _u16_le(data, 2),
            "adc2": _u16_le(data, 4),
            "adc3": _u16_le(data, 6),
        }
    )


def _decode_emg3_sensor(row: Dict[str, object], data: bytes) -> None:
    adc0 = _u16_le(data, 0)
    adc1 = _u16_le(data, 2)
    adc2 = _u16_le(data, 4)
    adc3 = _u16_le(data, 6)
    row.update(
        {
            "adc0": adc0,
            "adc1": adc1,
            "adc2": adc2,
            "adc3": adc3,
            "emg_biceps": adc0,
            "emg_triceps": adc1,
            "emg_ant_deltoid": adc2,
            "emg_flags": 0,
            "emg_seq": "",
        }
    )


def _decode_emg3_motor_frame(row: Dict[str, object], frame: CanFrame) -> None:
    can_id = frame.arbitration_id
    data = frame.data
    if len(data) < 8:
        return

    if M33_MOTOR_STATUS_BASE <= can_id < M33_MOTOR_STATUS_BASE + M33_MOTOR_STATUS_COUNT:
        if data[0] != M33_MOTOR_STATUS_MARKER:
            return
        flags = data[3]
        row.update(
            {
                "kind": "motor_status",
                "motor_slot": can_id - M33_MOTOR_STATUS_BASE,
                "ros_slot": can_id - M33_MOTOR_STATUS_BASE,
                "motor_seq": data[1],
                "motor_id": data[2],
                "m33_joint_id": data[2],
                "motor_flags": flags,
                "motor_fresh": (flags & M33_MOTOR_STATUS_FLAG_STALE) == 0,
                "motor_fault": (flags & M33_MOTOR_STATUS_FLAG_FAULT) != 0,
                "motor_saturated": (flags & M33_MOTOR_STATUS_FLAG_LIMITED) != 0,
                "motor_pos_mrad": _s16_le(data, 4),
                "motor_vel_mrad_s": _s8(data[6]) * 100,
                "motor_temp_c": "" if data[7] == 0xFF else data[7],
            }
        )
        return

    if _is_training_kin_id(can_id):
        if data[0] != M33_TRAINING_KIN_MARKER:
            return
        flags = data[3]
        row.update(
            {
                "kind": "motor_training_kin",
                "motor_slot": (can_id - M33_TRAINING_KIN_BASE) // 2,
                "ros_slot": data[2],
                "motor_seq": data[1],
                "motor_flags": flags,
                "motor_fresh": _training_flags_fresh(flags),
                "motor_fault": (flags & M33_TRAINING_FLAG_FAULT) != 0,
                "motor_pos_mrad": _s16_le(data, 4),
                "motor_vel_mrad_s": _s16_le(data, 6),
            }
        )
        return

    if _is_training_effort_id(can_id):
        if data[0] != M33_TRAINING_EFFORT_MARKER:
            return
        flags = data[3]
        row.update(
            {
                "kind": "motor_training_effort",
                "motor_slot": (can_id - M33_TRAINING_EFFORT_BASE) // 2,
                "ros_slot": data[2],
                "motor_seq": data[1],
                "motor_flags": flags,
                "motor_fresh": _training_flags_fresh(flags),
                "motor_fault": (flags & M33_TRAINING_FLAG_FAULT) != 0,
                "motor_saturated": (flags & M33_TRAINING_FLAG_SATURATED) != 0,
                "motor_torque_mNm": _s16_le(data, 4),
                "output_current_cmd_a": _s8(data[6]) / 50.0,
                "limit_current_a": data[7] / 50.0,
            }
        )


def _is_training_kin_id(can_id: int) -> bool:
    offset = can_id - M33_TRAINING_KIN_BASE
    return 0 <= offset < M33_TRAINING_SLOT_COUNT * 2 and offset % 2 == 0


def _is_training_effort_id(can_id: int) -> bool:
    offset = can_id - M33_TRAINING_EFFORT_BASE
    return 0 <= offset < M33_TRAINING_SLOT_COUNT * 2 and offset % 2 == 0


def _training_flags_fresh(flags: int) -> bool:
    return (flags & M33_TRAINING_FLAG_FRESH) != 0 and (flags & M33_TRAINING_FLAG_STALE) == 0


def _parse_serial_joint_fields(
    row: Dict[str, object],
    prefix: str,
    parts: Sequence[str],
    offset: int,
) -> None:
    flags = int(parts[offset + 6], 0)
    row.update(
        {
            f"{prefix}_pos_mrad": int(parts[offset], 0),
            f"{prefix}_vel_mrad_s": int(parts[offset + 1], 0),
            f"{prefix}_torque_mNm": int(parts[offset + 2], 0),
            f"{prefix}_temp_c": int(parts[offset + 3], 0),
            f"{prefix}_output_current_cmd_a": float(parts[offset + 4]),
            f"{prefix}_limit_current_a": float(parts[offset + 5]),
            f"{prefix}_fresh": _serial_joint_fresh(flags),
            f"{prefix}_fault": (flags & M33_TRAINING_FLAG_FAULT) != 0,
            f"{prefix}_saturated": (flags & M33_TRAINING_FLAG_SATURATED) != 0,
            f"{prefix}_stale": (flags & M33_TRAINING_FLAG_STALE) != 0,
        }
    )


def _serial_joint_fresh(flags: int) -> bool:
    return (flags & M33_TRAINING_FLAG_FRESH) != 0 and (flags & M33_TRAINING_FLAG_STALE) == 0


def _serial_command_bytes(command: str) -> bytes:
    commands = [item.strip() for item in re.split(r"[;\r\n]+", command) if item.strip()]
    if not commands:
        return b""
    return "".join(f"{item}\r\n" for item in commands).encode("utf-8")


def _serial_diagnostic_error(line: str) -> Optional[RuntimeError]:
    clean_line = line.strip()
    lower_line = clean_line.lower()
    if "command not found" not in lower_line:
        return None

    command = clean_line.split(":", 1)[0].strip() or "serial command"
    return RuntimeError(
        f"{command} is not available on the board firmware. "
        "Flash the M33 firmware built from this branch, or pass the correct "
        "--serial-start-command for the firmware currently on the board."
    )


def _add_target_aliases(row: Dict[str, object]) -> None:
    for prefix in ("shoulder", "elbow"):
        mappings = (
            ("output_current_cmd_a", "output_current_cmd_a"),
            ("vel_mrad_s", "vel_mrad_s"),
            ("pos_mrad", "pos_mrad"),
        )
        for source_suffix, target_suffix in mappings:
            source_field = f"{prefix}_{source_suffix}"
            target_field = f"target_{prefix}_{target_suffix}"
            if source_field in row and row.get(source_field) not in (None, ""):
                row[target_field] = row[source_field]


def _allowed_can_ids(protocol: str) -> set:
    can_ids = {F103_ACK_ID, F103_SENSOR_ID, F103_HEALTH_ID}
    if protocol == PROTOCOL_EMG3_MOTOR:
        can_ids.update(range(M33_MOTOR_STATUS_BASE, M33_MOTOR_STATUS_BASE + M33_MOTOR_STATUS_COUNT))
        for slot in range(M33_TRAINING_SLOT_COUNT):
            can_ids.add(M33_TRAINING_KIN_BASE + slot * 2)
            can_ids.add(M33_TRAINING_EFFORT_BASE + slot * 2)
    return can_ids


def _row_slot(row: Dict[str, object]) -> Optional[int]:
    if row.get("ros_slot") not in (None, ""):
        return int(row["ros_slot"])
    if row.get("motor_slot") not in (None, ""):
        return int(row["motor_slot"])
    return None


def _state_value(state: Optional[Dict[str, object]], field: str) -> object:
    if state is None:
        return ""
    return state.get(field, "")


def _build_window_aggregator(protocol: str, window_ms: int, step_ms: int) -> Optional[object]:
    if window_ms <= 0:
        return None
    if protocol == PROTOCOL_EMG3_MOTOR:
        return Emg3MotorWindowAggregator(window_ms, step_ms)
    return WindowAggregator(window_ms, step_ms)


def _build_aligner(args: argparse.Namespace) -> Optional[Emg3MotorAligner]:
    if args.protocol != PROTOCOL_EMG3_MOTOR:
        return None
    return Emg3MotorAligner(stale_after_ms=args.stale_after_ms)


def _observe_and_align(
    row: Dict[str, object],
    aligner: Optional[Emg3MotorAligner],
) -> Dict[str, object]:
    if aligner is None:
        _add_target_aliases(row)
        return row
    if row.get("source") == "serial":
        _add_target_aliases(row)
        return row
    aligner.observe(row)
    if row.get("kind") == "sensor":
        return aligner.align_sensor_row(row)
    _add_target_aliases(row)
    return row


def _write_windows(
    aggregator: Optional[object],
    window_writer: Optional[CsvRowWriter],
    row: Dict[str, object],
) -> None:
    if aggregator is None or window_writer is None:
        return
    for window_row in aggregator.add_sensor_row(row):  # type: ignore[attr-defined]
        window_writer.write(window_row)


def _attach_capture_fields(
    row: Dict[str, object],
    args: argparse.Namespace,
    session_id: str,
    label: str,
    trial_id: str,
) -> None:
    row["session_id"] = session_id
    row["subject_id"] = args.subject_id
    row["label"] = label
    row["trial_id"] = trial_id


def _write_trials_csv(
    path: Path,
    plan: GuidedTrialPlan,
    session_id: str,
    subject_id: str,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = CsvRowWriter(output, TRIAL_COLUMNS)
        for trial in plan.trials:
            _write_trial_row(writer, session_id=session_id, subject_id=subject_id, trial=trial)


def _write_trial_row(
    writer: CsvRowWriter,
    session_id: str,
    subject_id: str,
    trial: GuidedTrial,
) -> None:
    writer.write(
        {
            "session_id": session_id,
            "subject_id": subject_id,
            "trial_index": trial.trial_index,
            "trial_id": trial.trial_id,
            "label": trial.label,
            "label_trial_index": trial.label_trial_index,
            "prepare_s": trial.prepare_s,
            "record_s": trial.record_s,
            "rest_s": trial.rest_s,
            "expected_samples": trial.expected_samples,
        }
    )


def _parse_labels(labels: str) -> Tuple[str, ...]:
    parsed = tuple(label.strip() for label in labels.split(",") if label.strip())
    return parsed or DEFAULT_EMG3_LABELS


def _sleep_if_live(args: argparse.Namespace, seconds: float) -> None:
    if seconds <= 0:
        return
    if args.source in ("python-can", "candump", "ssh-candump"):
        time.sleep(seconds)


def _u16_le(data: bytes, offset: int) -> int:
    return int(data[offset]) | (int(data[offset + 1]) << 8)


def _s16_le(data: bytes, offset: int) -> int:
    value = _u16_le(data, offset)
    return value - 0x10000 if value & 0x8000 else value


def _s8(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    if not values:
        return 0.0
    mean = _mean(values)
    return math.sqrt(_mean([(value - mean) * (value - mean) for value in values]))


def _numeric_values(samples: List[Dict[str, object]], field: str) -> List[float]:
    return [_as_float(sample[field]) for sample in samples if sample.get(field) not in (None, "")]


def _count_any_flag(samples: List[Dict[str, object]], fields: Sequence[str]) -> int:
    count = 0
    for sample in samples:
        if any(_as_bool(sample.get(field)) for field in fields):
            count += 1
    return count


def _as_float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def _format_timestamp(timestamp: float) -> str:
    return _dt.datetime.fromtimestamp(timestamp).isoformat(timespec="milliseconds")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    normalize_args(args)
    collect(args)
    return 0


def normalize_args(args: argparse.Namespace) -> None:
    if args.manual and args.guided:
        raise SystemExit("--manual and --guided cannot be used together")
    if args.source == "serial" and args.protocol == PROTOCOL_LEGACY:
        args.protocol = PROTOCOL_EMG3_MOTOR


if __name__ == "__main__":
    raise SystemExit(main())
