# Project Progress

## 2026-06-10

Completed:
- CM55 LVGL Wi-Fi provisioning now supports direct nearby-network selection on the touchscreen. The panel scans APs, shows a selectable SSID/RSSI/security/channel list, fills the SSID field when a network is tapped, accepts the password on the same page, then saves/connects through the shared Wi-Fi config service.
- CM55 Wi-Fi scan now uses the RT-Thread WLAN scan-report event callback path and keeps a bounded AP cache (`WIFI_CONFIG_SCAN_MAX_APS=12`) for LVGL/App reuse.
- Synchronized the updated Wi-Fi service and LVGL panel from the M55 Git reference repo into the actual RT-Thread Studio `wifi` project.

Validated:
- Built the M55 Git reference repo `_m55_ref_repo` with `scons -j4`: passed, produced `rtthread.hex`, size `text=1173056 data=80860 bss=4534696`.
- Built the actual M55 RT-Thread Studio `wifi` project with `scons -j4`: passed, produced `rtthread.hex`, size `text=1173056 data=80860 bss=4534700`.

Failed or unverified:
- Physical LVGL touch selection, Wi-Fi scan visibility, password entry, and live save/connect still need board-side QA after flashing this M55 image.
- Hidden SSID remains supported through manual SSID entry; it will not appear in the scan list.

Decision:
- Touchscreen, shell, M33/App IPC, and future BLE/App provisioning must continue to use the shared CM55 Wi-Fi config service. Do not add a second Wi-Fi state machine inside voice/XiaoZhi code.

Next step:
- Flash the new M55 image, tap `Scan` on the LVGL page, select the target SSID from the list, enter the password, press `Connect`, then verify `saved=1 auto=1 storage=0` and a live netdev/IP through the screen or `m55qa_status`.

Completed:
- CM55 Wi-Fi configuration was promoted from RAM-only debug commands to a reusable mainline service with local flash persistence at `/flash/rehab_wifi.cfg`.
- CM55 now supports local shell commands for user-facing provisioning: `m55_wifi_ssid`, `m55_wifi_password`, `m55_wifi_save`, `m55_wifi_connect`, `m55_wifi_auto`, `m55_wifi_forget`, `m55_wifi_status`, `m55_wifi_diag`, and `m55_wifi_scan`.
- Added a LVGL touchscreen Wi-Fi setup panel in the M55 `wifi` project. The panel shows live WLAN/WHD/netdev state, saved/auto-connect/storage state, and provides SSID/password entry, scan, diag, save, connect, off, and forget actions.
- CM55 now attempts saved Wi-Fi auto-connect after boot, without storing platform relay tokens or vendor LLM API keys in the Wi-Fi config file.
- M33/CM55 IPC added explicit Wi-Fi config keys: `VOICE_CONFIG_WIFI_SAVE`, `VOICE_CONFIG_WIFI_FORGET`, and `VOICE_CONFIG_WIFI_AUTO_CONNECT`.
- M33 shell bridge added `m55qa_wifi_save`, `m55qa_wifi_forget`, and `m55qa_wifi_auto <0|1>` for the future BLE/App provisioning path.
- M33 `m55qa_status` now reports Wi-Fi persistence observability: `saved`, `auto`, and `storage`.

Validated:
- Built the actual M55 RT-Thread Studio `wifi` project with `scons -j4`: passed, produced `rtthread.hex`, size `text=1171040 data=80860 bss=4534060`.
- Built the M55 Git reference repo `_m55_ref_repo` with `scons -j4`: passed, produced `rtthread.hex`, size `text=1171040 data=80860 bss=4534056`.
- Built the M33 repo `yiliao_m33` with `scons -j4`: passed, produced `rtthread.hex`, size `text=552844 data=16244 bss=310576`.

Failed or unverified:
- The LVGL touchscreen provisioning panel has only been build-validated; physical touch coordinate accuracy and save/connect behavior still need board-side QA after flashing.
- Saved Wi-Fi auto-connect has not yet been live-validated after reboot on the powered board.
- Existing `strncpy` truncation warnings remain in status-name and bounded credential copies; builds pass and the copies are bounded.

Decision:
- Wi-Fi provisioning is now a shared CM55 service used by local shell, LVGL, and M33/App IPC. Do not add separate Wi-Fi state machines in voice, BLE, or App code.
- `/flash/rehab_wifi.cfg` may contain only local Wi-Fi SSID/password and auto-connect state. Platform scoped relay tokens remain in the XiaoZhi token path and vendor API keys must never be stored on the device.

Next step:
- Flash the new M55 image, use either the touchscreen panel or M33 shell to configure Wi-Fi, then reboot and verify `m55qa_status` shows `saved=1 auto=1 storage=0` and a live netdev/IP after auto-connect.

Completed:
- Added `tools/xiaozhi_ws_smoke_test.ps1`, a PC-side XiaoZhi WebSocket smoke test that simulates the device hello/listen/binary PCM flow without needing a person physically near the CM55 microphone.
- CM55 XiaoZhi binary audio streaming now accumulates local mic PCM into fixed `640` byte frames before sending to the platform, matching `16 kHz mono PCM S16LE, 20 ms` from the current platform contract. M55 commit: `31df3a3 Align XiaoZhi PCM frame contract`.
- Added `tools/load_xiaozhi_token.ps1` to load platform scoped XiaoZhi relay tokens over the visible M33 shell without printing token chunks in terminal output.
- CM55 voice status flags now report XiaoZhi observability bits for `xiaozhi_listening`, `xiaozhi_connected`, and `xiaozhi_has_token`.
- M33 `m55qa_status` decodes voice status flags into readable fields: `wake_on`, `wake_ready`, `wake_hit`, `xz_listening`, `xz_ws`, and `xz_token`.
- CM55 default XiaoZhi WebSocket endpoint was aligned with the current cloud command-center implementation:
  `ws://106.55.62.122:8011/api/rehab-arm/v1/projects/fd6a55ed-a63c-44b3-b123-96fb3c154966/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha`.
- CM55 listen-stop handling now distinguishes local stop from server-directed stop. When the platform sends `{"type":"listen","state":"stop"}`, CM55 closes local listening state without echoing another stop back to the server.
- Added long XiaoZhi platform-token configuration over the visible M33 shell using chunked commands: `m55qa_xz_token_begin`, `m55qa_xz_token_part`, `m55qa_xz_token_commit`, and `m55qa_xz_token_clear`.
- Added matching CM55 voice-config IPC keys and CM55-side token staging/commit handling so platform relay tokens longer than the FinSH line limit can be configured without hardcoding secrets in firmware.
- Increased CM55 XiaoZhi relay token storage to 768 bytes and WebSocket extra-header/handshake buffers to handle long platform-scoped relay tokens.
- CM55 XiaoZhi flow was realigned to the official `Edgi_Talk_M55_XiaoZhi` sequence: local wake word -> WebSocket connection -> `hello` -> `listen start` -> streaming binary audio frames -> platform `listen stop`/reply.
- The project-specific platform is now treated as the WebSocket/API endpoint behind the official XiaoZhi client flow, not a separate firmware-side LLM/API-key implementation.
- Added M33-to-CM55 voice configuration IPC: `MSG_TYPE_VOICE_CONFIG` with URL, token, and reconnect keys.
- Added M33 shell bridge commands `m55qa_xz_url`, `m55qa_xz_token`, and `m55qa_xz_reconnect` so the visible M33 shell can configure the CM55 XiaoZhi relay without stealing the CM55 console.
- Fixed the M33 SCons include path handling so `vendor_btstack` headers resolve under the current RT-Thread Studio Python2/SCons environment.
- Increased the M55 WebSocket client path/request buffers so the long rehab-arm platform endpoint is not truncated.

Validated:
- Burned the latest actual `wifi/rtthread.hex` containing the 640-byte PCM framing update to CM55. OpenOCD reported `wrote 847872 bytes`; the final reset/acquisition step printed a KitProg acquisition warning, but COM26 subsequently proved M33/M55 IPC was alive.
- COM26 after the latest CM55 burn:
  - `m55qa_wake_on` returned `voice_ack seq=11 cmd=3 result=0`.
  - `m55qa_status` showed `ipc_ready=1`, `has_model=1`, `wake_on=1`, `wake_ready=1`, `frames/windows` increasing, and `latest_pcm_len=320` for local mic chunks. Cloud WebSocket framing is now handled separately at 640 bytes per binary frame.
- HTTP reachability from the Windows PC to the platform is available: `http://106.55.62.122:8011/` returns the uvicorn 404 response, and `http://106.55.62.122:3001/` redirects to `/login`.
- `tools/xiaozhi_ws_smoke_test.ps1` loads and starts a connection attempt. With a dummy `rehab-relay.v1.fake.fake` token it fails before the XiaoZhi flow, as expected for an invalid token/test.
- Built M55 `_m55_ref_repo` and actual RT-Thread Studio `wifi` with `scons -j4` after the 640-byte XiaoZhi PCM framing update. Both builds passed; only the existing `m55_console_detach` unused-function warning remains.
- Ran `tools/load_xiaozhi_token.ps1 -ReconnectOnly` on COM26. It read `m55qa_status`, sent `m55qa_xz_reconnect`, and read status again. Because no matching scoped token is loaded, CM55 still reports `cmd=1003 result=-255`, `xz_token=0`, and `xz_ws=0`, which is expected.
- Built M55 `_m55_ref_repo`, actual `wifi`, and M33 `yiliao_m33` with `scons -j4` after adding decoded status flags.
- Re-relocated M33 `build/rtthread.hex`; first line is `:02000004603466`.
- Burned both cores after the status-observability update. OpenOCD reported `wrote 847872 bytes` for CM55 and `wrote 569344 bytes` for M33.
- COM26 after burn:
  - `m55qa_wake_on` returns `voice_ack ... cmd=3 result=0`.
  - `m55qa_status` prints decoded fields, for example `wake_on=1 wake_ready=1 wake_hit=0 xz_listening=0 xz_ws=0 xz_token=0`.
  - `m55qa_xz_reconnect` returns `voice_ack ... cmd=1003 result=-255` when no scoped relay token is loaded, which is expected.
- M55 `_m55_ref_repo` and the actual RT-Thread Studio `wifi` working tree both build successfully after the endpoint/listen-stop update.
- Cloud platform owner reported the current existing medical rehab-arm command center has verified WebSocket 101, hello/listen/audio/reply, 16 kHz mono PCM S16LE binary frame intake, scoped-token auth, and no low-level control field leakage.
- M55 `_m55_ref_repo` builds successfully with `scons -j4`; synchronized files also build successfully in the actual RT-Thread Studio `wifi` working tree.
- Burned the current `wifi/rtthread.hex` to CM55; OpenOCD reported `wrote 847872 bytes`.
- M33 `yiliao_m33` builds successfully with `scons -j4`; the latest `build/rtthread.hex` was fully relocated from `0x0834..0x083C` to `0x6034..0x603C`.
- M33 burn used the fully relocated `build/rtthread.hex`; OpenOCD reported `wrote 569344 bytes`.
- COM26 after burning both cores:
  - M33 shell is alive.
  - `help` lists `m55qa_xz_token_begin`, `m55qa_xz_token_part`, `m55qa_xz_token_commit`, and `m55qa_xz_token_clear`.
  - `m55qa_xz_token_begin` and `m55qa_xz_token_part abc123` return CM55 ACKs with `cmd=1004 result=0` and `cmd=1005 result=0`, proving chunked token IPC reaches CM55.
  - `m55qa_xz_token_commit` returns `cmd=1006 result=-255` with a dummy token because the subsequent WebSocket reconnect fails as expected, proving commit triggers the CM55 reconnect path.
  - `m55qa_xz_token_clear` reaches CM55 as `cmd=1007`; the temporary dummy token was cleared after validation.
  - `m55qa_wake_on` returns `voice_ack ... cmd=3 result=0`.
  - `m55qa_status` shows `ipc_ready=1`, `flags=0x3`, increasing `frames/windows`, and `wake_stage=201`.
  - `help` lists `m55qa_xz_url`, `m55qa_xz_token`, and `m55qa_xz_reconnect`.
  - `m55qa_xz_reconnect` reaches CM55 and returns `voice_ack ... cmd=1003 result=-255`, proving the config command path works while the external platform connection is not yet accepted/reachable.

Failed or unverified:
- End-to-end PC-side XiaoZhi WebSocket smoke testing still needs a valid scoped relay token for `project_id=fd6a55ed-a63c-44b3-b123-96fb3c154966`, `device_id=nanopi-m5`.
- The previously shared `rehab-relay.v1...` sample token appears scoped to a different project/device than `fd6a55ed-a63c-44b3-b123-96fb3c154966 / nanopi-m5`, so it was not loaded into CM55 for production endpoint testing.
- `xz_ws=0` and `xz_token=0` remain expected until a valid platform scoped relay token is loaded into CM55.
- End-to-end spoken XiaoZhi chat from the physical CM55 microphone still needs live validation after loading a valid scoped relay token into CM55.
- Current CM55 stream sends verified 16 kHz mono PCM frames. The official sample declares Opus in `hello` and uses an Opus encoder path; migrating Opus should be a separate step after the platform-side PCM path is proven or platform requires Opus.
- Live wake-word trigger after the latest official-sequence refactor still needs another spoken test; the wake backend itself is ready at `wake_stage=201`.

Decision:
- Keep M55 firmware aligned with official XiaoZhi client state flow. The platform adapts its endpoint, auth, ASR/LLM/classification, and VLA-language routing around that flow.
- M55 does not hold vendor LLM API keys. It only uses a platform-scoped relay token/configuration.
- Voice remains HTTP/WebSocket, not CAN. M33 remains safety authority and only receives high-level classified text/status, never direct LLM motor commands.

Next step:
- First run `tools/xiaozhi_ws_smoke_test.ps1` with a valid scoped relay token to prove the cloud XiaoZhi endpoint accepts hello/listen/640-byte PCM without needing an on-site speaker. Then load the same token into CM55 through `tools/load_xiaozhi_token.ps1`, confirm `xz_token=1` and `xz_ws=1`, and leave live wake-word speech validation for when someone is physically near the board.

Completed:
- CM55 wake-word mainline switched away from the blocked DEEPCRAFT/U55 path to the official XiaoZhi Edge Impulse TFLite model backend.
- Added `applications/xiaozhi_edge_impulse_wake_backend.cpp` in the M55 reference tree and wired it through `xiaozhi_wake_engine`.
- Fixed the local CM55 mic wake path so 20 ms PCM frames are continuously fed into the wake backend; the backend owns the 1 second rolling inference window.
- Large wake buffers now allocate from RT-Thread heap instead of M55 internal `.bss`, avoiding internal RAM overflow.
- Synchronized the current M55 wake source changes from `D:\RT-ThreadStudio\workspace\wifi` into `D:\RT-ThreadStudio\workspace\_m55_ref_repo`.

Validated:
- `scons -j4` in the M55 working tree builds successfully and produces `rtthread.hex`.
- OpenOCD flash-bank preflight showed `cat1d.cm33.smif1_ns` at `0x60000000`.
- Burned the SCons-built M55 image directly with OpenOCD; write reported `wrote 827392 bytes`.
- COM26 QA passed after burn:
  - `m55qa_wake_on` returns `voice_ack ... cmd=3 result=0`.
  - `m55qa_status` shows `ipc_ready=1`, `flags=0x3`, `wake_stage=20`, `err=0`.
  - `frames` and `windows` increase while listening, proving CM55 mic PCM reaches the wake backend and the backend enters inference processing.

Failed or unverified:
- Acoustic wake detection by speaking `xiaorui` has not been user-validated yet.
- Current backend uses a minimal local MFCC-like extractor against the official XiaoZhi model. It builds and runs, but recognition quality still needs live validation and may need closer Edge Impulse DSP parity.
- The full Edge Impulse SDK was not imported into the repo because the generated SDK has restrictive subscription licensing text and previously caused TFLM/FlatBuffers/KissFFT link conflicts.

Decision:
- Treat CM55 wake word as the first product voice gate: local wake word on CM55, then voice/chat/instruction relay over HTTP/WebSocket to the platform. Do not send voice through CAN.
- Do not store platform model API keys in firmware or repository. M55 should use platform-scoped relay credentials/configuration.

Next step:
- With the board powered and mic near the speaker, run `m55qa_wake_on`, speak `xiaorui`, then verify `m55qa_status` increments `detected` and the platform voice relay receives the wake/listen event.

Completed:
- M33 mainline now exposes CM55 QA shell commands: `m55qa_status`, `m55qa_wake_on`, `m55qa_wake_off`, `m55qa_capture_on`, `m55qa_capture_off`.
- M33/CM55 IPC protocol added `MSG_TYPE_VOICE_CONTROL_ACK` so M33 can verify that CM55 actually consumed and handled voice-control commands.
- CM55 no longer binds `uart2` as its console during board init. The visible serial shell remains on M33, and CM55 is observed through M33 IPC/ACK.
- CM55 voice service keeps the official Infineon DEEPCRAFT wake path as the active wake backend and handles M33 voice-control commands.

Validated:
- Built `D:\RT-ThreadStudio\workspace\wifi\Debug` successfully.
- Built `D:\RT-ThreadStudio\workspace\yiliao_m33\Debug` successfully.
- Manually regenerated M33 hex and confirmed relocation first line is `:02000004603466`.
- Burned M33 and CM55 firmware with OpenOCD/program scripts.
- OpenOCD reset reported `Boot Status : CYBOOT_SUCCESS`.
- COM26 QA passed:
  - `m55qa_status`: `ipc_ready=1 tx_pending=0 rx_pending=0 has_model=1`.
  - `m55qa_wake_on`: CM55 returned `voice_ack ... cmd=3 result=0`.
  - `m55qa_capture_on`: CM55 returned `voice_ack ... cmd=1 result=0`.
  - `m55qa_wake_off`: CM55 returned `voice_ack ... cmd=4 result=0`.

Failed or unverified:
- Real wake-word acoustic detection was not field-validated in this pass; only the M33-to-CM55 command/ACK foundation was validated.
- CAN still emits repeated `direct tx pending` diagnostics when the bus/motor side is not acknowledging frames; this is separate from CM55 IPC.

Next step:
- Run a visible user test with microphone input: enable wake listening, speak the official wake phrase, verify CM55 publishes a wake result to M33 and the platform voice relay receives the follow-up utterance.
