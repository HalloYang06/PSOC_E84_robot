@echo off
setlocal
cd /d D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin
openocd.exe -s ../scripts -s ../flm/cypress/cat1d -f interface/kitprog3.cfg -f target/infineon/pse84xgxs2.cfg -c "init; reset init; flash write_image erase D:/RT-ThreadStudio/workspace/wifi/rtthread.hex; flash write_image erase D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin 0x60E00000 bin; reset run; exit"
endlocal
