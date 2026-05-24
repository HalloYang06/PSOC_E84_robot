# NanoPi CAN Master 使用说明

本文档说明 `/home/pi/nanopi_can_master.py` 的代码结构、协议含义和现场命令行测试方法。

本地源码路径：

```text
D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan\scripts\nanopi_can_master.py
```

NanoPi 上已部署路径：

```bash
/home/pi/nanopi_can_master.py
/home/pi/nanopi_ros/scripts/nanopi_can_master.py
```

## 1. 脚本整体作用

`nanopi_can_master.py` 是一个命令行 CAN 调试/控制工具，不是后台服务。

每执行一次命令，脚本会：

1. 打开 SocketCAN 接口，默认 `can0`。
2. 根据子命令组出一帧或多帧 CAN 数据。
3. 发送到 CAN 总线。
4. 等待一小段时间并打印收到的回包。
5. 退出。

它适合现场逐步测试：

- NanoPi 到 M33 心跳链路
- 4/5/6/7 私有扩展帧电机
- 3 号 CANSimple 电机
- F103 链路测试，当前先不管

## 2. CAN 接口默认值

脚本默认：

```text
CAN 接口: can0
波特率: 1000000
```

对应代码：

```python
DEFAULT_IFACE = "can0"
DEFAULT_BITRATE = 1000000
```

现场先拉起接口：

```bash
~/nanopi_can_master.py setup --iface can0 --bitrate 1000000
```

查看总线：

```bash
~/nanopi_can_master.py monitor --iface can0 --seconds 10
```

## 3. 协议分类

### 3.1 私有扩展帧电机协议

4/5/6/7 电机目前按私有扩展帧协议测试。

扩展 ID 组成：

```text
ext_id = (comm_type << 24) | (data2 << 8) | data1
```

脚本里的函数：

```python
private_ext_id(comm_type, data2, data1)
```

常用类型：

```text
0x00 Get_ID
0x01 MIT 控制
0x03 使能
0x04 停止
0x06 设零
0x11 读参数
0x12 写参数
0x18 主动上报
```

主机 ID：

```text
MASTER_ID = 0xFD
```

例如电机 4 的 Get_ID：

```text
comm_type = 0x00
data2 = 0x00FD
data1 = 0x04
ext_id = 0x0000FD04
```

### 3.2 CANSimple 协议

3 号电机目前按 CANSimple/ODrive 类标准帧协议测试。

标准 ID 组成：

```text
std_id = (node_id << 5) | cmd_id
```

脚本里的函数：

```python
cansimple_id(node_id, cmd_id)
```

例如 node 3 的 heartbeat：

```text
3 << 5 | 0x01 = 0x61
```

所以总线上看到 `0x61`，就是 3 号节点心跳。

### 3.3 M33 转发协议

M33 转发协议用于让 NanoPi 发命令给 M33，再由 M33 控制电机。

```text
0x320 NanoPi -> M33 控制命令
0x321 NanoPi -> M33 心跳
0x322 M33 -> NanoPi 状态回复
```

当前主控迁移到 NanoPi 时，建议优先使用 `private` 和 `cansimple` 两类直接控制；`m33` 子命令主要用于对照测试。

### 3.4 F103 协议

F103 代码中定义：

```text
0x7C0 NanoPi/M33 -> F103 控制
0x7C1 F103 -> ACK
0x7C2 F103 -> 传感器数据
0x7C3 F103 -> 健康状态
```

当前现场 F103 波形较差，先不作为电机调试重点。

## 4. 代码结构说明

### 4.1 常量区

文件开头定义 SocketCAN 标志位、默认接口、协议常量。

重点包括：

```python
MASTER_ID = 0xFD
MOTOR_TYPE_CTRL = 0x01
MOTOR_TYPE_ENABLE = 0x03
MOTOR_TYPE_STOP = 0x04
RUN_MODE_MIT = 0
```

MIT 控制范围：

```text
位置 pos:    -12.57 ~ 12.57 rad
速度 vel:    -33.0  ~ 33.0 rad/s
kp:          0.0    ~ 500.0
kd:          0.0    ~ 5.0
torque:      -14.0  ~ 14.0 Nm
```

### 4.2 CanFrame

`CanFrame` 表示一帧 CAN：

```python
can_id
data
extended
```

`extended=True` 表示 29 位扩展帧。

`extended=False` 表示 11 位标准帧。

### 4.3 打包和发送

核心函数：

```python
pack_frame()
unpack_frame()
open_can()
send()
recv_until()
```

作用：

- `pack_frame()` 把 Python 对象转换成 Linux SocketCAN 二进制帧。
- `unpack_frame()` 把收到的 SocketCAN 二进制帧解析成 `CanFrame`。
- `open_can()` 打开 `can0`。
- `send()` 发一帧。
- `recv_until()` 等待回包并打印。

### 4.4 私有电机帧生成

主要函数：

```python
frame_private_probe()
frame_private_enable()
frame_private_stop()
frame_private_zero()
frame_private_mode()
frame_private_mit()
frame_private_read()
frame_private_write_float()
```

其中 `frame_private_mit()` 是运动控制核心。

MIT 控制帧里：

- `pos / vel / kp / kd` 被压缩到 8 字节 payload。
- `torque` 被压缩进扩展 ID 的 `data2` 字段。

### 4.5 CANSimple 帧生成

主要函数：

```python
frame_cansimple()
```

配合 `cmd_cansimple()` 实现：

- closed-loop
- idle
- clear
- vel
- pos
- torque

### 4.6 命令行入口

`build_parser()` 定义所有命令行子命令。

当前支持：

```text
setup
monitor
heartbeat
probe
private
cansimple
m33
f103
raw
```

## 5. 现场测试推荐流程

### 5.1 拉起 CAN

```bash
~/nanopi_can_master.py setup --iface can0 --bitrate 1000000
```

### 5.2 观察总线

```bash
~/nanopi_can_master.py monitor --iface can0 --seconds 5
```

### 5.3 测 M33 心跳

```bash
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
```

正常会看到：

```text
TX STD 0x00000321 ...
RX STD 0x00000322 A5 ...
```

### 5.4 扫描 4/5/6/7 电机

```bash
~/nanopi_can_master.py probe --iface can0 --start 4 --end 7 --wait 0.5
```

单独扫描某个电机：

```bash
~/nanopi_can_master.py probe --iface can0 --motor 4 --wait 1
```

## 6. 控制 4/5/6/7 私有协议电机

### 6.1 停止

```bash
~/nanopi_can_master.py private stop --iface can0 --motor 4 --clear-fault
```

### 6.2 使能

```bash
~/nanopi_can_master.py private enable --iface can0 --motor 4
```

### 6.3 小速度测试

建议先从很小速度开始：

```bash
~/nanopi_can_master.py private speed --iface can0 --motor 4 --vel 0.05 --kd 1.0 --wait 0.5
```

然后立即停止：

```bash
~/nanopi_can_master.py private stop --iface can0 --motor 4 --clear-fault
```

### 6.4 完整 MIT 控制

```bash
~/nanopi_can_master.py private mit --iface can0 --motor 4 \
  --pos 0.0 --vel 0.1 --kp 0.0 --kd 1.0 --torque 0.0 --wait 0.5
```

参数含义：

```text
--motor   电机 ID，4/5/6/7
--pos     目标位置，rad
--vel     目标速度，rad/s
--kp      位置刚度
--kd      阻尼
--torque  力矩前馈，Nm
--wait    发送后等待回包的秒数
```

### 6.5 设零

确认机械位置安全后再用：

```bash
~/nanopi_can_master.py private zero --iface can0 --motor 4
```

### 6.6 读参数

读运行模式 `0x7005`：

```bash
~/nanopi_can_master.py private read --iface can0 --motor 4 --index 0x7005 --wait 1
```

### 6.7 写运行模式

```bash
~/nanopi_can_master.py private mode --iface can0 --motor 4 --mode 0
```

模式值：

```text
0 MIT
1 PP
2 SPEED
3 CURRENT
5 CSP
```

## 7. 控制 3 号 CANSimple 电机

### 7.1 看心跳

```bash
~/nanopi_can_master.py monitor --iface can0 --seconds 3 | grep 00000061
```

`0x61` 是 node 3 heartbeat。

### 7.2 进闭环

```bash
~/nanopi_can_master.py cansimple closed-loop --iface can0 --node 3 --wait 1
```

### 7.3 小速度测试

```bash
~/nanopi_can_master.py cansimple vel --iface can0 --node 3 --vel 0.05 --torque 0.0 --wait 1
```

### 7.4 回 idle

```bash
~/nanopi_can_master.py cansimple idle --iface can0 --node 3 --wait 1
```

## 8. 通过 M33 转发控制

使能：

```bash
~/nanopi_can_master.py m33 enable --iface can0 --joint 4
```

停止：

```bash
~/nanopi_can_master.py m33 stop --iface can0 --joint 4 --clear-fault
```

目标位置控制：

```bash
~/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 5 --rpm 5 --torque-ma 0
```

参数含义：

```text
--joint      M33 侧关节号
--deg        目标角度，度
--rpm        目标速度，rpm
--torque-ma  目标电流/力矩字段，mA
```

## 9. 安全建议

1. 先 `monitor` 看总线是否正常。
2. 先 `probe`，确认电机 ID。
3. 第一次运动用 `0.05 rad/s` 或更低。
4. 每次运动测试前准备好 stop 命令。
5. 不确认机械零点时不要发 `zero`。
6. 当前脚本的 `private speed` 和 `private mit` 默认只发一次控制帧，不持续刷新。

如果电机协议要求周期刷新，需要新增一个持续命令，例如：

```text
hold-speed --duration-ms 3000 --period-ms 10
```

当前版本还没有实现持续刷新。

