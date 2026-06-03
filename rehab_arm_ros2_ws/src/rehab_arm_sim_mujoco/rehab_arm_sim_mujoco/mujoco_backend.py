from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


LEGACY_5DOF_PROFILE = 'legacy_5dof'
MEDICAL_ARM_6DOF_PROFILE = 'medical_arm_6dof'

JOINT_NAMES = [
    'shoulder_lift_joint',
    'elbow_lift_joint',
    'shoulder_abduction_joint',
    'upper_arm_rotation_joint',
    'forearm_rotation_joint',
]

MEDICAL_ARM_6DOF_JOINT_NAMES = [
    'jian_hengxiang_joint',
    'jian_zongxiang_joint',
    'jian_xuanzhuan_joint',
    'zhou_zongxiang_joint',
    'wanbu_zongxiang_joint',
    'wanbu_hengxiang_joint',
]

LIMITS = {
    'shoulder_lift_joint': (-0.70, 1.40, 0.60),
    'elbow_lift_joint': (0.00, 1.80, 0.70),
    'shoulder_abduction_joint': (-0.45, 0.80, 0.40),
    'upper_arm_rotation_joint': (-1.20, 1.20, 0.70),
    'forearm_rotation_joint': (-1.20, 1.20, 0.70),
}

MEDICAL_ARM_6DOF_LIMITS = {
    'jian_hengxiang_joint': (-0.7854, 1.5708, 0.35),
    'jian_zongxiang_joint': (-0.5236, 1.7453, 0.35),
    'jian_xuanzhuan_joint': (-1.0472, 1.0472, 0.45),
    'zhou_zongxiang_joint': (0.0, 2.3562, 0.45),
    'wanbu_zongxiang_joint': (-0.7854, 0.7854, 0.60),
    'wanbu_hengxiang_joint': (-0.3491, 0.5236, 0.60),
}


@dataclass(frozen=True)
class JointSpec:
    name: str
    axis: str
    range_min: float
    range_max: float
    link_length: float
    link_radius: float


LEGACY_5DOF_JOINT_SPECS = [
    JointSpec('shoulder_lift_joint', '0 1 0', -0.70, 1.40, 0.30, 0.035),
    JointSpec('elbow_lift_joint', '0 1 0', 0.00, 1.80, 0.32, 0.030),
    JointSpec('shoulder_abduction_joint', '0 0 1', -0.45, 0.80, 0.22, 0.028),
    JointSpec('upper_arm_rotation_joint', '1 0 0', -1.20, 1.20, 0.20, 0.026),
    JointSpec('forearm_rotation_joint', '1 0 0', -1.20, 1.20, 0.18, 0.024),
]

MEDICAL_ARM_6DOF_JOINT_SPECS = [
    JointSpec('jian_hengxiang_joint', '0 0 1', -0.7854, 1.5708, 0.18, 0.040),
    JointSpec('jian_zongxiang_joint', '0 1 0', -0.5236, 1.7453, 0.24, 0.038),
    JointSpec('jian_xuanzhuan_joint', '1 0 0', -1.0472, 1.0472, 0.18, 0.034),
    JointSpec('zhou_zongxiang_joint', '0 1 0', 0.0, 2.3562, 0.28, 0.032),
    JointSpec('wanbu_zongxiang_joint', '0 1 0', -0.7854, 0.7854, 0.12, 0.026),
    JointSpec('wanbu_hengxiang_joint', '0 0 1', -0.3491, 0.5236, 0.10, 0.024),
]

JOINT_SPECS = LEGACY_5DOF_JOINT_SPECS

JOINT_PROFILE_CONFIGS = {
    LEGACY_5DOF_PROFILE: {
        'model_name': 'rehab_arm_minimal',
        'joint_names': JOINT_NAMES,
        'limits': LIMITS,
        'specs': LEGACY_5DOF_JOINT_SPECS,
        'model_filename': 'rehab_arm_minimal.xml',
    },
    MEDICAL_ARM_6DOF_PROFILE: {
        'model_name': 'medical_arm_6dof_shadow',
        'joint_names': MEDICAL_ARM_6DOF_JOINT_NAMES,
        'limits': MEDICAL_ARM_6DOF_LIMITS,
        'specs': MEDICAL_ARM_6DOF_JOINT_SPECS,
        'model_filename': 'medical_arm_6dof.xml',
    },
}


def normalize_joint_profile(joint_profile: str | None) -> str:
    profile = str(joint_profile or LEGACY_5DOF_PROFILE).strip() or LEGACY_5DOF_PROFILE
    if profile not in JOINT_PROFILE_CONFIGS:
        choices = ', '.join(sorted(JOINT_PROFILE_CONFIGS))
        raise ValueError(f'unknown joint_profile {profile!r}; expected one of: {choices}')
    return profile


def joint_names_for_profile(joint_profile: str | None) -> list[str]:
    profile = normalize_joint_profile(joint_profile)
    return list(JOINT_PROFILE_CONFIGS[profile]['joint_names'])  # type: ignore[arg-type]


def limits_for_profile(joint_profile: str | None) -> dict[str, tuple[float, float, float]]:
    profile = normalize_joint_profile(joint_profile)
    return dict(JOINT_PROFILE_CONFIGS[profile]['limits'])  # type: ignore[arg-type]


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def clamp_positions(positions: list[float], joint_profile: str | None = None) -> list[float]:
    joint_names = joint_names_for_profile(joint_profile)
    limits = limits_for_profile(joint_profile)
    clamped = [0.0] * len(joint_names)
    for index, name in enumerate(joint_names):
        if index >= len(positions):
            break
        low, high, _ = limits[name]
        clamped[index] = clamp(float(positions[index]), low, high)
    return clamped


def default_model_path(joint_profile: str | None = None) -> Path:
    profile = normalize_joint_profile(joint_profile)
    filename = str(JOINT_PROFILE_CONFIGS[profile]['model_filename'])
    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory('rehab_arm_sim_mujoco')) / 'models' / filename
    except Exception:
        return Path(__file__).resolve().parents[1] / 'models' / filename


def load_mjcf_xml(model_path: str | None = None, joint_profile: str | None = None) -> str:
    if not model_path:
        path = default_model_path(joint_profile)
    else:
        path = Path(model_path).expanduser()
    if path.exists():
        return path.read_text(encoding='utf-8')
    return build_rehab_arm_mjcf(joint_profile)


def build_rehab_arm_mjcf(joint_profile: str | None = None) -> str:
    profile = normalize_joint_profile(joint_profile)
    config = JOINT_PROFILE_CONFIGS[profile]
    model_name = escape(str(config['model_name']))
    joint_names = list(config['joint_names'])  # type: ignore[arg-type]
    limits = dict(config['limits'])  # type: ignore[arg-type]
    specs = list(config['specs'])  # type: ignore[arg-type]
    body_xml = ''
    indent = '    '
    for index, spec in enumerate(specs):
        joint_name = escape(spec.name)
        body_name = escape(spec.name.replace('_joint', '_body'))
        child_pos = spec.link_length
        body_xml += (
            f'{indent * (index + 1)}<body name="{body_name}" pos="{child_pos if index else 0} 0 0">\n'
            f'{indent * (index + 2)}<joint name="{joint_name}" type="hinge" axis="{spec.axis}" '
            f'range="{spec.range_min} {spec.range_max}" limited="true" damping="1.0"/>\n'
            f'{indent * (index + 2)}<geom type="capsule" fromto="0 0 0 {spec.link_length} 0 0" '
            f'size="{spec.link_radius}" mass="0.2"/>\n'
        )

    for index in reversed(range(len(specs))):
        body_xml += f'{indent * (index + 1)}</body>\n'

    actuators = '\n'.join(
        f'    <position name="{escape(name)}_pos" joint="{escape(name)}" kp="35" kv="4" ctrlrange="{limits[name][0]} {limits[name][1]}"/>'
        for name in joint_names
    )

    return (
        f'<mujoco model="{model_name}">\n'
        '  <compiler angle="radian"/>\n'
        '  <option timestep="0.002" gravity="0 0 -9.81"/>\n'
        '  <visual>\n'
        '    <headlight ambient="0.45 0.45 0.45" diffuse="0.7 0.7 0.7" specular="0.2 0.2 0.2"/>\n'
        '  </visual>\n'
        '  <worldbody>\n'
        '    <geom name="floor" type="plane" pos="0 0 0" size="1.2 1.2 0.02" rgba="0.82 0.84 0.86 1"/>\n'
        '    <light name="key_light" pos="0.2 -0.8 1.8" dir="0 0 -1"/>\n'
        '    <body name="base" pos="0 0 0.8">\n'
        '      <geom type="cylinder" size="0.06 0.04" rgba="0.18 0.20 0.24 1" mass="0.5"/>\n'
        f'{body_xml}'
        '    </body>\n'
        '  </worldbody>\n'
        '  <actuator>\n'
        f'{actuators}\n'
        '  </actuator>\n'
        '</mujoco>\n'
    )


class RehabArmMujocoBackend:
    def __init__(self, model_path: str | None = None, joint_profile: str | None = None, mujoco_module=None):
        if mujoco_module is None:
            import mujoco as mujoco_module  # type: ignore[no-redef]
        self.mujoco = mujoco_module
        self.joint_profile = normalize_joint_profile(joint_profile)
        self.joint_names = joint_names_for_profile(self.joint_profile)
        self.limits = limits_for_profile(self.joint_profile)
        self.model_path = str(model_path or default_model_path(self.joint_profile))
        self.model = self.mujoco.MjModel.from_xml_string(load_mjcf_xml(model_path, self.joint_profile))
        self.data = self.mujoco.MjData(self.model)
        self.joint_qpos_addr = [
            self.model.jnt_qposadr[
                self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_JOINT, name)
            ]
            for name in self.joint_names
        ]
        self.target_positions = [0.0] * len(self.joint_names)

    def step(self, target_positions: list[float], dt: float) -> list[float]:
        self.target_positions = clamp_positions(target_positions, self.joint_profile)
        safe_dt = max(dt, self.model.opt.timestep)
        for index, target in enumerate(self.target_positions):
            name = self.joint_names[index]
            low, high, velocity_limit = self.limits[name]
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
