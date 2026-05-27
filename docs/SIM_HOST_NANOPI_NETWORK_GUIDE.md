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

## Safety Boundary

These tests only use ROS2 demo/string topics.

They do not:

- start `psoc_can_bridge_node`,
- publish `/arm_controller/joint_trajectory`,
- send CAN,
- command M33,
- move motors.

## Next Integration Step

After MuJoCo and the rehab ROS2 workspace are ready on the simulation host:

1. Start NanoPi bridge in read-only or target-disabled mode first.
2. Confirm the simulation host can see:
   - `/joint_states`
   - `/rehab_arm/safety_state`
   - `/rehab_arm/motor_state`
   - `/rehab_arm/sensor_state`
3. Only after safety review, test the shared trajectory interface:
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
