# Rehab Arm ROS2 Workspace

Formal ROS2 workspace for the rehabilitation exoskeleton arm.

New users should first read the step-by-step framework guide:

```text
../docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md
../docs/REHAB_ARM_ROS2_SIM_FRAMEWORK_GUIDE.md
```

The official motion path is:

```text
Linux workstation / VLA / planner
  -> /arm_controller/joint_trajectory
NanoPi ROS2 bridge
  -> PSoC command frames on CAN 0x320/0x321
Infineon PSoC
  -> motor drive, limits, emergency stop, safety fallback
```

NanoPi direct motor CAN control remains in `nanopi_can_ros_ws` as a debug tool only.

## Packages

```text
rehab_arm_description   URDF and joint configuration
rehab_arm_sim_mujoco    simulation/shadow node; current legacy baseline is 5-joint
rehab_arm_control       experimental demo/VLA placeholder; not a real-device planner
rehab_arm_psoc_bridge   formal NanoPi <-> M33 ROS/CAN bridge
rehab_arm_bringup       launch files; real launch must keep safety gates explicit
```

## Mainline vs Demo Boundary

Mainline code is the path that may eventually touch the real device:

```text
real M33/CAN telemetry
  -> NanoPi rehab_arm_psoc_bridge
  -> ROS state topics
  -> planner-generated, checked JointTrajectory
  -> M33 final safety decision
```

Demo/debug code is not mainline and must not be used as proof of real-device readiness:

```text
rehab_arm_control/demo_trajectory_node.py      legacy 5-joint demo publisher
rehab_arm_control/vla_task_planner_node.py     placeholder that emits demo trajectory
sim_data_collection.launch.py enable_demo_trajectory:=true
m33_motor_status_smoke.py                      synthetic telemetry only
nanopi_can_master.py direct motor commands     bench/debug only
```

Rules for future work:

- Do not connect demo publishers to a live bridge unless the run is explicitly labelled `dry-run` or `bench-debug`.
- Do not use `demo_trajectory_node.py` as the planner for the 6-joint `medical_arm.zip` model.
- Do not treat synthetic/smoke/fallback data as fresh motor feedback.
- Do not move demo scripts into real launch paths.
- Keep `enable_target_tx:=false` until a separate safety review enables real target frames.

## Build

```bash
cd rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
./build_ros2.sh
source install/setup.bash
```

## Simulation

```bash
ros2 launch rehab_arm_bringup sim.launch.py
```

In another terminal:

```bash
source rehab_arm_ros2_ws/install/setup.bash
ros2 run rehab_arm_control demo_trajectory_node
ros2 topic echo /joint_states
```

This simulation command is a legacy 5-joint demo. It is useful for ROS topic smoke tests, but it is not the current 6-joint medical-arm MuJoCo contract.

## Real NanoPi Bridge

Bring up classic CAN first:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 restart-ms 100 berr-reporting on
sudo ip link set can0 up
ip -details link show can0
```

Start the formal PSoC bridge:

```bash
ros2 launch rehab_arm_bringup real_nanopi.launch.py
```

For first integration, keep the bridge target-disabled and observe state only. If a trajectory smoke test is needed, label it as dry-run and confirm CAN has no `0x320` target frame:

```bash
ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py --ros-args \
  -p interface:=can0 \
  -p enable_target_tx:=false
```

Do not run `rehab_arm_control demo_trajectory_node` against a real NanoPi bridge as a normal workflow. It is a legacy demo publisher, not a clinically checked planner.

## VLA Placeholder

VLA publishes high-level task goals only:

```bash
ros2 topic pub --once /vla/task_goal std_msgs/msg/String "{data: '{\"task\":\"preset_reach\"}'}"
```

`rehab_arm_control` converts the task into `JointTrajectory`. It never accesses CAN.

Current note: the VLA placeholder still emits the legacy demo trajectory. Treat it as a topic-contract smoke test only until it is replaced by a checked planner using the 6-joint schema.
