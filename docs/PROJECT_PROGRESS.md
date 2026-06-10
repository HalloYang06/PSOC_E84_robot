# Project Progress

## 2026-06-10

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
