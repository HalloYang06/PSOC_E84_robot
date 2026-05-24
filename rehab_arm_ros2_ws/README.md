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
rehab_arm_sim_mujoco    MuJoCo-ready simulation node with fallback fake dynamics
rehab_arm_control       demo trajectory publisher and VLA task placeholder
rehab_arm_psoc_bridge   ROS trajectory <-> PSoC CAN bridge
rehab_arm_bringup       simulation and real NanoPi launch files
```

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

Then publish the same `JointTrajectory` used by simulation:

```bash
ros2 run rehab_arm_control demo_trajectory_node
```

## VLA Placeholder

VLA publishes high-level task goals only:

```bash
ros2 topic pub --once /vla/task_goal std_msgs/msg/String "{data: '{\"task\":\"preset_reach\"}'}"
```

`rehab_arm_control` converts the task into `JointTrajectory`. It never accesses CAN.
