# App, Web, and platform API

## Owner

FastAPI 的 rehab-arm module 拥有 HTTP/WebSocket contract；mobile Web/Capacitor App 与 platform Web 是消费者；NanoPi/device uploaders 是 telemetry producer。该 API 与 BLE NUS、ROS topics、CAN 是三个不同边界，不能混作一个“设备控制 API”。

## Consumers and direction

- Mobile/App → `/api/rehab-arm/app/v1`：账户、手机号验证、设备绑定、训练计划/session、EMG/intent summary、Agent message、AI training draft、offline queue 和 platform sync。
- Platform Web ↔ `/api/rehab-arm/v1`：device dashboard、command-center snapshot、camera、model package、VLA task request、model relay、Xiaozhi WebSocket、wiring/safety view。
- NanoPi/device → `/api/rehab-arm/v1/devices/{device_id}`：register、session/file sync、motor/sensor/safety state、camera/voice/model data。
- API → App/Web：JSON responses 与 WebSocket product events。没有 API → SocketCAN/M33 的直接 motor output implementation。

## Format, units, and version

两个 versioned HTTP prefix 是 `/api/rehab-arm/app/v1` 与 `/api/rehab-arm/v1`，payload 由 Pydantic schemas 校验，通常使用 JSON；session file、camera/model package 另含 multipart/binary。App runtime 以 bearer token 调用 JSON API。

代表性、由当前客户端实际调用的 App routes：

| Method | Route | 角色 |
| --- | --- | --- |
| GET | `/me` | App bootstrap/profile/home |
| POST | `/account/phone-verifications` 与 `/{id}/confirm` | 手机验证 |
| POST | `/devices/bind` | 绑定 M33/BLE identity 到用户记录 |
| POST | `/agent/messages` | 康复建议；不是运动命令 |
| POST/GET/PATCH | `/training-sessions/...` | 训练记录状态机与 safety events |
| POST | `/ai-training-drafts/generate` | 生成计划草稿 |

Platform/device routes 数量较多，以 router 源码为准。schema 中的 timestamp、EMG、joint fields 单位依各 payload schema/source；API prefix 的 `v1` 不会自动给内部 telemetry schema 统一单位。代码/文档证据未建立所有 route 的统一 envelope version 或统一实时 QoS，不能自行补充。

## Implementation links

- App router/schemas/service：`platform/api/app/modules/rehab_arm/app_router.py`、`platform/api/app/modules/rehab_arm/app_schemas.py`、`platform/api/app/modules/rehab_arm/app_service.py`
- Device/platform router/service：`platform/api/app/modules/rehab_arm/router.py`、`platform/api/app/modules/rehab_arm/service.py`
- Mobile calls：`apps/mobile/www/rehab-mobile-runtime.js`
- Platform Web calls：`platform/web/app/projects/[id]/rehab-arm-control/rehab-arm-control-client.tsx`
- BLE wire profile：`firmware/m33/applications/m33/bt_app_gatt_handler.c`
- ROS device bridge：`ros/rehab_arm_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py`

## Tests

`platform/api/tests/test_rehab_arm_app_backend.py` 覆盖 App workflow，`platform/api/tests/test_rehab_arm_sync.py` 覆盖 device/platform sync，`platform/api/tests/test_rehab_arm_vla_closed_loop_status.py` 固定 VLA closed-loop status 的非许可边界。

## Failure behavior

API 使用认证/项目权限、Pydantic validation 和 HTTP 4xx 拒绝非法请求；device/path ID 不一致返回 422。上传和 session 状态写入数据库或本地 telemetry storage，断网由 App offline queue/replay 路径处理。服务代码以 `non_realtime_data_only`、`*_not_motion_permission` 等 control boundary 标记数据；HTTP 成功只说明记录/请求被接受，不说明 M33 已接受运动。

## Safety restrictions

Platform API 不直接控制 motor。`estop` endpoint 当前记录 estop request，不是已证明的 SocketCAN 急停执行链；App 的 plan sync、session start、Agent answer、AI draft acceptance、VLA relay 和 Web dashboard action 均不能授予运动许可。正式动作必须另经 ROS candidate path、NanoPi gate、`0x320` 与 M33 本地裁决。BLE 也不经此 HTTP API；其当前 NUS profile 只允许 telemetry stream/heartbeat 控制。
