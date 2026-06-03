# 康复外骨骼机械臂关节与电机映射草案

本文记录 `medical_arm.zip` 导出的 6 关节 URDF、当前用户确认的电机对应关系、传动比缺口和 AI 后续必须遵守的边界。它是 MuJoCo/MJCF、NanoPi/M33 映射、服务器/VLA 输入输出 schema 的当前草案来源。

## 当前 URDF 关节顺序

| 序号 | URDF joint | 人体/机构自由度初步解释 | 保守初始 ROM | 备注 |
|---|---|---|---|---|
| 0 | `jian_hengxiang_joint` | 肩横向，肩外展/内收或水平摆动 | `-45° .. +90°` | 已知由 `node_id=3` 经 `1:2` 传动带动 |
| 1 | `jian_zongxiang_joint` | 肩纵向，肩屈伸/抬举 | `-30° .. +100°` | 已知由 `motor_id=4` 经若干齿轮联动，齿轮比待补 |
| 2 | `jian_xuanzhuan_joint` | 肩/上臂轴向旋转 | `-60° .. +60°` | 已知由 `motor_id=6` 带动 |
| 3 | `zhou_zongxiang_joint` | 肘纵向屈伸 | `0° .. +135°` | 已知由 `motor_id=5` 带动 |
| 4 | `wanbu_zongxiang_joint` | 腕部纵向屈伸/俯仰 | `-45° .. +45°` | 已知由 4015 小电机 `motor_id=1/2` 之一带动，具体交叉关系待确认 |
| 5 | `wanbu_hengxiang_joint` | 腕部横向偏摆/桡尺偏 | `-20° .. +30°` | 已知由 4015 小电机 `motor_id=1/2` 之一带动，具体交叉关系待确认 |

这些 ROM 是根据网页可视化和康复外骨骼保守安全初值给出的工程草案，不是临床处方。正式穿戴必须再叠加患者 profile、机械硬限位、软限位、速度/力矩/电流限制和医生/康复师确认。

## 当前电机对应关系

| 电机/节点 | 当前角色 | 关联 URDF joint | 已知传动 | 状态 |
|---|---|---|---|---|
| `motor_id=1` | 后加 4015 腕部小电机 | `wanbu_zongxiang_joint` 或 `wanbu_hengxiang_joint` | 待确认 | 已知属于腕部，未确认具体轴 |
| `motor_id=2` | 后加 4015 腕部小电机 | `wanbu_zongxiang_joint` 或 `wanbu_hengxiang_joint` | 待确认 | 已知属于腕部，未确认具体轴 |
| `node_id=3` | 肩横向电机 | `jian_hengxiang_joint` | 电机轮:轴轮 = `1:2`，输出约为电机角的 `0.5`，方向/零点待标定 | 已确认关联，未完成安全标定 |
| `motor_id=4` | 肩纵向电机 | `jian_zongxiang_joint` | 多级齿轮，齿轮比待实测 | 已确认关联，未完成安全标定 |
| `motor_id=5` | 肘纵向电机 | `zhou_zongxiang_joint` | 待确认 | 已确认关联，未完成安全标定 |
| `motor_id=6` | 肩/上臂旋转电机 | `jian_xuanzhuan_joint` | 待确认 | 已确认关联，未完成安全标定 |
| `motor_id=7` | 外部调试电机 | 不属于当前机械臂 | 不适用 | 不参与机械臂/VLA/MuJoCo 正式映射 |

注意：`motor_id` 不是 `joint`。M33/NanoPi/服务器/VLA/MuJoCo 必须用输出端 joint 状态作为运动语义，原始电机轴角只作为诊断和标定输入。

## 旧 5 关节台架主线与新 6 关节 medical_arm 的区别

仓库里仍保留早期 ROS/MuJoCo/M33 5 关节台架表，用于 `bench-debug`、`dry-run` 和历史数据工具：

| legacy ROS joint | joint_id | 电机 | 型号/协议 | 与当前 6 关节实物关系 |
|---|---:|---|---|---|
| `shoulder_lift_joint` | 0 | `node_id=3` | 伺泰威 CANSimple/ODrive-like，关节目标需要按减速/协议侧单位换算 | 当前真实机械臂草案对应 `jian_hengxiang_joint` |
| `elbow_lift_joint` | 1 | `motor_id=4` | 灵足 RS00，RobStride CSP，当前关节命令比例 `1.0` | 当前真实机械臂草案对应 `jian_zongxiang_joint` |
| `shoulder_abduction_joint` | 2 | `motor_id=5` | 灵足 RS00，RobStride CSP，当前关节命令比例 `1.0` | 当前真实机械臂草案对应 `zhou_zongxiang_joint` |
| `upper_arm_rotation_joint` | 3 | `motor_id=6` | 灵足 EL05，RobStride CSP，当前关节命令比例 `1.0` | 当前真实机械臂草案对应 `jian_xuanzhuan_joint` |
| `forearm_rotation_joint` | 4 | `motor_id=7` | 灵足 EL05，RobStride CSP，当前关节命令比例 `1.0` | 只允许作为外部台架/临时 MuJoCo shadow actuator，不属于当前 6 关节机械臂 |

`motor_profiles.py` 里的 `gear_ratio=1.0` 对 4/5/6/7 是当前正确的 RobStride CSP 关节命令比例，不要再额外乘 RS00/EL05 的内部减速比。RS00/EL05 的 `10:1/9:1` 只作为驱动内部型号资料记录在 `drive_internal_reduction_ratio`，不是 M33 formal path 或 MuJoCo shadow joint 的输出角换算比例。伺泰威 3 号 CANSimple/ODrive-like 路径不同，它使用电机协议侧 rev 单位，才需要按减速/协议比例做换算。

## 后续必须补齐的参数

每个 `motor -> joint` 绑定都要补：

- `motor_id` 或 `node_id`、协议、厂家型号。
- 输出端 joint 名称、人体自由度名称。
- 传动比：电机角到输出端 joint 角的比例。
- 方向：电机正转时 joint 正方向。
- 机械零位：输出端 0 rad 对应的电机读数。
- 机械硬限位、软件绝对限位、患者 ROM 限位。
- 速度、加速度、电流、力矩、温度限制。
- 回差/死区/同步带弹性说明。
- 标定版本、标定日期、现场验证人。

## AI 必须遵守

- 不得把 `motor_id=7` 当作当前机械臂关节。
- 可以把 `motor_id=7` 临时当作 MuJoCo shadow/台架 demo actuator，用于验证 NanoPi、M33、ROS、MuJoCo 数据流；但必须标记为 `temporary_mujoco_shadow_and_external_bench_only`，不得进入正式 6DOF 映射、患者 profile 或 VLA 真机决策。
- 不得把 `motor_id=1/2` 直接写死到某个腕部轴，直到现场确认哪个电机对应 `wanbu_zongxiang_joint`、哪个对应 `wanbu_hengxiang_joint`。
- 不得把 `node_id=3` 的电机轴角直接当 `jian_hengxiang_joint` 输出角；必须经过 `1:2` 传动、方向和零点换算。
- `motor_id=4` 的齿轮比未知前，只能做仿真/文档草案和极低风险台架规划，不能作为正式运动比例。
- VLA 只允许输出高层任务、子目标或轨迹候选，不允许输出 CAN、电流、力矩、裸电机角或绕过 M33 的运动命令。
- M33 仍是最终安全裁决者；NanoPi、仿真主机、服务器和 VLA 只能提出候选。
