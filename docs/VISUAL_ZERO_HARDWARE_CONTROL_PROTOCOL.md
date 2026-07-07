# Visual Zero Hardware Control Protocol

Date: 2026-07-07

Status: bench-debug hardware-control workflow through the formal ROS trajectory
entry point. This does not bypass NanoPi, the PSoC bridge, or M33 safety.

## Purpose

The Linux desktop MuJoCo viewer is the operator-facing control thread for the
current demo. The viewer pose that is open on the desktop is the calibrated
visual zero for the real arm's natural hanging state.

Do not copy the visual zero numbers into a separate control path and then tune
again. Future server target-coordinate and IK work should attach to this same
protocol:

```text
server target XYZ -> IK in visual-zero model frame
-> hardware joint command conversion
-> /arm_controller/joint_trajectory
-> NanoPi PSoC bridge
-> M33 safety/control
-> motors
```

## Entry Point

Current script:

```text
cal host: /home/cal/medical_arm_mujoco/open_visual_zero_viewer.py
repo copy: tools/open_visual_zero_viewer.py
model: /home/cal/medical_arm_mujoco/medical_arm_mujoco.xml
```

Run on the Linux visualization host:

```bash
source /opt/ros/jazzy/setup.bash
source /home/cal/.rehab_arm_ros2_network
cd /home/cal/medical_arm_mujoco
python3 open_visual_zero_viewer.py --enable-hardware-tx --confirm-onsite
```

Hardware transmission is disabled unless both flags are present:

```text
--enable-hardware-tx
--confirm-onsite
```

The script does not publish an initial real motion command by default. It only
publishes after a relevant MuJoCo slider changes beyond the deadband. Use
`--publish-initial` only when the operator explicitly wants the current slider
state sent to the real arm.

## Visual Zero

The MuJoCo qpos used as the visual zero is:

```text
[jian_hengxiang_joint,
 jian_zongxiang_joint,
 jian_xuanzhuan_joint,
 zhou_zongxiang_joint,
 wanbu_zongxiang_joint,
 wanbu_hengxiang_joint]
=
[-0.236, -0.675, 0.0, -1.12, -1.57, 1.05]
```

The viewer uses MuJoCo controls as offsets around that visual zero:

```text
visual_qpos[i] = VISUAL_ZERO[i] + VISUAL_CTRL_SCALES[i] * ctrl[i]
VISUAL_CTRL_SCALES = [1.0, -1.0, 1.0, 1.0, 1.0, 1.0]
```

The negative scale on `jian_zongxiang_joint` is intentional. It records the
field finding that the shoulder longitudinal visual direction was reversed
relative to the useful hardware command direction.

## Hardware Slider Mapping

Only the installed 4/5/6 hardware chain is published by this viewer in the
current demo.

| MuJoCo ctrl | Real motor | Published hardware joint | Medical visual joint | Visual qpos formula | Hardware command |
|---:|---|---|---|---|---|
| `ctrl[1]` | motor 4 | `elbow_lift_joint` | `jian_zongxiang_joint` | `-0.675 - ctrl[1]` | `ctrl[1]` |
| `ctrl[3]` | motor 5 | `shoulder_abduction_joint` | `zhou_zongxiang_joint` | `-1.12 + ctrl[3]` | `ctrl[3]` |
| `ctrl[2]` | motor 6 | `upper_arm_rotation_joint` | `jian_xuanzhuan_joint` | `0.0 + ctrl[2]` | `ctrl[2]` |

Current visual-only joints:

```text
ctrl[0] -> jian_hengxiang_joint
ctrl[4] -> wanbu_zongxiang_joint
ctrl[5] -> wanbu_hengxiang_joint
```

Do not add motor 1/2/3 publishing here until their zero, direction, output ratio,
and safe limits have been confirmed in the same on-site process.

## Published ROS Message

Topic:

```text
/arm_controller/joint_trajectory
```

Message type:

```text
trajectory_msgs/msg/JointTrajectory
```

Joint order:

```text
['elbow_lift_joint',
 'shoulder_abduction_joint',
 'upper_arm_rotation_joint']
```

Position payload:

```text
[ctrl[1], ctrl[3], ctrl[2]]
```

Default timing and force-related fields:

```text
--rpm 3              -> velocity = 3 rpm = 0.314159 rad/s
--current-ma 3000    -> effort field = 3.0 A
--duration 0.4       -> point.time_from_start = 0.4 s
--publish-rate-hz 5  -> max publish rate
--deadband-rad 0.005 -> slider change threshold
```

The effort/current value is a trajectory request field for the downstream bridge
and M33-side control path. It is not permission to bypass M33 current, torque,
temperature, limit, heartbeat, or emergency-stop checks.

## Software Limits In The Viewer

The viewer refuses to publish if a hardware command is outside these limits:

| Published joint | Low rad | High rad |
|---|---:|---:|
| `elbow_lift_joint` | `0.0` | `1.8` |
| `shoulder_abduction_joint` | `0.0` | `2.617993878` |
| `upper_arm_rotation_joint` | `-1.2` | `1.2` |

These are demo-side guardrails only. M33 remains the final safety authority.

## Future Server XYZ To IK Contract

Server-side target coordinates should be treated as target XYZ in the same
medical-arm MuJoCo visual frame used by the desktop viewer.

The IK node should:

1. Solve desired medical visual joint positions in the visual-zero model frame.
2. Convert the desired visual qpos to the current hardware command frame.
3. Publish a `JointTrajectory` with the same topic, joint names, current field,
   speed field, and confirmation gates used by this viewer.

Conversion from IK qpos to hardware commands:

```python
motor4_elbow_lift = -(q_jian_zongxiang - VISUAL_ZERO[1])
motor5_shoulder_abduction = q_zhou_zongxiang - VISUAL_ZERO[3]
motor6_upper_arm_rotation = q_jian_xuanzhuan - VISUAL_ZERO[2]
```

Equivalent with current constants:

```python
motor4_elbow_lift = -q_jian_zongxiang - 0.675
motor5_shoulder_abduction = q_zhou_zongxiang + 1.12
motor6_upper_arm_rotation = q_jian_xuanzhuan
```

Before enabling server-originated real motion, keep the staged gate:

```text
dry-run IK -> MuJoCo viewer check -> onsite confirmation
-> publish JointTrajectory -> NanoPi bridge -> M33 safety decision
```

The server must not send raw CAN frames, direct current commands, or motor-private
protocol frames. It may send target XYZ or a reviewed trajectory candidate; real
motion still enters through `/arm_controller/joint_trajectory` and is accepted or
rejected by M33.
