# 阶段2 API说明：F103私有轻量CAN协议（经典CAN 2.0）

## 1. 总览
- 物理层：经典 CAN 2.0
- 波特率：1 Mbps
- 帧类型：11-bit 标准数据帧（不使用 FD、扩展帧）
- F103 固定 ID：
  - `0x7C0`：PSoC -> F103 控制/参数
  - `0x7C1`：F103 -> PSoC ACK/NACK
  - `0x7C2`：F103 -> PSoC 传感数据
  - `0x7C3`：F103 -> PSoC 健康状态

## 2. 代码接口（app/include）

### 2.1 协议编解码（`can_proto.h`）
- `int32_t can_proto_encode_sensor(const fusion_snapshot_t *snapshot, can_message_t *message);`
  - 输入：融合快照
  - 输出：`0x7C2` 传感帧（8字节）
- `int32_t can_proto_encode_health(node_state_t state, uint16_t error_count, uint8_t q_fill, uint16_t rx_count, uint16_t tx_count, can_message_t *message);`
  - 输出：`0x7C3` 健康帧（8字节）
- `int32_t can_proto_decode_control(const can_message_t *message, can_proto_command_t *command);`
  - 输入：`0x7C0` 控制帧
  - 输出：命令结构体 `cmd_id/seq/payload`
- `int32_t can_proto_encode_ack(uint8_t cmd_id, uint8_t seq, uint8_t status, const uint8_t *resp_payload, uint8_t resp_len, can_message_t *message);`
  - 输出：`0x7C1` ACK/NACK 帧

### 2.2 传输层（`can_transport.h`）
- `int32_t can_transport_init(CAN_HandleTypeDef *hcan);`
  - 初始化 CAN、配置硬件过滤器、启用 FIFO0 接收中断
- `void can_transport_register_command_handler(can_command_handler_t handler, void *user_ctx);`
  - 注册命令处理回调
- `int32_t can_tx_submit(const can_message_t *message, can_tx_prio_t prio);`
  - 投递发送队列（高/普通优先级）
- `void can_transport_process(uint32_t now_ms);`
  - 主循环周期调用，负责发送队列排空
- `void can_transport_poll_rx(void);`
  - 拉取 FIFO0 并分发协议处理
- `uint16_t can_transport_error_count(void);`
- `uint8_t can_transport_queue_fill(void);`

## 3. 帧格式定义（固定8字节）

### 3.1 控制帧 `0x7C0`（PSoC -> F103）
- Byte0: `cmd_id`
- Byte1: `seq`
- Byte2~7: `p0~p5`

### 3.2 ACK帧 `0x7C1`（F103 -> PSoC）
- Byte0: `cmd_id`
- Byte1: `seq`
- Byte2: `status`（`0=成功, 1=失败`）
- Byte3~7: 响应参数（最多5字节）

### 3.3 传感帧 `0x7C2`（F103 -> PSoC）
- Byte0~1: `EMG_raw`（小端）
- Byte2~3: `EMG_filt`（int16，小端）
- Byte4~5: `HR_raw`（小端）
- Byte6: `HR_filt`（uint8）
- Byte7: `flags`（bit0:EMG有效，bit1:HR有效）

### 3.4 健康帧 `0x7C3`（F103 -> PSoC）
- Byte0: `state`（INIT/RUN/DEGRADED/FAULT）
- Byte1~2: `err_cnt`（小端）
- Byte3: `q_fill`（发送队列占用）
- Byte4~5: `rx_count`（F103 已从 FIFO0 拉取的标准数据帧计数，小端）
- Byte6~7: `tx_count`（F103 已成功提交到 CAN mailbox 的发送帧计数，小端）

## 4. 命令集（当前实现）
- `0x01 CAN_CMD_SET_RATE`：设置采样/发送频率
- `0x02 CAN_CMD_SET_FILTER_PARAM`：设置滤波参数
- `0x03 CAN_CMD_START_STREAM`：开启上报
- `0x04 CAN_CMD_STOP_STREAM`：关闭上报
- `0x05 CAN_CMD_GET_STATUS`：查询状态
- `0x06 CAN_CMD_SET_STATE`：设置节点状态

## 5. 可靠性策略
- 硬件过滤：仅接收 `0x7C0`，减少无关中断负载
- 命令去重：`cmd_id + seq` 命中时直接回放缓存 ACK，避免重复副作用
- 发送调度：高优先级帧优先出队（ACK/健康优先于普通遥测）
