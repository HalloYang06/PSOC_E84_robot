# VLA vision calibration contract

## Scope

This contract covers fixed-stereo eye-to-hand calibration for the temporary
three-motor chain. It produces coordinate evidence for VLA planning. It does
not publish ROS trajectories, send CAN frames, or grant motion permission.

## Frames and transform

The stereo pipeline reports the independently matched gripper tip in
`stereo_left_optical_frame`. Forward kinematics reports the same physical tip
relative to the MuJoCo `base` body origin, named `base_link` in calibration
sessions. The solved transform convention is:

```text
p_base = R_base_from_camera * p_camera + t_base_from_camera
```

The model's floor/world placement (`base pos="0 0 1.15"`) is deliberately not
part of `base_link` coordinates.

## Three-motor mapping

Only motors `4/5/6` are active. Their measured output angles map to the medical
visual model as follows; all values are radians after input conversion:

```text
motor 4 -> jian_zongxiang_joint = -0.675 - motor4
motor 5 -> zhou_zongxiang_joint = -1.12 + motor5
motor 6 -> jian_xuanzhuan_joint = motor6
```

Frozen visual joints are:

```text
jian_hengxiang_joint = -0.236
wanbu_zongxiang_joint = -1.57
wanbu_hengxiang_joint = 1.05
```

The mapping comes from historical visual-zero protocol commit `69450f71` and
uses `ros/rehab_arm_ws/src/rehab_arm_sim_mujoco/models/medical_arm_6dof.xml` as
the geometry source. Motor angles stored by `capture-raw` are degrees and are
converted once by `finalize-raw`.

## Workflow and quality gates

1. `capture-raw` requires independent left/right gripper detection, accepted
   stereo depth, distinct timestamps, and stable camera XYZ.
2. `finalize-raw` writes a separate session with FK-derived `robot_xyz_m`.
3. Collect at least eight well-spread training poses and three independent
   validation poses.
4. `solve` binds the result to the active stereo calibration ID and applies
   RANSAC, workspace coverage, scale, RMSE, and validation-error gates.
5. Only an accepted transform may populate robot-frame target and gripper
   evidence. Motion still follows `JointTrajectory -> NanoPi -> M33`.

Raw sessions must be retained so a corrected mechanical model or zero mapping
can regenerate robot points without repeating camera capture.

## Closed-loop handoff after calibration

The live NanoPi uploader loads `/home/pi/rehab_arm_calibration/base_from_camera.json`.
It emits robot-frame fields only when the calibration state is `accepted` and
its `source_stereo_calibration_id` matches the active stereo calibration:

```text
target_3d_camera_frame -> target_3d_robot_frame
end_effector_3d_camera_frame -> end_effector_3d_robot_frame
robot_frame_delta_to_target
```

The platform preserves these fields and may create a three-motor IK candidate
only after L semantic mode is `fetch_object` or `vision_servo`, both robot-frame
points exist, and the visual lock is stable. The endpoints are:

```text
POST /api/rehab-arm/v1/devices/{device_id}/ik-candidates
GET  /api/rehab-arm/v1/devices/{device_id}/ik-candidates/latest
```

The singular `ik-candidate` aliases are retained in the unified API. The
historical cloud platform already has the plural POST route but may not yet
have a latest GET route; the Linux agent falls back to dashboard evidence.

Targets are cached on a calibration-bound 1 cm grid so unchanged video frames
do not repeat the expensive IK solve. The Linux execution agent consumes the
latest candidate, publishes the visual six-joint pose to the MuJoCo shadow
topic, and waits for convergence. Hardware publication reuses visual-zero
protocol commit `69450f71` and remains behind explicit onsite flags and fresh
M33 permission. Platform HTTP never sends CAN or motor-private frames.
