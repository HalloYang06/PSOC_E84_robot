# M33 助力模式反馈准备修复与实机复盘

日期：2026-07-17

## 1. 现场现象

M33 能接受 `rehab assist 5`，但进入后不输出助力。首次受限烟测把 `assist_max` 临时降到 0.2 A，结果为：

```text
rehab assist ret=0
rehab status mode=assist fresh=0 detail=9 assist=0 last=-116
```

`detail=9` 是 `CONTROL_STATUS_DETAIL_MOTOR_FAULT`，`last=-116` 是 `-RT_ETIMEOUT`。安全 STOP 成功，测试没有产生电流。

## 2. 根因

助力 worker 在调用 `control_motor_current_control()` 前，要求目标电机存在 100 ms 内的新鲜反馈。私有协议电机上电后未必主动上报，而 `control_motor_set_active_report()` 原来只由 Shell 或特定命令调用。

这形成了启动依赖死锁：

```text
未开启主动上报
  -> 反馈缓存过期
  -> rehab worker 拒绝进入电流控制
  -> control_motor_current_control() 中的电机 enable 永远不会执行
```

现场执行 `cmd_motor_report 5 1` 后，`rx_total` 快速增长，电机反馈时间戳持续更新；再次执行助力烟测即可达到 `fresh=1 detail=0 assist=1`，证明算法和限流路径本身可工作。

## 3. 修复

提交：`092e05670 fix(rehab): prepare motor feedback before assist`

单关节活动模式进入前现在会：

1. 调用 `control_motor_set_active_report(m33_joint_id, RT_TRUE)`。
2. 最多等待 300 ms。
3. 只有检测到 100 ms 内的新鲜反馈，才提交 ACTIVE、ASSIST 或 RESIST 状态转换。
4. 上报请求失败或等待超时则返回错误，保持原模式，不下发电流。

该等待发生在取得 `actuation_lock` 之前，不会在等待 CAN 首帧时长期占用执行锁。

## 4. 自动验证

测试遵循先失败、后实现的顺序：

```powershell
rtk python tools/test_rehab_service_actuation_static.py
```

结果：4 项通过。完整 SCons 构建通过，生成新的 `build/rtthread.hex`。构建仍有工程原有的 CAN、BLE 和 main 警告，本次新增代码没有产生新警告。

`tools/test_rehab_mode_static.py` 当前被工作区已有 `main.c` 配置差异阻断：测试要求 `M33_XIAOZHI_MINIMAL_FRAMEWORK 1`，当前文件没有该宏。本次没有修改这部分用户代码。

## 5. 复位后实机验证

新镜像通过 verified flash 流程完成编程、原始地址校验和 XIP 地址校验。复位会清除之前手动开启的主动上报，因此烧录后没有执行 `cmd_motor_report 5 1`，直接运行 0.2 A 助力烟测。

关键结果：

```text
rehab assist ret=0
rehab status mode=assist fresh=1 detail=0 assist=1 limit_x1000=200 last=0
MOTOR[5]: mode=2 fault=0x00
rehab stop ret=0
rehab status mode=passive detail=0 last=0
```

本次关节基本静止，扭矩和速度在策略触发阈值附近，因此观测电流为 0 A；它证明反馈准备和模式进入已恢复，但不能替代操作者手动施力时的助力方向、幅值和连续运行测试。STOP 后运行参数已恢复为 `assist_max=1.0 A`。

## 6. NanoPi/CAN mask 入口补强

后续独立提交 `ccbc93604 fix(rehab): prepare feedback for CAN joint masks` 修复了 `rehab_service_set_mode_mask()`：

1. 先向 mask 中全部电机发送主动上报请求。
2. 使用一个共享的 300 ms 窗口等待全部反馈新鲜，不按关节累计超时时间。
3. 任一请求失败或任一反馈未就绪，都保持原模式并记录 `MOTOR_FAULT`，不会进入部分关节已启动的状态。
4. 反馈全部就绪后才取得 `actuation_lock` 并提交模式转换。

回归测试从预期的 2 项失败转为 6 项通过，租约静态测试 6 项保持通过，SCons 增量编译通过。新镜像完成 verified flash 后，从 NanoPi 发送 PASSIVE 烟测得到：

```text
CTRL_DBG: rx_total=2 hb=42 ros_id=1 parsed=1 enq=1 applied=1 qfail=0
CTRL_DBG_Q: emergency=1 stale=0 recheck_reject=0 apply_fail=0 ttl_ms=500
CTRL_DBG_LEASE: mode=0 gen=1 timeout=0 retry=0 latched=0 hb_timeout_ms=2500
```

## 7. 尚未进行的活动 mask 实测

当前 `0x320 SET_MODE` 解析器没有从 payload 读取 joint mask，而是固定使用：

```text
CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK = 0x38
```

`0x38` 对应 M33 关节 4、5、6，不是单关节 5。历史文档中“Byte5 是 active_joint_mask”的描述与当前代码不一致。为了避免一次远程 ASSIST 同时驱动三个关节，本次只完成 PASSIVE 端到端复测，没有从 NanoPi 发送活动模式命令。

下一步应先确定兼容方案：扩展 `0x320 SET_MODE` 明确携带并校验 joint mask，或者将单关节台架默认 mask 改为经过确认的单 bit。该协议决策必须同步修改 NanoPi、M33 和协议文档后再做活动实测，不能只改 M33 常量。

2026-07-17 后续已采用“Byte3 显式单关节 mask”方案。实现、兼容规则、提交和待完成的真机验证见 `docs/M33_NANOPI_0X320_SET_MODE_MASK_20260717.md`。
