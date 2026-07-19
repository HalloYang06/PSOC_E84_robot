# Rehab Arm device Bluetooth protocol handoff - 2026-07-08

## Current Decision

Use BLE NUS/GATT as the primary phone-to-device path for the current M33
firmware. Treat Bluetooth Classic SPP JSON as legacy/debug compatibility unless
the firmware thread deliberately revives and validates it on hardware.

The current mobile release must not fake Bluetooth search results. If the native
Bluetooth bridge is missing, the app should show an unavailable state and tell
the user to install a build with native Bluetooth enabled.

## Current M33 BLE NUS Profile

Source files:

- `applications/m33/bt_app_gatt_db.h`
- `applications/m33/bt_app_gatt_handler.c`
- `applications/m33/app_ble_service.c`

GATT UUIDs:

- Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- RX/write characteristic, phone to device: `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
- TX/notify characteristic, device to phone: `6e400003-b5a3-f393-e0a9-e50e24dcca9e`

Limits and framing:

- RX max length: `0x0200` bytes.
- TX max length: `0x0200` bytes.
- Commands are ASCII text frames.
- Device ACKs accepted commands as `OK:<original-frame>\n`.
- Device rejects invalid commands as `ERR:invalid\n`.
- TX notifications must be enabled by the phone on the TX CCCD.

Accepted downlink command frames:

```text
heartbeat
stream:on
stream:off
stop
mode:passive
mode:active
mode:memory
mode:ai
mode:ai_assist
move:<joint_id>:<target_float>
```

Command meaning:

- `heartbeat`: link keepalive.
- `stream:on`: enable device telemetry notifications.
- `stream:off`: stop telemetry notifications.
- `stop`: emergency/stop command path.
- `mode:*`: maps to `CONTROL_MODE_*`.
- `move:<joint_id>:<target_float>`: bench/debug movement command. Do not expose
  this in patient UI without firmware safety confirmation.

Telemetry payload emitted by firmware:

```json
{"s":1,"m":1,"sh":12.3,"el":45.6,"la":0.0,"hr":75,"sp":98,"e1":0.51,"e2":0.44,"sf":0}
```

Field meanings:

- `s`: streaming enabled flag.
- `m`: control mode.
- `sh`: shoulder angle.
- `el`: elbow angle.
- `la`: lateral position.
- `hr`: heart rate.
- `sp`: SpO2.
- `e1`: EMG channel 1.
- `e2`: EMG channel 2.
- `sf`: safety state.

## Legacy Cloud/App SPP Compatibility

Source:

- Live `GET /api/rehab-arm/app/v1/public-config`
- `cloud/rehab-platform/app/api/routes/rehab_app.py`
- Live server `app/modules/rehab_arm/app_service.py`

Legacy transport:

- Bluetooth Classic SPP RFCOMM.
- Standard UUID: `00001101-0000-1000-8000-00805F9B34FB`.
- Name hint: `RehabRobotArm`.
- Encoding: UTF-8.
- Packet delimiter: newline `\n`.
- Message format: newline-delimited JSON.
- Default baud reference: `115200`.

Legacy device-to-app JSON message classes:

- `sensor`
- `mode_ack`
- `control_ack`
- `memory_ack`
- `execute_ack`
- `stop_ack`
- `error`

Legacy sensor fields known by cloud:

```text
timestamp, mode,
shoulder_angle, elbow_angle, lateral_position, lateral_pos,
shoulder_torque, elbow_torque, shoulder_force, elbow_force,
emg_ch1, emg_ch2,
shoulder_accel_x, shoulder_accel_y, shoulder_accel_z,
elbow_accel_x, elbow_accel_y, elbow_accel_z,
temperature, shoulder_temp, elbow_temp, lateral_temp
```

Legacy app-to-device command types:

```text
mode
control
memory
execute_memory
stop
stop_memory
```

## Cloud API Binding Contract

Public config:

```text
GET /api/rehab-arm/app/v1/public-config
```

Current live status:

- `device_binding.native_bluetooth_bridge.status=missing_in_current_apk`
- `device_binding.web_fallback=show_unavailable_state_do_not_fake_devices`
- `PHONE_NATIVE_BLUETOOTH_BRIDGE=missing_in_current_apk`

Device binding:

```text
POST /api/rehab-arm/app/v1/devices/bind
Authorization: Bearer <access_token>
```

Minimum body:

```json
{
  "m33_device_id": "OpenClaw-NUS",
  "ble_name": "OpenClaw-NUS"
}
```

SPP evidence upload, legacy/debug:

```text
POST /api/rehab-arm/app/v1/devices/{device_id}/legacy-spp/inbound
Authorization: Bearer <access_token>
```

Example:

```json
{
  "raw_text": "{\"type\":\"sensor\",\"emg\":0.51,\"battery\":87}"
}
```

Latest EMG readback:

```text
GET /api/rehab-arm/app/v1/emg/latest
Authorization: Bearer <access_token>
```

## Native App Bridge Expected By Frontend

Expose one of these bridge names to WebView JavaScript:

- `window.RehabArmBluetoothBridge`
- `window.Capacitor.Plugins.RehabArmBluetooth`

Minimum methods:

- `requestBluetoothPermissions()`
- `scanDevices()`
- `connect(deviceId)`
- `disconnect(deviceId)`
- `write(deviceId, text)`
- `subscribeNotifications(deviceId, callback)`

Frontend behavior:

- Ask permission before scanning.
- Scan only after the user taps the search button.
- Show only real discovered devices.
- Bind to backend only after the user selects a real device.
- If the bridge is missing, show a clear unavailable state; do not render demo
  devices.

## Safety Boundary

The app may select devices, request status, stream telemetry, and send
backend-approved setup frames. It must not expose:

- raw motor current
- raw torque
- raw motor position/velocity overrides
- CAN frames
- M33 override
- emergency stop release

M33/device firmware remains the final motion authority.

## Resource Notes

This coordination should not be heavy if scoped correctly:

- BLE scanning is the expensive part on the phone; keep scans user-initiated and
  time-limited.
- Keep only one active device connection.
- Start telemetry only after `stream:on`; stop it when the page leaves training
  or pairing.
- Do not upload every telemetry notification to the cloud in real time. Throttle
  or batch, and upload key evidence only.
- The rehab therapist Agent should call the cloud model only when the user asks a
  question, not continuously during BLE scanning.

Suggested initial resource target:

- Scan window: 8-12 seconds per user tap.
- Telemetry UI update: 2-5 Hz is enough for patient display.
- Cloud evidence upload: event-based or 1 Hz max during QA, lower for release.

## Handoff Prompt For Another Thread

Coordinate the native Android/Capacitor Bluetooth bridge for the rehab arm app.
Primary firmware protocol is BLE NUS/GATT with service
`6e400001-b5a3-f393-e0a9-e50e24dcca9e`, RX/write
`6e400002-b5a3-f393-e0a9-e50e24dcca9e`, TX/notify
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`. Downlink frames are ASCII commands such
as `heartbeat`, `stream:on`, `stream:off`, `stop`, `mode:active`, and
`move:<joint_id>:<target_float>`. Device replies with `OK:<frame>\n` or
`ERR:invalid\n`, and telemetry notification payloads are compact JSON ending in
newline. Classic SPP UUID `00001101-0000-1000-8000-00805F9B34FB` is legacy/debug
only unless current hardware validation proves it should be revived. The WebView
must expose `window.RehabArmBluetoothBridge` or
`window.Capacitor.Plugins.RehabArmBluetooth` with permission, scan, connect,
write, and notification methods. Never fake discovered devices; if the bridge is
missing, show unavailable state.
