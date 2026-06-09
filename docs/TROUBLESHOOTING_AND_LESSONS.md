# Troubleshooting And Lessons

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
