# Troubleshooting And Lessons

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

## 2026-06-10 - M33 Hex Relocation

Symptom:
- M33 post-build may print `arm-none-eabi-objcopy: interleave must be positive` and ignore the post-build error.

Fix:
- Manually run `arm-none-eabi-objcopy -O ihex Debug\rtthread.elf Debug\rtthread.hex`.
- Then run `tools\edgeprotecttools\bin\edgeprotecttools.exe run-config -i config\boot_with_extended_boot.json` from `Debug`.
- Confirm the first line of `Debug\rtthread.hex` is `:02000004603466` before burning.

Status:
- Fixed workflow, still a manual step until the generated post-build command is corrected.
