from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape


JOINT_NAMES = [
    'shoulder_lift_joint',
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
    'forearm_rotation_joint',
]

LIMITS = {
    'shoulder_lift_joint': (-0.70, 1.40, 0.60),
    'elbow_lift_joint': (0.00, 1.80, 0.70),
    'shoulder_abduction_joint': (-0.45, 0.80, 0.40),
    'upper_arm_rotation_joint': (-1.20, 1.20, 0.70),
    'forearm_rotation_joint': (-1.20, 1.20, 0.70),
}


@dataclass(frozen=True)
class JointSpec:
    name: str
    axis: str
    range_min: float
    range_max: float
    link_length: float
    link_radius: float


JOINT_SPECS = [
    JointSpec('shoulder_lift_joint', '0 1 0', -0.70, 1.40, 0.30, 0.035),
    JointSpec('elbow_lift_joint', '0 1 0', 0.00, 1.80, 0.32, 0.030),
    JointSpec('shoulder_abduction_joint', '0 0 1', -0.45, 0.80, 0.22, 0.028),
    JointSpec('upper_arm_rotation_joint', '1 0 0', -1.20, 1.20, 0.20, 0.026),
    JointSpec('forearm_rotation_joint', '1 0 0', -1.20, 1.20, 0.18, 0.024),
]


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def clamp_positions(positions: list[float]) -> list[float]:
    clamped = [0.0] * len(JOINT_NAMES)
    for index, name in enumerate(JOINT_NAMES):
        if index >= len(positions):
            break
        low, high, _ = LIMITS[name]
        clamped[index] = clamp(float(positions[index]), low, high)
    return clamped


def build_rehab_arm_mjcf() -> str:
    body_xml = ''
    indent = '    '
    for index, spec in enumerate(JOINT_SPECS):
        joint_name = escape(spec.name)
        body_name = escape(spec.name.replace('_joint', '_body'))
        geom_pos = spec.link_length / 2.0
        child_pos = spec.link_length
        body_xml += (
            f'{indent * (index + 1)}<body name="{body_name}" pos="{child_pos if index else 0} 0 0">\n'
            f'{indent * (index + 2)}<joint name="{joint_name}" type="hinge" axis="{spec.axis}" '
            f'range="{spec.range_min} {spec.range_max}" limited="true" damping="1.0"/>\n'
            f'{indent * (index + 2)}<geom type="capsule" fromto="0 0 0 {spec.link_length} 0 0" '
            f'size="{spec.link_radius}" mass="0.2"/>\n'
        )

    for index in reversed(range(len(JOINT_SPECS))):
        body_xml += f'{indent * (index + 1)}</body>\n'

    actuators = '\n'.join(
        f'    <position joint="{escape(name)}" kp="35" kv="4" ctrlrange="{LIMITS[name][0]} {LIMITS[name][1]}"/>'
        for name in JOINT_NAMES
    )

    return (
        '<mujoco model="rehab_arm_minimal">\n'
        '  <compiler angle="radian"/>\n'
        '  <option timestep="0.002" gravity="0 0 -9.81"/>\n'
        '  <worldbody>\n'
        '    <body name="base" pos="0 0 0.8">\n'
        '      <geom type="sphere" size="0.04" mass="0.5"/>\n'
        f'{body_xml}'
        '    </body>\n'
        '  </worldbody>\n'
        '  <actuator>\n'
        f'{actuators}\n'
        '  </actuator>\n'
        '</mujoco>\n'
    )


class RehabArmMujocoBackend:
    def __init__(self, mujoco_module=None):
        if mujoco_module is None:
            import mujoco as mujoco_module  # type: ignore[no-redef]
        self.mujoco = mujoco_module
        self.model = self.mujoco.MjModel.from_xml_string(build_rehab_arm_mjcf())
        self.data = self.mujoco.MjData(self.model)
        self.joint_qpos_addr = [
            self.model.jnt_qposadr[
                self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_JOINT, name)
            ]
            for name in JOINT_NAMES
        ]
        self.target_positions = [0.0] * len(JOINT_NAMES)

    def step(self, target_positions: list[float], dt: float) -> list[float]:
        self.target_positions = clamp_positions(target_positions)
        safe_dt = max(dt, self.model.opt.timestep)
        for index, target in enumerate(self.target_positions):
            name = JOINT_NAMES[index]
            low, high, velocity_limit = LIMITS[name]
            address = self.joint_qpos_addr[index]
            current = float(self.data.qpos[address])
            next_position = clamp(
                current + clamp(target - current, -velocity_limit * safe_dt, velocity_limit * safe_dt),
                low,
                high,
            )
            self.data.qpos[address] = next_position
            self.data.qvel[index] = (next_position - current) / safe_dt
            self.data.ctrl[index] = target

        self.mujoco.mj_forward(self.model, self.data)
        return self.positions()

    def positions(self) -> list[float]:
        return [float(self.data.qpos[address]) for address in self.joint_qpos_addr]
