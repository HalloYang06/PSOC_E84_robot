from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
import os

def generate_launch_description():
    # 查找包路径
    camera_client_share = FindPackageShare('camera_client')
    http_bridge_share = FindPackageShare('http_bridge')

    # 包含摄像头launch
    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            camera_client_share, '/launch/camera.launch.py'
        ])
    )

    # 包含HTTP Bridge launch
    http_bridge_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            http_bridge_share, '/launch/http_bridge.launch.py'
        ])
    )

    return LaunchDescription([
        camera_launch,
        http_bridge_launch,
    ])
