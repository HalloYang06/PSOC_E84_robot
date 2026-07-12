#!/usr/bin/env bash
set -euo pipefail

# Joint validation helper for NanoPi/Ubuntu + can-utils.
# Usage:
#   sudo ./phase4_joint_validation.sh can0 1000000

CAN_IF="${1:-can0}"
BITRATE="${2:-1000000}"
SAMPLE_COUNT="${SAMPLE_COUNT:-200}"
TMP_DUMP="${TMP_DUMP:-/tmp/f103_joint_dump.log}"

echo "[1/6] Configure ${CAN_IF} as classical CAN at ${BITRATE} bps"
ip link set "${CAN_IF}" down || true
ip link set "${CAN_IF}" type can bitrate "${BITRATE}" restart-ms 100
ip link set "${CAN_IF}" up

echo "[2/6] Show interface details"
ip -details link show "${CAN_IF}"

echo "[3/6] Send F103 status query and start-stream commands"
# 0x7C0: [cmd_id][seq][p0..p5]
cansend "${CAN_IF}" 7C0#0501000000000000
cansend "${CAN_IF}" 7C0#0302000000000000

echo "[4/6] Capture ${SAMPLE_COUNT} frames to ${TMP_DUMP}"
candump -L -n "${SAMPLE_COUNT}" "${CAN_IF}" > "${TMP_DUMP}"

echo "[5/6] Check classical CAN frames only"
if grep -q "##" "${TMP_DUMP}"; then
  echo "[FAIL] CAN FD frame found; this network must use classical CAN only"
  exit 1
fi
echo "[PASS] No CAN FD frame marker found"

echo "[6/6] Check F103 private frames"
if ! grep -Eq "7C1[# ]" "${TMP_DUMP}"; then
  echo "[WARN] 0x7C1 ACK not observed; check whether F103 is online"
else
  echo "[PASS] 0x7C1 ACK observed"
fi

if ! grep -Eq "7C2[# ]" "${TMP_DUMP}"; then
  echo "[WARN] 0x7C2 sensor frame not observed; check stream state and F103 sampling"
else
  echo "[PASS] 0x7C2 sensor frame observed"
fi

if ! grep -Eq "7C3[# ]" "${TMP_DUMP}"; then
  echo "[WARN] 0x7C3 health frame not observed; check 1Hz heartbeat"
else
  echo "[PASS] 0x7C3 health frame observed"
fi

echo "[INFO] Dump saved at ${TMP_DUMP}"
