cmake_minimum_required(VERSION 3.8)
project(rehab_arm_control)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  rehab_arm_control/demo_trajectory_node.py
  rehab_arm_control/vla_task_planner_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME}/)

ament_package()
