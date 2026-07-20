#!/usr/bin/env python3
from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

from rehab_arm_sim_mujoco.mujoco_backend import (
    MEDICAL_ARM_VISUAL_ZERO_3MOTOR_PROFILE,
    default_model_path,
    initial_positions_for_profile,
    joint_names_for_profile,
)


class MedicalArmVisualizerNode(Node):
    def __init__(self) -> None:
        super().__init__('medical_arm_visual_zero_viewer')
        self.declare_parameter('joint_state_topic', '/sim/medical_arm/joint_states')
        self.declare_parameter('model_path', '')
        self.joint_state_topic = str(self.get_parameter('joint_state_topic').value)
        model_path = str(self.get_parameter('model_path').value or '')

        import mujoco

        self.mujoco = mujoco
        self.joint_names = joint_names_for_profile(MEDICAL_ARM_VISUAL_ZERO_3MOTOR_PROFILE)
        self.model_path = model_path or str(default_model_path(MEDICAL_ARM_VISUAL_ZERO_3MOTOR_PROFILE))
        self.model = mujoco.MjModel.from_xml_path(self.model_path)
        self.data = mujoco.MjData(self.model)
        self.qpos_addresses = {
            name: int(self.model.jnt_qposadr[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)])
            for name in self.joint_names
        }
        self.positions = dict(zip(self.joint_names, initial_positions_for_profile(MEDICAL_ARM_VISUAL_ZERO_3MOTOR_PROFILE)))
        self.create_subscription(JointState, self.joint_state_topic, self._on_joint_state, 20)
        self.apply_positions()
        self.get_logger().info(f'visualizer ready topic={self.joint_state_topic} model={self.model_path}')

    def _on_joint_state(self, msg: JointState) -> None:
        for index, name in enumerate(msg.name):
            if name in self.qpos_addresses and index < len(msg.position):
                self.positions[name] = float(msg.position[index])

    def apply_positions(self) -> None:
        for name, value in self.positions.items():
            self.data.qpos[self.qpos_addresses[name]] = value
        self.mujoco.mj_forward(self.model, self.data)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MedicalArmVisualizerNode()
    import mujoco.viewer

    try:
        with mujoco.viewer.launch_passive(node.model, node.data) as viewer:
            while rclpy.ok() and viewer.is_running():
                rclpy.spin_once(node, timeout_sec=0.0)
                node.apply_positions()
                viewer.sync()
                time.sleep(1.0 / 60.0)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
