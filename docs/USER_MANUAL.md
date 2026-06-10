# User Manual

## M33/CM55 Voice Foundation QA

Prerequisites:
- Infineon board powered and connected by KitProg/OpenOCD.
- M33 visible shell on `COM26` at `115200 8N1`.
- M33 and CM55 firmware burned from the matching `M33` and `M55` branches.
- Cloud command center XiaoZhi WebSocket endpoint:
  `ws://106.55.62.122:8011/api/rehab-arm/v1/projects/fd6a55ed-a63c-44b3-b123-96fb3c154966/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha`
- A platform-generated scoped relay token for this `project_id/device_id`; do not place vendor LLM API keys on the device.

Build:
```powershell
$env:Path='D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin;' + $env:Path
mingw32-make -C D:\RT-ThreadStudio\workspace\yiliao_m33\Debug all -j4
mingw32-make -C D:\RT-ThreadStudio\workspace\wifi\Debug all -j4
```

M33 hex relocation:
```powershell
arm-none-eabi-objcopy -O ihex D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.elf D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.hex
Push-Location D:\RT-ThreadStudio\workspace\yiliao_m33\Debug
..\tools\edgeprotecttools\bin\edgeprotecttools.exe run-config -i ..\config\boot_with_extended_boot.json
Get-Content .\rtthread.hex -TotalCount 1
Pop-Location
```

Pass criterion:
- The first hex line must be `:02000004603466`.

M33 shell QA:
```text
m55qa_status
m55qa_xz_token_begin
m55qa_xz_token_part <first_48_to_60_char_token_chunk>
m55qa_xz_token_part <next_48_to_60_char_token_chunk>
m55qa_xz_token_commit
m55qa_status
m55qa_wake_on
m55qa_status
m55qa_capture_on
m55qa_status
m55qa_wake_off
m55qa_status
```

Expected output:
```text
[m55qa] ipc_ready=1 tx_pending=0 rx_pending=0 has_model=1
[m55_model_bridge] voice_ack seq=<n> cmd=1004 result=0 ...
[m55_model_bridge] voice_ack seq=<n> cmd=1005 result=0 ...
[m55_model_bridge] voice_ack seq=<n> cmd=1006 result=<0_or_network_error> ...
[m55qa] voice_ack seq=<n> cmd=3 result=0 ...
[m55qa] voice_ack seq=<n> cmd=1 result=0 ...
[m55qa] voice_ack seq=<n> cmd=4 result=0 ...
```

Notes:
- The firmware default endpoint already targets `/xiaozhi/ws?robot_id=rehab-arm-alpha`; use `m55qa_xz_url <ws://...>` only when overriding it for diagnostics.
- `cmd=1004` begins a chunked XiaoZhi platform-token update on CM55.
- `cmd=1005` appends one token chunk; keep each chunk short enough for the embedded shell line, usually 48 to 60 characters.
- `cmd=1006` commits the staged token and reconnects the XiaoZhi WebSocket. A negative result can still mean the token was committed but the platform endpoint/auth/network is not ready.
- `m55qa_xz_token_clear` clears the CM55 platform token and should be used after dummy-token tests.
- Platform `daily_chat`, `none`, and `vla_command` replies are not motion permission. A `vla_command` is only the VLA language input and must still pass dry-run, operator review, and M33 safety gating before any motion.
- `cmd=3` is start wake listening.
- `cmd=1` is start capture.
- `cmd=4` is stop wake listening.
- Repeated `[drv_can] direct tx pending ...` lines indicate CAN/motor bus acknowledgement issues and do not by themselves mean CM55 IPC failed.
