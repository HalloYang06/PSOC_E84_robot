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
  rehab_arm_psoc_bridge/check_recording.py
  rehab_arm_psoc_bridge/build_manifest.py
  rehab_arm_psoc_bridge/sync_dry_run.py
  rehab_arm_psoc_bridge/sync_upload.py
  rehab_arm_psoc_bridge/decode_psoc_cmd.py
  rehab_arm_psoc_bridge/encode_psoc_cmd.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME}/)

ament_package()
