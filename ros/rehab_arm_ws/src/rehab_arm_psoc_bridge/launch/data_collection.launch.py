from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    output_dir = LaunchConfiguration('output_dir')
    session_id = LaunchConfiguration('session_id')
    device_id = LaunchConfiguration('device_id')
    robot_id = LaunchConfiguration('robot_id')
    software_version = LaunchConfiguration('software_version')
    mode = LaunchConfiguration('mode')
    flush_every = LaunchConfiguration('flush_every')

    return LaunchDescription([
        DeclareLaunchArgument('output_dir', default_value='/home/pi/rehab_arm_logs'),
        DeclareLaunchArgument('session_id', default_value=''),
        DeclareLaunchArgument('device_id', default_value='nanopi-m5'),
        DeclareLaunchArgument('robot_id', default_value='rehab-arm-alpha'),
        DeclareLaunchArgument('software_version', default_value='dev'),
        DeclareLaunchArgument('mode', default_value='logging_only'),
        DeclareLaunchArgument('flush_every', default_value='1'),
        Node(
            package='rehab_arm_psoc_bridge',
            executable='data_recorder_node.py',
            name='rehab_arm_data_recorder',
            output='screen',
            parameters=[{
                'output_dir': output_dir,
                'session_id': session_id,
                'device_id': device_id,
                'robot_id': robot_id,
                'software_version': software_version,
                'mode': mode,
                'flush_every': flush_every,
            }],
        ),
    ])
