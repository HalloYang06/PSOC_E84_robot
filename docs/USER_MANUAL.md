# User Manual

## M33/CM55 Voice Foundation QA

Prerequisites:
- Infineon board powered and connected by KitProg/OpenOCD.
- M33 visible shell on `COM26` at `115200 8N1`.
- M33 and CM55 firmware burned from the matching `M33` and `M55` branches.

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
[m55qa] voice_ack seq=<n> cmd=3 result=0 ...
[m55qa] voice_ack seq=<n> cmd=1 result=0 ...
[m55qa] voice_ack seq=<n> cmd=4 result=0 ...
```

Notes:
- `cmd=3` is start wake listening.
- `cmd=1` is start capture.
- `cmd=4` is stop wake listening.
- Repeated `[drv_can] direct tx pending ...` lines indicate CAN/motor bus acknowledgement issues and do not by themselves mean CM55 IPC failed.
