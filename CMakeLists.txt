cmake_minimum_required(VERSION 3.10)
project(camera_websocket_client)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 查找依赖
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

# 链接库
target_link_libraries(camera_websocket_client
    ${OpenCV_LIBS}
    ${Boost_LIBRARIES}
    Threads::Threads
)

# 编译选项
target_compile_options(camera_websocket_client PRIVATE -Wall -Wextra)
