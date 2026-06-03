from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='rehab_arm_sim_mujoco',
            executable='mujoco_sim_node.py',
            name='medical_arm_6dof_shadow_sim',
            output='screen',
            parameters=[{
                'rate_hz': 100.0,
                'joint_profile': 'medical_arm_6dof',
                'joint_state_topic': '/sim/medical_arm/joint_states',
                'trajectory_topic': '/sim/medical_arm/joint_trajectory',
                'safety_state_topic': '/sim/medical_arm/safety_state',
                'sensor_state_topic': '/sim/medical_arm/sensor_state',
            }],
        ),
        Node(
            package='rehab_arm_sim_mujoco',
            executable='medical_arm_shadow_relay_node.py',
            name='medical_arm_shadow_relay',
            output='screen',
            parameters=[{
                'source_joint_state_topic': '/joint_states',
                'target_trajectory_topic': '/sim/medical_arm/joint_trajectory',
                'joint_map_json': '{"forearm_rotation_joint":"jian_xuanzhuan_joint"}',
                'publish_full_target': True,
                'target_joint_names_json': (
                    '["jian_hengxiang_joint","jian_zongxiang_joint","jian_xuanzhuan_joint",'
                    '"zhou_zongxiang_joint","wanbu_zongxiang_joint","wanbu_hengxiang_joint"]'
                ),
                'placeholder_positions_json': (
                    '{"jian_hengxiang_joint":0.0,"jian_zongxiang_joint":0.0,'
                    '"jian_xuanzhuan_joint":0.0,"zhou_zongxiang_joint":0.0,'
                    '"wanbu_zongxiang_joint":0.0,"wanbu_hengxiang_joint":0.0}'
                ),
                'duration_sec': 0.25,
            }],
        ),
    ])
