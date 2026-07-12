# Legacy 5DOF ROS demos

This directory preserves the historical `demo_trajectory_node`,
`vla_task_planner_node`, their trajectory helper, and the former control launch
entry for source-level traceability.

This directory is not a colcon package. Its code is not installed by the formal
ROS workspace and must not be referenced by formal launch files. It is retained
for historical reference only, not as a supported simulation, planner, or
real-device workflow.

The archived publishers emit a fixed five-joint trajectory. They do not satisfy
the current six-joint medical-arm contract and must never be used as evidence of
hardware readiness or clinical safety.
