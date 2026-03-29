#!/usr/bin/env bash
set -euo pipefail

# 阶段4联调脚本（NanoPi/Ubuntu + can-utils）
# 用法:
#   sudo ./phase4_joint_validation.sh can0 1000000

CAN_IF="${1:-can0}"
BITRATE="${2:-1000000}"
SAMPLE_COUNT="${SAMPLE_COUNT:-200}"
TMP_DUMP="${TMP_DUMP:-/tmp/f103_joint_dump.log}"

echo "[1/6] 配置 ${CAN_IF} 为经典 CAN ${BITRATE}bps"
ip link set "${CAN_IF}" down || true
ip link set "${CAN_IF}" type can bitrate "${BITRATE}" restart-ms 100
ip link set "${CAN_IF}" up

echo "[2/6] 检查接口参数"
ip -details link show "${CAN_IF}"

echo "[3/6] 发送 F103 状态查询命令（cmd=0x05, seq=0x01）"
# 0x7C0: [cmd_id][seq][p0..p5]
cansend "${CAN_IF}" 7C0#0501000000000000

echo "[4/6] 抓取 ${SAMPLE_COUNT} 帧，保存到 ${TMP_DUMP}"
candump -L -n "${SAMPLE_COUNT}" "${CAN_IF}" > "${TMP_DUMP}"

echo "[5/6] 快速规则检查"
if grep -q "##" "${TMP_DUMP}"; then
  echo "[FAIL] 发现 CAN FD 帧（含 ##），当前网络应为经典 CAN"
  exit 1
fi

if ! grep -Eq "7C1[# ]" "${TMP_DUMP}"; then
  echo "[WARN] 未观察到 0x7C1 ACK 帧，请检查 F103 是否在线"
else
  echo "[PASS] 观察到 0x7C1 ACK 帧"
fi

if ! grep -Eq "7C2[# ]" "${TMP_DUMP}"; then
  echo "[WARN] 未观察到 0x7C2 传感帧，请检查 stream 是否开启"
else
  echo "[PASS] 观察到 0x7C2 传感帧"
fi

if ! grep -Eq "7C3[# ]" "${TMP_DUMP}"; then
  echo "[WARN] 未观察到 0x7C3 健康帧，请检查 1Hz 心跳发送"
else
  echo "[PASS] 观察到 0x7C3 健康帧"
fi

echo "[6/6] 完成。建议手动复核以下内容:"
echo "  1) ACK延迟是否 < 20ms"
echo "  2) 传感帧周期是否接近 100Hz"
echo "  3) 长时间运行错误计数是否稳定"
