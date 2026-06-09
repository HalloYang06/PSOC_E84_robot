cmake_minimum_required(VERSION 3.8)
project(rehab_arm_psoc_bridge)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  rehab_arm_psoc_bridge/psoc_can_bridge_node.py
  rehab_arm_psoc_bridge/data_recorder_node.py
  rehab_arm_psoc_bridge/camera_keyframe_node.py
  rehab_arm_psoc_bridge/joint_state_motor_state_node.py
  rehab_arm_psoc_bridge/jsonl_replay_node.py
  rehab_arm_psoc_bridge/check_recording.py
  rehab_arm_psoc_bridge/summarize_recording.py
  rehab_arm_psoc_bridge/build_replay_plan.py
  rehab_arm_psoc_bridge/validate_recording_quality.py
  rehab_arm_psoc_bridge/export_recording_csv.py
  rehab_arm_psoc_bridge/build_manifest.py
  rehab_arm_psoc_bridge/build_annotation_queue.py
  rehab_arm_psoc_bridge/export_annotation_template.py
  rehab_arm_psoc_bridge/validate_annotations.py
  rehab_arm_psoc_bridge/build_dataset_index.py
  rehab_arm_psoc_bridge/sync_dry_run.py
  rehab_arm_psoc_bridge/sync_upload.py
  rehab_arm_psoc_bridge/check_server_quality_gate.py
  rehab_arm_psoc_bridge/sync_test_server.py
  rehab_arm_psoc_bridge/candump_motor_telemetry.py
  rehab_arm_psoc_bridge/check_m33_motor_status_presence.py
  rehab_arm_psoc_bridge/feedback_source_readiness.py
  rehab_arm_psoc_bridge/calibration_observation.py
  rehab_arm_psoc_bridge/motion_test_report.py
  rehab_arm_psoc_bridge/bench_motion_sequence.py
  rehab_arm_psoc_bridge/motor_profiles.py
  rehab_arm_psoc_bridge/board_manifest.py
  rehab_arm_psoc_bridge/board_manifest_sync_dry_run.py
  rehab_arm_psoc_bridge/decode_psoc_cmd.py
  rehab_arm_psoc_bridge/encode_psoc_cmd.py
  rehab_arm_psoc_bridge/validate_patient_profile.py
  rehab_arm_psoc_bridge/build_patient_profile_template.py
  rehab_arm_psoc_bridge/check_patient_profile_release_gate.py
  rehab_arm_psoc_bridge/export_m33_safety_subset.py
  rehab_arm_psoc_bridge/review_patient_profile_change.py
  rehab_arm_psoc_bridge/build_ble_m33_safety_package.py
  rehab_arm_psoc_bridge/build_voice_pipeline_plan.py
  rehab_arm_psoc_bridge/build_rehab_session_plan.py
  rehab_arm_psoc_bridge/build_command_center_sync_plan.py
  rehab_arm_psoc_bridge/check_command_center_sync_plan.py
  rehab_arm_psoc_bridge/check_vla_plan_candidate.py
  rehab_arm_psoc_bridge/build_mujoco_dry_run_review_plan.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME}/)

ament_package()
