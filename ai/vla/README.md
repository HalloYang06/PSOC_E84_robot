# VLA Prototype Boundary

This directory contains task parsing, grounding, schemas, validation, and offline evaluation for the VLA prototype.

Its output is limited to a high-level request or dry-run candidate. It must not issue CAN commands, motor current, torque, raw setpoints, emergency-stop release, or an M33 safety override.

ROS adapters remain in `ros/rehab_arm_ws`.
