# Troubleshooting And Lessons

## 2026-06-17 - CM55 XiaoZhi Assert Was Status/IPC Pressure, Not Wi-Fi

Symptom:
- After XiaoZhi probe or repeated `m55qa_capture_on` / `m55qa_capture_off`, M33 shell stayed alive but `m55qa_status` showed stale `voice_status age_ticks` and new commands accumulated in `tx_pending`.
- OpenOCD showed CM55 halted in `rt_assert_handler`.

Evidence:
- One CM55 stack mapped through `addr2line` to `voice_service_publish_status -> voice_service_refresh_netdev_snapshot_locked -> rt_wlan_dev_get_rssi -> WHD ioctl -> rt_mutex/IPC`.
- A later stack mapped to `voice_service_publish_status -> m33_m55_comm_publish -> mtb_ipc_queue_put`, where the MTB IPC library asserts if a blocking timeout is used from an invalid context.

Root cause:
- The voice/status hot path was doing too much work: live Wi-Fi driver queries and blocking IPC queue publish from the same control/audio bring-up loop.
- This looked like "小智没回话" or "Wi-Fi卡住", but the actual failure was CM55 falling into an RT-Thread assert after status/IPC pressure.

Fix:
- `voice_service_publish_status()` now uses the Wi-Fi config snapshot and no longer calls live WLAN/RSSI queries while publishing status.
- CM55 `m33_m55_comm_publish()` now calls `mtb_ipc_queue_put(..., 0)` so queue full/invalid timing returns an error instead of asserting the core.
- TTS binary payload handling remains deferred out of the lwIP WebSocket callback and is drained by the voice service thread.

Validation:
- After rebuild/burn, repeated `m55qa_capture_on` / `m55qa_capture_off` over COM4 returned ACKs, `tx_pending` returned to 0, and status remained fresh.
- Wi-Fi auto-connect still recovered after reset with saved credentials and `xz_ws=1`.

Next diagnostic:
- Re-run a prompt that reliably causes platform binary TTS. Pass criteria are `xz_rx` binary increment, `tts_fwd` increment, M33 `tts audio rx/write`, and audible speaker output.

## 2026-06-17 - CM55 Speaker Init Can Kill The Voice Service Before Mic QA Starts

Symptom:
- CM55 would boot into an assert instead of staying alive for XiaoZhi status and wake/capture QA.
- `m55qa_status` could fall back to shallow or stale output, and control commands would stop getting consumed.

Root cause:
- The M55 `sound0` / I2S init path asserted inside `ifx_i2s_init()` when `Cy_AudioTDM_Init()` failed.
- That speaker path is not required for the CM55-local XiaoZhi mic-first workflow, but it was still part of the CM55 boot path.

Fix:
- Remove `drv_i2s.c` from the M55 build for now.
- Keep CM55 on `mic0` / PDM capture for XiaoZhi uplink audio.
- Let the M33 side own speaker playback and keep CM55 focused on status, wake, capture, and network control.

Lesson:
- When a board has separate capture and playback responsibilities, do not let a failing speaker init block microphone bring-up.
- For this project, CM55 should be the audio input worker, not the whole audio stack.

## 2026-06-16 - Board ASR Is Proven; Remaining Gap Is TTS Downlink/Playback

Symptom:
- After Wi-Fi and WebSocket were stable, XiaoZhi still looked stuck or silent from the user perspective.
- Earlier board runs either produced no reply or forwarded garbled bytes as `tts text`.

Findings:
- The CM55 Wi-Fi/WebSocket path is healthy when `m55qa_status` shows `wlan=1 ready=1`, `xz_ws=1`, `xz_stage=70`, and `xz_errno=0`.
- Sending raw `pcm_s16le` from M33 via `m33qa_xz_probe` now reaches cloud ASR. Board logs show ASR text on M33 and `xz_last` byte/chunk counters increase.
- A PC-side control test using the same platform endpoint, scoped token, `Protocol-Version: 3`, `hello.audio_params.format=pcm_s16le`, and raw PCM frames returns the complete cloud sequence: `stt`, `llm`, `chat`, `tts start`, binary PCM TTS frames, `tts stop`.
- Therefore the current blocker is not Wi-Fi, token, WebSocket connect, or upstream ASR. The remaining gap is board-side TTS downlink classification/forwarding and `sound0` playback validation.

Fixes applied:
- CM55 no longer prefixes outbound raw PCM with a fake local v3 header.
- The M33-to-M55 shared PCM route now forwards non-control IPC messages into `voice_service_handle_ipc_message()`.
- Shared PCM is accepted while XiaoZhi listening is active, not only while wake listening is active.
- Non-JSON text-opcode WebSocket payloads are no longer published to M33 as `MSG_TYPE_TTS_REQUEST` garbage. PCM-looking payloads are routed as audio instead.

Next diagnostic:
- Run `m55qa_capture_on`, `m33qa_xz_probe`, then watch for `xz_rx` binary count and M33 `MSG_TYPE_TTS_AUDIO` / `audio_playback_write()` logs.
- If PC still receives binary TTS but board does not, instrument the CM55 lwIP WebSocket callback around opcode/text/binary classification.
- If board receives `MSG_TYPE_TTS_AUDIO` but no sound, focus only on M33 `audio_playback` and `sound0`, not cloud or Wi-Fi.

## 2026-06-15 - XiaoZhi Binary Frames Stayed Silent Because The PCM Path Was Still Wrapped Wrong

Symptom:
- XiaoZhi stayed in `connecting` / `thinking` with no reliable `listen -> send -> reply` progress.
- Status counters showed mic activity, but there was no clear evidence that the platform actually received binary audio.

Findings:
- The M55 WebSocket client already sends binary frames with `OPCODE_BINARY`; adding a fake 4-byte v3 header on top of raw PCM made the send path harder to reason about.
- The official XiaoZhi WebSocket reference supports binary protocol v1 as raw audio frames, while v2/v3 framing is only needed when both sides explicitly agree on that binary protocol.
- The current board-side practical path is raw `pcm_s16le` over binary WebSocket frames, with explicit JSON `hello`/`listen` control messages and status counters.

Fix:
- Remove the extra binary header and send the raw 16 kHz mono PCM bytes directly.
- Expose `xiaozhi_listening_bytes`, `xiaozhi_listening_chunks`, `xiaozhi_last_sent_bytes`, `xiaozhi_last_sent_chunks`, `xiaozhi_send_fail_count`, `xiaozhi_rx_text_count`, `xiaozhi_rx_binary_count`, and `xiaozhi_audio_frame_len` in `m55qa_status`.

Lesson:
- When the platform contract already says `pcm_s16le`, do not stack another framing layer unless the server explicitly requires it.
- Make the audio path observable before tuning wake/EOU thresholds; otherwise every failure looks like the same "still connecting" symptom.

Status:
- Fixed in the working tree; board QA still needed after the next burn.

## 2026-06-15 - XiaoZhi Cloud Blocker Is WebSocket Transport, Not Wi-Fi

Symptom:
- CM55 Wi-Fi auto-connect is stable and `m55qa_status` shows a valid IP/gateway/DNS, but XiaoZhi remains in connecting state.
- Early diagnostics made it look like `connect()` was hanging forever.

Findings:
- A dedicated CM55 TCP probe to `106.55.62.122:8011` succeeds, proving basic Wi-Fi association, DHCP, gateway, and outbound TCP are working.
- A PC-side raw WebSocket Upgrade using the same URL and scoped token returns `HTTP/1.1 101 Switching Protocols`, so the cloud endpoint, token, and path are valid.
- The CM55 hand-written socket client can send the HTTP Upgrade request, then reaches handshake receive (`xz_stage=50`) and blocks/timeouts in the RT-Thread/lwIP socket receive path.
- `select()`, `fcntl(O_NONBLOCK)`, `MSG_DONTWAIT`, `SO_RCVTIMEO`, direct `lwip_recv`, and `FIONBIO` did not produce a dependable nonblocking receive on this BSP path.

Lesson:
- Do not keep debugging this as a Wi-Fi scan/firmware-resource issue once `wlan=1 ready=1 ip=192.168.3.32` and the TCP probe passes.
- Avoid building the XiaoZhi production transport on the POSIX/SAL socket receive path for this board. Use the bundled lwIP callback WebSocket client (`lwip/apps/websocket_client.h`) or a netconn/raw callback API.

Validation notes:
- M55 image and WHD resources were flashed together after each iteration.
- COM4 QA showed Wi-Fi auto-connect remained stable after reset.
- The scoped relay token must not be printed or committed.

## 2026-06-10 - LVGL Code In Image Does Not Mean The GUI Thread Started

Symptom:
- CM55 firmware built successfully with `BSP_USING_LVGL`, `rehab_wifi_panel_cmd` existed in the symbol table, but no LVGL screen appeared on boot.

Root cause:
- The RT-Thread LVGL port had `INIT_ENV_EXPORT(lvgl_thread_init)` commented out.
- `lvgl_thread_init()` was only exported as the shell command `thread_init`, so the GUI thread did not start automatically.

Fix:
- CM55 `main()` now calls `lvgl_thread_init()` during boot when `BSP_USING_LVGL` is enabled.
- `lvgl_thread_init()` now has a duplicate-start guard so manually typing `thread_init` remains safe.
- The LVGL RT-Thread port now includes `<lvgl.h>` directly to avoid implicit LVGL API declarations.

Validation:
- M55 reference repo and actual RT-Thread Studio `wifi` project both build with `scons -j4`.

Reusable trick:
- If LVGL is compiled in but the screen is blank, first type `thread_init` in the shell. If the screen appears, the issue is GUI-thread startup, not the Wi-Fi panel code.
- If `thread_init` starts but the screen remains blank, run `lcd_test` next to separate display hardware/driver issues from LVGL widget issues.

Status:
- Built. Physical verification requires flashing the new M55 image and watching for `[m55] LVGL thread init ret=0`.

## 2026-06-10 - LVGL Wi-Fi Scan Should Use WLAN Scan Report Events

Symptom:
- The touchscreen Wi-Fi page needed a selectable nearby-network list, but the obvious synchronous scan helper was not a safe implementation target in this BSP baseline.

Root cause:
- `rt_wlan_scan_sync()` is declared in the RT-Thread WLAN headers, but this project source does not provide a usable implementation path for the current BSP.
- The RT-Thread shell `wifi scan` command already uses `RT_WLAN_EVT_SCAN_REPORT` callbacks with `rt_wlan_scan_with_info(RT_NULL)`.

Fix:
- CM55 Wi-Fi config service now registers a temporary `RT_WLAN_EVT_SCAN_REPORT` handler, starts `rt_wlan_scan_with_info(RT_NULL)` in a background thread, caches up to 12 AP records, and exposes the cache to LVGL through `wifi_config_get_scan_count()` and `wifi_config_get_scan_ap()`.
- The LVGL panel shows a selectable list and keeps manual SSID entry for hidden networks.

Validation:
- M55 reference repo and actual RT-Thread Studio `wifi` project both build with `scons -j4`.

Reusable trick:
- For this BSP, follow the known-working RT-Thread `wifi scan` event-callback pattern instead of assuming every declared WLAN helper is linked and usable.

Status:
- Built. Physical scan/touch/connect QA still needs the board flashed with the new M55 image.

## 2026-06-10 - CM55 Wi-Fi Provisioning Must Use One Shared Service

Symptom:
- Wi-Fi configuration was available through shell commands, but SSID/password were RAM-only and would be lost after reset.
- Adding LVGL or App provisioning directly on top of WLAN APIs would create several independent Wi-Fi state machines.

Root cause:
- The first bring-up path was debug-oriented. It did not persist credentials and did not expose save/forget/auto-connect state to M33/App.

Fix:
- Added a shared CM55 Wi-Fi config service used by local shell, LVGL touchscreen, and M33/CM55 IPC.
- Saved credentials live at `/flash/rehab_wifi.cfg` and contain only SSID/password/auto-connect state.
- Added M33 QA commands `m55qa_wifi_save`, `m55qa_wifi_forget`, and `m55qa_wifi_auto <0|1>`.
- Added status fields so `m55qa_status` prints Wi-Fi `saved`, `auto`, and `storage` state.

Validation:
- M55 actual `wifi`, M55 Git reference `_m55_ref_repo`, and M33 `yiliao_m33` all build with `scons -j4`.

Reusable trick:
- Put Wi-Fi provisioning behind one service before adding UI/BLE/App entry points. UI code should not own connection state.

Status:
- Built. Physical LVGL touch/save/connect and reboot auto-connect still need board-side QA after flashing.

## 2026-06-10 - RT-Thread DFS Build Does Not Always Provide `dfs_posix.h`

Symptom:
- Adding Wi-Fi config persistence failed to build with:
  `fatal error: dfs_posix.h: No such file or directory`

Root cause:
- This BSP enables DFS and newlib stdio, but does not expose a `dfs_posix.h` header at the expected include path.

Fix:
- Use standard `stdio.h` file APIs (`fopen`, `fgets`, `fprintf`, `remove`) for `/flash/rehab_wifi.cfg`.
- Keep the code guarded by `RT_USING_DFS` so it degrades cleanly if DFS is disabled.

Validation:
- Rebuilt the M55 actual `wifi` project and `_m55_ref_repo` successfully after removing the `dfs_posix.h` include.

Reusable trick:
- On this RT-Thread Studio BSP, check which POSIX headers actually exist before including RT-Thread DFS wrapper headers. If stdio works, prefer it for simple config files.

Status:
- Fixed.

## 2026-06-10 - XiaoZhi Endpoint Moved Under The Existing Command Center

Symptom:
- Device firmware still pointed at the older `/voice/xiaozhi/ws` path while the cloud platform implemented the production XiaoZhi-compatible WebSocket under the existing medical rehab-arm command center.

Root cause:
- The platform contract was finalized after the first CM55 XiaoZhi bridge was added.

Fix:
- CM55 default WebSocket URL is now:
  `ws://106.55.62.122:8011/api/rehab-arm/v1/projects/fd6a55ed-a63c-44b3-b123-96fb3c154966/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha`
- CM55 accepts server `listen stop` as a local stop signal without echoing another stop back to the platform.

Validation:
- M55 reference tree and actual `wifi` working tree both build with `scons -j4`.
- Platform side reports 101 handshake, hello/listen/audio/reply, scoped-token auth, and safety filtering have been validated.

Reusable trick:
- Keep the default firmware endpoint aligned with the command-center contract, and reserve `m55qa_xz_url` for temporary diagnostics.

Status:
- Device build is aligned. Physical spoken end-to-end validation still requires loading a valid scoped relay token into CM55.

## 2026-06-10 - Decode XiaoZhi Status Before Live Token Testing

Symptom:
- `m55qa_status` previously printed only a raw `flags=0x...` value, so it was hard to tell whether a failure was wake backend, token, WebSocket, or active audio streaming.

Root cause:
- CM55 status flags did not expose token/connect/listening state, and M33 did not decode the existing bits.

Fix:
- Added shared voice status bits for XiaoZhi listening, WebSocket connected, and scoped token loaded.
- M33 `m55qa_status` now prints `wake_on`, `wake_ready`, `wake_hit`, `xz_listening`, `xz_ws`, and `xz_token`.

Validation:
- After burning both cores, COM26 showed `wake_on=1 wake_ready=1 wake_hit=0 xz_listening=0 xz_ws=0 xz_token=0`.
- `m55qa_xz_reconnect` returned ACK `cmd=1003 result=-255` with no scoped relay token loaded, which matches `xz_token=0`.

Reusable trick:
- Before testing a cloud voice path, expose local token/connect/streaming state in firmware status. Otherwise HTTP/WebSocket failures all look the same.

Status:
- Fixed. Next live test should first load a scoped token and confirm `xz_token=1`, then reconnect and confirm `xz_ws=1`.

## 2026-06-10 - Do Not Load Wrong-Scope Relay Tokens

Symptom:
- A `rehab-relay.v1...` token may look structurally valid but still fail XiaoZhi WebSocket auth.

Root cause:
- Scoped relay tokens are bound to a specific project/device. The active device contract is `project_id=fd6a55ed-a63c-44b3-b123-96fb3c154966`, `device_id=nanopi-m5`, and `robot_id=rehab-arm-alpha`.

Fix:
- Use `tools/load_xiaozhi_token.ps1` only with a platform-generated token for the active project/device.
- The tool rejects non-`rehab-relay.v1.` values so vendor LLM API keys are not accidentally loaded onto CM55.

Validation:
- `tools/load_xiaozhi_token.ps1 -ReconnectOnly` reached COM26 and confirmed the expected no-token state: `xz_token=0`, `xz_ws=0`, and `cmd=1003 result=-255`.

Reusable trick:
- Treat `xz_token=1` as "a scoped token is loaded", not proof the token belongs to the current project/device. `xz_ws=1` is the real device-side sign that auth and handshake have passed.

Status:
- Tooling is ready. End-to-end chat remains blocked until a correct-scope relay token is generated and loaded.

## 2026-06-10 - XiaoZhi PCM Binary Frames Must Match The Platform Contract

Symptom:
- M33 status showed local `latest_pcm_len=320` while the platform contract says 16 kHz mono PCM S16LE at 20 ms, which is 640 bytes per WebSocket binary frame.

Root cause:
- The local mic driver can deliver smaller chunks than the platform's logical XiaoZhi audio frame. Forwarding each local chunk directly can create half-frame binary messages.

Fix:
- CM55 now accumulates local PCM into `XIAOZHI_AUDIO_FRAME_BYTES=640` before each `websocket_client_send_binary` call.
- The hello audio parameters and frame byte calculation share constants in `xiaozhi_voice_relay.h`.

Validation:
- M55 reference repo and actual `wifi` working tree both build with `scons -j4` after the change.

Reusable trick:
- Keep local audio-driver chunk size separate from cloud protocol frame size. The bridge should reframe audio before sending it over WebSocket.

Status:
- Built, pushed, and burned to CM55. COM26 confirms M33/M55 IPC and wake status still run. Needs WebSocket/audio test with a valid scoped token.

## 2026-06-10 - Test XiaoZhi Cloud Without Someone Near The Microphone

Symptom:
- Live wake-word/chat testing cannot always proceed because nobody is physically near the CM55 microphone.

Root cause:
- Physical wake-word validation depends on local audio, but platform WebSocket compatibility can be tested independently.

Fix:
- Added `tools/xiaozhi_ws_smoke_test.ps1` to simulate the device-side WebSocket flow from a Windows PC:
  `hello` -> `listen start` -> synthetic 640-byte PCM binary frames -> `listen stop`.

Validation:
- The script loads and attempts to connect.
- HTTP access to `106.55.62.122:8011` is reachable from the PC.
- Running with a dummy `rehab-relay.v1.fake.fake` token fails before a full XiaoZhi flow, which is expected for invalid auth/test data.

Reusable trick:
- Split voice bring-up into two tests: PC smoke test for cloud XiaoZhi contract, then physical CM55 wake-word test for local microphone and wake model.

Status:
- Tooling is ready. A valid scoped relay token is required for a real cloud pass.

## 2026-06-10 - Long XiaoZhi Tokens Exceed FinSH Command Length

Symptom:
- Platform relay tokens can be around 410 characters, while the RT-Thread FinSH command line is only about 80 characters.
- A single `m55qa_xz_token <token>` paste is truncated before it reaches CM55, so WebSocket auth cannot be configured reliably.

Root cause:
- The shell line limit is smaller than real platform-scoped relay tokens.
- The old CM55 token buffer and WebSocket header/request buffers were sized for short test tokens, not production relay credentials.

Fix:
- Keep `m55qa_xz_token <short_token>` for short debug tokens.
- Use chunked M33 shell commands for real relay tokens:
  - `m55qa_xz_token_begin`
  - repeated `m55qa_xz_token_part <chunk>` with chunks around 48 to 60 characters
  - `m55qa_xz_token_commit`
  - `m55qa_xz_token_clear` when clearing stale credentials
- CM55 now stages token chunks, commits atomically, and then reconnects XiaoZhi WebSocket.
- CM55 token storage is 768 bytes; WebSocket extra headers are 1024 bytes; the HTTP Upgrade request is 2048 bytes with truncation checks.

Validation:
- COM26 showed `m55qa_xz_token_begin` -> `voice_ack ... cmd=1004 result=0`.
- COM26 showed `m55qa_xz_token_part abc123` -> `voice_ack ... cmd=1005 result=0`.
- COM26 showed `m55qa_xz_token_commit` -> `voice_ack ... cmd=1006 result=-255` with a dummy token, proving the token reached CM55 and commit triggered reconnect.
- The dummy token was cleared with `m55qa_xz_token_clear`.

Reusable trick:
- Never paste long platform credentials directly into a small embedded shell command. Add a chunked config protocol and keep secrets out of source control.

Status:
- Fixed in M33/M55 firmware. End-to-end platform auth still depends on a valid platform token and XiaoZhi-compatible server endpoint.

## 2026-06-10 - OpenOCD Tcl Paths Need Forward Slashes On Windows

Symptom:
- `flash banks` did not register the external SMIF flash bank, and OpenOCD printed a corrupted path such as `D:RT-ThreadStudio...OpenOCD-Infineon...PSE84_SMIF.FLM`.

Root cause:
- Passing Windows backslash paths through OpenOCD `-c "set QSPI_FLASHLOADER ..."` lets Tcl treat backslashes as escapes.
- The SMIF flash-loader path becomes invalid, so `cat1d.cm33.smif1_ns` at `0x60000000` is not created.

Fix:
- Use forward slashes in OpenOCD command strings, for example:
  `D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/flm/cypress/cat1d/PSE84_SMIF.FLM`.
- Keep the generated QSPI config directory in the OpenOCD search path.

Validation:
- `flash banks` showed `cat1d.cm33.smif1_ns (cmsis_flash) at 0x60000000`.
- Subsequent burns wrote `847872 bytes` for CM55 and `569344 bytes` for M33.

Reusable trick:
- For OpenOCD on Windows, prefer `/` paths inside all Tcl `-c` snippets even when PowerShell accepts `\` paths.

## 2026-06-10 - XiaoZhi Flow Should Follow The Official Streaming State Machine

Symptom:
- A naive wake implementation can detect the wake word and then upload only the wake frame or a fixed-length PCM clip, but this does not match the official XiaoZhi behavior and is brittle for real conversation.

Root cause:
- The official `Edgi_Talk_M55_XiaoZhi` flow is stateful and streaming: wake callback, reconnect if needed, `hello`, `listen start`, microphone binary audio stream, server-controlled `listen stop`/reply/TTS, then return to wake listening.

Fix:
- Keep the firmware client aligned to the official state machine.
- Adapt only endpoint URL, auth headers, platform device scope, and server response parsing for the rehab-arm command center.
- Do not store LLM vendor API keys in firmware; CM55 uses only platform-scoped relay configuration.

Validation:
- M55 builds and burns with the official-sequence client path.
- M33 shell can bridge `m55qa_xz_reconnect` to CM55; CM55 returns an ACK, proving the configuration command path works.

Status:
- Firmware-side foundation is in place. Platform WebSocket compatibility and live chat response remain to be validated.

## 2026-06-10 - Relocate Every M33 Intel HEX Segment

Symptom:
- OpenOCD wrote only `65536 bytes` from a freshly relocated M33 hex and printed `no flash bank found for address 0x08350000`.

Root cause:
- Only the first Intel HEX extended linear address record was changed from `0x0834` to `0x6034`.
- Later records such as `0x0835`, `0x0836`, ... remained unrelocated, so OpenOCD skipped those runtime-alias addresses.

Fix:
- Relocate every type-04 extended linear address in the M33 image from `0x0834..0x083C` to `0x6034..0x603C`, recomputing the Intel HEX checksum for each record.

Validation:
- The corrected relocated file begins with `:02000004603466` and contains subsequent records `6035`, `6036`, etc.
- OpenOCD then reported `wrote 569344 bytes`, confirming the full M33 image was programmed.

Reusable trick:
- For PSoC Edge E84 external flash images, trust the OpenOCD `wrote N bytes` count more than command exit code. A suspiciously small write means relocation or flash-bank mapping is still wrong.

## 2026-06-10 - CM55 DEEPCRAFT Wake Blocked By EthosU Stub

Symptom:
- `m55qa_status` reported CM55 IPC alive, but DEEPCRAFT wake init failed with `wake_stage=37` and `err=138280962`.

Root cause:
- `138280962` is `0x083E0002`, matching `MTB_ML_RESULT_ALLOC_ERR`.
- The current TensorFlow Lite Micro package has `tensorflow/lite/micro/kernels/ethosu.cc` implemented as a stub; `Register_ETHOSU()` returns `nullptr`, so the DEEPCRAFT U55 model cannot allocate/run correctly in this firmware baseline.

Fix:
- Do not keep debugging DEEPCRAFT as the active product wake path in this baseline.
- Use the official XiaoZhi Edge Impulse TFLite model as the current CM55 wake backend, with a local lightweight MFCC-like extractor and existing repo TFLM.

Validation:
- M55 SCons build passes.
- After OpenOCD burn, COM26 `m55qa_status` shows `wake_stage=20 err=0`, proving the new backend enters inference processing without the EthosU allocation error.

Status:
- Fixed for bring-up. Acoustic recognition quality still needs live `xiaorui` validation.

## 2026-06-10 - Short PCM Frames Can Starve Wake Inference

Symptom:
- CM55 voice status showed `frames` increasing but `detected=0`; before the fix, the wake backend stayed at init stage and did not receive enough PCM to infer.

Root cause:
- `voice_service_submit_local_pcm()` receives local mic data as short 640-byte frames, roughly 20 ms at 16 kHz mono 16-bit.
- The pre-wake heuristic gate required `WAKE_GATE_MIN_ACTIVE_FRAMES=28`, which is impossible for a single 20 ms frame. The gate returned before calling `xiaozhi_wake_engine_process_pcm16()`, so the wake backend never accumulated its 1 second model window.

Fix:
- Feed every listening PCM frame to `xiaozhi_wake_engine_process_pcm16()`.
- Let the wake backend own the rolling 16000-sample model window and inference cadence.

Validation:
- After rebuild and burn, `m55qa_status` shows `wake_stage=20 err=0` while listening. This means PCM reaches the backend and the backend runs inference.

Reusable trick:
- For streaming audio, do not apply full-window speech gates to a single short device read. Either aggregate first or let the model backend own the rolling window.

## 2026-06-10 - CM55 Stuck In `rt_assert_handler`

Symptom:
- M33 `m55qa_status` showed `ipc_ready=1` but M33-to-CM55 `tx_pending` increased after `m55qa_wake_on`; CM55 was not consuming the queue.
- OpenOCD showed CM55 PC at `0x6059f766`, which resolved to `rt_assert_handler`.

Root cause:
- GDB backtrace showed CM55 asserted in `libraries/HAL_Drivers/drv_uart.c:199` while `rt_hw_board_init()` called `rt_console_set_device("uart2")`.
- The visible serial shell belongs to M33. CM55 binding `uart2` during board init is not a valid mainline path for this product architecture.

Fix:
- Guarded console binding in `libraries/HAL_Drivers/drv_common.c` with `!defined(COMPONENT_CM55)`.
- CM55 is now observed and controlled through M33 shell commands and M33/CM55 IPC ACKs.

Validation:
- After rebuild, burn, and reset, CM55 no longer stops in `rt_assert_handler`.
- `m55qa_wake_on`, `m55qa_capture_on`, and `m55qa_wake_off` all return CM55 voice ACK frames with result `0`.

Reusable trick:
- If CM55 appears dead but M33 shell is alive, first check CM55 PC with OpenOCD and run `addr2line`/GDB before changing voice or IPC code.
- Do not treat `tx_pending=0` alone as full validation; require `MSG_TYPE_VOICE_CONTROL_ACK` for command handling confirmation.

## 2026-06-13 - Do Not Drift From Official XiaoZhi WebSocket Fields

Symptom:
- The M55 XiaoZhi relay path had drifted into a custom `hello.version=3`, `audio_params.format=pcm_s16le`, `frame_duration=20`, and `listen.mode=auto_stop` shape.
- This differed from the official XiaoZhi ESP32 WebSocket example and made it unclear whether board-side failures were network issues, protocol incompatibility, or relay-specific behavior.

Official reference:
- `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32\docs\websocket.md`
- `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32\main\protocols\websocket_protocol.cc`
- `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32\main\protocols\protocol.cc`

Fix:
- Realign M55 and the PC smoke test to official-style WebSocket fields:
  - `hello.version=1`
  - `audio_params.format=opus`
  - `sample_rate=16000`
  - `channels=1`
  - `frame_duration=60`
  - `listen.mode=auto`

Validation:
- PC smoke test using the scoped relay token received hello ACK, listen ACK, and a chat/VLA reply from the relay with the official-style message shape.
- M55 builds after the JSON/protocol change.

Remaining gap:
- M55 still lacks a real Opus encoder. Current relay testing accepted the binary frame path, but full official parity requires adding Opus encoding on M55 or documenting relay PCM compatibility explicitly.

Reusable trick:
- Before debugging wake word, ASR, or platform model logic, first compare the exact JSON fields against the official XiaoZhi example. A single mode or audio format mismatch can look like a networking or model failure.

## 2026-06-13 - NanoPi Camera QA SSH Port Open But No Banner

Symptom:
- Windows host can detect `192.168.2.66:22` as open with `Test-NetConnection`.
- `ping 192.168.2.66` times out.
- Paramiko fails with `Error reading SSH protocol banner`.
- OpenSSH exits with `Connection closed by 192.168.2.66 port 22`.
- Direct TCP read from port 22 returns an empty byte string instead of an `SSH-2.0...` banner.

Impact:
- The established NanoPi USB camera QA path for photographing the Infineon LCD cannot be used, even though the host sees the TCP port as open.

Current best hypothesis:
- The NanoPi is reachable at the TCP layer, but the SSH daemon is not serving a valid SSH session, is immediately closing new connections, or another service/socket is occupying port 22.

Fix/status:
- Unfixed in this pass. Do not assume NanoPi camera QA is available solely because port 22 is open.

Reusable trick:
- For camera QA, verify the SSH banner first. A successful `Test-NetConnection` is not enough; require an actual SSH login before planning remote `v4l2-ctl`/`ffmpeg` capture.

## 2026-06-10 - M33 Hex Relocation

Symptom:
- M33 post-build may print `arm-none-eabi-objcopy: interleave must be positive` and ignore the post-build error.

Fix:
- Manually run `arm-none-eabi-objcopy -O ihex Debug\rtthread.elf Debug\rtthread.hex`.
- Then run `tools\edgeprotecttools\bin\edgeprotecttools.exe run-config -i config\boot_with_extended_boot.json` from `Debug`.
- Confirm the first line of `Debug\rtthread.hex` is `:02000004603466` before burning.

Status:
- Fixed workflow, still a manual step until the generated post-build command is corrected.

## 2026-06-13 - LVGL Font Symbols Must Come From Fixed UI Source

Symptom:
- After adding more XiaoZhi status text, the LCD could still show square glyphs even though a previous font regeneration had added several manually guessed Chinese characters.

Root cause:
- `lv_font_conv --symbols` only includes the exact glyphs listed. Hand-written symbols lists drift whenever UI text changes.

Fix:
- Extract the fixed Chinese UI/status characters from M55 source files and regenerate `applications/rehab_wifi_font.c` from that set.
- Keep the generated include as `#include "lvgl.h"` for the current RT-Thread Studio LVGL include path.

Status:
- Fixed for fixed UI/status text. Dynamic XiaoZhi model replies can still contain arbitrary Chinese outside the static font.

Reusable trick:
- Before regenerating a small LVGL C font, scan the actual display source strings and build the symbols list from source, not memory.

## 2026-06-13 - XiaoZhi Speaker Path Is Not Complete Without Opus Decode

Symptom:
- The screen can show XiaoZhi text/status, but speaker output may still be silent or invalid even when the platform sends audio.

Root cause:
- Official XiaoZhi WebSocket binary audio is Opus. The current local M33 playback path writes PCM/WAV-like chunks to `sound0`; it does not decode Opus yet.
- M33 `sound0` initialization had also been skipped by default for earlier M55 QA, so playback code could not find a real speaker device.

Fix:
- Re-enabled `sound0` initialization by default on M33.
- Wired M33 main IPC handling for `MSG_TYPE_TTS_AUDIO` to `audio_playback_write()`.
- Updated `audio_playback` to open/configure `sound0` and call `rt_device_write()`.

Status:
- PCM/WAV-compatible playback path is compiled and burned after M33 hex relocation.
- Official Opus decode is still unimplemented and must be added, or the relay must explicitly return PCM/WAV chunks for this board.

Reusable trick:
- Treat “platform returned audio” and “speaker can play it” as two separate checks: verify codec format first, then verify `sound0` write path.

## 2026-06-13 - Do Not Eagerly Initialize M33 Speaker During XiaoZhi Bring-up

Symptom:
- After flashing a freshly built M33 image, COM4 produced no boot logs.
- OpenOCD showed M33 halted in `Handler HardFault` with `pc=0x1400267c`.
- Flashing an older full M33 image restored COM4 and `m55qa_status`, proving the board, UART, and CM55 IPC were not the primary failure.

Root cause:
- The current best fix confirmed that eager `audio_playback_init()`/`audio_playback_start()` during M33 framework startup was too risky for this bring-up baseline.
- The failure looked similar to a bad M33 hex relocation at first, but the post-fix image ran in Non-secure Thread mode, so startup hardware audio init was the actionable cause for this pass.

Fix:
- Do not initialize `sound0` during `m33_init_framework()`.
- Attempt speaker playback initialization lazily only when `MSG_TYPE_TTS_AUDIO` arrives.
- Keep `M33_SKIP_SOUND0_INIT_FOR_XIAOZHI_QA=1` while validating WiFi, WebSocket, ASR, and text/model response.

Validation:
- M33 built with `python -m SCons -j4`.
- The rebased M33 hex started with `:02000004603466`.
- After flashing, OpenOCD showed M33 in Non-secure Thread mode at `pc=0x08365d84`, not HardFault.

Reusable trick:
- When XiaoZhi network/voice QA depends on M33 shell, keep speaker hardware init out of the boot path. Validate audio output as a later, isolated step after WiFi and WebSocket are proven.

## 2026-06-15 - lwIP ERR_RTE During XiaoZhi WebSocket Connect Means Routing/Netif Context, Not WiFi Scan

Symptoms:
- M55 WiFi auto-connect is stable after reset.
- `m55qa_status` shows `saved=1 auto=1`, `wlan=1 ready=1`, and a valid DHCP lease.
- XiaoZhi still does not connect; serial shows `xz_ws=0 xz_stage=20 xz_errno=-4`.
- The cloud WebSocket URL/token/path had already been proven valid from PC with HTTP `101 Switching Protocols`.

Root cause / best current hypothesis:
- `-4` is lwIP `ERR_RTE`.
- The failure happens while starting `wsock_connect()` / `altcp_connect()`, before hello or audio.
- This points to lwIP routing/default-netif context or explicit PCB binding, not WiFi scanning or password storage.

Fix / next diagnostic move:
- Keep the WebSocket client on the official lwIP callback path.
- Before guessing at higher-level XiaoZhi logic, inspect `netif_default`, `ip_route()`, and the active WiFi netif binding.
- If needed, bind the WebSocket PCB to the live WiFi interface/local IP before connecting.

Reusable trick:
- Once WiFi DHCP works but lwIP TCP connect returns `ERR_RTE`, stop chasing SSID/password/UI. The bug is below the app layer, usually in netif selection or route context.

## 2026-06-15 - XiaoZhi Connected But No Reply: Separate Transport From Audio Codec/ASR

Symptoms:
- Board status shows stable WiFi and a connected XiaoZhi WebSocket: `xz_ws=1 xz_stage=70 xz_errno=0`.
- Manual capture starts M55 mic successfully and sends many binary frames: examples include `frames=2326 pcm_seq=2326 probe_lwip=387/744588`.
- After `m55qa_capture_off`, no `stt`, `llm`, `tts`, or binary audio reply is observed; only server hello/listen control text is counted.
- A PC-side synthetic speech WAV converted to 16 kHz mono S16LE PCM and sent through the same v3 WebSocket path also received only `listen start/stop`, with no STT/TTS within the wait window.

Root cause / current best hypothesis:
- Transport is no longer the blocker. WebSocket, mic capture, M33->M55 command path, and binary upstream have all been proven.
- The remaining boundary is audio format handling. Official XiaoZhi expects Opus frames, while the current M55 path sends raw `pcm_s16le` wrapped in v3 binary framing.
- A PC `ClientWebSocket` probe showed the platform can echo `pcm_s16le` in hello, but the synthetic speech probe indicates the downstream relay still may not perform PCM ASR.

Fix/status:
- M55 now declares `Protocol-Version: 3`, `hello.version=3`, and `audio_params.format=pcm_s16le` so the protocol matches the current payload instead of claiming Opus.
- `WSMSG_MAXSIZE` is 4096 so 60 ms PCM packets plus the v3 header are not rejected by the local lwIP WebSocket send path.
- Status is partially fixed: upstream transport is working, model reply is not yet working.

Reusable trick:
- Do not debug WiFi, DHCP, or LVGL when `xz_ws=1` and `probe_lwip` increases during capture. At that point inspect server-side ASR/codec logs or add Opus/PCM transcode support.
- Treat these as separate gates: WebSocket connected, server hello received, mic frames captured, binary frames sent, server STT returned, TTS audio returned, speaker playback.
- If nobody is physically near the board, generate a local 16 kHz mono WAV with Windows speech synthesis and send its PCM frames through the WebSocket probe to remove ambient noise from the diagnosis.

Update:
- After the platform relay was fixed, the same PC synthetic speech PCM probe returned `stt`, `llm`, `chat`, and `tts start/stop`.
- The board then needed a reset because M55 voice status had gone stale and M33 `tx_pending` increased without fresh ACKs.
- After reset, M55 IPC and WebSocket recovered and board PCM upstream was again proven by `probe_lwip=386/742664`.
- If board capture still produces no STT while nobody is near the microphone, treat it as no valid speech input, not as a relay regression.

## 2026-06-17 - Do Not Claim Opus While Sending PCM

Symptoms:
- A PC-side XiaoZhi smoke test connected to the platform and passed `hello`/`listen start`, but the platform returned `opus_decode_not_configured` after binary frames.
- The test output said `declared_format=opus` while the script actually generated 16 kHz S16LE PCM tone frames.

Root cause:
- The smoke test's `hello.audio_params.format` was hardcoded to `opus`, but `New-PcmFrame` produced raw PCM. This made a good platform rejection look like a board or server Opus failure.

Fix:
- `tools/xiaozhi_ws_smoke_test.ps1` now defaults to `AudioFormat=pcm_s16le`.
- `AudioFormat=opus` requires an explicit length-prefixed Opus packet file; the script does not pretend to encode PCM on the PC.
- CM55 firmware now enables `XIAOZHI_USE_OFFICIAL_OPUS_AUDIO` and fixes the Opus encoder sample-count check to 960 samples for 60 ms at 16 kHz.

Status:
- Board-side official Opus uplink is validated by `m55qa_status` examples such as `xz_last=158/28282 xz_fail=0`.
- The latest probe did not receive binary TTS (`xz_rx=2/0`), so speaker playback remains unverified rather than proven broken.

Reusable trick:
- Keep the XiaoZhi gates separate: declared audio format, actual binary payload format, WebSocket connection, upstream packet counter, STT text, binary TTS, CM55 `tts_fwd`, and M33 `sound0`.
- If `xz_last` is around tens of KB for several seconds of speech, it is likely Opus. If it is hundreds of KB, it is likely raw PCM.

## 2026-06-15 - XiaoZhi LVGL Stuck Thinking And Missing Chinese Glyphs

Symptoms:
- LCD XiaoZhi panel can remain on “正在思考” after an utterance if no TTS/text completion arrives.
- Some Chinese UI text renders as square boxes.

Root cause:
- `xiaozhi_ui_state` recorded the last phase but did not expire `THINKING` or `SPEAKING` if the platform reply or stop event never arrived.
- The generated `rehab_wifi_font` only contains a small fixed symbol set and had `.fallback = NULL`, even though `LV_FONT_SIMSUN_16_CJK` is enabled.

Fix:
- Expire `XIAOZHI_UI_THINKING` after about 20 s into `READY` with “未收到回复，请重试”.
- Expire `XIAOZHI_UI_SPEAKING` after about 30 s into `READY`.
- Declare `lv_font_simsun_16_cjk` and assign it as the fallback for `rehab_wifi_font`.

Reusable trick:
- On this bench COM4 is the M33 shell. M55-only finsh exports are not directly callable there; use `m55qa_status` as the authoritative M55 IPC snapshot.
- Do not grow the custom LVGL font with every possible model reply. Keep dynamic replies off the small LCD and use a CJK fallback for fixed UI text.

Status:
- Built and burned on M55 with WiFi resources. Serial QA confirmed WiFi, XiaoZhi WebSocket, wake readiness, and LVGL flush in the stable state.
- Visual LCD confirmation is still required for the final glyph appearance.

## 2026-06-15 - Speaker QA Tone Is Not Representative Of XiaoZhi Voice

Symptom:
- `audio_playback_tone_cmd` proves `sound0` and I2S writes, but the square-wave tone sounds harsh and does not resemble a XiaoZhi/person voice.

Root cause:
- The first QA command intentionally generated a simple square wave to make driver failures obvious. It is useful for electrical/software bring-up but poor for user-facing audio evaluation.

Fix:
- Added `audio_playback_voice_cmd`, an algorithmic voice-like sample with a 64-point sine table, simple harmonic/formant-like mixing, pitch movement, and attack/release envelope.
- Avoided embedding a large PCM asset in firmware.

Reusable trick:
- Keep two speaker QA levels: a simple tone for low-level driver verification, and a softer voice-like local sample for human listening checks. Neither replaces real platform TTS validation.

Status:
- Command built, burned, and ran successfully through `sound0`; physical listening quality still needs onsite confirmation.

Update:
- Onsite feedback confirmed the algorithmic sample sounds noisy and must not be used as a user-facing response.
- Keep `audio_playback_voice_cmd` only as a speaker QA/debug command.
- Do not wire local generated audio into XiaoZhi wake acknowledgement. For a real “我在” response, use platform/official TTS audio or a separately validated real prompt asset.

## 2026-06-19 - COM4 token reload can succeed while XiaoZhi reconnect still fails

Symptoms:
- `tools/load_xiaozhi_token.ps1` successfully sent `m55qa_xz_token_begin`, a sequence of `m55qa_xz_token_part` chunks, and `m55qa_xz_token_commit` over COM4.
- The visible shell returned ACKs for the config bridge path, but `m55qa_xz_reconnect` still ended in `cmd=1003 result=-255`.
- `m55qa_status` showed the token updated to `token_len=480`, yet `xz_ws` stayed `0` and `xz_errno` remained `-403`.

Environment:
- Active shell: `COM4` KitProg3 USB-UART.
- Loader source: `D:\RT-ThreadStudio\workspace\yiliao_m33\tools\load_xiaozhi_token.ps1`.
- Token source: scoped relay token file beginning with `rehab-relay.v1.`.

Root cause:
- The token write path was fine; the remaining failure sits on the platform acceptance / authorization side, not on WiFi or the shell transport.

Fix:
- Treat the current blocker as cloud/token acceptance, not board-side WiFi bring-up.
- Keep using the chunked loader path because it avoids shell truncation and proves the token reached CM55.

Trick:
- Check both the ACK chain and the status snapshot. A successful `m55qa_xz_token_commit` does not guarantee `xz_ws=1`; always confirm `m55qa_status` after reconnect.

Status:
- Partially fixed: token rewrite works, reconnect still rejected.

## 2026-06-19 - Port 3001 platform front door is live, but unauthenticated requests only see login

Symptoms:
- `http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab` returns HTTP 200 and serves the platform shell.
- The same request from this shell lands on the login page rather than the project workspace.

Environment:
- Front door: `106.55.62.122:3001`
- Project path: `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab`

Root cause:
- The platform exists and is reachable, but the current session is not authenticated for the project page.

Fix:
- Treat `3001` as the active platform entry and login gate, not as evidence that the model-relay-lab workspace is already available in the current shell.

Trick:
- When a platform page works in the browser but not from a shell, check whether you are seeing the front door or the authenticated project surface.

Status:
- Live but not authenticated from this context.

## 2026-06-19 - The platform login page expects a real email/password pair, not the bench account stub

Symptoms:
- The login page at `http://106.55.62.122:3001/login` rendered correctly and accepted form input.
- Submitting `3245056131 / 1234` returned `INVALID_CREDENTIALS`.
- A best-effort `3245056131@qq.com / 1234` retry also stayed on the login page.

Environment:
- Platform front door: `106.55.62.122:3001`
- Target project path: `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab`

Root cause:
- The supplied pair is not a valid login for this platform account system.
- The page is email-based, so a raw numeric identifier is not enough by itself.

Trick:
- When a login page uses email fields, do not assume a numeric chat handle is a usable account.
- Treat `INVALID_CREDENTIALS` as a hard stop and stop guessing after one careful retry.

Status:
- Unauthenticated; relay inspection from the project page is still blocked until the correct account or session is available.
