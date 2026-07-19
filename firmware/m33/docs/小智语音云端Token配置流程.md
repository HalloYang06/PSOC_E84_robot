# 小智语音云端 Token 配置流程

记录日期：2026-07-06

这份文档记录本次给 M55 配置小智云端 relay token 的实际方法。核心原则是：云平台只负责签发 token，小智语音只连云端；M33/M55 仍然通过现有 `m55qa_*` 桥接命令和 `rehab_service/rehab_mode_manager` 安全链路工作，不让文本命令绕过心跳、限流和停机逻辑。

## 本次配置结论

本次配置走通了以下链路：

1. 使用云平台账号登录 `http://106.55.62.122:8011/api/auth/session`。
2. 调用当前项目和设备的 relay-token 接口签发新 token。
3. 通过 M33 可见 shell 的 `m55qa_xz_token_begin`、`m55qa_xz_token_part`、`m55qa_xz_token_commit` 分片写入 M55。
4. 重新连接 WiFi 后执行 `m55qa_xz_reconnect`。
5. 通过 `m55qa_status` 确认 `xz_token=1`、`xz_ws=1`、`xz_stage=70`、`srv_hello>=1`。
6. 查询云平台 dashboard，确认能看到 `nanopi-m5 / rehab-arm-alpha` 设备。

敏感信息处理：

- 不把真实 relay token 写进 Git。
- 不把平台账号密码写进文档。
- 不把 WiFi 密码写进文档。
- 终端输出中 token 分片必须打码。

## 当前项目参数

本项目当前使用的云端参数如下：

```text
project_id = e201f41c-25a6-46e1-baf8-be6dcb83284c
device_id  = nanopi-m5
robot_id   = rehab-arm-alpha
```

小智 WebSocket 目标路径由 M55 固件侧拼接，当前等价于：

```text
ws://106.55.62.122:8011/api/rehab-arm/v1/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha
```

## 方式一：网页生成 Token

如果要用网页操作，打开平台项目页：

```text
http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab
```

登录平台账号后，在 `model-relay-lab` 页面生成设备调用令牌。生成出来的 token 必须以：

```text
rehab-relay.v1.
```

开头。不要把供应商大模型 API key 当作这个 token 使用。

## 方式二：API 生成 Token

本次实际采用的是 API 方式。

登录平台：

```http
POST http://106.55.62.122:8011/api/auth/session
Content-Type: application/json

{
  "email": "<平台账号邮箱>",
  "password": "<平台账号密码>"
}
```

成功后，从响应里取：

```text
data.access_token
```

然后签发设备 relay token：

```http
POST http://106.55.62.122:8011/api/rehab-arm/v1/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/devices/nanopi-m5/model/relay-token
Authorization: Bearer <平台 access_token>
Content-Type: application/json

{
  "ttl_seconds": 2592000,
  "label": "relay-nanopi-m5"
}
```

成功后，从响应里取：

```text
data.token
```

本次签发结果的 token 长度为 `439`，未记录明文。

## 写入 M55

### 方式 A：运行时分片写入

M55 不建议直接粘贴一整条长 token，串口或 shell 可能截断。要通过 M33 shell 分片下发：

```text
m55qa_xz_token_begin
m55qa_xz_token_part <第 1 段 token，约 40 到 60 字符>
m55qa_xz_token_part <第 2 段 token，约 40 到 60 字符>
...
m55qa_xz_token_commit
m55qa_status
```

每片之间建议间隔约 1 秒。如果某片返回 `ret=-28` 或 `result=-28`，说明 IPC 队列忙，等待后重发同一片，不要跳到下一片。

项目里已有工具脚本：

```powershell
powershell -ExecutionPolicy Bypass -File tools\load_xiaozhi_token.ps1 `
  -PortName COM20 `
  -TokenFile <只在本机临时保存的 token 文件> `
  -ChunkSize 56 `
  -CommandDelayMs 1000 `
  -FinalWaitMs 8000
```

脚本会检查 token 是否以 `rehab-relay.v1.` 开头，并在输出中隐藏 token 分片。使用完临时 token 文件后应删除，不要提交。

本次因为 Python `pyserial` 打开 `COM20` 失败，但 PowerShell/.NET `System.IO.Ports.SerialPort` 能打开，所以直接用 PowerShell 串口对象完成了同样的分片写入。

### 方式 B：烧录时预置到 Flash

如果希望设备重启后不再重新配置，可以把 WiFi 和 token 预置到 M55 外部 Flash 的 FAL 配置分区。当前 M55 分区表已经改为 256KB 擦除粒度对齐：

```text
filesystem   FAL offset 0x100000  size 512KB
wifi_cfg     FAL offset 0x180000  size 256KB  -> flash address 0x60F80000
xiaozhi_cfg  FAL offset 0x1C0000  size 256KB  -> flash address 0x60FC0000
```

注意：PSE84 SMIF Flash 的擦除粒度是 `0x40000`。不要把 `wifi_cfg` 或 `xiaozhi_cfg` 做成 4KB 这类小分区，否则运行时擦写配置时可能卡住 M55 或 M33 shell 通路。

预置内容采用固件已有的 FAL record 格式：

```text
wifi_cfg:
  magic        = 0x57494649
  version      = 1
  auto_connect = 1
  ssid[33]
  password[65]
  checksum     = FNV-1a(record 前半段)

xiaozhi_cfg:
  magic    = 0x585A544B
  version  = 1
  token[768]
  checksum = FNV-1a(record 前半段)
```

生成二进制时不要把真实 token 或 WiFi 密码写进 Git。烧录后应删除临时二进制文件。烧录命令的关键动作是：

```text
flash write_image erase <wifi_cfg_record.bin> 0x60F80000 bin
verify_image <wifi_cfg_record.bin> 0x60F80000 bin
flash write_image erase <xiaozhi_cfg_record.bin> 0x60FC0000 bin
verify_image <xiaozhi_cfg_record.bin> 0x60FC0000 bin
```

本次实测写入和校验通过，随后临时二进制文件已删除。

## WiFi 和重连

如果 `m55qa_xz_token_commit` 返回 `result=-255`，先看 `m55qa_status`。本次失败原因是 WiFi 掉线：

```text
wlan=0 ready=0 ip=0.0.0.0
xz_token=1 token_len=439
xz_ws=0
```

这说明 token 已经写入，但云端还连不上。重新配置并连接 WiFi：

```text
m55qa_wifi_ssid <SSID>
m55qa_wifi_password <WiFi 密码>
m55qa_wifi_auto 1
m55qa_wifi_save
m55qa_wifi_connect
m55qa_status
```

WiFi 正常后，再触发小智重连：

```text
m55qa_xz_reconnect
m55qa_status
```

旧版分区表缺少 `wifi_cfg` / `xiaozhi_cfg` 或分区未按 256KB 对齐时，`m55qa_wifi_save` 的 ACK 可能返回 `result=-255`，最终状态里也可能出现：

```text
storage=-255 saved=0
```

这表示板端 WiFi 持久化不可靠。修正后的状态应为 `saved=1 auto=1`，并且重启后能自动连接 WiFi。

## 成功判据

`m55qa_status` 中至少要看到：

```text
ipc_ready=1
xz_token=1
token_len=439
wlan=1
ready=1
ip=<有效 IP>
xz_ws=1
xz_stage=70
xz_errno=0
srv_hello>=1
```

本次最终关键状态为：

```text
wlan=1 ready=1 ip=192.168.3.46 rssi=-41
xz_token=1 token_len=439
xz_ws=1 xz_stage=70 xz_errno=0
srv_hello=1
saved=1 auto=1
```

闭环测试命令：

```text
m55qa_xz_text assist
```

实测返回链路：

```text
m55qa_xz_text -> ret=0
m55_model_bridge -> asr text: assist
m55qa_status -> srv_stt=1 srv_tts=1 xz_rx>0
rehab status -> mode=passive
```

这说明小智云端文本已经回到 M33。后续“小智文本切换运动模式”的实验链路已回退：M33 只记录 ASR 文本，不再把小智文本转换为助力、阻力、主动或被动模式请求，也不会调用 `rehab_service/rehab_mode_manager`。

云平台 dashboard 可用下面接口确认设备可见：

```http
GET http://106.55.62.122:8011/api/rehab-arm/v1/devices/dashboard?project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c
```

本次 dashboard 返回中能看到：

```text
device_id = nanopi-m5
robot_id  = rehab-arm-alpha
project_id = e201f41c-25a6-46e1-baf8-be6dcb83284c
```

## 常见问题

`xz_token=0`

M55 没有可用 token。重新从云平台生成 relay token，并用分片命令写入。

`xz_token=1` 但 `xz_ws=0`

token 已经写入，但 WebSocket 没连上。优先检查 WiFi：`wlan`、`ready`、`ip`、`dns0`。WiFi 正常后执行 `m55qa_xz_reconnect`，再看 `xz_stage` 和 `xz_errno`。

`m55qa_xz_token_commit result=-255`

不一定表示 token 写入失败。本次就是 token 已写入，但 WiFi 未连接导致重连失败。要看后续 `m55qa_status` 里的 `xz_token` 和 `token_len`。

单条 `m55qa_xz_token <token>` 不可靠

长 token 容易被 shell 或串口输入截断。生产配置必须使用 `begin/part/commit` 分片路径。

`ret=-28` 或 `result=-28`

IPC 队列忙。等待 1 到 2 秒，重发同一个 token 分片。

`storage=-255 saved=0`

板端配置持久化失败。当前运行态可继续测试，但重启后可能需要重新写 WiFi，必要时也重新检查 token。
