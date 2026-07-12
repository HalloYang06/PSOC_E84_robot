# Motor 控制层开发文档（含 API 与开发日志）

## 1. 文档目标

这份文档面向两类读者：

1. 想快速联调的开发者：看完即可知道怎么发命令、怎么看反馈。
2. 想学习架构思路的同学：看完能理解为什么这样分层、如何扩展到更多电机。

本次文档对应代码：

- `applications/control/control_layer.c`
- `applications/control/control_layer.h`
- `applications/control/control_layer_cfg.h`
- `libraries/HAL_Drivers/drv_can.c`
- `libraries/HAL_Drivers/CAN_config.h`

---

## 2. 总体架构（与集成方案一致）

当前控制层在 PSoC 上实现 3 条链路：

1. `can_rx_task`：接收 CAN 帧并分发解析
2. `ros_command_task`：接收 ROS 指令并执行控制动作
3. `motor protocol`：电机私有协议封装（兼容当前电机）

逻辑上对应方案文档中的职责：

- NanoPi ROS -> 发指令
- PSoC -> 实时执行 + 状态聚合
- CAN 总线 -> Classic CAN 1Mbps

---

## 3. CAN 与协议约定

### 3.1 Classic CAN 约束

本工程默认强制 Classic CAN：

- 发送侧禁用 FD/BRS
- RT-Thread CAN 配置默认 `enable_canfd = 0`（驱动层）
- 底层 CANFD 外设以 Classic 模式运行

### 3.2 电机协议（当前实现）

当前电机控制仍使用扩展帧私有协议（便于快速落地），接口命名统一为 `motor`。

### 3.3 ROS 命令帧（标准帧）

- CAN ID：`CONTROL_CAN_ID_ROS_COMMAND`（默认 `0x320`）
- Byte0：命令码
- Byte1：`joint_id`
- Byte2~7：命令参数

命令码定义：

- `0x01`：使能
- `0x02`：停止（Byte2=`clear_fault`）
- `0x03`：设目标（Byte2~3 pos_0.1deg，Byte4~5 vel_rpm，Byte6~7 torque_mA）
- `0x04`：设模式（Byte2=`mode`）
- `0x05`：设零位
- `0x06`：主动上报开关（Byte2=0/1）

---

## 4. API 文档

### 4.1 初始化与基础

- `int control_layer_init(const char *can_name);`
说明：初始化 CAN、RX 线程、ROS 命令队列和命令线程。

### 4.2 电机控制 API（推荐新接口）

- `rt_err_t control_motor_enable(rt_uint8_t joint_id);`
- `rt_err_t control_motor_stop(rt_uint8_t joint_id, rt_bool_t clear_fault);`
- `rt_err_t control_motor_set_zero(rt_uint8_t joint_id);`
- `rt_err_t control_motor_set_run_mode(rt_uint8_t joint_id, control_motor_run_mode_t mode);`
- `rt_err_t control_motor_private_control(rt_uint8_t joint_id, float p, float v, float kp, float kd, float t);`
- `rt_err_t control_motor_set_active_report(rt_uint8_t joint_id, rt_bool_t enable);`
- `rt_err_t control_get_motor_feedback(rt_uint8_t joint_id, control_motor_feedback_t *out);`

### 4.3 ROS 命令观测 API

- `rt_err_t control_get_last_ros_command(control_ros_command_t *out);`
说明：获取最近一次已解析的 ROS 命令（便于调试）。

### 4.4 兼容 API（旧接口保留）

为了不影响旧代码，仍保留兼容别名：

- `control_rs00_*` -> 自动映射到 `control_motor_*`
- `control_get_rs00_feedback` -> 映射到 `control_get_motor_feedback`

建议新开发统一使用 `control_motor_*` 命名。

### 4.5 传感器 API（保留）

- `rt_err_t control_sensor_report_enable(rt_bool_t enable, rt_uint16_t period_ms);`
- `rt_err_t control_get_emg_report(control_emg_report_t *out);`
- `rt_err_t control_get_heart_report(control_heart_report_t *out);`

---

## 5. 关键配置项（`control_layer_cfg.h`）

推荐先看这几个宏：

- `CONTROL_MOTOR_JOINT_COUNT`（默认 5）
- `CONTROL_MOTOR_JOINT1_ID` ~ `CONTROL_MOTOR_JOINT5_ID`（默认 0x01~0x05）
- `CONTROL_CAN_ID_ROS_COMMAND`（默认 0x320）
- `CONTROL_CAN_CLASSIC_ONLY`（默认 1）
- `CONTROL_CAN_DEV_DEFAULT`（默认 `can0`）

---

## 6. MSH 调试命令

新命令：

- `control_init [can_dev]`
- `motor_en <joint>`
- `motor_stop <joint> [clear_fault]`
- `motor_ctrl <joint> <pos_rad> <vel_rad_s> <kp> <kd> <torque_nm>`
- `motor_mode <joint> <mode>`
- `motor_fb <joint>`
- `ros_last`
- `sensor_rate <en> <period_ms>`
- `sensor_show`

兼容旧命令仍可用（`rs00_*`），但建议迁移到 `motor_*`。

---

## 7. 学习者提示

如果你第一次接触这套代码，建议按顺序看：

1. 先看 `control_layer_cfg.h`，明白 ID 和范围参数
2. 再看 `control_layer.h`，把 API 视为“控制台”
3. 最后看 `control_layer.c`，理解线程与协议解析细节

调试时建议先打通 `motor_en -> motor_ctrl -> motor_fb`，再接入 ROS 命令帧。

---

## 8. 开发日志

### 2026-03-29（本次重构）

1. 将控制 API 命名从 `rs00` 统一重构为 `motor`
2. 保留 `rs00` 兼容别名，避免旧业务代码立即失效
3. 将关节映射扩展为 5 电机默认配置（0x01~0x05）
4. 新增 ROS 指令接收链路：
   - CAN 收包解析 ROS 命令
   - 消息队列缓存
   - `ros_command_task` 执行
5. 增加 `control_get_last_ros_command` 用于联调可观测性
6. 英飞凌 CAN 驱动改为 Classic CAN 默认策略（禁用 FD/BRS）
7. 修复 CAN 默认配置依赖问题（无 Configurator 生成也可编译）
8. 在 `main.c` 增加控制层初始化入口（启用 CAN 时自动初始化）

---

## 9. 后续建议

1. 把 ROS 命令帧升级为真正 CANopen RPDO 输入（进一步标准化）
2. 增加限幅/斜坡/互锁安全状态机（`safety_task` 细化）
3. 增加总线超时看门狗（命令超时自动停机）
4. 为关键 API 补单元测试或联调脚本
