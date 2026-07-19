# EMG 三分类模型与 NanoPi 上报切换说明

## 1. 修改原因

旧 M55 EMG intent 模型输出四类：

```text
0 = elbow_extend
1 = elbow_flex
2 = rest
3 = shoulder_flex
```

2026-07-19 同步到实际 M55 工程的新模型输出三类：

```text
0 = elbow_curl
1 = rest
2 = shoulder_flex
```

旧 NanoPi 只读上报代理把 `result_code` 按四分类表翻译成字符串。若只更换 M55 固件而不更新 NanoPi，会出现数值传输正常但动作名称错误的问题：

| 新 M55 输出 | 旧 NanoPi 错误解释 |
|---|---|
| `0 elbow_curl` | `elbow_extend` |
| `1 rest` | `elbow_flex` |
| `2 shoulder_flex` | `rest` |

## 2. 协议边界

M55 通过 M33/M55 IPC 返回：

```text
model_code
result_code
confidence
result_flags
```

M33 将结果封装到 CAN 标准帧 `0x323`：

| 字节 | 含义 |
|---|---|
| `0` | 固定标记 `0xB5` |
| `1` | 序号 |
| `2` | `model_code`，EMG intent 为 `2` |
| `3` | `result_code` |
| `4` | 置信度，单位为百分之一 |
| `5` | 状态标志 |
| `6` | 窗口长度，单位为 10 ms |
| `7` | 保留 |

IPC 和 CAN 只传递分类编号，不固定类别总数，所以 M33 帧格式无需因四类改三类而调整。当前协议也没有携带模型版本或标签表版本，因此新旧模型不能在同一 NanoPi 解码配置下安全混用。

云端 `predicted_action` 使用字符串存储，不限制为四分类枚举，不需要数据库迁移。平台训练计划中的 `elbow_flexion` 是训练动作类型，不是 M55 分类编号，不能批量替换为 `elbow_curl`。

## 3. 已完成修改

独立 M55 工程：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED
commit 2de409eb fix(emg): 同步三分类意图模型
```

修改内容：

- 特征数从 `20` 改为 `21`。
- 类别数从 `4` 改为 `3`。
- 标签改为 `elbow_curl / rest / shoulder_flex`。
- `rest` 索引从 `2` 改为 `1`。
- 同步 int8 模型、golden samples、量化参数和日志输出长度。

NanoPi/平台工程：

```text
F:\RT-ThreadStudio\workspace\ai-
commit 2e7db43 fix(nanopi): 对齐三分类意图标签
```

修改内容：

- `0 -> elbow_curl`
- `1 -> rest`
- `2 -> shoulder_flex`
- 删除旧的 `3 -> shoulder_flex` 映射。
- 更新 NanoPi 解码合同测试和硬件清单标签表。

## 4. 验证记录

M55 相关合同测试：

```text
Ran 15 tests
OK
```

M55 使用 STM32CubeCLT GCC 完整编译通过，生成：

```text
F:\RT-ThreadStudio\workspace\Edgi_Talk_M55_Blink_LED\rtthread.hex
```

编译后的 ELF 已确认：

```text
日志输出为 out=[%d,%d,%d]
包含 elbow_curl / shoulder_flex
不包含旧 elbow_extend / elbow_flex 标签
```

NanoPi 相关测试：

```text
9 passed, 1 skipped
```

M55 全量工具测试另有两个与本次修改无关的既有失败：仓库缺少 `applications/edge_ai_bridge/edge_ai_result_contract.h`。三分类相关测试和固件编译均不依赖该缺失文件。

## 5. 实机切换顺序

由于 `0x323` 暂无标签表版本字段，必须按以下顺序切换：

1. 停止 NanoPi 只读上报代理，避免切换窗口产生错标签数据。
2. 烧录新 M55 `rtthread.hex`。
3. 在 M55 Shell 执行 `intent_tflm_smoke -v`，确认三分类 golden samples 全部通过。
4. 更新 NanoPi 上的 `nanopi-rehab-arm-readonly-agent.py`。
5. 重启 NanoPi 上报代理。
6. 抓取 CAN `0x323`，同时核对 NanoPi JSON 和云端页面标签。

建议至少验证三种结果：

```text
result_code=0 -> elbow_curl
result_code=1 -> rest
result_code=2 -> shoulder_flex
```

若 M55 尚未烧录新固件，不得提前部署新的 NanoPi 标签表；若 NanoPi 已更新，也不得继续运行旧四分类 M55 固件。

## 6. 后续协议改进

下一版协议建议使用当前保留字节 `payload[7]` 携带 `label_map_version`，或者为三分类模型分配新的 `model_code`。在版本字段落地前，固件和 NanoPi 只能作为一个发布单元同步切换。

