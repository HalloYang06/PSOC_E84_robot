from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='rehab_arm_control',
            executable='vla_task_planner_node.py',
            name='rehab_arm_vla_task_planner',
            output='screen',
        ),
    ])
