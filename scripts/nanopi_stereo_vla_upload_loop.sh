#!/usr/bin/env bash
# Operator-controlled NanoPi stereo VLA-V upload loop.
#
# Safety boundary:
# - Captures two USB camera frames and uploads stereo_vision_context only.
# - Does not publish ROS motion topics.
# - Does not send CAN frames.
# - Does not change M33/M55 state.
# - Defaults to a finite loop for demo use; set COUNT=0 only when you really
#   want to keep it running until Ctrl+C.

set -euo pipefail

WORKSPACE="${WORKSPACE:-/home/pi/rehab_arm_ros2_ws}"
PROJECT_ID="${PROJECT_ID:-e201f41c-25a6-46e1-baf8-be6dcb83284c}"
API_BASE="${API_BASE:-http://106.55.62.122:8011}"
ROBOT_ID="${ROBOT_ID:-rehab-arm-alpha}"
DEVICE_ID="${DEVICE_ID:-nanopi-m5}"
LEFT_DEVICE="${LEFT_DEVICE:-/dev/video45}"
RIGHT_DEVICE="${RIGHT_DEVICE:-/dev/video47}"
BASELINE_M="${BASELINE_M:-0.06}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
COUNT="${COUNT:-12}"
START_SEQUENCE="${START_SEQUENCE:-1}"
OUTPUT_DIR="${OUTPUT_DIR:-/home/pi/rehab_arm_stereo_frames}"
LOG_DIR="${LOG_DIR:-/home/pi/rehab_arm_vla_logs}"
VISION_IMPL="${VISION_IMPL:-cpp}"
TARGET_LABEL_ALLOWLIST="${TARGET_LABEL_ALLOWLIST:-bottle,cup}"
SSD_MODEL="${SSD_MODEL:-/home/pi/rehab_arm_models/ssd/mobilenet_iter_73000.caffemodel}"
SSD_PROTOTXT="${SSD_PROTOTXT:-/home/pi/rehab_arm_models/ssd/deploy.prototxt}"
SSD_LABELS="${SSD_LABELS:-/home/pi/rehab_arm_models/ssd/voc21.txt}"
SSD_CONFIDENCE_THRESHOLD="${SSD_CONFIDENCE_THRESHOLD:-0.25}"
USE_YOLOX="${USE_YOLOX:-1}"
YOLOX_MODEL="${YOLOX_MODEL:-/home/pi/rehab_arm_models/yolo/yolox_nano.onnx}"
YOLOX_LABELS="${YOLOX_LABELS:-/home/pi/rehab_arm_models/yolo/coco80.txt}"
YOLOX_INPUT_SIZE="${YOLOX_INPUT_SIZE:-416}"
YOLOX_CONFIDENCE_THRESHOLD="${YOLOX_CONFIDENCE_THRESHOLD:-0.20}"
YOLOX_NMS_THRESHOLD="${YOLOX_NMS_THRESHOLD:-0.45}"
CLEANUP_OLDER_THAN_DAYS="${CLEANUP_OLDER_THAN_DAYS:-0}"
UPLOAD_KEYFRAME="${UPLOAD_KEYFRAME:-1}"
KEYFRAME_CAMERA_IDS="${KEYFRAME_CAMERA_IDS:-stereo_left,stereo_right}"
KEYFRAME_WIDTH="${KEYFRAME_WIDTH:-640}"
KEYFRAME_HEIGHT="${KEYFRAME_HEIGHT:-480}"

need_path() {
    local path="$1"
    local label="$2"
    if [ ! -e "$path" ]; then
        echo "FAIL: missing ${label}: ${path}" >&2
        exit 2
    fi
}

need_file() {
    local path="$1"
    local label="$2"
    if [ ! -f "$path" ]; then
        echo "FAIL: missing ${label}: ${path}" >&2
        exit 2
    fi
}

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "FAIL: missing command: $1" >&2
        exit 2
    fi
}

if [ ! -d "$WORKSPACE" ]; then
    echo "FAIL: missing ROS2 workspace: $WORKSPACE" >&2
    exit 2
fi

need_path "$LEFT_DEVICE" "left camera"
need_path "$RIGHT_DEVICE" "right camera"
need_file "$SSD_MODEL" "SSD model"
need_file "$SSD_PROTOTXT" "SSD prototxt"
need_file "$SSD_LABELS" "SSD labels"
if [ "$USE_YOLOX" = "1" ]; then
    need_file "$YOLOX_MODEL" "YOLOX ONNX model"
    need_file "$YOLOX_LABELS" "YOLOX labels"
fi
need_cmd date
need_cmd mkdir
if [ "$UPLOAD_KEYFRAME" = "1" ]; then
    need_cmd curl
    need_cmd sha256sum
fi

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

if [ "$CLEANUP_OLDER_THAN_DAYS" -gt 0 ]; then
    find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.jpg' -mtime "+$CLEANUP_OLDER_THAN_DAYS" -delete || true
fi

cd "$WORKSPACE"
set +u
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source install/setup.bash
set -u
need_cmd ros2

case "$VISION_IMPL" in
    cpp)
        VISION_EXECUTABLE="stereo_camera_capture_upload_cpp"
        ;;
    python)
        VISION_EXECUTABLE="stereo_camera_capture_upload.py"
        ;;
    *)
        echo "FAIL: VISION_IMPL must be cpp or python, got: $VISION_IMPL" >&2
        exit 2
        ;;
esac

run_id="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="$LOG_DIR/stereo_vla_upload_${run_id}.jsonl"
sequence="$START_SEQUENCE"
iteration=0

echo "Stereo VLA-V upload loop"
echo "  project_id=$PROJECT_ID"
echo "  api_base=$API_BASE"
echo "  cameras=$LEFT_DEVICE,$RIGHT_DEVICE"
echo "  baseline_m=$BASELINE_M"
echo "  interval_seconds=$INTERVAL_SECONDS"
echo "  count=$COUNT"
echo "  vision_impl=$VISION_IMPL"
echo "  yolox=$USE_YOLOX"
echo "  log_file=$log_file"
echo "  boundary=stereo_vision_context_only_not_motion_permission"

interval_ms_from_seconds() {
    awk -v seconds="$INTERVAL_SECONDS" 'BEGIN { printf "%d", seconds * 1000 }'
}

latest_frame_for_side() {
    local side="$1"
    find "$OUTPUT_DIR" -maxdepth 1 -type f -name "*__${side}.jpg" -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | awk 'NR==1 { $1=""; sub(/^ /, ""); print }'
}

upload_keyframe_file() {
    local camera_id="$1"
    local side="$2"
    if [ "$UPLOAD_KEYFRAME" != "1" ]; then
        return 0
    fi

    local image_path
    image_path="$(latest_frame_for_side "$side")"
    if [ -z "$image_path" ] || [ ! -f "$image_path" ]; then
        echo "WARN: no $side keyframe found in $OUTPUT_DIR" >&2
        return 0
    fi

    local sha256
    sha256="$(sha256sum "$image_path" | awk '{print $1}')"
    curl -fsS \
        -X POST "$API_BASE/api/rehab-arm/v1/devices/$DEVICE_ID/camera/keyframes" \
        -F "robot_id=$ROBOT_ID" \
        -F "camera_id=$camera_id" \
        -F "image_format=jpg" \
        -F "frame_ts_unix=$(date +%s)" \
        -F "width=$KEYFRAME_WIDTH" \
        -F "height=$KEYFRAME_HEIGHT" \
        -F "sha256=$sha256" \
        -F "detection_summary=stereo VLA keyframe" \
        -F "scene_summary=low-rate visual evidence frame for VLA page" \
        -F "vla_context=keyframe_only_not_motion_permission" \
        -F "project_id=$PROJECT_ID" \
        -F "file=@$image_path;type=image/jpeg" \
        >/dev/null
    echo "Uploaded camera keyframe: $camera_id $image_path"
}

upload_latest_keyframes() {
    if [ "$UPLOAD_KEYFRAME" != "1" ]; then
        return 0
    fi
    case ",$KEYFRAME_CAMERA_IDS," in
        *,stereo_left,*) upload_keyframe_file "stereo_left" "left" ;;
    esac
    case ",$KEYFRAME_CAMERA_IDS," in
        *,stereo_right,*) upload_keyframe_file "stereo_right" "right" ;;
    esac
}

run_cpp_loop_once() {
    if [ "$COUNT" -eq 0 ]; then
        echo "FAIL: COUNT=0 is only supported by the shell-managed python loop. Use a finite COUNT for persistent C++ loop." >&2
        exit 2
    fi
    INTERVAL_MS="$(interval_ms_from_seconds)"
    yolox_args=()
    if [ "$USE_YOLOX" = "1" ]; then
        yolox_args=(
            --yolox-onnx "$YOLOX_MODEL"
            --yolox-labels "$YOLOX_LABELS"
            --yolox-input-size "$YOLOX_INPUT_SIZE"
            --yolox-confidence-threshold "$YOLOX_CONFIDENCE_THRESHOLD"
            --yolox-nms-threshold "$YOLOX_NMS_THRESHOLD"
            --detect-right-yolox
        )
    fi
    ros2 run rehab_arm_psoc_bridge "$VISION_EXECUTABLE" \
        --project-id "$PROJECT_ID" \
        --api-base "$API_BASE" \
        --robot-id "$ROBOT_ID" \
        --device-id "$DEVICE_ID" \
        --left-device "$LEFT_DEVICE" \
        --right-device "$RIGHT_DEVICE" \
        --output-dir "$OUTPUT_DIR" \
        --baseline-m "$BASELINE_M" \
        --rotate-180 \
        --upload \
        --sequence "$START_SEQUENCE" \
        --loop-count "$COUNT" \
        --interval-ms "$INTERVAL_MS" \
        --analyze-image-quality \
        "${yolox_args[@]}" \
        --ssd-model "$SSD_MODEL" \
        --ssd-prototxt "$SSD_PROTOTXT" \
        --ssd-labels "$SSD_LABELS" \
        --ssd-confidence-threshold "$SSD_CONFIDENCE_THRESHOLD" \
        --detect-right-ssd \
        --auto-target-from-detections \
        --target-label-allowlist "$TARGET_LABEL_ALLOWLIST" \
        --stereo-associate-target | tee -a "$log_file"
}

if [ "$VISION_IMPL" = "cpp" ]; then
    run_cpp_loop_once
    upload_latest_keyframes
    echo "Done: sent $COUNT sample(s)."
    exit 0
fi

while true; do
    if [ "$COUNT" -gt 0 ] && [ "$iteration" -ge "$COUNT" ]; then
        echo "Done: sent $iteration sample(s)."
        exit 0
    fi

    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "[$ts] capture sequence=$sequence"

    if ros2 run rehab_arm_psoc_bridge "$VISION_EXECUTABLE" \
        --project-id "$PROJECT_ID" \
        --api-base "$API_BASE" \
        --robot-id "$ROBOT_ID" \
        --device-id "$DEVICE_ID" \
        --left-device "$LEFT_DEVICE" \
        --right-device "$RIGHT_DEVICE" \
        --output-dir "$OUTPUT_DIR" \
        --baseline-m "$BASELINE_M" \
        --rotate-180 \
        --upload \
        --sequence "$sequence" \
        --analyze-image-quality \
        --ssd-model "$SSD_MODEL" \
        --ssd-prototxt "$SSD_PROTOTXT" \
        --ssd-labels "$SSD_LABELS" \
        --ssd-confidence-threshold "$SSD_CONFIDENCE_THRESHOLD" \
        --detect-right-ssd \
        --auto-target-from-detections \
        --target-label-allowlist "$TARGET_LABEL_ALLOWLIST" \
        --stereo-associate-target | tee -a "$log_file"; then
        echo "[$ts] upload ok"
        upload_latest_keyframes || echo "[$ts] keyframe upload failed" | tee -a "$log_file" >&2
    else
        rc="$?"
        echo "[$ts] upload failed rc=$rc" | tee -a "$log_file" >&2
    fi

    iteration="$((iteration + 1))"
    sequence="$((sequence + 1))"

    if [ "$COUNT" -gt 0 ] && [ "$iteration" -ge "$COUNT" ]; then
        continue
    fi
    sleep "$INTERVAL_SECONDS"
done
