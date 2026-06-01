# Simulation Host <-> NanoPi ROS2 Network Guide

This guide records the current LAN setup for the rehab arm simulation host and NanoPi bridge.

## Current Machines

| Role | Hostname | IP | User | Purpose |
|---|---|---:|---|---|
| Simulation host | `cal-MS-7D90` | `192.168.2.46` | `cal` | MuJoCo, RViz, planning, trajectory generation |
| NanoPi bridge | `NanoPi-M5` | `192.168.2.66` | `pi` | ROS2 bridge to M33/CAN, motor/sensor state publisher |

Both hosts are on `192.168.2.0/24`.

## ROS2 DDS Settings

Both machines use the same network profile:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
```

The settings are stored in:

```bash
~/.rehab_arm_ros2_network
```

and sourced from `~/.bashrc`.

Use this before ROS2 commands in non-interactive SSH sessions:

```bash
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
```

## Verified Connectivity

Network:

- NanoPi can ping simulation host `192.168.2.46`.
- Simulation host can ping NanoPi `192.168.2.66`.
- SSH works to both machines.

ROS2 DDS:

- Simulation host -> NanoPi passed with `demo_nodes_cpp talker` and NanoPi `ros2 topic echo /chatter --once`.
- NanoPi -> simulation host passed with NanoPi `ros2 topic pub /rehab_net_test std_msgs/msg/String "{data: from_nanopi}" -r 1` and simulation host `ros2 topic echo /rehab_net_test std_msgs/msg/String --once`.

## Current Workspace Status

The simulation host has the repo at:

```bash
/home/cal/桌面/Medical-Rehabilitation-Manipulator
```

Because the simulation host could not fetch from GitHub through either its SSH remote or HTTPS, the current branch was transferred from the Windows workstation as a Git bundle and checked out locally:

```bash
feature/rehab-arm-ros2-architecture
```

Current verified commit on the simulation host:

```bash
0edee779
```

ROS2 workspace build passed for:

```bash
./build_ros2.sh --packages-select rehab_arm_description rehab_arm_sim_mujoco rehab_arm_psoc_bridge
```

`check_sim_env.py` reports:

```text
ok=true
readiness=ready_with_fallback_sim
```

MuJoCo Python is the only missing optional component. The fallback simulator and data tools are ready.

## Current NanoPi Bridge Check

NanoPi `can0` was brought up as classic CAN 1 Mbps:

```text
can0: UP, LOWER_UP, ERROR-ACTIVE, tx/rx error counters 0/0
```

The bridge was started with target transmission disabled:

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

After the readonly validation, the bridge process was stopped so NanoPi would not keep sending heartbeat frames in the background.

From the simulation host, these topics were visible:

```text
/arm_controller/joint_trajectory
/joint_states
/rehab_arm/motor_state
/rehab_arm/safety_state
/rehab_arm/sensor_state
```

The simulation host received `/rehab_arm/safety_state`.

A 3 second passive candump showed only heartbeat/status frames:

```text
321#43
322#A543070000060000
321#44
322#A544070000060000
321#45
322#A545070000060000
```

No `0x320` trajectory target frame was observed. No motor control frame was sent by this test.

`/rehab_arm/motor_state` and `/joint_states` did not produce a sample during the short check because the bus only showed `0x321/0x322`; no M33 motor status frame was present in that window.

Use the dedicated readonly checker to make this condition explicit:

```bash
ros2 run rehab_arm_psoc_bridge check_m33_motor_status_presence.py \
  /tmp/simhost_bridge_readonly.candump \
  --pretty \
  --output /tmp/simhost_bridge_motor_status_presence.json
```

Current result:

```text
ok=false
heartbeat_0x321_count=3
psoc_status_0x322_count=3
target_0x320_count=0
valid_m33_motor_status_count=0
missing_expected_m33_motor_status_ids=0x330..0x337
```

This is a useful safe failure: it proves the bridge/network can see M33 status and that no trajectory target was sent, while also proving M33 motor telemetry is not yet available to the simulation host.

## Safety Boundary

These tests only use ROS2 demo/string topics.

They do not:

- start `psoc_can_bridge_node`,
- publish `/arm_controller/joint_trajectory`,
- send CAN,
- command M33,
- move motors.

## Wireless Latency Position

The simulation host and NanoPi are connected over Wi-Fi/LAN ROS2 DDS. This is acceptable for:

- MuJoCo/RViz visualization.
- State monitoring and data recording.
- Server/VLA context collection.
- Planning and dry-run trajectory validation.
- Low-rate task goals and reviewed trajectory candidates.

It is not acceptable for:

- emergency stop enforcement,
- torque/current/impedance inner loops,
- motor freshness safety decisions,
- high-frequency human-assist closed-loop control,
- any behavior that must stay safe if Wi-Fi drops.

Those responsibilities stay on M33 and the local CAN/electrical safety path.

Expected practical behavior:

- Good LAN/Wi-Fi often gives millisecond to tens-of-milliseconds latency, but jitter and packet loss can spike higher.
- VLA inference and server round trips are much slower and should be treated as high-level planning, not realtime control.
- If wireless ROS2 is unstable, the correct response is to slow down, dry-run, record data locally, or stop; never increase authority to compensate.

Recommended latency check:

```bash
ping -c 50 192.168.2.66
```

ROS2 one-way discovery/data smoke test:

```bash
# On simulation host
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
ros2 run demo_nodes_cpp talker

# On NanoPi
source ~/.rehab_arm_ros2_network
source /opt/ros/jazzy/setup.bash
ros2 topic echo /chatter --once
```

Before any trajectory test, keep NanoPi target transmission disabled:

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

Acceptance for wireless use:

- ROS2 topics are discoverable both ways.
- `/rehab_arm/safety_state`, `/rehab_arm/motor_state`, and `/joint_states` are visible on the simulation host.
- Dry-run `JointTrajectory` reaches NanoPi bridge.
- CAN capture confirms no `0x320` is emitted while `enable_target_tx=false`.
- Real motion remains blocked unless M33 local safety state and fresh feedback gates pass.

## Next Integration Step

After MuJoCo and the rehab ROS2 workspace are ready on the simulation host:

1. Start NanoPi bridge in read-only or target-disabled mode first.
2. Confirm the simulation host can see:
   - `/joint_states`
   - `/rehab_arm/safety_state`
   - `/rehab_arm/motor_state`
   - `/rehab_arm/sensor_state`
3. Confirm M33 motor status frames are present so `/rehab_arm/motor_state` and `/joint_states` publish real samples.
4. Only after safety review, test the shared trajectory interface:
   - simulation/planner publishes `/arm_controller/joint_trajectory`
   - NanoPi bridge receives it
   - `enable_target_tx` remains `false` until explicitly approved.

## Troubleshooting

If one direction works but the other does not:

- Confirm both machines have `ROS_DOMAIN_ID=42`.
- Confirm `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` is set on both machines.
- Confirm no firewall blocks DDS UDP discovery/data traffic.
- Confirm the machine is using the `192.168.2.x` interface, not a VPN or virtual interface.
- Use explicit message type when echoing a topic that has not been discovered yet:

```bash
ros2 topic echo /rehab_net_test std_msgs/msg/String --once
```
