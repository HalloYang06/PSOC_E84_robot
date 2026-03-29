#!/usr/bin/env bash
set -euo pipefail

# NanoPi classical CAN bring-up script for mixed bus v1
# Usage:
#   sudo ./socketcan_canopen_v1.sh can0 1000000

CAN_IF="${1:-can0}"
BITRATE="${2:-1000000}"

echo "[INFO] Bringing down ${CAN_IF}"
ip link set "${CAN_IF}" down || true

echo "[INFO] Configuring ${CAN_IF} as classical CAN at ${BITRATE} bps"
ip link set "${CAN_IF}" type can bitrate "${BITRATE}" restart-ms 100

echo "[INFO] Bringing up ${CAN_IF}"
ip link set "${CAN_IF}" up

echo "[INFO] Interface details:"
ip -details link show "${CAN_IF}"

echo "[INFO] Quick health check commands:"
echo "  candump ${CAN_IF}"
echo "  cangen ${CAN_IF} -g 10 -L 8 -I 123"
echo "[INFO] Frame type check:"
echo "  candump -L ${CAN_IF}   # mixed bus v1 requires classical CAN frames only"
