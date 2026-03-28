cmake_minimum_required(VERSION 3.8)
project(http_bridge)

# 设置C++标准
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 查找ROS 2依赖
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

# Python节点
ament_python_install_package(${PROJECT_NAME})

# 安装Python脚本和工具
install(PROGRAMS
    test_http_bridge.py
    start_http_bridge.sh
    run_tests.sh
    DESTINATION lib/${PROJECT_NAME}
)

# 测试
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()

# 安装launch文件
install(DIRECTORY
    launch
    DESTINATION share/${PROJECT_NAME}/
)
