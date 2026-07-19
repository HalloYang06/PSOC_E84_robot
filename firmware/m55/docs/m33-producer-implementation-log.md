# M33 Producer 实现记录

日期：2026-06-07

这份记录说明本次已经在 `F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3` 工程里完成的 M33 producer 接入。注意：M33 工程当前不是 git 仓库，所以这份文档放在 M55 AI 工程里作为可追溯记录。

## 1. 目标

让 M33 LSM6DS3 例程在保持原有串口 IMU 打印的同时，把 IMU 样本打包成 `edge_ai_signal_window_t` 并发布到 M33/M55 共享内存：

```text
M33 LSM6DS3 sample
  -> edge_ai_m33_producer_push_imu_sample()
  -> edge_ai_transport_publish_signal_window()
  -> shared block 0x261C0000
  -> M55 edge_ai_online_consumer
```

## 2. M33 新增文件

新增目录：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3\applications\edge_ai\
```

同步自 M55 工程的通用契约文件：

```text
edge_ai_status.h
edge_ai_signal.h
edge_ai_signal.c
edge_ai_transport.h
edge_ai_transport.c
edge_ai_transport_sharedmem.h
edge_ai_transport_sharedmem.c
edge_ai_shared_contract.h
edge_ai_shared_contract.c
```

M33 专属 producer：

```text
edge_ai_m33_producer.h
edge_ai_m33_producer.c
SConscript
```

## 3. M33 修改文件

修改：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3\packages\lsm6ds3tr\SConscript
```

作用：给 LSM6DS3 package 增加 `applications/edge_ai` include path。

修改：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3\packages\lsm6ds3tr\lsm6ds3tr-c_port.c
```

作用：

- 引入 `edge_ai_m33_producer.h`；
- LSM6DS3 初始化完成后调用 `edge_ai_m33_producer_init()`；
- 每次同时获得 accel / gyro / temperature 后，把样本推入 producer；
- producer 每累计 8 个样本发布一个 signal window；
- 原有三行日志 `Acceleration / Angular rate / Temperature` 保持不变。

## 4. 当前发布窗口格式

```text
sample_count = 8
channel_count = 7

channel_ids:
  EDGE_AI_SIGNAL_ACCEL_X_MG
  EDGE_AI_SIGNAL_ACCEL_Y_MG
  EDGE_AI_SIGNAL_ACCEL_Z_MG
  EDGE_AI_SIGNAL_GYRO_X_MDPS
  EDGE_AI_SIGNAL_GYRO_Y_MDPS
  EDGE_AI_SIGNAL_GYRO_Z_MDPS
  EDGE_AI_SIGNAL_TEMPERATURE_C
```

每 8 个完整样本发布一次。当前 LSM6DS3 例程里有 `rt_thread_mdelay(500)`，所以大约 4 秒发布一帧窗口。

## 5. 期望串口现象

M33：

```text
[m33_edge_ai] producer init status=0 addr=0x261c0000 size=...
Acceleration [mg]:...
Angular rate [mdps]:...
Temperature [degC]:...
[m33_edge_ai] publish seq=1 count=8 channels=7 status=0
```

M55：

```text
[edge_ai_online] waiting producer status=-4 attached=0 addr=0x261c0000
[edge_ai_online] seq=1 classifier=imu_mlp label=... score=... channels=7
```

`status=-4` 是 `EDGE_AI_STATUS_MAGIC`，表示 M55 正在等待 M33 format 共享块。只要 M33 producer init 后它就应该消失。

## 6. 构建验证

M33 构建命令：

```powershell
cd F:\RT-ThreadStudio\workspace\Edgi_Talk_M33_LSM6DS3
F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4
```

结果：

```text
CC build\applications\edge_ai\edge_ai_m33_producer.o
CC build\applications\edge_ai\edge_ai_shared_contract.o
CC build\applications\edge_ai\edge_ai_signal.o
CC build\applications\edge_ai\edge_ai_transport.o
CC build\applications\edge_ai\edge_ai_transport_sharedmem.o
CC build\packages\lsm6ds3tr\lsm6ds3tr-c_port.o
LINK rt-thread.elf
text=81500 data=1344 bss=257253
Edge Protect: Saved file to 'build/rtthread.hex'
```

M55 构建也通过，当前 M55 固件已包含在线 consumer runtime。

## 7. 还没有做什么

还没有做自动烧录和串口抓取，因为当前工作区没有找到现成 `.launch` 烧录配置。下一步可以：

- 用 RT-Thread Studio 分别下载 M33 `build/rtthread.hex` 和 M55 `rtthread.hex`；
- 或补充 OpenOCD 烧录命令后，让脚本自动烧录并抓取串口。

第一版仍然不加 IPC notify。M55 用轮询方式读取共享块，先把链路跑稳。
