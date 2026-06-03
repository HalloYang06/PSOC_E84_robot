#!/usr/bin/env bash
set -euo pipefail

IFACE="${IFACE:-can0}"
CAN_BITRATE="${CAN_BITRATE:-1000000}"
CAN_RESTART_MS="${CAN_RESTART_MS:-100}"
RECOVER_MCP251XFD="${RECOVER_MCP251XFD:-1}"

if ! ip link show "$IFACE" >/dev/null 2>&1 && [ "$RECOVER_MCP251XFD" = "1" ]; then
  modprobe -r mcp251xfd 2>/dev/null || true
  sleep 1
  modprobe mcp251xfd 2>/dev/null || true
  sleep 2
fi

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "SocketCAN interface not found: $IFACE" >&2
  exit 2
fi

ip link set "$IFACE" down 2>/dev/null || true
ip link set "$IFACE" type can bitrate "$CAN_BITRATE" restart-ms "$CAN_RESTART_MS" berr-reporting on
ip link set "$IFACE" up
ip -details link show "$IFACE"
