from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='rehab_arm_sim_mujoco',
            executable='mujoco_sim_node.py',
            name='rehab_arm_mujoco_sim',
            output='screen',
            parameters=[{'rate_hz': 100.0}],
        ),
    ])
