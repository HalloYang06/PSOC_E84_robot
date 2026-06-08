# Rehab Arm Current System Handoff - 2026-06-08

AI identity: Codex GPT-5
Role: Rehab arm mainline / MuJoCo / NanoPi / M33 handoff keeper

This document is the current thread-to-thread handoff for the Medical Rehabilitation Manipulator repository. Use it before relying on chat history.

## Repository Baseline

- Main ROS2/NanoPi/MuJoCo repo: `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan`
- Main branch: `feature/rehab-arm-ros2-architecture`
- Latest main commit at handoff: `2869ce23 Map installed motors into MuJoCo shadow`
- M33 firmware repo/workspace: `D:\RT-ThreadStudio\workspace\yiliao_m33`
- M33 branch: `M33`
- Latest M33 commit pushed at handoff: `192ad049 Stabilize M33 BLE and model bridge telemetry`
- M55 local working project: `D:\RT-ThreadStudio\workspace\wifi`
- M55 Git evidence repo: `D:\RT-ThreadStudio\workspace\_m55_ref_repo`

Do not commit credentials into GitHub. Host IPs and usernames are recorded here; passwords were provided by the user during live bring-up and should remain out of repo documents.

## Active Devices And Hosts

| Node | Address / workspace | Role | Current status |
|---|---|---|---|
| NanoPi | `pi@192.168.2.66` | SocketCAN, ROS2 bridge, M33 status parser, camera/server gateway | Online during latest validation; `can0` was `ERROR-ACTIVE`, `berr-counter tx 0 rx 0`; `rehab-arm-nanopi-readonly.service` active/enabled |
| Linux sim host | `cal@192.168.2.46`, workspace `/home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws` | MuJoCo 6DOF hardware shadow over wireless ROS2 | Online during latest validation; `rehab-arm-sim-host-shadow.service` active/enabled; `/sim/medical_arm/joint_states` about 100 Hz |
| M33 | PSoC Edge E84 M33, local workspace `yiliao_m33` | CAN master, final safety authority, M33/M55 IPC endpoint, BLE App endpoint, motor telemetry aggregation | Running and publishing `0x322` plus `0x330~0x334`; latest firmware commit pushed |
| M55 | PSoC Edge E84 M55, local workspace `wifi` | EMG/voice/audio small model runtime, model result publisher, M33 data consumer | Previously validated with `req_snap` and `req_m7`; current TFLM model is still a validation model, not final EMG model |
| C8T6 sensor board | not powered in last full-chain validation | 4-channel EMG/sensor acquisition toward M33 | Not part of latest validation; keep expected path `C8T6 -> M33 -> M55/NanoPi` |
| Server/VLA | server endpoint not finalized in this repo | High-level VLA task/trajectory candidate generation | Must remain suggestion/dry-run until M33 safety accepts; no direct CAN or motor control |
| Android App | branch `APP` | BLE to M33 for local display/request/annotation; HTTP high-level service path | Do not let App bypass M33 or NanoPi safety contracts |

## Mainline Architecture Contract

Formal motion path:

```text
JointTrajectory -> NanoPi -> M33 -> motor
```

Read-only/shadow path currently validated:

```text
M33 motor status 0x330~0x333
-> NanoPi /joint_states
-> wireless ROS2
-> Linux sim host medical_arm_shadow_relay
-> /sim/medical_arm/joint_trajectory
-> MuJoCo /sim/medical_arm/joint_states
```

Safety boundaries:

- M33 is final safety authority.
- NanoPi product service stays read-only by default: `enable_target_tx=false`.
- `nanopi_can_master.py` direct motor commands are bench-debug only.
- MuJoCo hardware shadow is `shadow-sim`; it must not control real motors directly.
- M55, App BLE, server/VLA outputs are suggestions/status/labels until the formal path and M33 safety gate accept them.
- Always confirm no unexpected `0x320` target frames during read-only or shadow checks.

## Current Motor And Joint Mapping

Medical-arm MuJoCo joints:

```text
jian_hengxiang_joint
jian_zongxiang_joint
jian_xuanzhuan_joint
zhou_zongxiang_joint
wanbu_zongxiang_joint
wanbu_hengxiang_joint
```

Installed/currently known mappings:

| Motor / node | Protocol / type | Legacy ROS joint from NanoPi | MuJoCo medical joint | Notes |
|---|---|---|---|---|
| `node_id=3` | Sitaiwei CANSimple / ODrive-like | `shoulder_lift_joint` | `jian_hengxiang_joint` | Installed. User says external pulley ratio is motor-side:joint-side `1:2`; output joint angle is about motor angle `0.5`. Current code metadata still has CANSimple protocol-side reduction fields; final direction/zero/ratio must be calibrated. |
| `motor_id=4` | Lingzu RS00 private extended-frame / RobStride CSP | `elbow_lift_joint` | `jian_zongxiang_joint` | Installed. Shoulder longitudinal. Multi-gear mechanical ratio unknown; current command semantics treat RobStride CSP `loc_ref` as output-side rad until calibration proves otherwise. |
| `motor_id=5` | Lingzu RS00 private extended-frame / RobStride CSP | `shoulder_abduction_joint` | `zhou_zongxiang_joint` | Installed. Elbow longitudinal. Direction/zero/output scale pending calibration. |
| `motor_id=6` | Lingzu EL05 private extended-frame / RobStride CSP | `upper_arm_rotation_joint` | `jian_xuanzhuan_joint` | Installed. Shoulder/upper-arm rotation. Direction/zero pending calibration. |
| `motor_id=1` | 4015 small motor, protocol pending | not wired | wrist axis pending | Not wired in latest validation. One of `wanbu_zongxiang_joint` or `wanbu_hengxiang_joint`. |
| `motor_id=2` | 4015 small motor, protocol pending | not wired | wrist axis pending | Not wired in latest validation. One of `wanbu_zongxiang_joint` or `wanbu_hengxiang_joint`. |
| `motor_id=7` | Lingzu EL05 private extended-frame / RobStride CSP | `forearm_rotation_joint` historically | none by default | External bench motor only. Do not use as default medical-arm shadow source. |

Current MuJoCo hardware shadow default mapping:

```text
shoulder_lift_joint      -> jian_hengxiang_joint
elbow_lift_joint         -> jian_zongxiang_joint
shoulder_abduction_joint -> zhou_zongxiang_joint
upper_arm_rotation_joint -> jian_xuanzhuan_joint
```

Wrist joints currently remain placeholder `0.0` in hardware shadow until motors 1/2 are wired and mapped.

## Latest Validation Summary

NanoPi checks:

- `can0` state: `ERROR-ACTIVE`, `berr-counter tx 0 rx 0`.
- `rehab-arm-nanopi-readonly.service`: active/enabled.
- M33 heartbeat reply visible: `0x321 -> 0x322`.
- M33 aggregate slots visible: `0x330~0x334`.
- 3号 slot `0x330` fresh with flags `0x01`.
- 4/5/6 are normally stale after active-report cleanup; they become fresh when active-report is temporarily enabled.
- `timeout 2 candump -L can0,320:7FF` had no output during final safety check.

Simulation host checks:

- `rehab-arm-sim-host-shadow.service`: active/enabled.
- Build command passed remotely:

```bash
cd /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select rehab_arm_sim_mujoco --symlink-install
```

- `/sim/medical_arm/joint_states` publishes at about `99.9 Hz`.
- With only 3号 fresh, MuJoCo shadow outputs six joints with `jian_hengxiang_joint=0.0` and others at placeholders.
- With temporary 4/5/6 active-report, NanoPi `/joint_states` published:

```text
shoulder_lift_joint=0.0
elbow_lift_joint=2.563
shoulder_abduction_joint=6.324
upper_arm_rotation_joint=4.507
```

- Relay output mapped to MuJoCo target positions:

```text
[jian_hengxiang, jian_zongxiang, jian_xuanzhuan, zhou_zongxiang, wanbu_zongxiang, wanbu_hengxiang]
[0.0, 2.563, 4.507, 6.324, 0.0, 0.0]
```

- MuJoCo then clamped by current limits to:

```text
[0.0, 1.7453, 1.0472, 2.3562, 0.0, 0.0]
```

This limit clamp is expected with current conservative model limits; it is not yet calibrated physical truth.

## M33 Firmware Handoff

Latest pushed M33 commit: `192ad049 Stabilize M33 BLE and model bridge telemetry`.

What changed:

- `applications/m33/app_ble_service.c`: formats BLE telemetry JSON without relying on `%f`; this avoids embedded printf float-format issues and keeps App telemetry stable.
- `applications/m33/m55_model_bridge.c`: captures and logs `control_publish_m55_model_result()` return value as `can_ret`, so M55 result-to-CAN failures are visible in serial logs.

Build validation:

```powershell
$env:Path = 'D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin;' + $env:Path
mingw32-make -C D:\RT-ThreadStudio\workspace\yiliao_m33\Debug all -j4
```

Result:

```text
text=580412 data=15512 bss=311269 dec=907193 hex=dd7b9 rtthread.elf
```

Uncommitted in M33 workspace and intentionally not pushed:

- `.settings/projcfg.ini`: RT-Thread Studio timestamp-only local change.
- `.codex_tmp/`: local debug captures and scratch files.
- `docs/ai-handoffs/`: older local handoff files in M33 workspace.
- `tools/serial_bridge_logger.ps1` plus local tool bundles: not part of this firmware commit.

## Useful Commands For Next AI

NanoPi read-only checks:

```bash
ssh pi@192.168.2.66 "ip -details -statistics link show can0; systemctl is-active rehab-arm-nanopi-readonly.service"
ssh pi@192.168.2.66 "timeout 6 candump -L can0,321:7FF,322:7FF,323:7FF,330:7F8,320:7FF"
ssh pi@192.168.2.66 "source /opt/ros/jazzy/setup.bash; source ~/.rehab_arm_ros2_network; source /home/pi/rehab_arm_ros2_ws/install/setup.bash; timeout 6 ros2 topic echo --once /joint_states sensor_msgs/msg/JointState"
```

Temporary 4/5/6 telemetry check, then cleanup:

```bash
ssh pi@192.168.2.66 'for m in 4 5 6; do python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor $m --enable-report --wait 0.1; done'
ssh pi@192.168.2.66 'for m in 4 5 6; do python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor $m --wait 0.1; done'
ssh pi@192.168.2.66 "timeout 2 candump -L can0,320:7FF || true"
```

Simulation host checks:

```bash
ssh cal@192.168.2.46
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws/install/setup.bash
ros2 topic echo --once /sim/medical_arm/joint_states
ros2 topic hz /sim/medical_arm/joint_states
journalctl -u rehab-arm-sim-host-shadow.service -n 80 --no-pager
```

M33 firmware pull on another computer:

```bash
git clone -b M33 https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git yiliao_m33
# or, in an existing clone:
git checkout M33
git pull origin M33
git log -1 --oneline
```

Expected latest M33 commit:

```text
192ad049 Stabilize M33 BLE and model bridge telemetry
```

## Next Steps

1. Calibrate installed 3/4/5/6 directions, zeros, and output-side ratios using read-only telemetry first.
2. Decide whether 4/5/6 active-report should be enabled by M33 startup logic or by a safe bring-up state, instead of relying on NanoPi debug commands.
3. Wire and identify 1/2 wrist motors; add protocol, mapping, limits, and shadow mapping only after read-only feedback is fresh.
4. Bring C8T6 4-channel EMG online and route it through `C8T6 -> M33 -> M55 -> M33 -> 0x323 -> NanoPi /rehab_arm/model_state`.
5. Replace the M55 validation model with a real int8 TFLite Micro model once EMG window features and labels are available.
6. Keep VLA/server outputs as high-level suggestions or dry-run trajectory candidates until MuJoCo and M33 safety both accept them.

