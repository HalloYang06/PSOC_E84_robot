# NanoPi 到 M33 0x320 PASSIVE 烟测记录

日期：2026-07-17

## 为什么先只测 PASSIVE

当前 M33 的 CAN `SET_MODE` 路径把活动关节掩码固定为 `0x38`，远程 ASSIST 并不等价于 Shell 的单关节 `rehab assist 5`。同时 `rehab_mode_manager_tick()` 尚未实现 heartbeat 超时退出，NanoPi 掉线后不能证明活动模式会自动回到 PASSIVE。

因此本阶段只验证链路：

```text
NanoPi cansend -> CAN 0x321/0x320 -> M33 parse/apply -> rehab PASSIVE
```

脚本明确拒绝 `active/assist/resist`，直到单关节映射、heartbeat 超时和异步队列安全门全部验证。

## PASSIVE 帧

```text
321#SS        heartbeat，SS 为本次 sequence
321#SS        第二次 heartbeat
320#04SS00    SET_MODE，mode=PASSIVE
```

脚本在发送前检查：

- CAN interface 为 UP。
- controller state 为 ERROR-ACTIVE。
- bitrate 为 1000000。
- 历史 bus-off counter 为 0。

`set -euo pipefail` 保证任一 `ip`、`awk` 或 `cansend` 失败时立即退出。每一帧发送前打印完整 payload，便于和 `candump` 对账。

## 自动测试

```powershell
rtk python -m unittest tools.test_nanopi_rehab_mode_script -v
rtk bash -n tools/nanopi_rehab_mode.sh
```

结果：9 个静态与行为测试通过，Bash syntax check 通过。行为测试通过 fake `ip/cansend/sleep` 实际执行脚本，覆盖健康 PASSIVE、仅有 `LOWER_UP`、错误 nominal bitrate 但正确 dbitrate、bus-off 历史非零、活动模式、多余参数，以及第 1/2 次 `cansend` 失败后立即停止。

测试使用系统临时目录，不依赖仓库中的未跟踪 `tmp/`。Bash 查找支持 `NANOPI_TEST_BASH`、Windows Git Bash 和系统 `PATH`，因此可在 Windows、Linux 或 NanoPi 上执行。`.gitattributes` 只为本脚本固定 `eol=lf`，防止 Windows checkout 写成 CRLF。

测试脚本只复制到 NanoPi `/tmp/nanopi_rehab_mode.sh`，没有覆盖正式工具或 systemd 服务。

## 板端证据

NanoPi：

```text
host=NanoPi-M5
can0=UP,LOWER_UP
state=ERROR-ACTIVE
bitrate=1000000
berr-counter tx=0 rx=0
bus-off=0
```

活动模式拒绝结果：

```text
remote active modes are blocked until heartbeat timeout and single-joint mapping are validated
```

PASSIVE 发送：

```text
tx 321#01
tx 321#01
tx 320#040100
sent rehab mode=passive seq=0x01 iface=can0
```

M33 第一次手工 PASSIVE 后：

```text
ros_id=1 parsed=1 enq=0 applied=1 qfail=0
mode=passive source=1 last=0
```

候选脚本初版 PASSIVE 后：

```text
ros_id=2 parsed=2 enq=0 applied=2 qfail=0
mode=passive source=1 last=0
rehab cycles=10247
F103 sensor=10276 health=205
```

结论：`0x320` 物理链路、M33 parser 和当前同步 apply 路径可以接收 PASSIVE。`enq=0` 是当前预期，因为 CAN RX 到 `ros_cmd` 的异步队列尚未接通；本结果不能用于证明异步命令链或远程活动模式安全。

修订版增加精确 `UP` flag 和 nominal bitrate 解析后，再次在 NanoPi `/tmp` 运行：

```text
tx 321#02
tx 321#02
tx 320#040200
ros_id=3 parsed=3 enq=0 applied=3 qfail=0
mode=passive source=1 last=0
rehab cycles=20391
F103 sensor=20427 health=408
```

脚本把历史 bus-off counter 非零也视为拒绝条件。这是有意的保守策略：出现过 bus-off 后应先记录现场并显式 down/up 恢复 CAN，而不是让烟测脚本自动清除错误历史。
