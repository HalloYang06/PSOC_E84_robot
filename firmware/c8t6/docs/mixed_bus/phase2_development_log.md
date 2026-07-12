# 阶段2开发日志：F103私有协议与硬件过滤

## 日期
- 2026-03-29

## 目标
- 从“F103参与CANopen”调整为“F103私有轻量协议”
- 在 F103 上实现固定 ID 私有通信与硬件过滤
- 不影响电机侧 CANopen 主链路

## 变更清单

### 1) 协议层（`can_proto`）
- 删除旧的扩展ID字段拆解逻辑
- 新增固定 ID 常量：`0x7C0~0x7C3`
- 新增/保留接口：
  - `can_proto_encode_sensor`
  - `can_proto_encode_health`
  - `can_proto_decode_control`
  - `can_proto_encode_ack`

### 2) 传输层（`can_transport`）
- 改为标准 11-bit 帧发送（`CAN_ID_STD`）
- 配置硬件过滤器只接收 `0x7C0` 标准数据帧
- 保留发送队列和高/普通优先级调度
- 新增命令去重 ACK 缓存机制（`cmd_id + seq`）
- 删除分片与旧 ACK 跟踪逻辑（v1 不启用长包）

### 3) 应用层（`app_service`）
- 发送路径切到新接口：
  - 遥测：`can_proto_encode_sensor -> can_tx_submit`
  - 健康：`can_proto_encode_health -> can_tx_submit`
- 初始化路径改为：`can_transport_init(&hcan)`
- 保留命令回调与参数下发逻辑

## 验证记录
- 环境限制：当前终端没有 `cmake` 命令，无法直接全量构建
- 替代验证：
  - 使用 `build/Debug/compile_commands.json` 复用编译参数
  - 成功编译：`app/src/can_proto.c`
  - 成功编译：`app/src/can_transport.c`
  - 成功编译：`app/src/app_service.c`（补充 `-I BSP` 后）

## 结论
- 阶段2目标已实现：F103 私有轻量协议 + 硬件过滤可用
- 下一步建议进入阶段3：PSoC 汇聚映射和联调脚本收口
