from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # HTTP Bridge节点
    http_bridge_node = Node(
        package='http_bridge',
        executable='http_bridge_server',
        name='http_bridge_server',
        output='screen',
        parameters=[{
            'port': 8081,
        }]
    )

    return LaunchDescription([
        http_bridge_node,
    ])
