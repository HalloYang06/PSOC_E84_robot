#!/usr/bin/env python3
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory

from rehab_arm_control.trajectory_utils import multijoint_demo_trajectory


class DemoTrajectoryNode(Node):
    def __init__(self):
        super().__init__('rehab_arm_demo_trajectory')
        self.publisher = self.create_publisher(
            JointTrajectory,
            '/arm_controller/joint_trajectory',
            10,
        )
        self.timer = self.create_timer(1.0, self.publish_once)
        self.published = False

    def publish_once(self):
        if self.published:
            return
        msg = multijoint_demo_trajectory()
        msg.header.stamp = self.get_clock().now().to_msg()
        self.publisher.publish(msg)
        self.published = True
        self.get_logger().info('Published multi-joint demo JointTrajectory')


def main(args=None):
    rclpy.init(args=args)
    node = DemoTrajectoryNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
