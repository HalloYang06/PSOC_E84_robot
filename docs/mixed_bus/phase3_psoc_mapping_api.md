# 阶段3 API说明：PSoC 汇聚层（CANopen电机 + F103私有帧）

## 1. 目标
PSoC 作为唯一总线汇聚点，完成两件事：
- 下行：CANopen 主站控制 5 个电机
- 上行：把 F103 私有帧转换成统一内部模型，提供给 NanoPi/ROS

这样 ROS 端只面对统一语义，不直接耦合 CANopen 细节和 F103 私有协议。

## 2. 下行控制面（PSoC -> F103）

### 2.1 控制命令帧
- CAN ID：`0x7C0`
- DLC：8
- 帧格式：`[cmd_id][seq][p0][p1][p2][p3][p4][p5]`

### 2.2 应答帧
- CAN ID：`0x7C1`
- DLC：8
- 帧格式：`[cmd_id][seq][status][r0][r1][r2][r3][r4]`
- `status=0` 成功，`status!=0` 失败

### 2.3 主站重发策略（建议）
- 命令超时：20ms
- 重发次数：最多 3 次
- 去重键：`cmd_id + seq`

## 3. 上行观测面（F103 -> PSoC）

### 3.1 传感帧（`0x7C2`）
- `EMG_raw(2B) + EMG_filt(2B) + HR_raw(2B) + HR_filt(1B) + flags(1B)`

### 3.2 健康帧（`0x7C3`）
- `state(1B) + err_cnt(2B) + q_fill(1B) + reserved(4B)`

## 4. PSoC 统一内部数据模型（建议）
```c
typedef struct
{
    uint32_t ts_ms;
    uint16_t emg_raw;
    int16_t emg_filt;
    uint16_t hr_raw;
    uint8_t hr_filt;
    uint8_t sensor_flags;
    uint8_t node_state;
    uint16_t node_err_cnt;
    uint8_t node_q_fill;
} sensor_node_sample_t;
```

## 5. PSoC 对 ROS 的统一语义接口（建议）
- `motor/command`：目标动作（不暴露底层 PDO/SDO）
- `motor/state`：电机状态汇总
- `sensor/f103`：传感节点融合数据
- `system/health`：网络状态、节点在线、错误计数

## 6. 关键边界
- 经典 CAN 网络中，不允许发送 FD 帧
- ROS 不直接发总线细节帧，不混控多协议 ID
- 协议转换责任固定在 PSoC，不放到 F103
