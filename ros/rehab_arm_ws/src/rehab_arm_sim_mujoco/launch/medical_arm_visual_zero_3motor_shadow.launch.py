from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('enable_viewer', default_value='true'),
        Node(
            package='rehab_arm_sim_mujoco',
            executable='mujoco_sim_node.py',
            name='medical_arm_visual_zero_3motor_shadow_sim',
            output='screen',
            parameters=[{
                'rate_hz': 100.0,
                'joint_profile': 'medical_arm_visual_zero_3motor',
                'joint_state_topic': '/sim/medical_arm/joint_states',
                'trajectory_topic': '/sim/medical_arm/joint_trajectory',
                'safety_state_topic': '/sim/medical_arm/safety_state',
                'sensor_state_topic': '/sim/medical_arm/sensor_state',
            }],
        ),
        Node(
            package='rehab_arm_sim_mujoco',
            executable='medical_arm_visualizer_node.py',
            name='medical_arm_visual_zero_viewer',
            output='screen',
            condition=IfCondition(LaunchConfiguration('enable_viewer')),
            parameters=[{
                'joint_state_topic': '/sim/medical_arm/joint_states',
            }],
        ),
    ])
