@echo off
setlocal
cd /d D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin
openocd.exe -s ../scripts -s ../flm/cypress/cat1d -f interface/kitprog3.cfg -f target/infineon/pse84xgxs2.cfg -c "init; reset init; dump_image D:/RT-ThreadStudio/workspace/wifi_resources/readback_fw_64.bin 0x60DC0000 64; exit"
endlocal
