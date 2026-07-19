# Edge AI 代码架构说明

这份文档专门解释当前 `applications/edge_ai/` 的分层。你后面要接的不只是 IMU，还会有肌电、电机电流、关节角度、力传感器，所以代码不能把“在线 AI”写死成“在线 IMU”。

先记住一句话：

```text
传感器数据是通用 signal window，模型只是消费这些 signal window 的 classifier。
```

## 1. 为什么要重新解耦

上一版已经可以跑通 IMU demo，但文件名和接口里出现了 `online_imu`。这在练手阶段没问题，但做外骨骼机械臂时会有问题：

- 肌电不是 IMU；
- 电机电流、编码器、关节角度也不是 IMU；
- 正式模型往往会融合多种数据，而不是只看一个传感器；
- 如果在线服务层写死 IMU，后续接 EMG 时就会到处改函数名和数据结构。

所以现在改成：

```text
M33/M55 数据通信层：只传 edge_ai_signal_window_t
在线推理服务层：只调用 edge_ai_classifier_t
具体模型适配层：决定自己需要哪些通道
```

## 2. 当前文件分层

```text
applications/edge_ai/
  edge_ai_status.h
    通用错误码。

  edge_ai_signal.*
    通用传感器窗口。支持 IMU、EMG、电机、关节等多种通道。

  edge_ai_transport.*
    通用 transport API。主接口是 signal window，保留 IMU 兼容包装。

  edge_ai_transport_sharedmem.*
    第一版共享内存 backend。共享内存里保存通道表和采样值矩阵。

  edge_ai_shared_contract.*
    M33/M55 共同使用的地址和角色契约。M33 producer 用 format，M55 consumer 用 attach。

  edge_ai_online_classifier.*
    通用在线分类服务。它不认识 IMU，也不认识肌电，只认识 classifier 回调。

  edge_ai_online_consumer.*
    纯 C 在线 consumer 状态机。负责等待共享块可用、attach、poll classifier，不依赖 RT-Thread。

  edge_ai_online_app.*
    RT-Thread 展示层。当前使用 IMU MLP classifier，打印 `[edge_ai_online]` 日志。

  edge_ai_imu_adapter.*
    IMU MLP 的输入适配器，从 signal window 里取 accel/gyro/temp。

  edge_ai_imu_mlp_classifier.*
    把当前 IMU MLP 包装成 edge_ai_classifier_t。

  edge_ai_imu_mlp.*
    纯 C IMU MLP 推理核心。

  edge_ai_exo_model.*
    第一版模拟外骨骼教学小模型。

  edge_ai_app.*
    RT-Thread 展示层，负责串口打印和周期调用 demo。
```

## 3. 通用 signal window 是什么

`edge_ai_signal_window_t` 可以理解成一个二维表：

```text
sequence = 12
sample_count = 8
channel_count = 4

channels:
  0: ACCEL_X_MG
  1: EMG_UV
  2: MOTOR_CURRENT_MA
  3: JOINT_ANGLE_DEG

samples:
  t0: [-26.0, 120.0, 450.0, 15.0]
  t1: [-26.2, 128.0, 460.0, 15.4]
  ...
```

也就是说，窗口不关心“我是不是 IMU 窗口”。它只说：这一帧里有几个采样点，每个采样点包含哪些通道。

当前已经定义的通道包括：

```text
ACCEL_X/Y/Z_MG
GYRO_X/Y/Z_MDPS
TEMPERATURE_C
EMG_UV
JOINT_ANGLE_DEG
JOINT_VELOCITY_DPS
LOAD_PERCENT
MOTOR_POSITION_DEG
MOTOR_VELOCITY_DPS
MOTOR_CURRENT_MA
```

后续如果你加新的传感器，比如力传感器、足底压力、编码器扭矩估计，只要在 `edge_ai_signal_id_t` 里加新的 channel id。

## 4. transport 不再绑定 IMU

新的主接口是：

```c
int edge_ai_transport_publish_signal_window(edge_ai_transport_t *transport,
                                            const edge_ai_signal_window_t *window);

int edge_ai_transport_try_read_signal_window(edge_ai_transport_t *transport,
                                             edge_ai_signal_window_t *window);

int edge_ai_transport_ack_signal_window(edge_ai_transport_t *transport,
                                        uint32_t sequence);
```

为了不破坏前面已经跑通的 IMU demo，当前仍然保留：

```c
edge_ai_transport_publish_imu_window()
edge_ai_transport_try_read_imu_window()
edge_ai_transport_ack_imu_window()
```

这三个函数只是兼容包装。后续新代码优先使用 `signal_window` 接口。

## 5. 在线推理服务不再绑定 IMU

新的在线服务入口是：

```c
int edge_ai_online_classifier_process_once(edge_ai_transport_t *transport,
                                           const edge_ai_classifier_t *classifier,
                                           edge_ai_online_classifier_result_t *result);
```

它内部只做四件事：

```text
try_read_signal_window
classifier->predict
ack_signal_window
返回分类结果
```

它不知道当前 classifier 是 IMU MLP、EMG 分类器，还是未来的多模态外骨骼模型。

## 6. 以后怎么接肌电和电机数据

第一步不是改在线服务，而是增加新的 classifier adapter。例如：

```text
edge_ai_exo_fusion_classifier.*
```

它从 `edge_ai_signal_window_t` 里取自己需要的通道：

```text
EMG_UV
JOINT_ANGLE_DEG
JOINT_VELOCITY_DPS
MOTOR_CURRENT_MA
```

然后把这些通道整理成模型输入，调用 TFLM / MTB ML / 手写 C 模型。这样 transport、sharedmem、online_classifier 都不用跟着改。

## 7. 当前验证

新增主机测试：

```powershell
gcc -std=c99 -Wall -Wextra -Iapplications tests/edge_ai_signal_test.c applications/edge_ai/edge_ai_signal.c applications/edge_ai/edge_ai_transport.c -o build/edge_ai_signal_test.exe
.\build\edge_ai_signal_test.exe

gcc -std=c99 -Wall -Wextra -Iapplications tests/edge_ai_online_classifier_test.c applications/edge_ai/edge_ai_online_classifier.c applications/edge_ai/edge_ai_signal.c applications/edge_ai/edge_ai_transport.c applications/edge_ai/edge_ai_transport_sharedmem.c -o build/edge_ai_online_classifier_test.exe
.\build\edge_ai_online_classifier_test.exe
```

期望输出：

```text
PASS edge_ai signal window
PASS edge_ai online classifier
```

固件侧也要跑 SCons，确认通用层可以被 ARM GCC 编译。

## 8. M33/M55 共享契约

当前默认共享块地址：

```text
0x261C0000
```

这个地址来自当前 BSP linker：

```text
M33: .cy_shared_socmem -> m33_m55_shared ORIGIN 0x261C0000
M55: m33_m55_shared ORIGIN 0x261C0000, 当前作为 reserved SOC memory
```

建议角色分工：

```text
M33 LSM6DS3/EMG/Motor producer:
  edge_ai_shared_contract_bind_producer()
  edge_ai_transport_publish_signal_window()

M55 AI consumer:
  edge_ai_shared_contract_bind_consumer()
  edge_ai_online_classifier_process_once()
```

注意：consumer 不能 format 共享块，只能 attach。否则 M55 可能把 M33 已经写好的窗口清空。

当前 M55 demo 已经接入 `edge_ai_online_app_run_once()`。如果 M33 还没有接入 producer，串口会偶尔看到：

```text
[edge_ai_online] waiting producer status=-4 attached=0 addr=0x261c0000
```

这不是错误，只表示共享块里还没有合法的 `magic/version`。等 M33 producer 调用 format 后，M55 会自动 attach；等 M33 publish 窗口后，M55 会输出：

```text
[edge_ai_online] seq=1 classifier=imu_mlp label=idle score=...
```
