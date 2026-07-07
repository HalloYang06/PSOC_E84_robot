# 康复臂 App 蓝牙设备协议

日期：2026-07-08

## 目标

手机 App 通过 BLE 连接 M33 固件，完成设备发现、绑定、心跳、遥测订阅和轻量控制指令下发。固件侧必须保证蓝牙链路不抢占 M55 IPC RX 队列、不绕过康复控制安全层、不在 GATT 回调里执行重控制逻辑。

## BLE 发现

- 设备名：`OpenClaw-NUS`
- 连接数：同一时间只接受 1 个手机中心设备连接；如果已有连接，新连接会被固件主动断开。
- 广播：WICED BLE undirected high advertising，断开后自动恢复广播。

## GATT Service

使用 NUS 风格 128-bit UUID。

| 类型 | UUID |
| --- | --- |
| Service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX 写入 | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX 通知/读取 | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |

属性句柄：

| 句柄 | 用途 |
| --- | --- |
| `0x0008` | TX value，固件到 App，notify/read |
| `0x0009` | TX CCCD，App 写 `0x0001` 开启通知 |
| `0x000B` | RX value，App 到固件，write/write-no-response |

## App 下行命令

编码：ASCII 文本帧，建议每帧以 `\n` 结尾，固件解析时不强依赖换行。

| 命令 | 示例 | 固件行为 |
| --- | --- | --- |
| 心跳 | `heartbeat` | 更新链路活跃时间，快速 ACK |
| 开启遥测 | `stream:on` | 开启 TX notify 遥测 |
| 关闭遥测 | `stream:off` | 关闭 TX notify 遥测 |
| 急停 | `stop` | full framework 下切回 passive；minimal framework 只记录并排空 |
| 模式切换 | `mode:active` / `mode:passive` / `mode:memory` / `mode:ai` | full framework 下交给控制层 |
| 关节目标 | `move:5:12.5` | full framework 下交给控制层 |

ACK：

| 响应 | 含义 |
| --- | --- |
| `OK:<原命令>` | 已解析并进入固件命令队列 |
| `ERR:invalid` | 命令格式错误 |
| `ERR:busy` | 固定命令队列满，App 应稍后重试 |
| `ERR:queue` | 固件队列提交失败 |

## 固件上行遥测

App 开启通知并发送 `stream:on` 后，固件通过 TX characteristic 分片发送 JSON 行。

示例：

```json
{"s":1,"m":0,"sh":0.0,"el":0.0,"la":0.0,"hr":0,"sp":0,"e1":0.00,"e2":0.00,"sf":0}
```

字段：

| 字段 | 含义 |
| --- | --- |
| `s` | streaming enabled |
| `m` | control mode |
| `sh` | shoulder angle |
| `el` | elbow angle |
| `la` | lateral position |
| `hr` | heart rate |
| `sp` | SpO2 |
| `e1` / `e2` | EMG 通道 |
| `sf` | safety state |

## 资源隔离规则

1. BLE/GATT 回调只做解析、固定队列入队、ACK/ERR 返回，不能直接执行运动控制。
2. App 下行命令队列固定深度为 `APP_BLE_COMMAND_QUEUE_DEPTH = 8`，满队列返回 `ERR:busy` 并累计 `dropped_commands`。
3. M55 IPC RX 队列仍由 `main.c:m33_handle_ipc_command()` 单一消费者负责，BLE/GATT 文件不得调用 `m33_m55_comm_consume()`。
4. minimal framework 下只启动 BLE App Link、CAN auto-init 和 IPC init，不启动完整控制/http/openclaw 链路；BLE 控制命令会被排空但不会下发运动。
5. HCI 链路由 `M33_ENABLE_APP_BLE_LINK` 控制，默认启用；如果实机确认与 WiFi/HCI 资源冲突，可编译时置 0 回退。

## App 侧建议

- 扫描时优先匹配 Service UUID，其次匹配设备名 `OpenClaw-NUS`。
- 绑定前必须完成云端登录和手机号/设备账号态确认。
- 连接成功后先写 TX CCCD 开通知，再发 `heartbeat`，收到 `OK:heartbeat` 后才显示“已连接”。
- 发送控制命令遇到 `ERR:busy` 时做 200-500 ms 退避重试，最多 3 次。
- App UI 上应区分“已绑定账号”和“已连接蓝牙设备”，避免把接口层绑定误认为真机在线。
