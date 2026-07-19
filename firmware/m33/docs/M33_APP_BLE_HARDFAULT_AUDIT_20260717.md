# M33 / App 蓝牙配对与 HardFault 审查（2026-07-17）

## 结论

当前不能直接恢复 M33 蓝牙自动启动，也不能认为 App 已经能和 M33 配对。

- M33 实现的是 BLE NUS GATT：`6E400001/2/3-B5A3-F393-E0A9-E50E24DCCA9E`。
- 正式 Android App 的 `RehabArmSppPlugin` 使用 Bluetooth Classic RFCOMM/SPP：`00001101-0000-1000-8000-00805F9B34FB`。
- 两端传输层不兼容，现状无法建立业务数据链路。
- App 当前“绑定成功”只调用云端 `/devices/bind`，没有连接设备、挑战应答或真机在线证明。
- M33 当前主线没有调用 `app_ble_service_init/start` 或 `bt_hci_transport_init/start`；BLE 源码存在不等于运行时启用。
- 历史实机记录显示，启用 HCI 后曾进入 Secure HardFault，关闭 HCI 后 Shell 恢复。因此必须保持默认关闭和手动单次启动。

风险最低的总体方向是让 Android App 增加 BLE GATT/NUS transport，而不是在 M33 再引入尚未集成的 RFCOMM/SPP。

## M33 侧主要风险

### P0：GATT 回调过重

`bt_app_gatt_handler.c` 在 BTSTACK 回调中执行了以下工作：

- 栈上分配约 577 字节的 frame/response；
- `sscanf` 浮点解析和日志输出；
- `RT_WAITING_FOREVER` 获取 App service mutex；
- 修改共享 TX buffer 并直接发 notification。

应改为：回调只做指针/长度/offset 校验、固定大小复制和非阻塞入队；解析、ACK 和业务分发放到独立低优先级 worker。

### P0：HCI 生命周期不完整

- RX/TX terminate 函数为空，但 deinit 会删除队列和释放内存，存在运行线程访问已释放资源的风险。
- HCI 初始化中途失败没有完整逆序回滚。
- CTS 等待存在无界阻塞。
- 重复或并发启动缺少单 owner 状态机。

首版必须禁止运行期 deinit/restart，只允许一次手动启动，并保留失败诊断。

### P1：输入和共享数据

- GATT callback 在判空前访问 `p_event_data`。
- write offset、prepared write 和 `p_val` 校验不完整。
- `app_ble_service` 仅保存最后一条命令，突发写入会覆盖。
- `stopXYZ`、`heartbeatXYZ` 会被前缀匹配接受；未知 mode 会静默变成 passive。
- joint、浮点有限性和运动范围没有在 BLE 边界验证。
- conn_id、CCCD、TX data/length 和 service runtime 缺少统一 owner 或快照 API。

### P1：配对并未持久化

- `app_kv_store_init()` 为空实现。
- link key 和 identity key update 事件没有保存，请求事件固定返回失败。
- bond 索引和全局结构缺少锁与损坏校验。
- GATT 属性当前没有强制 encrypted/authenticated 权限。

若以后写外部 Flash，必须通过 M33/M55 的 SMIF0 guard，在普通线程中有界执行，禁止在 BT callback 或运动过程中擦写。

## App 侧主要风险

正式 App 远端引用：`remotes/wenjunyong/app/rehab-arm-mobile-stitch`。

1. `RehabArmSppPlugin.java` 只列出 Android 系统已绑定的 Classic 设备并创建 RFCOMM socket。
2. Web runtime 的扫描 wrapper 只调用 `listBondedDevices()`，没有调用插件 `connect()`。
3. `bindSelectedDevice()` 只提交云端账号绑定，不能证明附近真机属于该账号。
4. `sendLegacyFrame()` 没有接入当前 patient binding 流程。
5. App 必须区分四个状态：云端账号已绑定、系统已配对、GATT 已连接、设备挑战已通过。

## 小提交整改顺序

### A. 默认关闭的启动门禁

- 新增独立 BLE runtime gate，不修改当前动作控制路径。
- 默认编译关闭，不自动启动。
- 只提供状态命令和一次性手动启动入口。

### B. GATT 边界硬化

- 先判空、handle、offset 和精确长度，再复制。
- callback 不做浮点解析，不永久等待 mutex。
- 补静态/主机测试，HCI 仍保持关闭。

### C. 有界 RX 队列

- 固定深度 MQ，普通命令非阻塞入队。
- STOP 使用独立 latch。
- worker 解析后只能进入现有 rehab 安全状态机，不能直接调用电机。
- ACK 区分 accepted 和 applied。

### D. 单 owner HCI 状态机

- `OFF -> STARTING -> RUNNING/FAILED`。
- CTS 有界超时，初始化失败逆序回滚。
- 禁止运行期 deinit/restart，仍不自动启动。

### E. M33 空载实机验证

- 先验证 HCI、广播、连接、NUS heartbeat。
- 同时检查 Shell、CAN、M33/M55 IPC、线程栈和 fault 寄存器。
- 通过前不开放运动命令。

### F. Android BLE GATT/NUS transport

- 新增 scan/connect/discover/CCCD/write/notify/reconnect。
- 有界串行写队列，按 MTU 分片并等待回调。
- 首版只允许 heartbeat/status，不发送运动命令。

### G. 真正配对和绑定

- 强制加密 GATT 权限。
- 带版本和 CRC 的 bond store。
- 设备 nonce 挑战通过后，App 才允许调用云端 bind。
- 运动非 PASSIVE 时禁止 bond Flash 写擦。

## 本轮边界

本轮审查没有启用 HCI、没有烧录、没有修改 App、没有发送 BLE 或运动命令。当前 CAN/MuJoCo 动作路径不受影响。
