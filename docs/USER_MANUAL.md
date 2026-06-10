# User Manual

## CM55 Wi-Fi Provisioning QA

Purpose:
- Configure CM55 Wi-Fi for XiaoZhi/WebSocket and later platform communication without hardcoding credentials in firmware.
- Keep user-facing provisioning reusable from three entries: LVGL touchscreen, CM55 shell, and M33/App IPC.

Safety and credential boundary:
- `/flash/rehab_wifi.cfg` stores only Wi-Fi SSID/password and auto-connect state.
- Do not store platform scoped relay tokens in the Wi-Fi config file.
- Do not store vendor LLM API keys on M33, CM55, NanoPi, or in Git.

Touchscreen path after flashing CM55:
1. Power the Infineon board and wait for the LVGL screen.
2. Open the `Rehab Arm WiFi Setup` panel if it is not already visible:
   ```text
   rehab_wifi_panel_cmd
   ```
3. Press `Scan`.
4. Wait up to about five seconds. Nearby networks should appear in the list with SSID, RSSI, security mode, and channel.
5. Tap the target Wi-Fi network. The SSID field is filled automatically.
6. Tap the password field and enter the Wi-Fi password on the LVGL keyboard.
7. Keep `Auto connect` checked for product-like boot behavior.
8. Press `Connect` to save and connect immediately, or press `Save` if you only want to persist credentials.
9. Press `Diag` after a few seconds and verify the screen shows a netdev, WLAN ready/connected state, and `saved:1 auto:1 storage:0`.

Touchscreen notes:
- If the target network is hidden or not listed, manually type the SSID field and continue from the password step.
- `Scan` refreshes the list automatically for a short period after tapping it. `Diag` also refreshes the cached list/status.
- The scan list is a convenience UI over the shared CM55 Wi-Fi config service; it does not store platform relay tokens or vendor API keys.

CM55 shell path, if the interactive shell is on CM55:
```text
m55_wifi_ssid <ssid>
m55_wifi_password <password>
m55_wifi_auto 1
m55_wifi_save
m55_wifi_connect
m55_wifi_status
```

M33 shell path, when the visible shell is M33:
```text
m55qa_wifi_ssid <ssid>
m55qa_wifi_password <password>
m55qa_wifi_auto 1
m55qa_wifi_save
m55qa_wifi_connect
m55qa_wifi_diag
m55qa_whd_diag
m55qa_status
```

Forget credentials:
```text
m55qa_wifi_forget
```
or on CM55:
```text
m55_wifi_forget
```

Expected pass criteria:
- `m55qa_status` prints `ipc_ready=1`.
- The netdev line eventually shows `saved=1 auto=1 storage=0`.
- `wlan=1` or `ready=1` appears after connection succeeds.
- IP/GW/mask/DNS fields are no longer all zero after DHCP succeeds.

If Wi-Fi was previously working but now does not enumerate:
```text
m55qa_whd_diag
m55qa_wifi_diag
m55qa_wifi_scan
m55qa_status
```

CM55 local scan-list fallback when the shell is on CM55:
```text
m55_wifi_scan
# wait 3-5 seconds
m55_wifi_aps
```

Expected `m55_wifi_aps` output:
```text
[wifi_config] cached_ap_count=<n>
[wifi_config] ap[0] ssid="<ssid>" rssi=-45 security=WPA2 channel=6 bssid=xx:xx:xx:xx:xx:xx
```

Use this when the LVGL screen or touch panel is not yet trusted. If `m55_wifi_aps` lists nearby APs but LVGL does not, debug the LVGL list/touch layer. If both show no APs, debug WHD/WLAN scan, antenna, power, or RF environment first.

Useful interpretation:
- `whd_stage=5` with a negative result usually means the SDIO/WHD probe path timed out; check reset timing, WLAN power, and WHD resource partitions before changing XiaoZhi logic.
- `storage` is the result of the last Wi-Fi config file operation. `0` means saved/loaded successfully; negative values mean the `/flash` filesystem or config file was not available.

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

Optional token loader from Windows PowerShell:
```powershell
# Save only the platform scoped relay token into token.txt. Do not save a vendor LLM API key.
powershell -ExecutionPolicy Bypass -File D:\RT-ThreadStudio\workspace\yiliao_m33\tools\load_xiaozhi_token.ps1 `
  -PortName COM26 `
  -TokenFile D:\RT-ThreadStudio\workspace\token.txt
```

The loader masks token chunks in terminal output. It sends `m55qa_xz_token_begin`, repeated `m55qa_xz_token_part`, `m55qa_xz_token_commit`, then `m55qa_status`.

Quick reconnect or clear without a token file:
```powershell
powershell -ExecutionPolicy Bypass -File D:\RT-ThreadStudio\workspace\yiliao_m33\tools\load_xiaozhi_token.ps1 -PortName COM26 -ReconnectOnly
powershell -ExecutionPolicy Bypass -File D:\RT-ThreadStudio\workspace\yiliao_m33\tools\load_xiaozhi_token.ps1 -PortName COM26 -Clear
```

PC-side XiaoZhi cloud smoke test when nobody is near the board microphone:
```powershell
powershell -ExecutionPolicy Bypass -File D:\RT-ThreadStudio\workspace\yiliao_m33\tools\xiaozhi_ws_smoke_test.ps1 `
  -TokenFile D:\RT-ThreadStudio\workspace\token.txt `
  -Frames 30
```

This test opens the same platform WebSocket, sends the XiaoZhi `hello`, sends `listen start`, streams 30 synthetic 640-byte PCM frames, then sends `listen stop`. It proves the platform WebSocket/audio contract without relying on local wake-word audio.

Expected output:
```text
[m55qa] ipc_ready=1 tx_pending=0 rx_pending=0 has_model=1
[m55qa] voice_status ... wake_on=<0_or_1> wake_ready=<0_or_1> wake_hit=<0_or_1> xz_listening=<0_or_1> xz_ws=<0_or_1> xz_token=<0_or_1> ...
[m55_model_bridge] voice_ack seq=<n> cmd=1004 result=0 ...
[m55_model_bridge] voice_ack seq=<n> cmd=1005 result=0 ...
[m55_model_bridge] voice_ack seq=<n> cmd=1006 result=<0_or_network_error> ...
[m55qa] voice_ack seq=<n> cmd=3 result=0 ...
[m55qa] voice_ack seq=<n> cmd=1 result=0 ...
[m55qa] voice_ack seq=<n> cmd=4 result=0 ...
```

Notes:
- `xz_token=0` means no scoped relay token is loaded on CM55; WebSocket auth is expected to fail.
- `xz_ws=0` means the XiaoZhi WebSocket is not connected.
- `xz_listening=1` means CM55 is actively streaming the post-wake utterance to the platform.
- XiaoZhi binary audio frames sent by CM55 are fixed at `640` bytes per frame: `16 kHz * 1 channel * 16 bit * 20 ms`.
- `latest_pcm_len=320` in `m55qa_status` can still be normal because it is the local mic driver chunk length. The cloud WebSocket frame length is separately reframed to 640 bytes in CM55.
- A matching platform token should make `xz_token=1`. A successful WebSocket connection should make `xz_ws=1`.
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
