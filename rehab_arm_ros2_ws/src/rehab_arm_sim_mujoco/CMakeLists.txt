cmake_minimum_required(VERSION 3.8)
project(rehab_arm_sim_mujoco)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  rehab_arm_sim_mujoco/mujoco_sim_node.py
  rehab_arm_sim_mujoco/check_sim_env.py
  rehab_arm_sim_mujoco/upload_sim_readiness.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch models DESTINATION share/${PROJECT_NAME}/)

ament_package()
