# Project Progress

## 2026-06-10

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
