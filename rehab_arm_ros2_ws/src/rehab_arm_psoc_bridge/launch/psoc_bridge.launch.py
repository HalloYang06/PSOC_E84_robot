from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='rehab_arm_psoc_bridge',
            executable='psoc_can_bridge_node.py',
            name='rehab_arm_psoc_bridge',
            output='screen',
            parameters=[{
                'interface': 'can0',
                'send_rate_hz': 50.0,
                'default_rpm': 5,
            }],
        ),
    ])
