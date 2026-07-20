# Linux VLA MuJoCo execution agent

`vla_mujoco_execution_agent.py` connects the platform IK evidence to the same
visual-zero ROS path used by the earlier slider-controlled recording demo.
It does not replace `open_visual_zero_viewer.py` from history commit `69450f71`;
both use the same motor `4/5/6` mapping and formal hardware topic.

Start the MuJoCo medical-arm shadow node and source the ROS 2 environment, then
run shadow-only mode first:

```bash
ros2 launch rehab_arm_sim_mujoco medical_arm_visual_zero_3motor_shadow.launch.py

python3 tools/linux/vla_mujoco_execution_agent.py \
  --api-base http://106.55.62.122:8011 \
  --device-id nanopi-m5 \
  --project-id e201f41c-25a6-46e1-baf8-be6dcb83284c
```

Shadow-only mode polls the latest calibrated candidate, publishes only
`/sim/medical_arm/joint_trajectory`, waits for
`/sim/medical_arm/joint_states`, and uploads simulation readiness.

The supervised real-motion mode uses the original two explicit confirmations:

```bash
python3 tools/linux/vla_mujoco_execution_agent.py \
  --api-base http://106.55.62.122:8011 \
  --device-id nanopi-m5 \
  --project-id e201f41c-25a6-46e1-baf8-be6dcb83284c \
  --enable-hardware-tx \
  --confirm-onsite
```

Even with both flags, hardware publication is blocked unless IK is precise,
MuJoCo reaches the candidate, and `/rehab_arm/safety_state` reports fresh
`motion_allowed=true`. The only hardware output is a ROS `JointTrajectory` on
`/arm_controller/joint_trajectory`; NanoPi and M33 retain their existing gates.

Do not use the generic `medical_arm_6dof_shadow.launch.py` for this temporary
three-motor workflow. Its original limits clamp the demonstrated visual zero;
the dedicated profile preserves the exact zero and motor `4/5/6` ranges without
changing the generic six-axis model.
