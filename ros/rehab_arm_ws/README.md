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
rehab_arm_control       reserved namespace; no runnable motion nodes are installed
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
tools/bench-debug/legacy-5dof/                 archived 5-joint demo/VLA sources
m33_motor_status_smoke.py                      synthetic telemetry only
nanopi_can_master.py direct motor commands     bench/debug only
```

Rules for future work:

- Do not copy archived demo publishers back into the ROS workspace or formal launches.
- Do not use the archived `demo_trajectory_node.py` as the planner for the 6-joint `medical_arm.zip` model.
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
ros2 topic echo /joint_states
```

The historical five-joint trajectory publisher is not installed by this workspace.
Its sources live under `../../tools/bench-debug/legacy-5dof/` for traceability only.

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

The workspace intentionally provides no demo trajectory or VLA placeholder
console entry point. A checked six-joint planner must be implemented and safety
reviewed before a replacement is added to a formal launch.
