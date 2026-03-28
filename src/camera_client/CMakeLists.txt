cmake_minimum_required(VERSION 3.8)
project(camera_client)

# 设置C++标准
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 查找ROS 2依赖
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)

# 查找其他依赖
find_package(OpenCV REQUIRED)
find_package(Boost REQUIRED COMPONENTS system)
find_package(Threads REQUIRED)

# 包含目录
include_directories(
    ${OpenCV_INCLUDE_DIRS}
    ${Boost_INCLUDE_DIRS}
)

# 可执行文件
add_executable(camera_websocket_client camera_websocket_client.cpp)

# ROS 2依赖
ament_target_dependencies(camera_websocket_client
    rclcpp
    sensor_msgs
    cv_bridge
    image_transport
)

# 链接库
target_link_libraries(camera_websocket_client
    ${OpenCV_LIBS}
    ${Boost_LIBRARIES}
    Threads::Threads
)

# 安装
install(TARGETS
    camera_websocket_client
    DESTINATION lib/${PROJECT_NAME}
)

install(PROGRAMS
    run_camera.sh
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
