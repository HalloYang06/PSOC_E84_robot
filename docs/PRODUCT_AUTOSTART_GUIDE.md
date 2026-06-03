# 产品上电自启动方案

真实产品不能靠 SSH 手动启动。手动教程用于研发验收和排错；产品形态应该一上电就进入安全默认态，并自动启动状态上报服务。

当前仓库提供两类 systemd 模板：

| 服务 | 设备 | 作用 | 默认是否发运动目标 |
|---|---|---|---|
| `rehab-arm-nanopi-readonly.service` | NanoPi | 自动启动 M33/CAN 到 ROS2 的只读 bridge | 否，固定 `enable_target_tx=false` |
| `rehab-arm-sim-host-shadow.service` | Linux 仿真主机 | 研发模式自动启动 MuJoCo 6DOF hardware shadow | 否，只接收 NanoPi `/joint_states` |

## 当前产品上电策略

上电后应该按这个安全层级启动：

1. M33 固件先启动，默认安全态是不动。
2. M33 初始化急停、限位、电源、电机故障和通信超时状态。
3. NanoPi systemd 自动启动只读 bridge。
4. NanoPi 自动发布 `/rehab_arm/safety_state`、`/rehab_arm/motor_state`、必要时 `/joint_states`。
5. 服务器/VLA/App 可以读取状态，但不能直接发底层电机命令。
6. 只有 M33 安全状态机、人工确认、训练 session、患者限位、fresh feedback 都通过后，才允许进入正式运动模式。

当前阶段第 6 步还没有产品化完成，所以 NanoPi 自启动服务必须保持：

```text
enable_target_tx=false
```

## NanoPi 安装只读自启动

在 NanoPi 上执行一次：

```bash
sudo install -m 0755 deploy/scripts/start_nanopi_product_readonly.sh \
  /usr/local/bin/start_nanopi_product_readonly.sh

sudo install -m 0644 deploy/systemd/rehab-arm-nanopi-readonly.service \
  /etc/systemd/system/rehab-arm-nanopi-readonly.service

sudo systemctl daemon-reload
sudo systemctl enable rehab-arm-nanopi-readonly.service
sudo systemctl start rehab-arm-nanopi-readonly.service
```

检查：

```bash
systemctl status rehab-arm-nanopi-readonly.service --no-pager
journalctl -u rehab-arm-nanopi-readonly.service -n 80 --no-pager
```

通过标准：

- service 是 `active (running)`。
- 日志出现 `PSoC CAN bridge ready ... enable_target_tx=False`。
- `candump can0,320:7FF` 没有任何 `0x320`。
- `/rehab_arm/motor_state` 有 M33 状态；只有 fresh motor feedback 存在时才会有 `/joint_states`。

如果要停止：

```bash
sudo systemctl stop rehab-arm-nanopi-readonly.service
```

如果要禁用开机自启：

```bash
sudo systemctl disable rehab-arm-nanopi-readonly.service
```

## 仿真主机安装研发 shadow 自启动

这个服务只适合研发环境，不是产品必须项。它让仿真主机开机后自动接 NanoPi `/joint_states` 并启动 MuJoCo 6DOF hardware shadow。

在仿真主机执行一次：

```bash
sudo install -m 0755 deploy/scripts/start_sim_host_medical_arm_shadow.sh \
  /usr/local/bin/start_sim_host_medical_arm_shadow.sh

sudo install -m 0644 deploy/systemd/rehab-arm-sim-host-shadow.service \
  /etc/systemd/system/rehab-arm-sim-host-shadow.service

sudo systemctl daemon-reload
sudo systemctl enable rehab-arm-sim-host-shadow.service
sudo systemctl start rehab-arm-sim-host-shadow.service
```

检查：

```bash
systemctl status rehab-arm-sim-host-shadow.service --no-pager
journalctl -u rehab-arm-sim-host-shadow.service -n 80 --no-pager
ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState
```

## 上电后自动启动不等于自动运动

必须区分：

| 概念 | 允许自动吗 | 当前策略 |
|---|---|---|
| CAN/ROS 状态读取 | 允许 | NanoPi 开机自启 |
| 安全状态发布 | 允许 | NanoPi/M33 开机自启 |
| MuJoCo shadow | 研发主机允许 | 仿真主机可选自启 |
| 真实运动目标发送 `0x320` | 当前不允许自动 | 必须单独安全审查 |
| VLA 直接发电机命令 | 不允许 | 永久禁止 |

后续产品化要做的是新增一个“运动授权服务”，而不是把 `enable_target_tx=true` 写进开机服务。运动授权服务至少需要：

- M33 上报正式 `motion_allowed=true`。
- 急停、电源、限位、温度、电机故障全部安全。
- fresh joint feedback 有效。
- 患者 profile 和 ROM 限位已加载。
- session 明确开始。
- App/医生/康复师确认。
- VLA 只输出高层目标或候选轨迹，最终仍由 NanoPi/M33 限位和审核。

## 文件位置

| 文件 | 用途 |
|---|---|
| `deploy/scripts/start_nanopi_product_readonly.sh` | NanoPi 产品默认只读启动脚本 |
| `deploy/scripts/start_sim_host_medical_arm_shadow.sh` | 仿真主机研发 shadow 启动脚本 |
| `deploy/systemd/rehab-arm-nanopi-readonly.service` | NanoPi systemd 服务模板 |
| `deploy/systemd/rehab-arm-sim-host-shadow.service` | 仿真主机 systemd 服务模板 |
