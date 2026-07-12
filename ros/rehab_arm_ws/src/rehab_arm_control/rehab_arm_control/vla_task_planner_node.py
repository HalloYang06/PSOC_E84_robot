#!/usr/bin/env python3
import json

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory

from rehab_arm_control.trajectory_utils import multijoint_demo_trajectory


class VlaTaskPlannerNode(Node):
    def __init__(self):
        super().__init__('rehab_arm_vla_task_planner')
        self.publisher = self.create_publisher(
            JointTrajectory,
            '/arm_controller/joint_trajectory',
            10,
        )
        self.subscription = self.create_subscription(
            String,
            '/vla/task_goal',
            self.on_task_goal,
            10,
        )
        self.get_logger().info('VLA task planner placeholder ready')

    def on_task_goal(self, msg: String):
        try:
            goal = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f'Ignoring invalid VLA JSON: {msg.data}')
            return

        task = str(goal.get('task', 'preset_reach'))
        if task not in ('preset_reach', 'assist_reach', 'demo_training'):
            self.get_logger().warn(f'Unknown task {task!r}, using preset_reach')

        trajectory = multijoint_demo_trajectory()
        trajectory.header.stamp = self.get_clock().now().to_msg()
        self.publisher.publish(trajectory)
        self.get_logger().info(f'Converted VLA task {task!r} to JointTrajectory')


def main(args=None):
    rclpy.init(args=args)
    node = VlaTaskPlannerNode()
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
