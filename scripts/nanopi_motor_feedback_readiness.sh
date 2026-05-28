#!/usr/bin/env bash
# NanoPi motor feedback source readiness check.
#
# Default behavior is read-only:
# - checks can0 state
# - captures candump
# - runs ROS feedback_source_readiness.py
# - sends no 0x320 target, no trajectory, no motor command
#
# Optional non-motion probes can be enabled with RUN_NON_MOTION_PROBES=1.
# They send only query frames such as CANSimple Get_Error/Address and Lingzu Get_ID.

set -euo pipefail

IFACE="${IFACE:-can0}"
WORKSPACE="${WORKSPACE:-/home/pi/rehab_arm_ros2_ws}"
DURATION_SECONDS="${DURATION_SECONDS:-5}"
TMP_DIR="${TMP_DIR:-/tmp/rehab_arm_feedback_readiness}"
RUN_NON_MOTION_PROBES="${RUN_NON_MOTION_PROBES:-0}"
SEND_M33_HEARTBEAT="${SEND_M33_HEARTBEAT:-0}"
NANOPI_CAN_MASTER="${NANOPI_CAN_MASTER:-/home/pi/nanopi_can_master.py}"

mkdir -p "$TMP_DIR"

CAN_STATUS_LOG="$TMP_DIR/can_status.txt"
READONLY_CANDUMP="$TMP_DIR/readonly_feedback.candump"
READONLY_REPORT="$TMP_DIR/readonly_feedback_report.json"
PROBE_CANDUMP="$TMP_DIR/non_motion_probe.candump"
PROBE_LOG="$TMP_DIR/non_motion_probe.log"
PROBE_REPORT="$TMP_DIR/non_motion_probe_report.json"
READONLY_RC=0
PROBE_RC=0

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "FAIL: missing command: $1" >&2
        exit 2
    fi
}

source_ros() {
    set +u
    if [ -f /opt/ros/jazzy/setup.bash ]; then
        # shellcheck disable=SC1091
        source /opt/ros/jazzy/setup.bash
    elif [ -f /opt/ros/humble/setup.bash ]; then
        # shellcheck disable=SC1091
        source /opt/ros/humble/setup.bash
    else
        set -u
        echo "FAIL: neither /opt/ros/jazzy nor /opt/ros/humble exists" >&2
        exit 2
    fi
    set -u

    if [ ! -f "$WORKSPACE/install/setup.bash" ]; then
        echo "FAIL: ROS workspace is not built: $WORKSPACE" >&2
        echo "Hint: cd $WORKSPACE && ./build_ros2.sh --packages-select rehab_arm_psoc_bridge" >&2
        exit 2
    fi
    set +u
    # shellcheck disable=SC1091
    source "$WORKSPACE/install/setup.bash"
    set -u
}

print_header() {
    echo "=== NanoPi motor feedback readiness ==="
    echo "iface=$IFACE"
    echo "workspace=$WORKSPACE"
    echo "duration=${DURATION_SECONDS}s"
    echo "tmp_dir=$TMP_DIR"
    echo "send_m33_heartbeat=$SEND_M33_HEARTBEAT"
    echo "run_non_motion_probes=$RUN_NON_MOTION_PROBES"
    echo "Safety: default path is passive readonly and never sends motion commands."
    echo
}

run_readonly_capture() {
    echo "--- CAN status ---"
    ip -details -statistics link show "$IFACE" | tee "$CAN_STATUS_LOG"
    if ! grep -q "state ERROR-ACTIVE" "$CAN_STATUS_LOG"; then
        echo "WARN: $IFACE is not ERROR-ACTIVE; readiness may fail."
    fi

    echo
    echo "--- readonly candump ${DURATION_SECONDS}s ---"
    rm -f "$READONLY_CANDUMP" "$READONLY_REPORT"
    if [ "$SEND_M33_HEARTBEAT" = "1" ]; then
        echo "Sending one safe M33 heartbeat 0x321 during capture."
        timeout "$DURATION_SECONDS" candump -L "$IFACE" > "$READONLY_CANDUMP" &
        DUMP_PID=$!
        sleep 0.3
        cansend "$IFACE" 321#55 || true
        wait "$DUMP_PID" || true
    else
        timeout "$DURATION_SECONDS" candump -L "$IFACE" > "$READONLY_CANDUMP" || true
    fi
    echo "captured: $READONLY_CANDUMP"

    echo
    echo "--- readonly feedback report ---"
    set +e
    ros2 run rehab_arm_psoc_bridge feedback_source_readiness.py \
        "$READONLY_CANDUMP" \
        --pretty \
        --output "$READONLY_REPORT"
    READONLY_RC=$?
    set -e
}

run_non_motion_probes() {
    if [ "$RUN_NON_MOTION_PROBES" != "1" ]; then
        return 0
    fi
    if [ ! -f "$NANOPI_CAN_MASTER" ]; then
        echo "FAIL: nanopi_can_master.py not found: $NANOPI_CAN_MASTER" >&2
        exit 2
    fi

    echo
    echo "--- optional non-motion probes ---"
    echo "These probes send query frames only; they do not enable or move motors."
    rm -f "$PROBE_CANDUMP" "$PROBE_LOG" "$PROBE_REPORT"
    timeout "$((DURATION_SECONDS + 4))" candump -L "$IFACE" > "$PROBE_CANDUMP" &
    DUMP_PID=$!
    sleep 0.2
    {
        python3 "$NANOPI_CAN_MASTER" cansimple get-error --iface "$IFACE" --node 3 --error-type 0 --wait 0.8
        python3 "$NANOPI_CAN_MASTER" cansimple address --iface "$IFACE" --wait 0.8
        python3 "$NANOPI_CAN_MASTER" probe --iface "$IFACE" --start 4 --end 7 --wait 0.2
    } > "$PROBE_LOG" 2>&1 || true
    sleep "$DURATION_SECONDS"
    kill "$DUMP_PID" 2>/dev/null || true
    wait "$DUMP_PID" 2>/dev/null || true

    echo "probe log: $PROBE_LOG"
    cat "$PROBE_LOG"
    echo
    echo "--- post-probe feedback report ---"
    set +e
    ros2 run rehab_arm_psoc_bridge feedback_source_readiness.py \
        "$PROBE_CANDUMP" \
        --pretty \
        --output "$PROBE_REPORT"
    PROBE_RC=$?
    set -e
}

print_next_step() {
    echo
    echo "--- result files ---"
    echo "can_status=$CAN_STATUS_LOG"
    echo "readonly_candump=$READONLY_CANDUMP"
    echo "readonly_report=$READONLY_REPORT"
    if [ "$RUN_NON_MOTION_PROBES" = "1" ]; then
        echo "probe_candump=$PROBE_CANDUMP"
        echo "probe_log=$PROBE_LOG"
        echo "probe_report=$PROBE_REPORT"
    fi
    echo
    echo "Pass direction:"
    echo "- raw_motor_feedback_ready=true means at least one real motor feedback source is visible."
    echo "- m33_joint_state_ready=true means ROS /joint_states can be expected."
    echo "- target_0x320_count must stay 0 for readonly evidence."
    if [ "$READONLY_RC" -ne 0 ]; then
        echo "Readonly readiness did not pass; inspect the report before any motion test."
    fi
    if [ "$PROBE_RC" -ne 0 ]; then
        echo "Probe readiness did not pass; inspect motor power/CAN branch/IDs before motion."
    fi
}

need_cmd ip
need_cmd candump
need_cmd timeout
need_cmd python3
if [ "$SEND_M33_HEARTBEAT" = "1" ] || [ "$RUN_NON_MOTION_PROBES" = "1" ]; then
    need_cmd cansend
fi
print_header
source_ros
run_readonly_capture
run_non_motion_probes
print_next_step

if [ "$READONLY_RC" -ne 0 ]; then
    exit "$READONLY_RC"
fi
if [ "$PROBE_RC" -ne 0 ]; then
    exit "$PROBE_RC"
fi
