#!/usr/bin/env python3
"""Capture Edgi-Talk IMU serial logs into a CSV file.

The script accepts both formats:

1. The current M33 LSM6DS3 example text output:
   Acceleration [mg]: ...
   Angular rate [mdps]: ...
   Temperature [degC]: ...

2. A future one-line firmware format:
   IMU_CSV,board_ms,ax_mg,ay_mg,az_mg,gx_mdps,gy_mdps,gz_mdps,temp_c
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path


ACC_RE = re.compile(r"Acceleration\s+\[mg\]:\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)")
GYRO_RE = re.compile(r"Angular\s+rate\s+\[mdps\]:\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)")
TEMP_RE = re.compile(r"Temperature\s+\[degC\]:\s*([-+0-9.]+)")


CSV_HEADER = [
    "host_ms",
    "board_ms",
    "label",
    "ax_mg",
    "ay_mg",
    "az_mg",
    "gx_mdps",
    "gy_mdps",
    "gz_mdps",
    "temp_c",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Edgi-Talk M33 LSM6DS3 serial output as training CSV."
    )
    parser.add_argument("--port", required=True, help="Serial port, for example COM7.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate.")
    parser.add_argument("--out", required=True, help="Output CSV path.")
    parser.add_argument(
        "--label",
        default="unlabeled",
        help="Label written to every row, for example idle or wave_left.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Capture seconds. 0 means run until Ctrl+C.",
    )
    parser.add_argument(
        "--raw-log",
        default="",
        help="Optional raw serial log path for debugging parser problems.",
    )
    return parser.parse_args()


def open_serial(port: str, baud: int):
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "pyserial is required. Install it with: python -m pip install pyserial"
        ) from exc

    return serial.Serial(port=port, baudrate=baud, timeout=1)


def parse_imu_csv_line(line: str) -> list[str] | None:
    if not line.startswith("IMU_CSV,"):
        return None

    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 9:
        return None

    _, board_ms, ax, ay, az, gx, gy, gz, temp = parts
    return [board_ms, ax, ay, az, gx, gy, gz, temp]


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw_log = None
    if args.raw_log:
        raw_path = Path(args.raw_log)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_log = raw_path.open("a", encoding="utf-8", newline="")

    sample_cache: dict[str, list[str] | str] = {}
    start = time.monotonic()
    rows = 0

    with open_serial(args.port, args.baud) as ser, out_path.open(
        "a", encoding="utf-8", newline=""
    ) as csv_file:
        writer = csv.writer(csv_file)
        if out_path.stat().st_size == 0:
            writer.writerow(CSV_HEADER)

        print(f"Capturing {args.port} @ {args.baud} -> {out_path}")
        print(f"label={args.label}; press Ctrl+C to stop")

        try:
            while True:
                if args.duration > 0 and (time.monotonic() - start) >= args.duration:
                    break

                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if raw_log is not None:
                    raw_log.write(line + "\n")

                host_ms = str(int(time.time() * 1000))
                direct = parse_imu_csv_line(line)
                if direct is not None:
                    writer.writerow([host_ms, direct[0], args.label] + direct[1:])
                    csv_file.flush()
                    rows += 1
                    print(f"\rrows={rows}", end="")
                    continue

                acc_match = ACC_RE.search(line)
                if acc_match:
                    sample_cache["acc"] = list(acc_match.groups())
                    continue

                gyro_match = GYRO_RE.search(line)
                if gyro_match:
                    sample_cache["gyro"] = list(gyro_match.groups())
                    continue

                temp_match = TEMP_RE.search(line)
                if temp_match:
                    sample_cache["temp"] = temp_match.group(1)

                if {"acc", "gyro", "temp"}.issubset(sample_cache):
                    acc = sample_cache.pop("acc")
                    gyro = sample_cache.pop("gyro")
                    temp = sample_cache.pop("temp")
                    writer.writerow(
                        [host_ms, "", args.label]
                        + list(acc)  # type: ignore[arg-type]
                        + list(gyro)  # type: ignore[arg-type]
                        + [str(temp)]
                    )
                    csv_file.flush()
                    rows += 1
                    print(f"\rrows={rows}", end="")

        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            if raw_log is not None:
                raw_log.close()

    print(f"\nSaved {rows} rows to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
