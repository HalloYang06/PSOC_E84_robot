# Changelog

## 2026-06-08 M55 LVGL AI 状态屏接入

### Added

- 新增 `edge_ai_ui_state.*`，由 AI 在线展示层发布“最后一次推理结果/等待状态”快照，保持为纯 C，不依赖 RT-Thread 或 LVGL。
- 新增 `applications/ui/edge_ai_lvgl_app.c`，只在 `BSP_USING_LVGL` 打开时编译；UI 层独立于 `applications/edge_ai/`，只读取快照并刷新屏幕，不直接调用模型或 transport。
- 新增 `tests/edge_ai_ui_state_test.c`，用主机测试验证 UI 快照默认值、在线结果和等待状态更新。

### Changed

- `.config` 和 `rtconfig.h` 打开 LCD、触摸、软件 I2C1、LVGL 相关宏；`libraries/components/SConscript` 接入 BSP 自带 `lvgl_9.2.0`，`applications/ui/SConscript` 独立接入 UI 应用层。
- `edge_ai_online_app.c` 在串口日志之外同步更新 UI 快照，实现 Edgi-AI 与 UI 解耦。
- LVGL RT-Thread port 补齐 include path；显示链路按 baremetal GFXSS 编译，避免误包含 FreeRTOS 头文件。
- ST7102 触摸初始化改为可跳过：如果板上触摸 I2C 未就绪，只打印提示并保留屏幕显示，不让系统 assert。

### Verification

- `edge_ai_ui_state_test` 通过。
- `edge_ai_model_test` 通过。
- M55 SCons 固件构建通过，生成 `rtthread.hex`，最终 size 为 `text=530476 data=2840 bss=4393500`。
- 尚未进行烧录后的屏幕和触摸实测，本次属于 compile-only verification。

## 2026-06-07 双核在线 IMU 链路板端验证

### Changed

- M33 LSM6DS3 工程中将 `lsm6ds3tr_c_read_data_sample()` 从 `INIT_APP_EXPORT` 直接永久循环，改为由 `INIT_APP_EXPORT` 创建 `lsm6ds3` 采集线程后返回，避免阻塞 M33 `main()` 和 CM55 启动链路。
- M33 LSM6DS3 工程中将 UART driver 的控制台打开失败从 `RT_ASSERT` 改为返回 `-RT_ERROR`，用于双核运行时避免 M33/M55 抢同一个 KitProg3 USB-UART 导致 M33 assert 死机。
- M55 工程文档补充本次真实烧录和串口验证结果。
- 新增 `docs/online-imu-board-verification.md`，记录本次烧录命令、失败原因、M33 修正点和最终通过日志。

### Verification

- M33 SCons 构建通过，Edge Protect 生成 `build/rtthread.hex`，size 为 `text=81764 data=1344 bss=257253`。
- M33 OpenOCD 烧录成功，必须带 `PSE84_SMIF.FLM`，实际写入 `188416 bytes`。
- M55 OpenOCD 烧录成功，必须带 `PSE84_SMIF.FLM`，实际写入 `65536 bytes`。
- COM16 / 115200 串口抓到 M55 在线消费 M33 共享内存数据：`[edge_ai_online] seq=2 classifier=imu_mlp label=tilt_left score=51002 channels=7`。
- 后续持续出现 `seq=3` 到 `seq=13`，说明 M33 producer 正在持续发布 7 通道 IMU 窗口，M55 consumer 能读取、分类并 ack。

### Notes

- 双核在线链路中建议让 M55 作为唯一串口日志核；M33 作为数据 producer，可以不依赖串口输出。
- 如果 OpenOCD 只配置 `PSE84_RRAM_NVM.FLM`，烧录 `0x6034...` 或 `0x6058...` 地址会出现 `no flash bank found` 或写入 `0 bytes`，必须加载 `PSE84_SMIF.FLM`。

## 2026-06-07 M33 LSM6DS3 Producer 接入

### Added

- 在 M33 LSM6DS3 工程新增 `applications/edge_ai/`，同步 M55 的通用 signal/transport/shared_contract 文件。
- 在 M33 LSM6DS3 工程新增 `edge_ai_m33_producer.*`，每累计 8 个 IMU 样本发布一个 `edge_ai_signal_window_t`。
- 新增 `docs/m33-producer-implementation-log.md`，记录 M33 实际修改文件、窗口格式、构建结果和后续烧录验证方法。

### Changed

- M33 `packages/lsm6ds3tr/SConscript` 增加 `applications/edge_ai` include path。
- M33 `packages/lsm6ds3tr/lsm6ds3tr-c_port.c` 在保留原有 IMU 串口打印的同时，把 accel/gyro/temp 样本推入 producer。

### Verification

- M33 SCons 构建通过，Edge Protect 成功生成 `build/rtthread.hex`，size 为 `text=81500 data=1344 bss=257253`。
- M55 SCons 构建通过，确认 consumer 侧 ABI 同步。

### Notes

- M33 工程当前不是 git 仓库，本次 M33 代码改动未能在 M33 工程内 git commit；M55 工程文档记录了 M33 修改清单。

## 2026-06-07 Shared Contract for M33/M55

### Added

- 新增 `applications/edge_ai/edge_ai_shared_contract.*`，集中定义 M33/M55 共享信号窗口的默认地址、大小和绑定入口。
- 新增 `applications/edge_ai/edge_ai_online_consumer.*`，提供纯 C 在线 consumer 状态机：M33 未初始化时返回等待状态，M33 format 后自动 attach 并推理。
- 新增 `applications/edge_ai/edge_ai_online_app.*`，把 M55 在线 consumer 接入当前 RT-Thread demo，串口前缀为 `[edge_ai_online]`。
- 新增 `tests/edge_ai_shared_contract_test.c`，验证 consumer attach 不会清空 producer 已发布的数据。
- 新增 `tests/edge_ai_online_consumer_test.c`，验证 consumer 可以先等待 producer，随后自动 attach、推理并 ack。

### Changed

- `edge_ai_transport_sharedmem.*` 拆分 `format` 和 `attach`：
  - producer 使用 `edge_ai_transport_sharedmem_format()` 初始化共享块；
  - consumer 使用 `edge_ai_transport_sharedmem_attach()` 挂接已有共享块，不清空数据；
  - 旧的 `edge_ai_transport_sharedmem_init()` 保留为 `format` 的兼容包装。

### Notes

- 默认共享块地址定义为 `0x261C0000`，对应 BSP linker 里的 `m33_m55_shared` / `.cy_shared_socmem` 区域。
- 后续 M33 LSM6DS3 工程接入时，M33 应作为 producer，M55 应作为 consumer。

### Verification

- `edge_ai_shared_contract_test` 通过。
- `edge_ai_online_consumer_test` 通过。
- M55 SCons 固件构建通过，`text=63068 data=1068 bss=1709964`。

## 2026-06-07 Edge AI 架构解耦

### Added

- 新增 `applications/edge_ai/edge_ai_status.h`，把通用错误码从 transport 里拆出来。
- 新增 `applications/edge_ai/edge_ai_signal.*`，定义通用 `edge_ai_signal_window_t`，支持 IMU、EMG、电机、关节等多种通道。
- 新增 `applications/edge_ai/edge_ai_online_classifier.*`，替代上一版 `edge_ai_online_imu.*`，在线服务只依赖 transport 和 classifier 回调，不再绑定 IMU。
- 新增 `applications/edge_ai/edge_ai_imu_mlp_classifier.*`，把当前 IMU MLP 包装成一个普通 `edge_ai_classifier_t`。
- 新增 `docs/edge-ai-architecture.md`，解释新的端侧 AI 分层、数据流和后续接肌电/电机数据的方法。
- 新增 `tests/edge_ai_signal_test.c` 和 `tests/edge_ai_online_classifier_test.c`。

### Changed

- `edge_ai_transport.*` 主接口从 IMU window 泛化为 signal window，同时保留 IMU 兼容包装，避免前面已经跑通的 IMU demo 断掉。
- `edge_ai_transport_sharedmem.*` 共享内存 ABI 升级为版本 2，保存通道表和采样矩阵，而不是写死 `edge_ai_imu_sample_t`。
- `edge_ai_imu_adapter.*` 改为从通用 signal window 中按通道取 IMU MLP 需要的 accel/gyro/temp。
- 删除 `edge_ai_online_imu.*` 和对应测试，避免在线推理服务层的文件名和职责绑定到 IMU。

### Verification

- `edge_ai_signal_test` 通过，验证 signal window 能承载 EMG、电机电流、IMU 通道。
- `edge_ai_online_classifier_test` 通过，验证在线分类服务可以运行非 IMU classifier。
- `edge_ai_transport_test`、`edge_ai_imu_adapter_test`、`imu_mlp_inference_test`、`edge_ai_layout_test` 均通过。
- M55 SCons 固件构建通过，`text=59060 data=1068 bss=1709908`。

## 2026-06-07 Edge AI Online IMU Service

### Added

- 新增 `applications/edge_ai/edge_ai_online_imu.*`，把“读取 IMU window、转换模型输入、运行 MLP、ack 已消费窗口”封装成一个不依赖 RT-Thread 的核心服务。
- 新增 `tests/edge_ai_online_imu_test.c`，用 shared-memory backend 在主机侧模拟 M33/M55 数据流，验证在线推理服务可以读到窗口并输出 `idle` 分类。

### Why

- 后续真正接 M33/M55 共享内存时，M55 业务层只需要周期调用 `edge_ai_online_imu_process_once()`，不用在应用代码里散落 `try_read`、adapter、predict、ack 这些步骤。
- 这个服务层未来也方便替换模型内部实现：当前是手写 MLP，后续可以替换成 TFLM 或 Infineon MTB ML，但 transport API 不需要跟着大改。

### Verification

- `edge_ai_online_imu_test` 通过，覆盖空窗口、发布窗口、推理、ack 后变空等路径。

## 2026-06-07 Edge AI 目录架构整理

### Changed

- 将 M55 AI demo 代码从旧的 `applications/edge_ai_demo/` 迁移到 `applications/edge_ai/`，后续所有端侧 AI 代码都优先放在这个目录下。
- 将 RT-Thread 展示层命名为 `edge_ai_app.*`，`applications/main.c` 只保留 LED 心跳和周期调用。
- 将外骨骼教学小模型命名为 `edge_ai_exo_model.*`，避免和后续正式模型、IMU 模型混在一起。
- 将 IMU MLP 推理核心命名为 `edge_ai_imu_mlp.*`，将固定窗口串口 demo 命名为 `edge_ai_imu_mlp_demo.*`。
- 将训练脚本导出的模型头文件目标路径更新为 `applications/edge_ai/edge_ai_imu_mlp_model.h`。
- 新增 `docs/next-step-online-imu-pipeline.md`，说明下一步 M33 采集 IMU、M55 在线推理的推荐链路和模块边界。

### Verification

- 新增并通过 `tests/edge_ai_layout_test.c`，验证新的 `edge_ai/...` 公共头文件路径和模型接口。
- 主机侧 `tests/edge_ai_model_test.c` 通过。
- 主机侧 `tests/imu_mlp_inference_test.c` 通过。
- M55 SCons 固件构建通过，生成新的 `rt-thread.elf` 和 `rtthread.hex`。
- M55 重构后固件已重新烧录，OpenOCD 显示写入 `61440 bytes`；本次串口复核时 `COM16` 被其他程序占用，未重新抓取日志。

## 2026-06-07 Edge AI Transport API

### Added

- 新增 `applications/edge_ai/edge_ai_transport.*`，定义可移植 IMU window transport API 和错误码。
- 新增 `applications/edge_ai/edge_ai_transport_sharedmem.*`，实现第一版共享内存 backend。
- 新增 `applications/edge_ai/edge_ai_imu_adapter.*`，把 transport 层 `edge_ai_imu_window_t` 转成当前 MLP 模型使用的 `imu_mlp_sample_t[]`。
- 新增 `docs/edge-ai-transport-api.md`，讲解 M33/M55 共享内存/IPC 的 API 边界、数据结构和后续接板步骤。
- 新增 `tests/edge_ai_transport_test.c` 和 `tests/edge_ai_imu_adapter_test.c`。

### Verification

- `edge_ai_transport_test` 通过。
- `edge_ai_imu_adapter_test` 通过。
- `edge_ai_layout_test` 通过。
- `imu_mlp_inference_test` 通过。
- M55 SCons 固件构建通过。

## 2026-06-07 双核烧录与板端验证补充

### Added

- 新增 `docs/m33-m55-bringup-log.md`，记录 M33 LSM6DS3 + M55 IMU MLP 双核烧录、Edge Protect 后处理、串口验证和问题分析。

### Verification

- M33 LSM6DS3 工程命令行构建通过，并确认 Edge Protect 后处理将 `0x08340400` relocation 到 `0x60340400`，输出 `build/rtthread.hex`。
- M33 固件烧录成功，OpenOCD 显示写入 `184320 bytes`。
- M55 AI 工程构建通过，M55 固件烧录成功，OpenOCD 显示写入 `61440 bytes`。
- 串口 `COM16 / 115200` 已抓到 M55 `[edge_ai]` 和 `[imu_mlp]` 日志，`idle / shake / tilt_left / tilt_right` 四类 IMU MLP 板端推理均匹配 expected 标签。

## 2026-06-07

### Added

- 新增 `tools/serial_csv_logger.py`，用于把 M33 LSM6DS3 例程的串口输出保存成带标签 CSV。
- 新增 `tools/train_imu_classifier.py`，读取 IMU CSV，按窗口提特征，训练最近质心分类器，并导出 C 模型参数头文件。
- 新增 `docs/sensor-data-capture-guide.md`，说明 M33 IMU 采集、PC 标注保存、训练和 M55 部署的练习链路。
- 新增 `docs/imu-training-guide.md`，解释第一轮 Python 训练流程、窗口特征、训练报告和后续 M55 部署方式。
- 新增 `docs/embedded-edge-ai-career-roadmap.md`，从大模型基础、端侧 AI 工程链路、嵌入式知识体系、技术栈和企业招聘需求角度梳理学习路线。
- 新增 `tests/test_imu_training.py`，验证训练脚本可以读取 CSV、训练预测并导出 C 模型。
- 新增 `applications/edge_ai/edge_ai_imu_mlp.*`，在 M55/主机侧复现 Python MLP 的 18 特征提取和前向推理。
- 新增 `applications/edge_ai/edge_ai_imu_mlp_demo.*`，在 M55 串口周期输出固定 IMU 窗口的推理结果。
- 新增 `tests/imu_mlp_inference_test.c`，验证 C 端 MLP 推理可识别 `idle / shake / tilt_left / tilt_right`。
- 新增 `docs/imu-mlp-m55-deploy-guide.md`，记录 IMU MLP 模型接入 M55、构建、烧录和日志验证方法。

### Notes

- 下一阶段推荐先用 IMU 跑通数据闭环，再迁移到肌电。
- 当前采集脚本兼容 M33 LSM6DS3 例程的三行文本输出，也兼容后续一行 `IMU_CSV,...` 输出。
- 当前真实数据训练结果：476 个采样点、104 个窗口、4 个标签；MLP 测试集准确率 1.000，最近质心测试集准确率 0.920。该结果只用于验证流程，不作为正式模型指标。
- M55 固件已接入离线 IMU MLP 推理 demo，当前仍未在线访问 IMU，避免 M33/M55 同时抢 I2C。

## 2026-06-04

### Added

- 新增 `AGENTS.md`，记录本工程 AI demo 的维护规则、文档规则和验证规则。
- 新增 Git 管理配置：`.gitignore` 排除编译产物、工具发布包和生成文档，`.gitattributes` 固定源码行尾和二进制文件类型。
- 新增 `applications/edge_ai/` 模块：
  - `edge_ai_exo_model.*`：纯 C int8 小模型推理核心。
  - `edge_ai_app.*`：RT-Thread 串口 demo 展示层。
  - `SConscript`：让 RT-Thread/SCons 自动编译该子目录。
- 新增 `tests/edge_ai_model_test.c`，在 PC 上验证四类模拟外骨骼特征分类。
- 新增 `docs/edge-ai-demo-guide.md`，从零解释端侧 AI demo 的原理、构建、烧录和后续演进。
- 新增 `docs/board-notes.md`，整理 Edgi-Talk PDF 资料里和 AI 部署相关的板级信息。

### Changed

- `applications/main.c` 从单纯 LED 闪烁扩展为 LED 心跳 + 周期性 AI 推理输出。
- `rtconfig.py` 的 GCC `DEVICE` 编译参数从 `cortex-m7` 校正为 `cortex-m55`，默认工具链路径指向 RT-Thread Studio 自带 GCC 13.3。
- `rtconfig.py` 的 RT-Thread `CPU` 选择保留为 `cortex-m7`，因为当前 RT-Thread 树没有 `libcpu/arm/cortex-m55`，仍需使用 BSP 原有上下文切换和中断桩代码。
- `libraries/components/Infineon_cmsis-latest/SConscript` 增加 CMSIS-NN/DSP include path，并纳入最小 CMSIS-NN 源码集合。
- RT-Thread Studio Debug 配置排除 `tests` 目录，并给主机侧 `edge_ai_model_test.c` 增加 ARM 工具链防护，避免它被当作固件源码编译。
- `applications/main.c` 改用 `edge_ai/edge_ai_app.h` 子目录 include 路径，匹配 RT-Thread Studio 生成的 `applications` include path。
- RT-Thread Studio Debug 配置和当前生成的 Debug makefile 统一使用 Cortex-M55 编译/链接参数，修复 `ns_start_pse84.c` 中 `__set_MSPLIM` 链接未定义问题。
- RT-Thread Studio C/C++/Assembler `Other flags` 显式加入 Cortex-M55 参数，防止重新生成 makefile 后源码或汇编文件丢失 `-mcpu=cortex-m55` 并触发 CMSIS/汇编目标不匹配问题。

### Verification

- 主机测试通过：
  - 命令：`gcc -std=c99 -Wall -Wextra -Iapplications/edge_ai tests/edge_ai_model_test.c applications/edge_ai/edge_ai_exo_model.c -o build/edge_ai_model_test.exe`
  - 结果：`idle / assist / resist / unsafe` 四组样例全部 PASS。
- SCons 固件构建通过：
  - 命令：`F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe -j4`
  - 结果：生成 `rt-thread.elf` 和 `rtthread.hex`，size 输出 `text=54860 data=1068 bss=1709900`。
- 硬件串口与 LED 验证尚未执行；当前状态为 compile-only verification。烧录后需要确认串口有 `[edge_ai]` 输出，绿灯保持心跳。
