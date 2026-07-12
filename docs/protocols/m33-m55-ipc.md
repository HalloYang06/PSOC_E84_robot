# M33-M55 IPC protocol

## Owner

M33 创建 MTB IPC instance 和两条共享队列；M55 等待有效 shared pointer 后 attach。两侧共享同一份 `m33_m55_message_t` 定义，M33 侧 canonical header 为 `firmware/m33/applications/common/m33_m55_comm.h`，M55 镜像为 `firmware/m55/applications/m33_m55_comm.h`。

## Consumers and direction

- M33 → M55 queue 0：sensor snapshot/stream、audio、控制与配置消息；模型输入消费者是 M55 `model_input_bridge`。
- M55 → M33 queue 1：AI inference response、ASR/TTS、voice ACK/status；M33 `m55_model_bridge` 消费并把模型摘要转为 CAN `0x323`。
- 大 PCM 使用 `g_m33_m55_pcm_shared` 共享区；queue message 可携带 stream metadata，小型 payload 为 16 bytes。

## Format, units, and version

transport 使用 `MTB_IPC_CHAN_1` 作为 internal channel、`MTB_IPC_CHAN_0` 作为 queue channel；M33 创建两条 depth 5 queue，元素大小为 `sizeof(m33_m55_message_t)`。顶层格式是 native C enum `type`、`uint32 seq` 和 union payload。

本产品模型路径可证明的类型：

- `MSG_TYPE_SENSOR_SNAPSHOT`：`source/flags/motor_id`，EMG float、heart rate/SPO2 `uint16`、6-axis IMU `int16[6]`、三个 angle/position float 与 timestamp。producer 将 `rt_tick_get_millisecond()` 返回的毫秒值存入 `rt_tick_t`；该字段表示毫秒，不应描述为原始 RT-Thread tick。部分字段被 motor-7 snapshot 复用为 position/velocity/mode/fault/torque/temp；因此字段物理单位必须结合 `source`，不能只看成员名。
- `MSG_TYPE_SENSOR_STREAM`：source、format、channels、sample rate、frame/chunk lengths、timestamp 和 16-byte data。format enum 包含 PCM S16、INT16、UINT16、FLOAT32、Q15。
- `MSG_TYPE_AI_INFERENCE_RESP`：motion/model/result codes、flags、float confidence、fatigue_score、pain_risk。当前 publisher 把 `window_ms / 1000` 放进 `pain_risk`，M33 又乘 1000 还原 window；这是当前实现约定，不应解释为通用 pain probability。
- shared PCM metadata 包含 total length、sample rate、channels、bits per sample、timestamp、CRC32 和容量 `16000*2*2` bytes。

源码没有 message ABI version、packing pragma、显式 endianness 或跨编译器兼容声明。该协议只能确认用于当前双核、共同工具链的 native ABI；任何持久化、网络转发或工具链变更都需要先引入显式 version/serialization。

## Implementation links

- message/struct 定义：`firmware/m33/applications/common/m33_m55_comm.h`
- M33 queue creator：`firmware/m33/applications/common/m33_m55_comm.c`
- M55 attach/retry：`firmware/m55/applications/m33_m55_comm.c`
- M33 sensor producer：`firmware/m33/applications/m33/m55_model_input_bridge.c`
- M55 model consumer/result producer：`firmware/m55/applications/model_input_bridge.c`、`firmware/m55/applications/model_result_publisher.c`
- M33 result consumer/CAN publisher：`firmware/m33/applications/m33/m55_model_bridge.c`

## Tests

`firmware/m55/tools/test_emg_intent_bridge_contract.py` 检查 EMG intent bridge 与 suggestion-only 边界；`firmware/m33/tools/test_m55_emg_stream_bridge_contract.py` 检查 M33 stream bridge 静态契约。它们证明源码接线，不等价于双核长时间压力或 ABI 兼容测试。

## Failure behavior

queue empty/full/timeout/not-found 映射为 RT-Thread error。M33 未初始化时 publish/consume 失败；M55 initial attach 找不到有效 shared pointer 时启动 deferred retry，而不是获得运动权限。普通 M55 publish 使用 zero timeout，queue full 可直接失败；TTS audio 单独等待 1000 ms。consume 是 non-blocking。当前消息没有 ACK、重传、CRC（PCM shared metadata 虽有 `crc32` 字段，但本协议路径未证明统一校验策略），所以调用者必须处理返回值与 freshness。

## Safety restrictions

M55 输出只是一条建议数据流。`MSG_TYPE_AI_INFERENCE_RESP` 不直接进入 motor API；M33 把它转换为强制 `suggestion_only` 的 `0x323`。IPC ready、model detected、high confidence 或 voice result 均不能替代 M33 的本地 safety assessment，也不能映射成未经审核的 `0x320`。
