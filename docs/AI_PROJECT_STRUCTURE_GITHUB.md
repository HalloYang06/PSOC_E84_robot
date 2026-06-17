# AI Project Index

This document is the stable entry index for AI agents working on the Medical Rehabilitation Manipulator repository.

It should not be used as a daily progress log. Update it only when the repository structure, branch ownership, document map, or agent operating rules change.

Scope note:

- This index only expands the routes I have personally checked on the current integration branch and the verified subsystem homes around it.
- It intentionally names M33, NanoPi, Linux sim host, and the formal/shadow/bench routes first.
- Unchecked subsystem branches stay ownership-only until their responsible AI verifies them.

Repository:

```text
https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator
```

## 1. How To Use This Index

Every AI agent should start here, then follow the document map for the subsystem it is touching.

Read order for any task:

1. `README.md`
2. `docs/AI_PROJECT_STRUCTURE_GITHUB.md`
3. `docs/CURRENT_MAINLINES.md`
4. The subsystem-specific documents listed below
5. `docs/PROJECT_PROGRESS.md` for latest state
6. `docs/TROUBLESHOOTING_AND_LESSONS.md` for known pitfalls

Before changing code or docs, classify the task:

```text
mainline / shadow-sim / dry-run / bench-debug / offline-demo / side-channel
```

If the classification is unclear, default to read-only, `shadow-sim`, or `dry-run`.

## 2. Document Update Policy

### Update On Every Relevant Task

These documents are living records and should be updated whenever the task changes their content.

| Path | Update when |
|---|---|
| `docs/PROJECT_PROGRESS.md` | Any meaningful task changes state, validates hardware/software, adds docs, changes architecture, or discovers a blocker |
| `docs/TROUBLESHOOTING_AND_LESSONS.md` | Any debugging, failed command, hardware/CAN/ROS issue, confusing behavior, workaround, or reusable lesson |
| `docs/USER_MANUAL.md` | User-facing commands, workflows, setup, safety notes, validation steps, or expected outputs change |
| `docs/CURRENT_MAINLINES.md` | Current mainline boundaries, subsystem responsibilities, or active/inactive branch meaning changes |
| `docs/MAINLINE_DEVELOPMENT_GUIDE.md` | The recommended development sequence or mainline workflow changes |

### Update Only For Architecture Or Contract Changes

These documents should remain relatively stable.

| Path | Update when |
|---|---|
| `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md` | System architecture, ownership boundary, or safety authority changes |
| `docs/PSOC_CAN_PROTOCOL_V1.md` | M33/PSoC CAN protocol changes |
| `docs/MOTOR_PROTOCOLS.md` | Motor protocol, unit, scaling, frame format, or drive semantics change |
| `docs/M33_SAFETY_INPUT_MAPPING.md` | M33 safety inputs, pre-arm rules, or safe/confirmed semantics change |
| `docs/M33_M55_IPC_BLE_FOUNDATION.md` | M33/M55 IPC or BLE foundation changes |
| `docs/M33_M55_MODEL_INPUT_PROTOCOL_V1.md` | M33-to-M55 model input contract changes |
| `docs/M55_MODEL_RESULT_PROTOCOL_V1.md` | M55 model result format or semantics change |
| `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` | Patient/device profile schema changes |
| `docs/COMMAND_CENTER_APP_PROTOCOL_V1.md` | App/command-center API contract changes |
| `docs/SERVER_SYNC_API_DRAFT.md` | Server sync API changes |

### Stable Index Documents

These should rarely change.

| Path | Update when |
|---|---|
| `docs/AI_PROJECT_STRUCTURE_GITHUB.md` | Branch map, document index, skill map, or repository organization changes |
| `docs/DOCUMENTATION_CLEANUP_AUDIT.md` | Documentation cleanup policy or archive/delete recommendations change |
| `README.md` | Top-level project entry or required reading list changes |

## 3. Useful Skills For AI Agents

Use these skills when available in the Codex environment. If a skill is unavailable, follow the same intent manually.

| Skill | Use for |
|---|---|
| `rehab-arm-task-closeout` | End-of-task updates, commit, and push discipline for this project |
| `rehab-arm-progress-keeper` | Keeping `PROJECT_PROGRESS.md` and `TROUBLESHOOTING_AND_LESSONS.md` current |
| `embedded-can-debug` | CAN bring-up, no heartbeat, no ACK, motor telemetry, SocketCAN, PSoC, NanoPi, STM32/C8T6 debugging |
| `stm32-keil-pyocd-motor-debug` | STM32/Keil/pyOCD motor or firmware bench debugging when applicable |
| `documentation-and-adrs` | Architecture decisions, contract docs, lasting design rationale |
| `debugging-and-error-recovery` | Systematic root-cause debugging |
| `test-driven-development` | Code changes that need tests or regression protection |
| `source-driven-development` | Framework/library changes that should be grounded in official docs |
| `code-review-and-quality` | Reviewing code or docs before merging |
| `handoff-path-closeout` / `handoff-path-output` | When explicit handoff paths are required |

Project-specific closeout rule:

```text
Update durable docs -> run relevant validation -> commit -> push.
```

Do not rely on chat history as the source of truth.

## 4. Branch Ownership Map

The repository uses branches as subsystem homes.

| Branch | Role | Primary documents |
|---|---|---|
| `feature/rehab-arm-ros2-architecture` | ROS2, NanoPi bridge, MuJoCo, docs, protocols, dry-run, profile, main integration | This document, `CURRENT_MAINLINES.md`, `REHAB_ARM_SYSTEM_ARCHITECTURE.md`, `USER_MANUAL.md` |
| `M33` | Infineon M33 firmware, CAN master, safety state machine, motor control, M33/M55 IPC, BLE near-field entry | `PSOC_CAN_PROTOCOL_V1.md`, `M33_SAFETY_INPUT_MAPPING.md`, `M33_M55_IPC_BLE_FOUNDATION.md` |
| `M55` | Infineon M55 WiFi, voice/audio, model runtime, model result bridge | `M55_MODEL_DEPLOYMENT_GUIDE.md`, `M55_MODEL_RESULT_PROTOCOL_V1.md`, `VOICE_WAKE_TTS_PORTABILITY_GUIDE.md` |
| `C8T6` | STM32F103C8T6 sensor node, CAN transport, EMG/IMU/health sensing | `PSOC_CAN_PROTOCOL_V1.md`, `TROUBLESHOOTING_AND_LESSONS.md` |
| `APP` | Android App, BLE UI, 3D arm view, local patient/operator interaction | `COMMAND_CENTER_APP_PROTOCOL_V1.md`, `APP_CONNECTION_GUIDE.md` |
| `nanopi-sdk` | NanoPi low-level CAN/system bring-up reference | `NANOPI_CAN_MASTER_USAGE.md`, `PRODUCT_AUTOSTART_GUIDE.md` |
| `nanopi-rosnode-usbcan` / `NanoPi_ROSNode` | Early NanoPi/ROS side branches | Historical reference only |
| `ROS_VLA_WebSocket` | Early ROS/VLA/WebSocket branch | Historical reference only |
| `PCB` | PCB/hardware reference | Hardware reference only |
| `ai` | Early platform/AI reference | Historical platform reference |
| `wake-word-model` | Wake word model reference | M55 voice reference only |
| `main` | Entry/early material | Not current development mainline |

## 4.1 External Platform / Command Center Repository

The current server platform and device command-center work is in a separate AI collaboration platform repository, not in the historical `ai` branch of this repository.

| Item | Verified value |
|---|---|
| Local path | `D:\ai-collab-product` |
| GitHub remote | `https://github.com/wenjunyong666/ai-.git` |
| Current branch | `ai/game-loop-core` |
| Relationship to this repo | External AI collaboration platform for command-center UI, model relay, XiaoZhi cloud relay, telemetry display, and VLA context/dry-run integration. It consumes this repo's protocols and safety boundaries; it is not the ROS2/NanoPi/M33 motion mainline. |
| Platform code entry | `apps/api/app/modules/rehab_arm/` in the platform repo |
| Platform docs checked | `docs/medical-rehab-arm-platform-development-plan.md`, `docs/rehab-arm-nanopi-vla-mujoco-integration.md` in the platform repo |
| Safety boundary | Platform/App/M55/VLA outputs are suggestions, language context, training advice, or dry-run candidates only. They must not emit CAN frames, motor current, motor torque, raw motor position/velocity, direct motor commands, or M33 safety overrides. Real execution remains `JointTrajectory -> NanoPi -> M33 -> motor`. |

## 5. Verified Mainline Routes I Have Checked

| Route | Where it lives | What it does | Notes |
|---|---|---|---|
| M33 safety/control | `origin/M33` | Final safety authority, CAN master, motor control, status aggregation | Real motion must come back here |
| NanoPi ROS2 bridge | `feature/rehab-arm-ros2-architecture` | ROS2 bridge, state aggregation, trajectory transfer, sim/platform gateway | Current integration workspace |
| Linux sim host | `cal@192.168.3.34` / `rehab-arm-sim-host-shadow.service` | MuJoCo shadow, dry-run, 6DOF visualization | Simulation and review only |
| Formal motion path | `JointTrajectory -> NanoPi -> M33 -> motor` | Real motion path | Only accepted real-motion route |
| Shadow-sim path | `/sim/medical_arm/joint_trajectory -> /sim/medical_arm/joint_states` | MuJoCo-only shadow motion | No real motor control |
| Bench-debug path | `nanopi_can_master.py`, `private/cansimple/*` | Direct CAN debug and bring-up | Debug only, not formal motion |

## 6. Repository Structure On The Integration Branch

Branch:

```text
feature/rehab-arm-ros2-architecture
```

Key paths:

| Path | Purpose |
|---|---|
| `README.md` | Repository entry |
| `docs/` | Architecture, protocols, progress, troubleshooting, manuals, handoff docs |
| `docs/assets/` | Images and visual reference assets used by docs |
| `docs/ai-handoffs/` | Historical handoff documents |
| `rehab_arm_ros2_ws/` | Main ROS2 workspace |
| `rehab_arm_ros2_ws/src/rehab_arm_description/` | URDF, robot schema, calibration/config |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/` | MuJoCo simulation, backend, models, launch files |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/` | NanoPi/PSoC/M33 ROS2 bridge, parsers, profile tools, dry-run gates |
| `rehab_arm_ros2_ws/src/rehab_arm_control/` | Trajectory utilities and placeholder planner nodes |
| `rehab_arm_ros2_ws/src/rehab_arm_bringup/` | Launch/integration entry points |
| `launch/` | Top-level launch or system integration helpers |
| `scripts/` | Utility scripts when present |

## 7. Subsystem Document Map

### Project And Architecture

| Path | Purpose |
|---|---|
| `docs/CURRENT_PROJECT_BRIEFING.md` | Human-readable project briefing |
| `docs/CURRENT_MAINLINES.md` | Current mainlines, side branches, and classification rules |
| `docs/MAINLINE_DEVELOPMENT_GUIDE.md` | How to continue mainline development |
| `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md` | System architecture baseline |
| `docs/REHAB_FUNCTIONAL_ROADMAP.md` | Functional roadmap |
| `docs/DOCUMENTATION_CLEANUP_AUDIT.md` | Documentation cleanup and archive plan |

### Progress, Troubleshooting, Handoff

| Path | Purpose |
|---|---|
| `docs/PROJECT_PROGRESS.md` | Latest task history and validation state |
| `docs/TROUBLESHOOTING_AND_LESSONS.md` | Pitfalls, root causes, fixes, reusable lessons |
| `docs/USER_MANUAL.md` | User-facing workflows and commands |
| `docs/ai-handoffs/` | Historical handoff notes |

### CAN, M33, M55, C8T6

| Path | Purpose |
|---|---|
| `docs/PSOC_CAN_PROTOCOL_V1.md` | PSoC/M33 CAN protocol |
| `docs/MOTOR_PROTOCOLS.md` | Motor protocol and unit references |
| `docs/M33_0X320_LOGGER_GUIDE.md` | M33 `0x320` logging/debug guide |
| `docs/M33_SAFETY_INPUT_MAPPING.md` | M33 physical/code safety inputs |
| `docs/M33_M55_IPC_BLE_FOUNDATION.md` | M33/M55 IPC and BLE foundation |
| `docs/M33_M55_MODEL_INPUT_PROTOCOL_V1.md` | M33-to-M55 model input contract |
| `docs/M55_MODEL_RESULT_PROTOCOL_V1.md` | M55 result output contract |
| `docs/M55_MODEL_DEPLOYMENT_GUIDE.md` | M55 model deployment |
| `docs/VOICE_WAKE_TTS_PORTABILITY_GUIDE.md` | Voice/wake/TTS portability |

### NanoPi, ROS2, MuJoCo

| Path | Purpose |
|---|---|
| `docs/M33_NANOPI_MUJOCO_POWERON_TEST_GUIDE.md` | Power-on validation from M33/NanoPi to MuJoCo |
| `docs/MUJOCO_MOVE_MOTOR_GUIDE.md` | MuJoCo-only movement and path-planning smoke tests |
| `docs/MUJOCO_URDF_GAP_AND_STEP_GUIDE.md` | URDF/MuJoCo gap and next steps |
| `docs/MUJOCO_NANOPI_INTEGRATION_PREP.md` | Historical MuJoCo/NanoPi integration prep |
| `docs/MEDICAL_ARM_MUJOCO_LEARNING_GUIDE.md` | Historical MuJoCo learning/reference guide |
| `docs/SIM_HOST_NANOPI_NETWORK_GUIDE.md` | Sim host and NanoPi ROS2 networking |
| `docs/PRODUCT_AUTOSTART_GUIDE.md` | Product/research autostart services |
| `docs/NANOPI_CAN_MASTER_USAGE.md` | NanoPi CAN debug tool usage |
| `docs/TESTING_GUIDE.md` | Testing guide |

### App, Platform, Server, Profile

| Path | Purpose |
|---|---|
| `docs/COMMAND_CENTER_APP_PROTOCOL_V1.md` | Command center and App protocol |
| `docs/PATIENT_DEVICE_PROFILE_PROTOCOL_V1.md` | Patient/device profile protocol |
| `docs/APP_CONNECTION_GUIDE.md` | App connection guide |
| `docs/SERVER_SYNC_API_DRAFT.md` | Server sync API draft |
| `docs/PLATFORM_AI_PROMPT_VLA_LVA_HTTP.md` | Platform/VLA prompt/API notes |
| `docs/HTTP_BRIDGE_README.md` | Historical HTTP bridge |
| `docs/OPENCLAW_BRIDGE_README.md` | Historical OpenClaw bridge |

## 8. Code Map On The Integration Branch

### Robot Description

| Path | Purpose |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_description/urdf/rehab_arm.urdf` | Base URDF |
| `rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_schema.yaml` | 6DOF joint/motor schema |
| `rehab_arm_ros2_ws/src/rehab_arm_description/config/medical_arm_6dof_temporary_calibration.yaml` | Temporary engineering-zero calibration table |
| `rehab_arm_ros2_ws/src/rehab_arm_description/test/test_medical_arm_6dof_schema.py` | Schema tests |

### MuJoCo

| Path | Purpose |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/medical_arm_6dof.xml` | 6DOF MuJoCo model |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/models/rehab_arm_minimal.xml` | Minimal model |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py` | ROS2 MuJoCo sim node |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_backend.py` | MuJoCo backend |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/medical_arm_shadow_relay_node.py` | Hardware shadow relay |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_shadow.launch.py` | Pure simulation launch |
| `rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/launch/medical_arm_6dof_hardware_shadow.launch.py` | Hardware shadow launch |

### NanoPi / PSoC Bridge

| Path | Purpose |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_can_bridge_node.py` | ROS2 bridge to M33 CAN |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_status.py` | M33 status parser |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/psoc_motor_status.py` | M33 motor aggregate parser |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_ros_contract.py` | M33/ROS contract |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_model_status.py` | M33/M55 model status parser |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/motor_profiles.py` | Motor profile table |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/patient_profile.py` | Patient profile validation and M33 subset export |

### Planner, Dry-Run, Review

| Path | Purpose |
|---|---|
| `rehab_arm_ros2_ws/src/rehab_arm_control/rehab_arm_control/trajectory_utils.py` | Trajectory helpers |
| `rehab_arm_ros2_ws/src/rehab_arm_control/rehab_arm_control/vla_task_planner_node.py` | Placeholder VLA task planner |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/vla_candidate_gate.py` | VLA candidate gate |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/mujoco_dry_run_review.py` | MuJoCo dry-run review plan |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/operator_review.py` | Operator/therapist review |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/m33_gate_preparation.py` | M33 gate preparation |
| `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/server_action_ingress.py` | Server action quality gate |

## 9. Current System Boundary

Formal real-motion path:

```text
JointTrajectory -> NanoPi ROS2 bridge -> M33 safety/control -> motor
```

All other subsystems produce context, suggestions, profiles, candidates, displays, or logs. They do not grant motion permission.

Important topic names:

| Topic | Meaning |
|---|---|
| `/joint_states` | Fresh robot joint state published by NanoPi bridge |
| `/rehab_arm/motor_state` | Motor state JSON |
| `/rehab_arm/safety_state` | M33/PSoC safety state JSON |
| `/rehab_arm/model_state` | M55/M33 model suggestion JSON |
| `/arm_controller/joint_trajectory` | Formal ROS trajectory input, still subject to M33 |
| `/sim/medical_arm/joint_trajectory` | MuJoCo shadow trajectory input |
| `/sim/medical_arm/joint_states` | MuJoCo shadow joint state output |

## 10. Current Hardware Naming Rules

Current installed/mainline motor understanding:

| ID | Meaning |
|---|---|
| `node_id=3` | CANSimple motor, current mainline |
| `motor_id=4` | RS00, current mainline |
| `motor_id=5` | RS00, current mainline |
| `motor_id=6` | EL05, current mainline |
| `motor_id=1/2` | Wrist 4015 candidates, not currently powered in latest context |
| `motor_id=7` | External debug motor, not current arm mainline |

Current MuJoCo 6DOF joint names:

```text
jian_hengxiang_joint
jian_zongxiang_joint
jian_xuanzhuan_joint
zhou_zongxiang_joint
wanbu_zongxiang_joint
wanbu_hengxiang_joint
```

## 11. What This Document Must Not Become

Do not turn this file into:

- A daily progress log.
- A troubleshooting dump.
- A hardware test transcript.
- A task-specific handoff.
- A list of every command ever run.

Put those in:

- `docs/PROJECT_PROGRESS.md`
- `docs/TROUBLESHOOTING_AND_LESSONS.md`
- `docs/USER_MANUAL.md`
- `docs/ai-handoffs/`

This document is only the stable index and operating map.
