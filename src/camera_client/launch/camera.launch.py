from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    # 声明参数
    server_ip_arg = DeclareLaunchArgument(
        'server_ip',
        default_value='10.100.191.235',
        description='WebSocket server IP address'
    )

    server_port_arg = DeclareLaunchArgument(
        'server_port',
        default_value='8080',
        description='WebSocket server port'
    )

    camera_id_arg = DeclareLaunchArgument(
        'camera_id',
        default_value='-1',
        description='Camera device ID (-1 for auto-detect)'
    )

    fps_arg = DeclareLaunchArgument(
        'fps',
        default_value='10',
        description='Target frame rate'
    )

    # 摄像头节点
    camera_node = Node(
        package='camera_client',
        executable='camera_websocket_client',
        name='camera_websocket_client',
        output='screen',
        parameters=[{
            'server_ip': LaunchConfiguration('server_ip'),
            'server_port': LaunchConfiguration('server_port'),
            'camera_id': LaunchConfiguration('camera_id'),
            'fps': LaunchConfiguration('fps'),
        }]
    )

    return LaunchDescription([
        server_ip_arg,
        server_port_arg,
        camera_id_arg,
        fps_arg,
        camera_node,
    ])
