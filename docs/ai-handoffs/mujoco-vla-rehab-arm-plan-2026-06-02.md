# MuJoCo and VLA Plan for Rehab Exoskeleton Arm

Date: 2026-06-02

## Inputs Reviewed

- GitHub-backed repos:
  - `_nanopi_rosnode_usbcan`, branch `feature/rehab-arm-ros2-architecture`, latest fetched commit `eaea6ed8 Add CSP slow retract before stop`.
  - `yiliao_m33`, branch `M33`, latest fetched commit `1e7ecb7b Ignore CANSimple host queries for motor freshness`.
  - `_m55_ref_repo`, branch `M55`, latest fetched commit `1cd7f69 同步当前M55工程版本`.
- URDF zip: `C:/Users/18312/xwechat_files/wxid_4anyq9um43fg22_7053/msg/file/2026-06/medical_arm.zip`.
- Extracted model package: `medical_arm`, with `urdf/medical_arm.urdf`, STL meshes, ROS launch/config files.

## URDF Findings

- The main URDF has 7 links and 6 continuous revolute joints:
  - `jian_hengxiang_joint`
  - `jian_zongxiang_joint`
  - `jian_xuanzhuan_joint`
  - `zhou_zongxiang_joint`
  - `wanbu_zongxiang_joint`
  - `wanbu_hengxiang_joint`
- The ROS config file currently lists only `jian_xuanzhuan_joint` and `zhou_zongxiang_joint` as controller joints.
- All six joints are exported as `continuous`; no joint has lower/upper limits, effort limits, or velocity limits.
- The meshes are STL and appear to be meter-scale. Collision meshes are high-triangle visual meshes, so MuJoCo should use simplified collision geoms instead of raw STL collision.
- The model is useful as a visual/kinematic starting point, but it is not ready as a clinical exoskeleton simulation model until human ROM limits, velocity limits, actuator limits, collision simplification, and verified joint-to-motor mapping are added.

## Current Project Constraints From Git History

- Formal motion path is `JointTrajectory -> NanoPi -> M33 -> motor`.
- M33 is the final safety authority.
- VLA, App, server, M55, and NanoPi must not send direct motor commands or bypass M33.
- Current known motor IDs are `node_id=3` for CANSimple and `motor_id=4/5/6/7` for private MIT protocol; mechanical joint binding remains to be confirmed.
- Recent commits focus on safe motor telemetry, stale/fresh state, clinical prearm gating, and preventing debug paths from being treated as formal control.

## Recommended MuJoCo Plan

1. Create a normalized robot description package:
   - Keep the SolidWorks-exported URDF as source evidence.
   - Create a cleaned `xacro`/URDF for ROS2 with final joint names matching project docs:
     - `shoulder_lift_joint`
     - `elbow_lift_joint`
     - `shoulder_abduction_joint`
     - `upper_arm_rotation_joint`
     - `forearm_rotation_joint`
     - optional wrist joint if clinically needed.
2. Add joint limits in layers:
   - Mechanical hard limits from CAD and motor mounting.
   - Human-safe ROM limits per patient profile.
   - Velocity, acceleration, and torque/current limits for simulation and M33.
3. Generate MuJoCo MJCF from the cleaned URDF, then hand-edit:
   - Add actuators as position/velocity/torque-limited servos.
   - Replace raw STL collision with capsules, boxes, cylinders, or convex hulls.
   - Add soft joint limits, damping, armature, friction loss, and tendon/strap approximations.
   - Add sites for elbow/wrist/strap/contact points and camera viewpoints.
4. Make ROS2 and MuJoCo share one action contract:
   - Observation: RGB/depth optional, joint positions, velocities, safety state, motor freshness, patient profile limits, optional EMG/IMU features.
   - Action: high-level task or safe `JointTrajectory` candidate only.
   - M33 remains the gate for real hardware execution.
5. Validate in stages:
   - Static model loads in MuJoCo and RViz.
   - Joint axes and signs match CAD and physical motors.
   - Replay recorded `/joint_states` and compare pose.
   - Run offline trajectory validation.
   - Only then do low-energy bench tests.

## VLA Recommendation

Best first version:

- Use OpenVLA/Octo-style policy only as a high-level planner or trajectory proposal generator.
- Do not let the VLA output motor current, torque, raw velocity, or CAN commands.
- For near-term development, start with Octo or a small diffusion-policy baseline for simulation/data plumbing, then move to OpenVLA LoRA/OFT once image-language-task data exists.

Model choice:

- `Octo-small` or a local diffusion policy is the practical first baseline because it is lighter and easier to fine-tune on a small custom dataset.
- `OpenVLA-7B` is the recommended open-source VLA target after data collection because it has active LoRA/OFT tooling and a clear custom robot fine-tuning path.
- `pi0`/Physical Intelligence and NVIDIA GR00T are useful strategic references, but should not be the first implementation dependency unless licensing, access, deployment, and medical safety validation are solved.

For this medical rehab/exoskeleton arm, the VLA should learn:

- Task intent: assist flexion/extension, guided ROM, reach-to-target, hold posture, stop on pain/fatigue.
- Context understanding: patient state, therapist instruction, object/target in camera view.
- Policy output: subgoal or safe trajectory candidate.
- Forbidden output: direct motor command, force override, emergency-state override.

## Data and Training Cost Estimate

Recommended first dataset:

- 20-50 hours of supervised teleoperation/simulation demonstrations for basic rehab motions.
- 100-300 labeled sessions for patient profile variants and stop/fatigue/pain annotations.
- Use rosbag plus JSONL metadata; keep camera frames, joint states, motor freshness, safety state, patient profile version, and command source.

Cost tiers:

- Simulation and data pipeline baseline: local RTX 4070/4080/4090 or cloud single L4/A10; mostly engineering time.
- Octo-small or diffusion policy fine-tune: 1x 24 GB GPU is usually enough for early experiments; budget roughly USD 100-500 cloud compute per iteration set if data is prepared.
- OpenVLA LoRA fine-tune: target 1x A100 80 GB for comfortable runs, or smaller GPUs with reduced batch and more accumulation; budget roughly USD 500-2,000 for several experiments, excluding data collection.
- Full VLA pretraining is not appropriate for this project stage; it is multi-GPU/TPU scale and should be avoided.
- Real cost driver is not GPU time; it is safe, labeled, repeatable rehab data collection and clinical validation.

## Immediate Next Step

Create a `rehab_arm_description` package that imports the cleaned URDF/MJCF, defines final joint names and conservative limits, and runs a no-hardware MuJoCo smoke test. The first VLA milestone should be a no-motion planner that consumes a camera frame, patient profile, safety state, and text instruction, then outputs a human-readable subgoal plus a simulated-only trajectory candidate.
