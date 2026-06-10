# Troubleshooting And Lessons

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
