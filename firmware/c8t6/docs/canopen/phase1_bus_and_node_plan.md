# 混合总线 v1：电机 CANopen + F103 私有轻量协议

## 1. 总线基线
- 总线类型：经典 CAN 2.0（同一物理总线禁用 CAN FD 帧）
- 波特率：1 Mbps（所有节点一致）
- 关键约束：PSoC 的 CANFD 控制器必须工作在经典模式，禁止发送 FD/BRS 帧

## 2. 节点与协议角色
- `PSoC`：CANopen 主站 + 协议汇聚节点
- `STM32F103`：传感从节点，仅私有轻量协议
- `NanoPi/ROS`：上层策略与观测，通过 PSoC 的统一接口交互
- `5 个电机`：统一 CANopen（MIT 不进入 v1 主流程）

## 3. ID 分区（避免与 CANopen 常用 ID 冲突）
- CANopen 电机区：按标准 COB-ID（`0x000`、`0x080`、`0x180+node`、`0x200+node`、`0x580/0x600+node`、`0x700+node`）
- F103 私有区：
  - `0x7C0`：PSoC -> F103 控制/参数下发
  - `0x7C1`：F103 -> PSoC ACK/NACK
  - `0x7C2`：F103 -> PSoC 传感数据
  - `0x7C3`：F103 -> PSoC 健康状态

## 4. F103 私有帧格式
- 控制帧（0x7C0）：`[cmd_id][seq][p0][p1][p2][p3][p4][p5]`
- ACK 帧（0x7C1）：`[cmd_id][seq][status][r0][r1][r2][r3][r4]`
- 传感帧（0x7C2）：`EMG_raw(2B) + EMG_filt(2B) + HR_raw(2B) + HR_filt(1B) + flags(1B)`
- 健康帧（0x7C3）：`state(1B) + err_cnt(2B) + q_fill(1B) + reserved(4B)`

## 5. 验收要点
- 抓包确认总线上无 CAN FD 帧
- 电机 CANopen 心跳/PDO 正常
- F103 只接收 `0x7C0`（及可选同步帧），其余帧被硬件过滤
- 30 分钟运行无中断风暴、无队列溢出、无持续错误增长
