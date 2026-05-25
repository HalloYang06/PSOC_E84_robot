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
    flush_every = LaunchConfiguration('flush_every')
    sim_rate_hz = LaunchConfiguration('sim_rate_hz')
    joint_motor_map = LaunchConfiguration('joint_motor_map')

    return LaunchDescription([
        DeclareLaunchArgument('output_dir', default_value='/home/pi/rehab_arm_logs'),
        DeclareLaunchArgument('session_id', default_value=''),
        DeclareLaunchArgument('device_id', default_value='sim-workstation'),
        DeclareLaunchArgument('robot_id', default_value='rehab-arm-alpha'),
        DeclareLaunchArgument('software_version', default_value='dev'),
        DeclareLaunchArgument('flush_every', default_value='1'),
        DeclareLaunchArgument('sim_rate_hz', default_value='100.0'),
        DeclareLaunchArgument('joint_motor_map', default_value=''),
        Node(
            package='rehab_arm_sim_mujoco',
            executable='mujoco_sim_node.py',
            name='rehab_arm_mujoco_sim',
            output='screen',
            parameters=[{
                'rate_hz': sim_rate_hz,
            }],
        ),
        Node(
            package='rehab_arm_psoc_bridge',
            executable='joint_state_motor_state_node.py',
            name='rehab_arm_joint_state_motor_state',
            output='screen',
            parameters=[{
                'robot_id': robot_id,
                'device_id': device_id,
                'source': 'simulation_joint_state_bridge',
                'joint_motor_map': joint_motor_map,
            }],
        ),
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
                'mode': 'simulation_data_collection',
                'flush_every': flush_every,
            }],
        ),
    ])
