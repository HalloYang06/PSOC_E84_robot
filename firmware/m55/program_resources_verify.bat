@echo off
setlocal
cd /d D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin
openocd.exe -s ../scripts -s ../flm/cypress/cat1d -f interface/kitprog3.cfg -f target/infineon/pse84xgxs2.cfg -c "init; reset init; flash write_image erase D:/RT-ThreadStudio/workspace/wifi_resources/whd_firmware.bin 0x60DC0000 bin; verify_image D:/RT-ThreadStudio/workspace/wifi_resources/whd_firmware.bin 0x60DC0000 bin; flash write_image erase D:/RT-ThreadStudio/workspace/wifi_resources/whd_clm.bin 0x60E20000 bin; verify_image D:/RT-ThreadStudio/workspace/wifi_resources/whd_clm.bin 0x60E20000 bin; flash write_image erase D:/RT-ThreadStudio/workspace/wifi_resources/whd_nvram.bin 0x60E30000 bin; verify_image D:/RT-ThreadStudio/workspace/wifi_resources/whd_nvram.bin 0x60E30000 bin; exit"
endlocal
