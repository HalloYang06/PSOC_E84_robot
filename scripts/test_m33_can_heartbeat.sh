#!/bin/bash

set -euo pipefail

CAN_INTERFACE="${CAN_INTERFACE:-can_usb0}"
HEARTBEAT_SEQ="${1:-01}"

if ! command -v cansend >/dev/null 2>&1 || ! command -v candump >/dev/null 2>&1; then
    echo "error: can-utils is required: sudo apt install can-utils"
    exit 1
fi

if ! ip link show "$CAN_INTERFACE" >/dev/null 2>&1; then
    echo "error: CAN interface $CAN_INTERFACE not found"
    echo "hint: sudo systemctl restart usbcan-slcan.service"
    exit 1
fi

sudo ip link set "$CAN_INTERFACE" up

echo "CAN interface:"
ip -details -statistics link show "$CAN_INTERFACE"
echo ""
echo "Sending NanoPi heartbeat on 0x321, seq=0x${HEARTBEAT_SEQ}"
echo "Expected M33 reply: 0x322 data starts with A5 ${HEARTBEAT_SEQ} 07 00"

timeout 3 candump -L "$CAN_INTERFACE",322:7FF &
DUMP_PID=$!
sleep 0.2
cansend "$CAN_INTERFACE" "321#${HEARTBEAT_SEQ}"
wait "$DUMP_PID" || true
