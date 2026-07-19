#!/usr/bin/env bash
set -euo pipefail

iface="${CAN_IFACE:-can0}"
mode="${1:-}"

usage() {
    echo "usage: $0 passive|stop [can_iface]" >&2
}

if (( $# < 1 || $# > 2 )); then
    usage
    exit 2
fi

if [[ $# -eq 2 ]]; then
    iface="$2"
fi

case "$mode" in
    passive|stop)
        ;;
    active|assist|resist)
        echo "remote active modes are blocked until heartbeat timeout and single-joint mapping are validated" >&2
        exit 3
        ;;
    *)
        usage
        exit 2
        ;;
esac

link_info="$(ip -details -statistics link show "$iface")"
flags="${link_info#*<}"
flags="${flags%%>*}"
if ! tr ',' '\n' <<<"$flags" | grep -qx 'UP'; then
    echo "$iface is not UP" >&2
    exit 4
fi
if [[ "$link_info" != *"state ERROR-ACTIVE"* ]]; then
    echo "$iface is not ERROR-ACTIVE" >&2
    exit 4
fi
nominal_bitrate="$(awk '$1 == "bitrate" {print $2; exit}' <<<"$link_info")"
if [[ "$nominal_bitrate" != "1000000" ]]; then
    echo "$iface nominal bitrate is not 1000000: ${nominal_bitrate:-unknown}" >&2
    exit 4
fi

bus_off="$(awk '/re-started bus-errors/{getline; print $6; exit}' <<<"$link_info")"
if [[ ! "$bus_off" =~ ^[0-9]+$ ]] || ((bus_off != 0)); then
    echo "$iface bus_off counter is not zero: ${bus_off:-unknown}" >&2
    exit 4
fi

seq_file="${REHAB_SEQ_FILE:-/tmp/rehab_mode_seq}"
seq=1
if [[ -f "$seq_file" ]]; then
    seq="$((($(cat "$seq_file" 2>/dev/null || echo 0) + 1) & 255))"
    if [[ "$seq" -eq 0 ]]; then
        seq=1
    fi
fi
printf '%s\n' "$seq" > "$seq_file"
seq_hex="$(printf '%02X' "$seq")"

echo "tx 321#${seq_hex}"
cansend "$iface" "321#${seq_hex}"
sleep 0.05
echo "tx 321#${seq_hex}"
cansend "$iface" "321#${seq_hex}"
sleep 0.05
echo "tx 320#04${seq_hex}000000000000"
cansend "$iface" "320#04${seq_hex}000000000000"

echo "sent rehab mode=passive seq=0x${seq_hex} iface=${iface}"
