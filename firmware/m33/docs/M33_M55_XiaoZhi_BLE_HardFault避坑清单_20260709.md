# M33/M55 小智、BLE、推理结果 HardFault 避坑清单

日期：2026-07-09

用途：给后续线程改 M33/M55、小智语义切换、BLE/App 连接、M55 肌电推理结果回传时先读。本文不是完整复盘，而是把这次反复 HardFault 的高危点整理成可执行规则，避免后续又把刚通的 CAN/模式/云端链路改崩。

## 一句话结论

这次最危险的组合是：

```text
BLE/App 连接初始化 + 小智切换助力/阻力模式 + M55 推理结果回传
```

它们都容易碰到 M33 的同一组薄弱点：

```text
启动时序、RT-Thread 线程栈、IPC 队列、共享内存/cache、字符串/变长 payload、回调上下文、M33 安全门边界
```

以后改这三类功能时，必须把它们当成高危实时链路，不要当普通业务代码直接塞进 `main.c` 或 CAN 回调里。

## 本次已知现象

出现过的表象包括：

```text
M33 shell 没日志
NanoPi / candump 看不到 0x322 回包
模式切换命令发了但没生效
云端页面 WAIT 或上下状态不一致
复位后短时间正常，运行一会儿又死
上一个固件能通，后面加 BLE/小智/M55 回传后突然不通
```

这些现象不要先归因到 CAN、NanoPi、F103、云端或页面。第一步先判断 M33 是否已经进 HardFault/Lockup。

## 先做的三步，不要跳

### 1. 第一时间看 shell 是否还活着

```text
能进 msh：先查日志、cmd_control_debug、相关状态命令
不能进 msh：不要继续猜 CAN 或云端，直接 halt 查 fault
```

### 2. halt 后查 fault 寄存器

至少记录：

```text
xPSR
CFSR
HFSR
BFAR / MMFAR
MSP / PSP
MSP_NS / PSP_NS / CONTROL_NS
VTOR
HardFault vector
```

Cortex-M33 + TrustZone 下，Non-secure RT-Thread 的 fault dump 可能是 0。dump 为 0 不代表没有 HardFault。

### 3. 回溯 stacked PC

如果 fault 进 Secure handler：

```text
读 CONTROL_NS bit[1]
选择 MSP_NS 或 PSP_NS
异常栈 +0x18 取 stacked PC
用 addr2line / objdump 对 rt-thread.elf 回溯
```

不要只看当前 PC 停在 Secure handler，然后误以为不知道源头。

## 高危点 1：BLE/App 初始化不能直接并入 M33 主链路

### 风险

BLE 初始化和 App 连接代码常见风险：

```text
启动太早，RT-Thread device/heap/timer 还没稳定
注册回调后中断或协议栈线程开始抢资源
线程栈不够，日志/协议解析一多就越界
BLE callback 里直接调用模式切换、CAN、IPC publish
把 App 连接状态当成实时控制入口
```

### 避坑规则

1. BLE 相关功能必须有编译开关，默认不要自动进入正式运动链路。

```c
#define M33_ENABLE_APP_BLE_RUNTIME 0
```

2. BLE 初始化不要和 M33 CAN、M55 IPC、EMG stream 同时在 boot 路径里全打开。先用 shell 手动启动验证。
3. BLE callback 只入队轻量事件，不直接：

```text
发 CAN
改 rehab_mode_manager
publish M33/M55 IPC
使能电机
调用会阻塞的网络/日志/printf 大输出
```

4. BLE/App 对 M33 只能是训练库、目标、配置、状态同步入口。真实助力/阻力执行仍要过 M33 安全门和既有模式管理。

## 高危点 2：小智切换助力/阻力只能是语义建议

### 风险

小智语音链路和实时控制链路节奏不同。语音结果如果直接写模式或触发 CAN，会造成：

```text
回调上下文不对
重复命令太快
和 NanoPi/M33 模式帧竞争
安全门状态未确认
IPC 队列堆积
```

### 避坑规则

1. 小智只输出固定枚举建议，不输出自由字符串控制命令。

```text
assist = 1
resist = 2
passive = 3
stop = 4
```

2. 语义建议必须先落到 shadow/suggestion 状态，再由 M33 主循环或专用线程在安全门允许时消费。
3. 必须做去抖和限频：

```text
同一模式 500-1000 ms 内重复命令丢弃
安全状态未知时只记录候选，不应用
队列满时丢弃新建议并打短日志
```

4. 不要在小智音频/网络/TTS 回调里直接调用 M33 模式切换函数。
5. 演示时如果只是给云端显示模式，优先用 NanoPi demo 上传，不要为了页面效果把语义链路接进实时固件。

## 高危点 3：M55 推理结果回传必须固定协议、固定长度

### 风险

M55 推理结果看似只是 `elbow_curl/rest/shoulder_flex`，但回传路径会碰：

```text
M33/M55 IPC queue
shared memory
D-cache flush/invalidate
payload length
结构体 ABI 对齐
字符串拷贝
RT-Thread 调度
```

高危写法：

```text
直接传字符串 label
变长 JSON 进固件 IPC
不检查 len 就 memcpy
M55 写共享内存后不 flush cache
M33 读共享内存前不 invalidate cache
queue full 还继续 publish
ISR/callback 里解析大 payload 或 rt_kprintf 大段日志
```

### 推荐协议

固件内只传小结构，不传长字符串：

```c
typedef struct {
    uint8_t version;
    uint8_t result_code;   /* 0 elbow_curl, 1 rest, 2 shoulder_flex */
    uint8_t confidence;    /* 0-100 */
    uint8_t flags;
    uint32_t seq;
    uint32_t timestamp_ms;
} m55_emg_result_v1_t;
```

云端/App 要显示中文或英文标签，在 NanoPi/云端映射，不要让 M33/M55 固件传长字符串。

## 必须保留的安全边界

```text
小智：语义建议，不直接动电机
BLE/App：训练库/目标/配置/状态，不直接动电机
M55 推理：动作意图候选，不直接动电机
NanoPi 云端 demo：展示/录屏，不代表 M33 已允许运动
M33：最终安全门、模式应用、CAN 输出唯一可信入口
```

以后任何线程如果把“小智结果 / BLE 按钮 / M55 推理结果”直接接到电机使能、力矩、速度、位置或 CAN 私有协议上，必须先停下来重审。

## 改代码前检查表

改 BLE、小智、M55 回传前，先确认：

```text
[ ] 当前固件基线能进 shell
[ ] NanoPi 0x321 -> M33 0x322 正常
[ ] F103 0x7C0 激活 / 0x7C2 数据链路是否需要参与本次改动
[ ] M33/M55 IPC 是否需要手动 shell 启动，而不是 boot 自动启动
[ ] 本次只改一个方向：BLE、小智、M55 回传三者不要混改
[ ] 已记录当前 hex/elf/map 时间和 git diff
[ ] 已准备回退到上一个已知好固件
```

本次对话里已经证明：不要凭“某个时间点镜像应该是好的”来判断。必须记录：

```text
固件文件名
生成时间
git commit/diff
rt-thread.elf size
关键宏开关
烧录后 shell 日志
```

## 改代码时的硬规则

1. 不在 CAN RX ISR、BLE callback、IPC callback、音频/TTS callback 里做重活。
2. 所有跨核/跨线程 payload 都要检查：

```text
version
type
len
seq
checksum 或最小 sanity check
```

3. 所有 copy 都要有上限。
4. 所有 queue publish 都要检查返回值；满了就丢，不要阻塞实时链路。
5. 所有 shared memory 通信都要显式处理 cache。
6. 新线程必须给足 stack，并记录 high watermark。
7. 新功能先 shell 手动启动，再考虑是否 boot 自动启动。
8. 默认宏应保持保守：

```c
#define M33_ENABLE_M55_IPC_AUTO_INIT        0
#define M33_AUTO_START_EMG_M55_INFERENCE   0
#define M33_CM55_AUTO_RESTART_ENABLE       0
```

## 改完后的验证顺序

不要一上来就跑全链路。按这个顺序：

```text
1. 烧录后只看 M33 shell 是否稳定 30-60 秒
2. halt 一次确认 xPSR/CFSR/HFSR 正常
3. 只测 NanoPi 0x321 heartbeat，确认 0x322
4. 只测 0x320 模式切换，确认 M33 有解析日志
5. 再测 F103 0x7C0 激活和 0x7C2 数据
6. 再手动 m55_ipc_start
7. 再打开 M55 推理回传
8. 最后才接小智/语音/蓝牙/App
```

任何一步不通，停在当前层，不要继续往上叠功能。

## HardFault 现场保存模板

后续线程遇到 HardFault，至少把下面内容贴进对应调试文档：

```text
日期：
固件/commit：
触发动作：
是否能进 shell：
xPSR：
CFSR：
HFSR：
BFAR/MMFAR：
VTOR：
HardFault vector：
MSP_NS：
PSP_NS：
CONTROL_NS：
stacked PC：
addr2line：
最近新增代码：
本次只尝试的一个修复：
验证结果：
```

## 本次坑的复盘结论

1. 加 BLE 代码后失败，不一定是 BLE 协议本身错，更可能是初始化时序、线程栈、回调上下文或资源竞争破坏了已通链路。
2. 小智切换助力模式不能直接进入实时控制路径，它应该先变成语义候选。
3. M55 推理结果回传不能用大字符串/变长结构硬塞 IPC，应使用固定小结构和云端映射。
4. CAN 不回、云端 WAIT、页面不动，第一步不是改页面或 NanoPi，而是确认 M33 是否活着。
5. Cortex-M33 TrustZone 下，HardFault dump 为空也要继续查 Secure handler 和 Non-secure 异常栈。
6. 以后改这块必须“一次只动一个变量”，先保存已知好版本，再扩展功能。

## 后续线程维护规则

后续线程可以继续修改本文，但必须遵守：

```text
只追加经过实测的新坑、新证据、新规避方法
不要删除已有结论，除非有新的硬件证据推翻
不要把 demo-only 的绕过写成正式链路
不要把云端展示成功写成 M33 真实运动授权成功
```

相关文档：

```text
docs/M33_HardFault调试定位分析活文档_20260708.md
docs/M33_CAN_HardFault四十分钟系统化调试复盘_20260708.md
docs/M33_CAN踩坑记录与排查索引_20260708.md
docs/M33_M55双核IPC与共享内存调试手册_20260707.md
```
