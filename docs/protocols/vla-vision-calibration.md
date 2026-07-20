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
