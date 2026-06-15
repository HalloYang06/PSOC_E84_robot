# Project Progress

## 2026-06-15

Completed:
- Revalidated CM55 Wi-Fi auto-connect on the powered board after repeated M55 flashes. `m55qa_status` consistently reports `saved=1 auto=1 storage=0`, `wlan=1 ready=1`, and IP `192.168.3.32`.
- Added staged XiaoZhi/WebSocket diagnostics so `m55qa_status` reports token length, WebSocket stage/errno, and reconnect progress separately from Wi-Fi state.
- Added a CM55 TCP probe path for `106.55.62.122:8011`; board-side TCP reaches the cloud endpoint, so the current blocker is above basic Wi-Fi/routing.
- PC-side validation with the same endpoint and scoped token returns `HTTP/1.1 101 Switching Protocols`, proving the cloud URL/token/path are valid.

Validated:
- M55 `wifi` builds with `python -m SCons -j4`.
- M55 image and WHD resources were flashed together with OpenOCD; application and resource writes reached 100%.
- Board QA over COM4 confirmed Wi-Fi auto-connect survives reset and the XiaoZhi reconnect no longer freezes the whole board while diagnosing.

Current blocker:
- The hand-written socket WebSocket client on CM55 reaches handshake receive (`xz_stage=50`) but RT-Thread/lwIP socket `recv` can block despite `O_NONBLOCK`, `MSG_DONTWAIT`, `SO_RCVTIMEO`, and direct `lwip_recv` attempts.
- Next implementation should move XiaoZhi WebSocket transport to the bundled lwIP callback WebSocket client (`RT_LWIP_USING_WEBSOCKET`, `lwip/apps/websocket_client.h`) or a netconn/raw callback path instead of continuing to patch POSIX/SAL sockets.

Next step:
- Enable/build the official lwIP WebSocket app sources and wrap `wsock_connect/wsock_write` behind the existing `applications/websocket_client.h` API, then rerun `m55qa_xz_reconnect` and proceed to wake-word audio once `xz_ws=1`.

## 2026-06-10

Completed:
- Fixed the CM55 LVGL screen not appearing after boot. The LVGL RT-Thread port existed in the image, but `lvgl_thread_init()` was only exported as the `thread_init` shell command and was not started automatically.
- CM55 `main()` now starts the LVGL thread at boot when `BSP_USING_LVGL` is enabled.
- Added a duplicate-start guard inside `lvgl_thread_init()` so manual `thread_init` remains safe as a fallback.
- Added the missing `<lvgl.h>` include in the LVGL RT-Thread port so LVGL APIs are declared explicitly.
- Synchronized the fixed LVGL startup code into the actual RT-Thread Studio `wifi` project.

Validated:
- Built the M55 Git reference repo `_m55_ref_repo` with `scons -j4`: passed, produced `rtthread.hex`, size `text=1173760 data=80860 bss=4534696`.
- Built the actual M55 RT-Thread Studio `wifi` project with `scons -j4`: passed, produced `rtthread.hex`, size `text=1173760 data=80860 bss=4534700`.

Failed or unverified:
- Physical screen output after flashing the new image is still unverified.
- If the old image is still flashed, the temporary field check is to type `thread_init` in the shell; if the LVGL screen appears, the missing auto-start was the root cause.

Next step:
- Flash the rebuilt M55 image from the actual `wifi` project, confirm boot logs show `[m55] starting LVGL thread` and `[m55] LVGL thread init ret=0`, then verify the Wi-Fi panel appears without typing `thread_init`.

Completed:
- Added CM55 shell-side Wi-Fi scan observability for cases where LVGL touch/display is not ready on site. `m55_wifi_scan` now starts the asynchronous scan and tells the operator to wait, while `m55_wifi_aps` prints the cached AP list with SSID, RSSI, security, channel, and BSSID.
- Synchronized the updated M55 `main.c` into the actual RT-Thread Studio `wifi` project.

Validated:
- Built the M55 Git reference repo `_m55_ref_repo` with `scons -j4`: passed, produced `rtthread.hex`, size `text=1173600 data=80860 bss=4534696`.
- Built the actual M55 RT-Thread Studio `wifi` project with `scons -j4`: passed, produced `rtthread.hex`, size `text=1173600 data=80860 bss=4534700`.

Failed or unverified:
- The new `m55_wifi_aps` output is build-validated only; live AP content still needs a flashed board with Wi-Fi powered.

Next step:
- On site, if LVGL scan UI is unclear, use CM55 shell `m55_wifi_scan`, wait 3-5 seconds, then run `m55_wifi_aps` to confirm the scan service is seeing APs.

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

## 2026-06-13 - LVGL WiFi Connected; XiaoZhi Auto-Connect Moved Behind WiFi Readiness

Completed:
- M55 WiFi/LVGL flow reached a real connected state from the touchscreen UI, without requiring command-line WiFi provisioning.
- Added a safe XiaoZhi auto-connect policy in the M55 WiFi project: the XiaoZhi voice/WebSocket path now waits until WiFi reports ready and has a non-zero IP for multiple checks before starting wake listening and reconnecting the relay.
- Updated the M55 voice initialization path so an early XiaoZhi WebSocket failure is treated as a deferred connection instead of aborting voice service setup.
- Added a local-only `xiaozhi_local_token.h` path in the M55 project and kept it ignored; token length was verified locally without printing the token.
- Added a planned LVGL status line for XiaoZhi state (`未配置/等待网络/连接中/已连接/重试中`, plus WebSocket stage/errno) so future QA does not depend on M33 shell.

Validated:
- PC-side XiaoZhi WebSocket smoke test had previously proven the relay token/server/model path accepts hello/listen and returns a chat reply.
- M55 `scons -j4` builds successfully after the WiFi-first XiaoZhi auto-connect change.
- `program_with_resources.bat` was run for M55; OpenOCD progress reached 100% for application and resource programming. The familiar trailing KitProg3 acquire error remains non-authoritative after completed write progress.
- After the M55 burn, the user confirmed WiFi connected again from LVGL.

Failed or unverified:
- M33 shell on `COM4` currently does not respond to `m55qa_status`; other visible COM ports also did not return MSH output during spot checks.
- No serial evidence yet for board-side `xz_ws=1` after WiFi connection because M33 shell/log forwarding is unavailable.
- NanoPi camera QA was not available: the recorded NanoPi IP `192.168.2.66` did not respond to ping from the Windows host.
- End-to-end spoken XiaoZhi conversation from CM55 mic remains unverified on hardware in this pass.

Decision:
- WiFi provisioning is the highest priority path. XiaoZhi must never start voice/mic/WebSocket work before WiFi has a stable IP, and reconnect failures must not block LVGL.
- Keep the platform token out of git and docs. The firmware uses local injection or ignored local headers only.

Next step:
- Restore a reliable M33 status channel or use platform-side connection logs to prove board-side `xz_ws=1`; then test wake word `xiaorui` -> CM55 audio -> relay reply.

## 2026-06-13 - XiaoZhi Protocol Realigned To Official WebSocket Example

Completed:
- Rechecked the local official XiaoZhi reference at `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32`.
- Identified the official WebSocket path in `docs/websocket.md`, `main/protocols/websocket_protocol.cc`, and `main/protocols/protocol.cc`.
- Updated the M55 XiaoZhi relay JSON to match the official example:
  - `hello.version=1`
  - `transport=websocket`
  - `features.mcp=true`
  - `audio_params.format=opus`
  - `sample_rate=16000`, `channels=1`, `frame_duration=60`
  - `listen start mode=auto`
- Updated `tools/xiaozhi_ws_smoke_test.ps1` to use the same official hello/listen shape and 60 ms frame cadence.

Validated:
- M55 `scons -j4` builds successfully after the official-protocol JSON change.
- PC-side smoke test with the local scoped token connected to the relay, received official-style `hello` ACK, received `listen start` ACK, sent 60 ms binary frames, and received a chat/VLA classification reply on `listen stop`.

Failed or unverified:
- The M55 firmware has not yet been reflashed with this official-protocol build because the board WiFi is currently connected and should not be reset unnecessarily.
- M55 still does not include a true Opus encoder. The relay accepted the 60 ms binary frame path in PC smoke testing, but full official parity requires either adding an M55 Opus encoder or making the relay's PCM compatibility an explicit documented contract.
- Board-side `xz_ws=1` remains unverified because M33 shell/COM4 is currently not returning status output.

Decision:
- XiaoZhi protocol work should follow the official ESP32 reference first. Any rehab relay extensions must be additive and documented, not silently replacing official field names or modes.
- WiFi remains the gate: XiaoZhi auto-connect starts only after stable WiFi/IP.

Next step:
- When a reset is acceptable, burn the latest M55 build, reconnect WiFi from LVGL, then verify the screen XiaoZhi status line or platform-side connection logs before attempting wake-word speech.

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

## 2026-06-13 - M55 LVGL XiaoZhi Status Visibility Burned

Completed:
- Updated the M55 LVGL WiFi panel so WiFi status stays in a compact two-line label and XiaoZhi WebSocket state is shown in its own `XiaoZhi: <state> S:<stage> E:<errno>` strip.
- Changed the bottom diagnostic toggle from Chinese text to `INFO/HIDE` to avoid missing glyph boxes on the current `rehab_wifi_font`.
- Recorded the UI/status lesson in the existing M55 `wifi避坑文档.md`.
- Synced and pushed the M55 Git branch with commit `42bd8fb Improve LVGL XiaoZhi status visibility`.

Validated:
- M55 `python -m SCons -j4` passed after the UI change.
- `program_with_resources.bat` was run after the build; both application and WHD resource programming reached 100% before the familiar trailing KitProg3 acquire error.

Failed or unverified:
- COM4 still only shows early M33 boot output, so `m55qa_status`/`xz_ws=1` remains unavailable from serial.
- NanoPi `192.168.2.66` has TCP port 22 open but closes before sending an SSH banner; camera QA could not capture the LCD in this pass.
- End-to-end spoken XiaoZhi conversation is still unverified on board. The next blocker is proving M55 WebSocket connection status after WiFi reconnect, then validating the PCM/Opus audio boundary.

Next step:
- After WiFi is reconnected on the flashed UI, use the visible XiaoZhi status strip or platform-side relay logs to prove `S:70`/connected before testing wake word speech.

## 2026-06-13 - M55 LVGL Layout Retry For Overlap

Completed:
- Reworked the M55 LVGL WiFi panel after a user photo still showed overlap: AP list shortened, SSID/password fields tightened, and the six main buttons changed to a `2 x 3` grid.
- XiaoZhi display now maps WebSocket stage/errno into actionable states such as `等待启动`, `TCP连接`, `握手中`, `TCP失败`, and `握手失败` instead of only showing `连接中`.
- Pushed M55 commits `94b63f2 Tighten LVGL WiFi panel layout` and `41e4a66 Document LVGL layout retry`.

Validated:
- M55 `python -m SCons -j4` passed.
- M55 was flashed with `program_with_resources.bat`; app and resource programming reached 100% before the known trailing KitProg3 acquire error.

Failed or unverified:
- COM4 still only shows early M33 boot output, so serial `m55qa_status` remains unavailable.
- Need the next screen photo or platform-side logs after WiFi reconnect to determine whether XiaoZhi is stuck at TCP, handshake, or auto-start.

Next step:
- Reconnect WiFi on the device, read the new XiaoZhi state/stage from the LVGL strip, then fix the specific network/WebSocket phase rather than guessing from a generic `连接中`.

## 2026-06-13 - M55 LVGL Chinese Font Coverage Fixed

Completed:
- Regenerated M55 `applications/rehab_wifi_font.c` from Noto Sans SC with expanded symbols for WiFi provisioning and XiaoZhi status text.
- Restored the LVGL diagnostic button text from `INFO/HIDE` back to Chinese `诊断/隐藏`.
- Documented the font coverage lesson in the existing M55 WiFi pitfalls document.
- Pushed M55 commits `6f869bb Expand LVGL WiFi Chinese font coverage` and `dac1e30 Document LVGL font coverage fix`.

Validated:
- M55 `python -m SCons -j4` passed after regenerating the font.
- M55 was flashed with `program_with_resources.bat`; app and resource programming reached 100% before the known trailing KitProg3 acquire error.

Next step:
- Use the next LCD photo to confirm no square glyphs remain, then continue spacing fixes only for actual overlap points.

## 2026-06-13 - XiaoZhi UI State And Source-Extracted Font Coverage

Completed:
- Added a lightweight M55 XiaoZhi UI state model for visible phases: waiting network, connecting, ready, listening, thinking, speaking, and error.
- Updated the LVGL WiFi screen with a dedicated XiaoZhi panel that shows status, detail text, last reply text, and a spinner while thinking.
- M55 voice service now updates UI state on WebSocket hello, wake/listen start, listen stop/thinking, `tts start/stop/sentence_start`, server text replies, and binary audio replies.
- Regenerated `rehab_wifi_font.c` from the actual fixed UI/status Chinese characters in M55 source files instead of a hand-written guess list.
- M33 audio playback path now initializes `sound0` by default, receives `MSG_TYPE_TTS_AUDIO` in the main IPC loop, and writes audio chunks to the RT-Thread audio device. This is a PCM/WAV-compatible playback path; official Opus decode remains a separate gap.

Validated:
- M55 `python -m SCons -j4` passed after the XiaoZhi panel and regenerated font.
- M55 was flashed with `program_with_resources.bat`; application and WHD resource programming reached 100%.
- M33 `python -m SCons -j4` passed after enabling `sound0` playback.
- M33 raw hex first failed to burn at `0x08340400`; after rebasing all type-04 records to `0x6034..`, `build/rtthread_rebased_6034_latest.hex` programmed to 100%.

Failed or unverified:
- The trailing KitProg3 acquire/reset error still appears after otherwise complete programming.
- End-to-end wake-word -> platform reply -> speaker audio is not yet field-verified.
- Official XiaoZhi audio uses Opus binary frames; M55/M33 still need a real Opus encode/decode path or an explicit relay-side PCM compatibility contract.

Next step:
- Reconnect WiFi, confirm the LVGL XiaoZhi panel reaches online/ready, speak the wake phrase, and verify both screen state transitions and speaker output.

## 2026-06-13 - XiaoZhi Board Runtime Recovery And M33 Audio Deferral

Completed:
- Recovered the board from a silent COM4 state by flashing a known-good full M33 image, proving M33 shell and M33/CM55 IPC could still run.
- Found that the latest M33 image entered HardFault after the eager `sound0` playback initialization path was added.
- Changed M33 startup to avoid initializing speaker playback during framework init. `MSG_TYPE_TTS_AUDIO` now attempts `audio_playback_init()` and `audio_playback_start()` lazily only when TTS audio actually arrives.
- Restored `M33_SKIP_SOUND0_INIT_FOR_XIAOZHI_QA` to `1` so the current XiaoZhi network/text bring-up is not blocked by the speaker device path.

Validated:
- M33 `python -m SCons -j4` passed after deferring audio playback, producing `text=273904 data=2640 bss=324181`.
- Rebased the generated M33 hex to `0x6034..` as `build/rtthread_rebased_6034_now.hex`; first line is `:02000004603466`.
- Burned M33, M55, and WiFi resources; programming progress reached 100% for all three phases.
- OpenOCD halt after the fix showed M33 running in Non-secure Thread mode at `pc=0x08365d84` instead of HardFault, and CM55 running at `pc=0x60662928`.
- M33 shell accepted `m55qa_status` and `m55qa_wifi_connect`; IPC reported `ipc_ready=1 tx_pending=0 rx_pending=0`.

Failed or unverified:
- WiFi was still not proven reconnected after reset during this pass, so XiaoZhi WebSocket remains at the network prerequisite stage.
- End-to-end wake word -> relay model -> reply audio is still unverified.
- Speaker output remains deferred; do not treat it as validated until a PCM TTS chunk reaches M33 and `sound0` is tested separately.

Next step:
- Restore stable WiFi auto-connect or manually reconnect WiFi, then verify `m55qa_status` shows `wlan/ready/ip` and `xz_ws=1` before testing wake-word speech.

## 2026-06-15 - M55 WiFi Auto-Connect Validated, XiaoZhi WebSocket Still Blocked At lwIP ERR_RTE

Completed:
- Kept the M55 `wifi` project as the active board firmware project and continued from the WiFi/LVGL XiaoZhi bring-up branch.
- Replaced the M55 hand-written WebSocket socket/handshake implementation in `D:\RT-ThreadStudio\workspace\wifi\applications\websocket_client.c` with a thin wrapper around the bundled lwIP `wsock_*` callback client.
- Enabled `RT_LWIP_USING_WEBSOCKET` in the M55 project and compiled the bundled lwIP websocket client sources.
- Patched the bundled lwIP websocket client so non-TLS `ws://` builds do not force-link `altcp_tls_*`/mbedTLS symbols.
- Documented the current WebSocket blocker in `D:\RT-ThreadStudio\workspace\wifi\wifi避坑文档.md`.

Validated:
- M55 `python -m SCons -j4` passed after the wrapper and lwIP websocket changes, producing `rtthread.hex`.
- Burned M55 firmware and `whd_resources_all.bin` with OpenOCD; both writes reached 100%.
- Serial QA on COM4 showed WiFi auto-connect is stable after reset: `saved=1 auto=1`, `wlan=1 ready=1`, `ip=192.168.3.32`, `gw=192.168.3.1`, `dns0=192.168.3.1`.

Failed or unverified:
- XiaoZhi WebSocket is still not connected: `xz_ws=0 xz_stage=20 xz_errno=-4`.
- `-4` is lwIP `ERR_RTE`, returned during `wsock_connect()` / `altcp_connect()` startup. This is a new, narrower blocker than the earlier hand-written socket receive/handshake hang.
- Wake word -> model reply -> speaker output remains unverified because WebSocket has not reached connected/hello state.
- The new official lwIP websocket path currently increases M55 image size substantially; after connectivity is proven, revisit footprint.

Next step:
- Diagnose lwIP raw/altcp routing on board: inspect `netif_default`, `ip_route()`, local IP binding, and WiFi netif selection around `wsock_connect_addr()`. If needed, explicitly bind the WebSocket PCB to the active WiFi netif/local IP before `altcp_connect()`.

## 2026-06-15 - XiaoZhi WebSocket Connected, PCM Audio Upstream Proven, Reply Still Not Returned

Completed:
- Continued XiaoZhi bring-up from the M55 `wifi` project after WiFi auto-connect was validated.
- Unified M55 XiaoZhi WebSocket declaration with the current binary v3 framing: `Protocol-Version: 3`, `hello.version=3`, and `BinaryProtocol3` `[type,reserved,payload_size_be16,payload]`.
- Changed M55 `XIAOZHI_AUDIO_FORMAT` to `pcm_s16le` so the protocol declaration matches the actual 16 kHz mono S16LE payload currently sent by M55.
- Synced the validated M55 source changes back into the `_m55_ref_repo` git-managed mirror.

Validated:
- M55 `python -m SCons -j4` passed after the protocol changes; final size remained `text=1420460 data=81448 bss=4529336`.
- Burned M55 firmware and `whd_resources_all.bin`; both programming phases reached 100%.
- COM4 serial QA showed WiFi remains stable after reset: `saved=1 auto=1`, `wlan=1 ready=1`, `ip=192.168.3.32`.
- COM4 serial QA showed XiaoZhi WebSocket now connects: `xz_ws=1 xz_stage=70 xz_errno=0`.
- Manual capture QA showed M55 microphone and WebSocket upstream are working: `frames=2326`, `pcm_seq=2326`, `probe_lwip=387/744588`.
- PC-side `ClientWebSocket` probe showed the platform hello can echo both `audio_params.format=opus` and `pcm_s16le` for protocol version 3.

Failed or unverified:
- No STT/LLM/TTS text or binary audio reply was observed after board capture stop; `probe_posix=0/2` indicates only handshake/listen control text was received.
- A PC-side synthetic speech PCM probe also received only `listen start/stop` and no STT/TTS, so platform PCM ASR is currently not proven and likely not wired.
- The board still streams PCM wrapped in v3 binary packets; official XiaoZhi remains Opus-first.
- Speaker reply remains unverified because no server TTS audio has reached M33 in this pass.

Next step:
- Inspect platform relay logs for whether PCM frames enter ASR. If the relay logs do not run PCM ASR, add relay-side PCM-to-ASR/transcode support or port a small Opus encoder/decoder path before chasing LVGL or speaker behavior.

## 2026-06-15 - Relay PCM ASR Fixed In PC Probe, Board Upstream Still Requires Real Speech

Completed:
- Re-ran the PC-side synthetic 16 kHz mono S16LE speech probe after the platform relay was updated.
- Confirmed the relay now accepts `Protocol-Version: 3` plus `audio_params.format=pcm_s16le` v3 binary frames and returns XiaoZhi events.
- Reset the Infineon board after the M55 voice status became stale and M33 commands accumulated in `tx_pending`.

Validated:
- PC probe returned STT text for the synthetic speech: `你好小智，请回答今天网络连接测试成功了吗？`.
- PC probe then returned `llm`, `chat`, and `tts start/stop`, proving the relay-side PCM ASR and daily-chat path now works.
- Board reset restored M55 IPC: `m55qa_xz_reconnect` returned `voice_ack ... cmd=1003 result=0`.
- Board WebSocket reconnected after reset: `xz_ws=1 xz_stage=70 xz_errno=0`.
- Board capture path still sends upstream PCM: after `m55qa_capture_on/off`, status showed `frames=2317`, `pcm_seq=2317`, and `probe_lwip=386/742664`.

Failed or unverified:
- No STT/TTS was observed from the board capture, but the user was not physically present and the microphone likely captured only ambient noise.
- Speaker playback remains unverified until a real spoken prompt or injected board-side audio produces platform TTS audio.

Next step:
- With someone near the board, speak a clear prompt during `m55qa_capture_on` and verify STT/LLM/TTS on COM4. If speaker audio is still absent after TTS events, debug M33 playback/codec separately.

## 2026-06-15 - M55 LVGL XiaoZhi UI Timeout And Font Fallback Burned

Completed:
- Updated the active M55 `wifi` firmware so XiaoZhi LVGL status no longer stays indefinitely in `XIAOZHI_UI_THINKING` if the platform does not return TTS/text.
- Added a 20 s thinking timeout and 30 s speaking timeout in `applications/xiaozhi_ui_state.c`.
- Connected the custom LVGL WiFi/XiaoZhi font fallback to `lv_font_simsun_16_cjk` so missing fixed UI Chinese glyphs use the enabled CJK fallback instead of boxes.
- Burned M55 with `program_with_resources.bat`, including the WHD resource image.

Validated:
- M55 SCons build passed: `text=1407424 data=81508 bss=4528996`.
- OpenOCD wrote both M55 `rtthread.hex` and `whd_resources_all.bin` to 100%.
- COM4 `m55qa_status` reached the expected stable state after auto-connect: `wlan=1 ready=1 ip=192.168.3.32`, `saved=1 auto=1`, `xz_ws=1 xz_stage=70 xz_errno=0`, `wake_on=1 wake_ready=1`, and LVGL flush count increased with `lvgl_last=0`.

Failed or unverified:
- Physical LCD photo confirmation is still needed to prove the remaining Chinese glyphs are visually fixed on the panel.
- Real wake phrase -> real spoken prompt -> platform STT/LLM/TTS -> speaker reply remains unverified without someone near the board microphone.
- A transient early boot sample showed `xz_stage=80 xz_errno=-13` and `lvgl_flush=0`; a later sample recovered, so this is not currently treated as a WiFi regression.

Next step:
- With the board in front of an operator, say `OK Infineon`, speak a short clear question, then verify LCD transitions `在线待唤醒 -> 我在听 -> 正在思考 -> 正在回答/在线待唤醒` and confirm speaker output.

## 2026-06-15 - Speaker QA Improved From Square Tone To Voice-Like Sample

Completed:
- Added `audio_playback_voice_cmd` to M33 as a local speaker QA command that generates a short voice-like sample using a small sine lookup table, harmonic mixing, pitch movement, and soft envelope.
- Kept the sample algorithmic instead of embedding a large WAV/PCM asset, preserving M33 space for future model work.
- Rebuilt and burned M33 after the change.

Validated:
- M33 build passed with `text=286892 data=16076 bss=310744`.
- OpenOCD wrote the M33 image with the required `0x58000000` offset: `wrote 307200 bytes`.
- `audio_playback_voice_cmd` found `sound0`, initialized at `16000 Hz / mono / 16-bit`, reached `Ready for I2S output`, flushed the tail, and completed `64000` bytes of sample playback.
- Earlier QA in the same pass confirmed `m55qa_capture_on` returned `result=0`, `xz_listening=1` during capture, then auto-ended to `xz_listening=0` with upstream stats `probe_lwip=134/257816`.

Failed or unverified:
- The generated local QA sample is voice-like, not real TTS speech with words.
- Physical listening confirmation is still needed from the user.
- End-to-end platform TTS audio through speaker still requires a real spoken prompt and server reply.

Next step:
- Ask the onsite operator to run or listen for `audio_playback_voice_cmd`, then test real XiaoZhi wake and question flow.
