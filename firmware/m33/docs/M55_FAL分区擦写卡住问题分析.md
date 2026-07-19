# M55 FAL 分区擦写卡住问题分析

记录日期：2026-07-06

本文记录 M55 上 `wifi_cfg` 和 `xiaozhi_cfg` 持久化分区从 4KB 调整为 256KB 对齐的原因、排查过程、根因判断和后续验证方法。文档不记录 WiFi 密码、relay token 等敏感信息。

## 问题背景

M55 需要在本地持久化两类配置：

1. WiFi 配置：SSID、密码、自动连接开关。
2. 小智云端 relay token：用于 M55 连接小智 WebSocket 云端链路。

代码侧已经实现了 FAL 持久化：

- `applications/wifi_config_service.c` 使用 FAL 分区 `wifi_cfg`。
- `applications/xiaozhi_voice_relay.c` 使用 FAL 分区 `xiaozhi_cfg`。

但原来的 M55 FAL 分区表没有这两个分区，导致 token 配置后重启仍然丢失，状态里会看到类似：

```text
xz_token=0 token_len=0
saved=0 或 storage=0
```

第一次补分区时，曾把 `wifi_cfg` 和 `xiaozhi_cfg` 做成 4KB 小分区。之后串口配置 WiFi/token 时出现 shell 无响应、M55 状态更新异常、屏幕/灯状态不符合预期等现象。

## 现象

当时可观察到的关键现象：

1. `m55qa_status` 一度无输出，M33 可见 shell 像被某条 M55 配置命令拖住。
2. 配置过程停在 WiFi 自动保存或后续 token 写入阶段，最终用户界面仍提示“未配置 token”。
3. 重新恢复串口后，WiFi 可以连上，但 token 状态仍为：

```text
xz_token=0 token_len=0
```

4. 改为 256KB 对齐分区并重新烧录、预置配置后，状态恢复为：

```text
xz_token=1 token_len=439
wlan=1 ready=1
xz_ws=1 xz_stage=70
srv_hello>=1
```

这说明问题主要发生在 M55 本地 Flash 配置持久化环节，而不是 token 本身格式错误，也不是云平台完全不可达。

## 根因判断

根因是 FAL 分区大小和外部 SMIF Flash 擦除粒度不匹配。

OpenOCD 烧录日志显示 M55 使用的外部 SMIF Flash 擦除扇区大小是：

```text
Erase sector size: 0x00040000 bytes
```

也就是 256KB。

而第一次加入的配置分区只有 4KB，且位于 Flash 末尾：

```text
wifi_cfg    4KB
xiaozhi_cfg 4KB
```

这种布局对运行时擦写有两个风险：

1. 分区小于硬件擦除扇区  
   FAL 逻辑以“分区”为单位管理，但底层 Flash 擦除以 256KB sector 为单位。4KB 分区无法独立擦除，底层实际需要处理它所在的整个 256KB sector。

2. 分区和其他数据共享同一个硬件擦除扇区  
   如果 4KB 配置区落在文件系统尾部同一个 256KB sector 内，擦除配置区时可能影响同 sector 内的其他内容，导致文件系统或配置日志状态异常。

所以 M55 在执行 `fal_partition_erase()` 或追加配置记录时，可能出现等待、失败、卡住或擦除邻近区域的风险。这个风险在“串口配置 WiFi/token、马上保存到 Flash”的流程里最容易暴露。

## 为什么改成 256KB

新的分区布局把 `wifi_cfg` 和 `xiaozhi_cfg` 各自放进独立的 256KB 擦除扇区：

```c
{FAL_PART_MAGIC_WORD, "filesystem",  NOR_FLASH_DEV_NAME, 0x100000, 512*1024, 0},
{FAL_PART_MAGIC_WORD, "wifi_cfg",    NOR_FLASH_DEV_NAME, 0x180000, 256*1024, 0},
{FAL_PART_MAGIC_WORD, "xiaozhi_cfg", NOR_FLASH_DEV_NAME, 0x1C0000, 256*1024, 0},
```

对应外部 Flash 地址：

```text
FAL base    = 0x60E00000
wifi_cfg    = 0x60F80000
xiaozhi_cfg = 0x60FC0000
```

这样做的好处：

1. 每个配置分区独占一个硬件擦除扇区。
2. `fal_partition_erase(part, 0, part->len)` 不会擦到文件系统或另一个配置区。
3. WiFi 配置和 token 配置可以安全追加日志记录。
4. 后续满日志时可以整分区擦除后重写，逻辑简单且可预测。

## 代码改动

涉及 M55 工程：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\libraries\Common\board\ports\fal\fal_cfg.h
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\applications\wifi_config_service.c
```

`fal_cfg.h` 的核心变化是：

```diff
- {FAL_PART_MAGIC_WORD, "filesystem", NOR_FLASH_DEV_NAME, 0x100000, 1024*1024, 0},
+ {FAL_PART_MAGIC_WORD, "filesystem",  NOR_FLASH_DEV_NAME, 0x100000, 512*1024, 0},
+ {FAL_PART_MAGIC_WORD, "wifi_cfg",    NOR_FLASH_DEV_NAME, 0x180000, 256*1024, 0},
+ {FAL_PART_MAGIC_WORD, "xiaozhi_cfg", NOR_FLASH_DEV_NAME, 0x1C0000, 256*1024, 0},
```

`wifi_config_service.c` 的核心变化是：当 WiFi 配置日志写满时，不再直接返回 `-RT_ENOSPC`，而是擦除整个 `wifi_cfg` 分区后从 offset 0 重写最新记录。

```c
if (write_offset == 0xFFFFFFFFU)
{
    rt_kprintf("[wifi_config] fal log full part=%s len=%lu\n",
               WIFI_CONFIG_FAL_PART,
               (unsigned long)part->len);
    if (fal_partition_erase(part, 0, part->len) < 0)
    {
        return -RT_ERROR;
    }
    write_offset = 0U;
}
```

## 调试验证步骤

### 1. 确认镜像不会覆盖配置区

烧录前检查 M55 `rtthread.hex` 地址范围。已验证应用镜像范围类似：

```text
0x60580400-0x607342CF
```

配置区在：

```text
wifi_cfg    0x60F80000
xiaozhi_cfg 0x60FC0000
```

两者不重叠。

### 2. 烧录 M55 新固件

烧录时关注 OpenOCD 输出中的 write/verify：

```text
wrote ... bytes
verified ... bytes
```

末尾如果出现 KitProg 退出阶段的 acquire 提示，需要结合前面的 write/verify 判断。只要写入和校验完成，应用镜像通常已经烧录成功。

### 3. 写入配置分区

可以通过两种方式配置：

1. 正常串口命令：`m55qa_wifi_*`、`m55qa_xz_token_*`。
2. 产测/恢复场景：生成配置 record 后用 OpenOCD 直接写入 `wifi_cfg` 和 `xiaozhi_cfg` 地址。

直接写入时必须保证不把真实 token、WiFi 密码提交进仓库，也不要写进文档。

### 4. 重启后检查状态

通过 M33 shell 执行：

```text
m55qa_status
```

成功标准：

```text
xz_token=1
token_len=439
wlan=1
ready=1
xz_ws=1
xz_stage=70
srv_hello>=1
```

如果刚重启后 WiFi 还没起来，可能先看到：

```text
wlan=0 ready=0 xz_ws=0
```

等待自动连接完成后再查一次。

## 经验结论

1. FAL 分区不能只按“数据大小”设计，还要按“Flash 擦除粒度”设计。
2. 对 SMIF Flash，当前板子的有效擦除粒度按 256KB 处理更安全。
3. 配置区、文件系统、资源区不要共享同一个硬件擦除扇区。
4. token 显示“未配置”时，不要只怀疑 token 内容，也要检查 token 是否真的持久化成功。
5. 串口命令配置 token 适合调试；量产或恢复场景更适合直接写入专用配置分区。

## 后续注意事项

后续如果继续增加 M55 本地持久化数据，建议遵守下面规则：

1. 新 FAL 分区起始地址按 `0x40000` 对齐。
2. 新 FAL 分区长度按 `0x40000` 的整数倍设置。
3. 不把高频写入数据放进同一个 sector，避免频繁擦除影响其他配置。
4. 每次改分区表后都重新确认：

```text
应用镜像范围
WHD 资源区
filesystem 范围
wifi_cfg 范围
xiaozhi_cfg 范围
```

5. 每次修复持久化问题后都做一次断电/重启验证，而不是只看当前 RAM 状态。

