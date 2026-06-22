# 康复外骨骼机械臂踩坑与技巧记录

本文档记录项目中踩过的坑、排查路径、根因、解决方法和以后要记住的技巧。每次遇到新的坑都要补充这里，不要只留在聊天记录里。

## 记录格式

每个坑尽量按这个格式写：

```text
标题:
现象:
环境:
排查:
根因:
解决:
技巧:
相关文件/命令:
状态:
```

## CAN 与硬件

### 远程查 ROS 图先统一 `ROS_DOMAIN_ID=42`

现象：

- 在 NanoPi 或仿真主机上，`ros2 node list` / `ros2 topic list` 直接看起来像空图，只剩 `/parameter_events` 和 `/rosout`。
- 但 systemd 服务日志里明明能看到 bridge、sim relay 和 MuJoCo 节点在跑。

环境：

- NanoPi：`pi@192.168.3.36`
- 仿真主机：`cal@192.168.3.34`
- 当前 bench 配置文件 `/home/pi/.rehab_arm_ros2_network` 和 `/home/cal/.rehab_arm_ros2_network` 都导出 `ROS_DOMAIN_ID=42`

根因：

- 外部 shell 没有继承 systemd 服务里的 ROS 网络环境。
- 机器上有多个 ROS 图或本地默认域时，不带 `ROS_DOMAIN_ID` 会直接看错图。

解决：

```bash
export ROS_DOMAIN_ID=42
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
ros2 topic list -t
```

技巧：

- 先查 `cat ~/.rehab_arm_ros2_network`，再查 `systemctl show ... -p Environment`，最后再跑 `ros2 topic info`。
- 不要把“没看到 topic”直接当成“节点没运行”。

状态：

- 2026-06-17 已复核并修正观察方式；同域下能看到 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state` 和 `/sim/medical_arm/joint_states`。

### 主线要单独成文

现象：

- 机械臂项目历史很长，`M33`、`M55`、`NanoPi`、`MuJoCo`、`C8T6`、`APP`、平台和一堆 bench/shadow/demo 容易混在一起。
- 只看进度文档，很容易把历史里已经通过的链路和当前退化状态混掉。

解决：

- 新增 [CURRENT_MAINLINES.md](CURRENT_MAINLINES.md)，只记录当前 7 条主线、边界和分类规则。
- 以后查主线先看这份文档，再看架构和进度。

技巧：

- 主线文档只写“谁负责什么、什么不能做”，不要塞太多过程记录。
- 进度文档记录状态变化，踩坑文档记录边界和教训，主线文档负责固定框架。

状态：

- 2026-06-17 已新增并接入现有文档入口。

### 最新电机配置要以现场口径为准，7 号只算外部调试

现象：

- 旧文档和旧调试记录里，`motor_id=7` 曾经被写进 shadow、bench 或临时映射口径。
- 如果直接沿用旧结论，很容易把外部调试电机当成当前机械臂主线，或者把旧的 7 号结论误套到今天的实物主线。

环境：

- M33 现场 shell：`cmd_m33_joint_calib`、`cmd_m33_prearm_check`、`cmd_motor_fb <joint>`
- NanoPi：`pi@192.168.3.36`，`can0` 为 `ERROR-ACTIVE`
- 现场用户最新口径：`motor_id=7` 是外部调试电机，不用管

排查：

- 读到的当前配置里，M33 固件仍保留 1~7 的内部 joint 槽位和 legacy/shadow 语义，但这不等于当前实物主线真的有 7 号机械臂关节。
- 现场只读复核时，1/2 没有原始反馈，3/4/5/6 有反馈，7 号虽然历史上能被测到，但现阶段已被用户明确排除出主线。

根因：

- 旧的 bench / shadow / temporary mapping 与当前实物主线混在一起，导致“最新配置”被误读。

解决：

- 当前主线口径改为：1/2 是腕部候选，3 是 CANSimple，4/5 是 RS00，6 是 EL05，7 号只保留外部调试含义，不再作为当前机械臂主线电机。
- 后续只要谈“当前机械臂主线”，都不要再把 7 号当作正式关节或故障主线。

技巧：

- 先问“这是当前实物主线，还是历史 bench/shadow？”再看抓包和配置。
- 遇到 `joint7`、`forearm_rotation_joint -> motor_id=7` 这类字样，先核口径，不要直接当成今天的真实映射。

相关文件/命令：

- `D:\RT-ThreadStudio\workspace\yiliao_m33\applications\control\control_layer_cfg.h`
- `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan\docs\JOINT_MOTOR_MAPPING_DRAFT.md`
- `cmd_m33_joint_calib`

状态：

- 2026-06-17 已按用户最新口径纠偏：7 号不算当前机械臂主线。

### 1/2 未上电时不要继续探测

现象：

- 最新主线里 `motor_id=1/2` 是腕部 4015 小电机候选，但用户确认当前 1/2 没上电。
- 如果继续对 1/2 发 Get_ID、参数读或 active-report，只会制造无效结果，还可能干扰现场判断。

解决：

- 在用户确认 1/2 上电和接入之前，不再对 1/2 发任何 CAN 探测帧。
- 当前电机读取主线只验证 3/4/5/6；7 号外部调试不算主线。

状态：

- 2026-06-17 已执行：停止 1/2 探测，把 1/2 标记为预留待上电。

### 3 号小幅真机动作可以用现成的 speed hold，再立刻 stop

现象：

- 现场无人穿戴，用户明确授权后，只想看 3 号最小幅度动作效果。
- M33 里已有 `cmd_motor3_speed`，它内部复用 `motor_speed_hold`，会按给定时长刷新并自动结束。

解决：

- 用极小速度、短时长执行台架验证：`cmd_motor3_speed 0.05 0.5 600 20`。
- 动作结束后再发 `cmd_motor3_stop 1`，然后复读 `cmd_motor3_status` 和 `cmd_motor_fb 3`。

技巧：

- 小幅动作优先选已有的 speed hold，而不是新写一套运动路径。
- 读回 `pos_mrad`/`tick` 和 `fault=0x00`，确认真的动过且已经停住。

状态：

- 2026-06-17 已验证：3 号从 `pos_mrad=0` 变到 `67`，随后 stop 成功。

### C8T6 没有回 `0x7C1/0x7C2/0x7C3` 时先按物理接入查

现象：

- NanoPi `can0` 为 1 Mbps `ERROR-ACTIVE`，错误计数为 0，且总线上能看到 `0x321 -> 0x322`、`0x330~0x334` 等现有主线流量。
- 向 C8T6 控制 ID `0x7C0` 发送 `GET_STATUS` 帧 `7C0#0501000000000000` 和 `START_STREAM` 帧 `7C0#0302000000000000` 后，抓包只看到 NanoPi 发出的 `0x7C0`，没有看到 C8T6 预期的 `0x7C1` ACK、`0x7C2` sensor 或 `0x7C3` health。

环境：

- NanoPi：`pi@192.168.3.36`，`can0` 由 `/usr/local/bin/setup_nanopi_can.sh` 配置为 `bitrate 1000000 restart-ms 100 berr-reporting on`。
- C8T6 代码：`D:\RT-ThreadStudio\workspace\c8t6_github_C8T6`，协议 ID 为 `0x7C0` control RX、`0x7C1` ACK TX、`0x7C2` sensor TX、`0x7C3` health TX。

判断：

- 这不是 NanoPi CAN 控制器没启动；同一总线上已有其他节点流量。
- 也不像单纯 C8T6 默认不开流；即使 sensor streaming 默认关闭，C8T6 固件运行并接到总线时也应该周期发 health 或至少对 `GET_STATUS` 回 `0x7C1`。
- 优先怀疑 C8T6 没有接到同一 CAN 主干、电源/共地缺失、CANH/CANL 反接、终端异常、收发器 STB/EN 未使能、PA11/PA12 到收发器接错，或烧录的不是当前 CAN 固件。

解决：

- 保留 NanoPi 侧最小安全探针：

```bash
timeout 7 candump -L can0,7C0:7F0 &
cansend can0 7C0#0501000000000000
sleep 1
cansend can0 7C0#0302000000000000
```

- 预期通过条件：看到 `0x7C1`，随后能看到周期 `0x7C3`；开流后再看 `0x7C2`。
- 若仍无回包，停止改协议，先查物理层和 C8T6 固件运行状态。

状态：

- 2026-06-16 实测未通过；NanoPi 能发 `0x7C0`，但 C8T6 当前未在 NanoPi 总线上可见。

### 不要把单个 `/joint_states` 当成 3/4/5/6 全关节已通

现象：

- NanoPi 侧 CAN 抓包能稳定看到 `0x330~0x334` 连续刷新，以及 `0x321 -> 0x322` 心跳/状态。
- 但 ROS `/joint_states` 只回出一个关节，例如 `shoulder_lift_joint=0.0`，没有同时出现 3/4/5/6 四个关节。

判断：

- 这说明 CAN 层和 ROS 关节发布层不是同一件事。
- `candump` 里看到四个电机相关报文，不等于 `/joint_states` 已经把四个关节正确映射并发布。

解决：

- 先确认 `/joint_states` 发布源是哪个 node，再查它的 joint map、fresh 条件和 ROS 订阅是否都在。
- 验证时至少同时看三样：`candump`、`ros2 topic info /joint_states`、`ros2 topic echo /joint_states`。
- 只有当 `/joint_states` 里同时出现预期关节名和对应位置，才能说 3/4/5/6 的 ROS 层真的通了。

状态：

- 2026-06-17 实测：CAN 层有 3/4/5/6 报文，但 `/joint_states` 仍只出单关节，属于“CAN 通、ROS 关节层未全通”。

### 接手机械臂代码时不要只看工作区根目录或 main 分支

现象：

- `D:\RT-ThreadStudio\workspace` 本身不是 Git 仓库，下面同时放着早期 PSoC 工程、M33/M55 checkout、NanoPi/ROS checkout、App/模型/参考工程和大量日志图片。
- GitHub 默认 `main`/本地 `qiansai` 只提供入口和早期资料；真实代码按 `feature/rehab-arm-ros2-architecture`、`M33`、`M55`、`APP`、`C8T6`、`nanopi-sdk` 等分支分散。

根因：

- `Medical-Rehabilitation-Manipulator` 仓库按子系统分支组织，而不是单一 monorepo 目录。
- 本地保留了多个不同时间点的 checkout；目录名相似，容易把参考副本、历史旁线或早期工程当成当前主线。

解决：

- 先以 HTTPS 远端 `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git` 更新远端分支引用，再用 `git ls-tree origin/<branch>` 查看分支内容，不要随意切分支覆盖本地工作区。
- 当前主线入口固定为 `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan` 的 `feature/rehab-arm-ros2-architecture` 分支。
- M33/M55 代码以远端 `origin/M33`、`origin/M55` 为准；本地 `_ref_m33_repo` 可能是浅/grafted 状态，单看日志会漏掉远端新提交。
- `qiansai` 是早期 RT-Thread/PSoC 工程和主 README 入口，不是当前 ROS2/NanoPi/MuJoCo 主工作区。

技巧：

- 接手顺序：先读 `docs/CURRENT_PROJECT_BRIEFING.md`、`docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`、`docs/PSOC_CAN_PROTOCOL_V1.md`，再看 ROS2 包、M33、M55、C8T6、APP。
- 判断能否影响真实运动时，先分类为 `mainline/shadow-sim/dry-run/bench-debug/offline-demo/side-channel`。
- 看到旧 OpenClaw HTTP 直控、`ROS_VLA_WebSocket` 或 App 直控描述时，要回到当前安全合同：正式运动只能走 `JointTrajectory -> NanoPi -> M33 -> 电机`。

状态：

- 2026-06-16 已完成一次代码位置盘点并记录到 `PROJECT_PROGRESS.md`；本轮只读和文档更新，没有改动控制代码。

### M55 语音上云不是直接控制链路，而是 VLA 的 L 部分

现象：

- 讨论云端 API AI 时，容易把“M55 语音直连服务器、服务器再下发 NanoPi”理解成 M55 或云端直接产生运动请求。
- 用户澄清真实框架是：M55 原始语音到服务器形成 VLA 的 `L / Language`，NanoPi 摄像头到服务器形成 `V / Vision`，服务器/VLA 融合后产生 `A / Action` 去完成指令。

根因：

- “语音助手”“聊天”“模型中转”和 “VLA 控制”容易混在一起。
- 对康复机械臂来说，`A` 如果不经过 dry-run、profile、安全状态和 M33 裁决，就会变成危险的隐性控制旁路。

解决：

- 文档统一改为 L/V/A：M55 只负责低延迟语音到 L；NanoPi 负责摄像头到 V；服务器/VLA 产生 A。
- A 只能是高层动作意图、分段任务或 dry-run 候选，不是 CAN、电流、力矩、速度、原始电机位置或 M33 安全覆盖。
- M55 直连平台只能保存短期 relay token，不能保存厂商 API key。
- M55 云端小智/VLA-L 主链路必须走 WiFi HTTP，不走 CAN；`0x323` 只保留给本地 wake/command 事件、模型摘要和兼容状态观察。
- 唤醒后先分类：`daily_chat` 只回复/TTS，`vla_command` 才进入 `vla_language_context_v1`，`none` 提示重说。

技巧：

- 后续 AI 或平台实现看到“M55 调服务器”时，先问它是不是 `vla_language_from_voice`；如果返回字段不是 `language_context/voice_intent/operator_facing_reply`，就要重新审查边界。
- 看到“服务器下发 NanoPi”时，先确认是否是 `vla_action_candidate_v1` 或高层请求队列；如果包含底层电机字段，必须拒绝。
- 看到“语音上云走 0x323/CAN”时要纠正：那是本地状态出口，不是小智聊天或 VLA-L 主链路。

状态：

- 2026-06-10 已同步到 README、系统架构、总控台协议、服务器同步 API 草案、语音迁移指南和 USER_MANUAL；`test_voice_gateway.py` 与系统架构合同测试通过；真实云端闭环未在本轮验证。

### 平台 VLA A 下发到 NanoPi 也不是轨迹发布许可

现象：

- 平台/VLA 融合 L 和 V 后会产生 A，高层上看像“开始抬手训练”这类动作请求。
- 如果 NanoPi 直接把 A 转成 `/arm_controller/joint_trajectory` 或 `0x320`，就绕过了 MuJoCo dry-run、operator review 和 M33 safety gate。

解决：

- 机械臂侧新增 `server_to_nanopi_high_level_command_v1` 入口质量门。
- 入口通过后只生成 `nanopi_high_level_action_queue_item_v1`，下一跳是 `vla_candidate_gate -> mujoco_dry_run_review -> operator_review -> m33_safety_gate_preparation`。
- CLI：`python -m rehab_arm_psoc_bridge.check_server_action_command --payload server_action.json --queue-item --pretty`。

技巧：

- 平台 AI 只需要按 [PLATFORM_AI_PROMPT_VLA_LVA_HTTP.md](PLATFORM_AI_PROMPT_VLA_LVA_HTTP.md) 产出高层 A payload。
- 如果 payload 含 `joint_trajectory`、`trajectory_points`、`can_frame`、`motor_current`、`motor_torque`、`motion_permission_granted` 或 `m33_safety_override`，NanoPi 入口必须拒绝。

状态：

- 2026-06-10 已实现 `server_action_ingress.py`、CLI 和测试；这是主线入口地基，不连接 CAN、不发 ROS 轨迹。

### 旧 wake 代码存在不等于语音唤醒闭环已通

现象：

- M55 `wifi` 工程里有 `voice_service.c`、`wake_word_detector.cpp`、`baidu_asr.c`、`baidu_tts.c` 和 `websocket_client.c`。
- 但用户现场要求“我喊它能回应我”时，不能据此声称已完成 wake -> ASR/LLM -> TTS speaker 闭环。

排查：

- `baidu_asr.c` 和 `baidu_tts.c` 当前仍是未实现 stub，返回 `-RT_ENOSYS`。
- 旧 `wake_word_detector` 路线此前被用户明确判定失败。
- Infineon 官方 local voice 例程提供了更可靠的 CM55 主线：PDM 10 ms frame、AFE、Voice Assistant inferencing、control_task map_id 和 I2S/扬声器路径。

根因：

- 旧工程里有语音相关模块，但缺少官方音频管线迁移、真实 ASR/LLM/TTS provider、以及上板端到端验收。
- 把存在的模块名当成完成状态，会误导后续联调。

解决：

- 正式语音主线改为官方例程优先：先验证 `_ifx_local_voice`，再分模块移植 PDM/AFE/VA/control_task 结构到 `wifi` 工程。
- 旧 `voice_service/wake_word_detector` 只保留为 PCM dump、API relay 或 fallback 诊断。
- 任何语音输出都必须通过 `MSG_TYPE_AI_INFERENCE_RESP -> M33 -> 0x323 -> NanoPi /rehab_arm/model_state` 或 `tts_playback_request_v1`，并保持 `*_not_motion_permission` 边界。

状态：

- 2026-06-09 已更新 `VOICE_WAKE_TTS_PORTABILITY_GUIDE.md`、`M55_MODEL_DEPLOYMENT_GUIDE.md`、`voice_gateway.py` 和测试；尚未上板完成真实唤醒播报闭环。

### VLA candidate 通过 JSON 审核不等于可以发真机轨迹

现象：

- 服务器/VLA 返回 `vla_plan_candidate_v1`，里面可能包含看起来合法的 `dry_run_joint_trajectory`。
- 如果平台或 NanoPi 直接把它转换成 ROS `JointTrajectory`，会绕过 MuJoCo dry-run、M33 safety gate 和人工确认。

根因：

- VLA candidate 是任务/轨迹建议，不是控制命令。
- `requires` 中的 `m33_motion_allowed_true` 是“未来进入真机前必须满足的条件”，不是 candidate 自带的运动许可。

解决：

- 服务器/VLA candidate 进入本地前先运行：

```bash
ros2 run rehab_arm_psoc_bridge check_vla_plan_candidate.py \
  --candidate vla_plan_candidate.json \
  --pretty
```

- 审核通过也只能进入 `mujoco_dry_run_review` 和 `operator_review`。
- 真实运动仍必须后续转换为正式 ROS `JointTrajectory`，再经过 NanoPi bridge、fresh motor feedback gate 和 M33 `motion_allowed=true`。

技巧：

- `check_vla_plan_candidate.py --example --pretty` 可用于现场演示安全样例。
- 如果 candidate 中出现 `can_frame/motor_current/motor_torque/raw_motor_position/raw_motor_velocity/m33_safety_override/direct_motor_command`，质量门必须失败。

状态：

- 2026-06-09 已加入 `vla_candidate_gate.py`、CLI、单元测试和仿真主机 QA 脚本入口；本地样例验证通过。

### MuJoCo dry-run 通过也不能授予真实运动许可

现象：

- VLA candidate 通过本地 gate 后，可以生成 MuJoCo dry-run review plan。
- 后续 MuJoCo 可能报告 `dry_run_passed=true`，但这只能说明仿真审核通过，不等于真机可动。

根因：

- MuJoCo 是仿真环境，无法替代实时 M33 安全状态、fresh motor feedback、急停、电源和现场人工确认。
- 仿真主机与 NanoPi 还走无线 ROS，延迟/丢包也不适合作为实时安全依据。

解决：

- 使用 `build_mujoco_dry_run_review_plan.py` 只生成审核计划。
- 未来 MuJoCo 报告必须用 `validate_mujoco_dry_run_review_report()` 或对应 CLI/测试质量门检查。
- 报告中如果出现 `motion_permission_granted=true`，必须判定失败。

技巧：

- MuJoCo dry-run 通过后的下一步是 `operator_review` 和“准备进入 M33 gate”，不是直接发 `JointTrajectory`。
- 真机执行前仍要重新检查 M33 `motion_allowed=true`、fresh motor feedback、患者 profile、现场急停和人工确认。

状态：

- 2026-06-09 已加入 `mujoco_dry_run_review.py`、CLI、单元测试和仿真主机 QA 脚本入口；本地样例验证通过。

### 操作者审核通过只允许准备进入 M33 gate

现象：

- MuJoCo dry-run 通过后，操作者/治疗师可能在平台上点击“同意”。
- 如果平台把这个同意直接当作运动命令，仍然会绕过 M33 本地安全状态机。

根因：

- 人工审核是流程记录和责任确认，不是电机控制授权。
- 真机执行时安全状态、fresh motor feedback、急停、电源和患者状态都必须实时再检查。

解决：

- 使用 `operator_review_record_v1` 记录审核人、角色、患者/session/profile 绑定和五项安全确认。
- 用 `check_operator_review.py` 校验记录；通过后的 `allowed_next_steps` 只有 `prepare_joint_trajectory_for_m33_gate`。

技巧：

- `approved_for_m33_gate_preparation=true` 不能被平台翻译成 `motion_allowed=true`。
- App/服务器/NanoPi 仍不得绕过 M33 gate 发 `JointTrajectory`、CAN、电流或力矩。

状态：

- 2026-06-09 已加入 `operator_review.py`、CLI、单元测试和仿真主机 QA 脚本入口；本地样例验证通过。

### Windows 本地跑 ROS Python 包测试要设置 PYTHONPATH

现象：

- 在 Windows 仓库根目录直接运行 `python -m unittest rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_command_center_sync.py ...`，测试报 `ModuleNotFoundError: No module named 'rehab_arm_psoc_bridge'`。
- 同一个 CLI 用源码 fallback 路径可以运行并输出 JSON。

根因：

- 本地 Windows 没有通过 `colcon build` 安装 ROS Python 包，也没有 source ROS install 环境。
- 直接按文件路径运行 unittest 时，Python 不会自动把 `rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge` 加到 import path。

解决：

```powershell
$env:PYTHONPATH='D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan\rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge'
python -m unittest `
  rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_command_center_sync.py `
  rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_voice_gateway.py `
  rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test\test_rehab_session.py
```

技巧：

- Windows 本地用 `PYTHONPATH` 做源码单测；真正用户视角 ROS 安装入口仍要到 NanoPi 或 Linux 仿真主机运行 `colcon build` 和 `ros2 run`。
- 新增 CLI 必须同时更新 `setup.py`、`CMakeLists.txt install(PROGRAMS ...)` 和 `scripts/sim_host_rehab_user_qa.sh`。

状态：

- 2026-06-09 已用该方式验证新增 command center sync、voice gateway、rehab session 共 10 项测试通过。

### Windows 本机没有 bash/可用 WSL 时不能验证 shell 脚本语法

现象：

- 在 Windows PowerShell 里执行 `bash -n scripts/sim_host_rehab_user_qa.sh`，返回 `The term 'bash' is not recognized`。
- 尝试 `wsl bash -lc ...` 时，系统提示需要安装 Linux 发行版，当前没有可用 WSL 环境。

根因：

- 当前 Codex Windows 环境只有 PowerShell、OpenSSH 和 `wsl.exe` 外壳入口，但没有 bash，也没有已安装的 WSL Linux 发行版。

解决：

- 本地先用 Python 单测、CLI 源码运行和 `git diff --check` 验证可覆盖的部分。
- shell 脚本语法和 ROS 安装入口仍要在 Linux 仿真主机或 NanoPi 上验证。

技巧：

- `scripts/sim_host_rehab_user_qa.sh` 是 Linux/ROS 用户视角 QA，权威验证命令仍是：

```bash
cd ~/桌面/Medical-Rehabilitation-Manipulator
git pull
./scripts/sim_host_rehab_user_qa.sh
```

- Windows 上不要因为缺 bash 就重写 QA 脚本为 PowerShell；该脚本目标运行环境是 Linux 仿真主机。

状态：

- 2026-06-09 已记录；本轮新增的 command center sync 质量门已通过 Python 单测和 CLI 源码验证，Linux shell 语法留待仿真主机复跑。

### 不要把 qiansai 当成云端 AI 合作平台

现象：

- 用户提到后续要接“本地 AI 合作平台项目”和云服务器总控台时，工作区里没有明显的前端/服务器平台仓库。
- `qiansai` 名字像早期项目，但目录内容是 RT-Thread/PSoC 工程、`applications/`、`board/`、`rt-thread/`、`http_server.c` 等嵌入式文件。

根因：

- 本地工作区同时保留了早期 PSoC、M33/M55、语音、模型和医疗臂仓库；目录名不能证明它是云平台。

解决：

- 后续真正接云平台前，先让用户确认平台仓库路径或远端 Git URL。
- 医疗臂仓库只维护协议合同，例如 `COMMAND_CENTER_APP_PROTOCOL_V1.md` 的 REST/WebSocket、租户隔离、VLA、语音和急停边界。

技巧：

- 平台仓库应有典型 server/frontend 结构，例如 `package.json`、后端服务、数据库 schema、auth/tenant 模块；如果只有 RT-Thread/PSoC 文件，就不要当云平台改。
- 多账号数据隔离必须提前设计：`tenant_id/workspace_id/user_id/role/device_id/patient_id/session_id` 不能后补成备注字段。

状态：

- 2026-06-09 已记录到总控台协议和路线图；本轮未修改任何平台仓库。

### 新增 ROS Python CLI 时要同时更新 setup.py 和 CMakeLists.txt

现象：

- 新增 `build_voice_pipeline_plan.py` 和 `build_rehab_session_plan.py` 后，源码方式 `python -m ...` 可运行。
- 但用户按 ROS 包安装后的习惯用 `ros2 run rehab_arm_psoc_bridge xxx.py` 时，如果只改 `setup.py` 的 `console_scripts`，CMake 安装清单可能没有把脚本放到 `lib/rehab_arm_psoc_bridge`。

根因：

- 当前 `rehab_arm_psoc_bridge` 是 `ament_cmake_python` 包，既用 `setup.py` 暴露 console scripts，也在 `CMakeLists.txt install(PROGRAMS ...)` 明确安装可执行脚本。新增 CLI 必须两边同时更新。

解决：

- `setup.py` 添加：
  - `build_voice_pipeline_plan = rehab_arm_psoc_bridge.build_voice_pipeline_plan:main`
  - `build_rehab_session_plan = rehab_arm_psoc_bridge.build_rehab_session_plan:main`
- `CMakeLists.txt` 添加：
  - `rehab_arm_psoc_bridge/build_voice_pipeline_plan.py`
  - `rehab_arm_psoc_bridge/build_rehab_session_plan.py`
- 脚本本身还必须有 executable bit；否则远程仿真主机可能出现 `colcon build` 通过，但 `ros2 pkg executables rehab_arm_psoc_bridge` 不列出新脚本。

技巧：

- 用户视角 QA 必须覆盖“源码运行”和“ROS 安装后运行”两个入口。
- 如果本机没有 `colcon`/`ros2`，至少用静态合同测试锁住 `setup.py` 和 `CMakeLists.txt`，再到 NanoPi/ROS 主机做安装验证。
- 对 `install(PROGRAMS ...)` 的 Python 脚本，新增后执行 `git update-index --chmod=+x path/to/script.py` 并在远程 ROS 主机检查 `ros2 pkg executables`。
- 后续复测优先在仿真主机运行 `./scripts/sim_host_rehab_user_qa.sh`，不要只在 Windows 上跑源码命令。
- 该脚本不要使用 `set -u`；ROS `/opt/ros/jazzy/setup.bash` 可能读取未定义的 `AMENT_TRACE_SETUP_FILES`，会在 `nounset` 下误失败。

状态：

- 2026-06-09 已补 CMake 安装清单和脚本 executable bit，并用静态合同测试锁住；远程仿真主机干净 worktree 已复测 `colcon build`、`ros2 pkg executables` 和两个 `ros2 run` dry-run CLI 通过，并新增 `scripts/sim_host_rehab_user_qa.sh` 作为后续固定验收入口。

### MuJoCo hardware shadow 无 3 号输出时先查 relay 映射

现象：

- NanoPi `/joint_states` 已发布 `shoulder_lift_joint`，仿真主机也能通过无线 ROS2 echo 到这个 topic。
- `rehab-arm-sim-host-shadow.service` active/enabled，`mujoco_sim_node.py` 日志显示 `backend=mujoco-model`。
- 但 `/sim/medical_arm/joint_trajectory` 或 `/sim/medical_arm/joint_states` 没有反映 3 号装机电机。

环境：

- 3 号伺泰威/CANSimple 已装机，对应 M33 `0x330`、NanoPi legacy `/joint_states shoulder_lift_joint`、MuJoCo `jian_hengxiang_joint`。
- 旧 hardware shadow 曾用 7 号外部 EL05 的 `forearm_rotation_joint -> jian_xuanzhuan_joint` 作为临时验证映射。

根因：

- relay 启动参数仍是旧映射 `{'forearm_rotation_joint':'jian_xuanzhuan_joint'}`，所以当前 3 号 `shoulder_lift_joint` 被忽略。

解决：

- 主线默认映射改为装机 3/4/5/6：

```text
shoulder_lift_joint      -> jian_hengxiang_joint
elbow_lift_joint         -> jian_zongxiang_joint
shoulder_abduction_joint -> zhou_zongxiang_joint
upper_arm_rotation_joint -> jian_xuanzhuan_joint
```

- 同步仿真主机后执行：

```bash
cd /home/cal/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select rehab_arm_sim_mujoco --symlink-install
sudo systemctl restart rehab-arm-sim-host-shadow.service
```

验证：

```bash
ros2 topic echo --once /joint_states
ros2 topic echo --once /sim/medical_arm/joint_trajectory
ros2 topic echo --once /sim/medical_arm/joint_states
ros2 topic hz /sim/medical_arm/joint_states
```

技巧：

- 如果 `/joint_states` 有数据而 `/sim/medical_arm/joint_trajectory` 不动，优先看 `journalctl -u rehab-arm-sim-host-shadow.service` 里的 `joint_map=...`。
- 7 号外部电机是 bench-debug，不要再把 `forearm_rotation_joint -> jian_xuanzhuan_joint` 作为 hardware shadow 默认主线。
- 4/5/6 验证时可以临时打开主动遥测，验证完必须关闭，并抓 `0x320` 确认没有运动目标帧。

状态：

- 2026-06-08 已修复并远端验证：3 号常态 fresh 可驱动 `jian_hengxiang_joint`，临时打开 4/5/6 后可驱动 4 个装机关节；MuJoCo `/sim/medical_arm/joint_states` 约 100 Hz 输出，4/5/6 验证后主动遥测已关闭，`0x320` 抓包为空。

### 7 号电机进 M55 模型先验反馈新鲜度，不要先改模型

现象：

- M55 shell 执行 `req_m7` 后，如果 M33 打印 `motor7 feedback unavailable`，或 M55 日志里 `flags` 没有 fresh bit。

环境：

- 7 号电机是外部 EL05 台架电机，不在机械臂正式关节上。
- `req_m7` 走现有 `M55 -> M33 voice_control -> M33 sensor_snapshot -> M55 TFLM -> M33 0x323`，不新建链路。

根因：

- M55 模型只能消费 M33 控制层已有的 7 号反馈缓存；如果 CAN、供电、主动上报或 M33 控制层缓存没有数据，M55 侧没有真实输入可跑。

解决：

```bash
python3 /home/pi/nanopi_can_master.py private active-report --iface can0 --motor 7 --enable-report --wait 0.5
timeout 3 candump -L can0,334:7FF,180007FD:1FFFFFFF
```

看到 7 号相关反馈后，再在 M55 shell 执行：

```text
req_m7
```

技巧：

- 先看 7 号反馈 freshness，再看 M55 模型日志；不要在没有真实反馈时调整 TFLM arena、模型阈值或 `motor7_model_runner`。
- 当前 `req_m7` 的模型权重是 wake-word 示例模型，只验证 TFLM runtime 和链路，不代表 motor/EMG 语义已经训练完成。

状态：

- 2026-06-04 代码已在 M33/M55 本地编译通过，并已上板验证 `req_m7` 闭环：7 号电机反馈进入 M55 TFLM slot，结果经 M33 `0x323` 到 NanoPi `/rehab_arm/model_state`。

### 当前串口 shell 在 M55 侧，不能直接调用 M33 FINSH 命令

现象：

- M33 新增 `m55_snap` 命令后，在 `COM26` 输入 `m55_snap` 返回 `command not found`。
- 同一个串口能正常执行 M55 命令，例如 `mdl_pub`、`req_snap`。

环境：

- PSoC Edge E84 M33/M55 共用 KitProg3 USB-UART `COM26`。
- M33/M55 都会向串口打印日志，但当前 FINSH shell 由 M55 侧接管。

根因：

- 串口日志能看到 M33 输出，不等于 M33 FINSH shell 可交互。
- M33 侧测试命令无法直接从当前 shell 调用。

解决：

- 不另开跨核链路，复用现有 `MSG_TYPE_VOICE_CONTROL`。
- M55 新增 `req_snap` 命令，发送 `VOICE_CTRL_PUBLISH_TEST_SNAPSHOT` 给 M33。
- M33 收到后调用 `m55_model_input_bridge_publish_snapshot()`，再走正式 `MSG_TYPE_SENSOR_SNAPSHOT` 回 M55。

技巧：

- 验证 M33 数据进入 M55 时，用 `req_snap`，不要用 M33 侧 `m55_snap`。
- 期望闭环日志是 `model_input_request_m33_snapshot ret=0`、`[m33] ipc publish test snapshot`、`[model_input] snapshot ...` 和新的 `0x323#B5...`。

状态：

- 2026-06-04 已上板验证通过；NanoPi 抓到 `323#B50A01012A831400`，ROS `/rehab_arm/model_state` 出现完整 JSON。

### 不要只凭 `wifi` 目录名认定 M55 工程

现象：

- 工作区有多个 M55/WiFi/参考目录，例如 `wifi`、`_m55_ref_repo`、`yiliao1_m55`。
- `wifi` 目录名看起来像 M55 工程，但当前 `git status` 报 `fatal: not a git repository`。
- 2026-06-17 复核仍是同一结论：`_m55_ref_repo` 是可提交的 `M55` 分支 checkout，`wifi` 只能当 RT-Thread Studio build/burn workspace。

环境：

- 主仓库 `docs/PSoC_README.md` 记录过 `git clone -b M55 git@github.com:ChillAmnesiac/Medical-Rehabilitation-Manipulator.git wifi`。
- `_m55_ref_repo` 是同一 GitHub 远端的 `M55` 分支，Git 正常，最新提交 `1cd7f69 同步当前M55工程版本`。

根因：

- 本地目录名只能说明历史用途，不能证明当前工程主线；`wifi` 的 `.git` 目录已损坏或不完整。

解决：

- M55 主线判断必须从 GitHub 远端、分支、提交历史和主仓库文档交叉确认。
- `wifi` 可作为本地 M55 WiFi 工程文件参考、构建和烧录工作区；提交历史和正式分支基准以 `_m55_ref_repo` / GitHub `M55` 分支为准。
- 文档已增加 `M33_M55_IPC_BLE_FOUNDATION.md`，要求后续 AI 不要新造 M33/M55 通讯，也不要把旧参考工程当主线。

技巧：

- 遇到多个固件目录时先跑 `git remote -v`、`git branch --show-current`、`git log -1 --oneline`，再用主仓库文档反查。
- 如果某目录 Git 损坏，不要在该目录做架构结论；找同远端同分支的有效副本或重新 clone。

状态：

- 已记录为架构约束；2026-06-04 已同时在 `_m55_ref_repo` 和实际 `wifi` 工程加入 `model_result_publisher.*`，以免 Git 证据仓库和 RT-Thread Studio 打开的 WiFi 工程脱节。

### M33/M55 小模型链路不要堆进 main.c

现象：

- M55 已有 wake-word/voice 小模型，M33 已有 IPC 和 CAN 控制层，但如果直接在 `main.c` 里拼 AI、IPC、CAN 逻辑，后续 EMG、语音、疲劳模型会很快变成不可维护的一坨。

根因：

- M55 小模型结果、M33 安全绑定、NanoPi ROS topic 是三个不同边界；混在入口文件会让后续 AI 分不清 side-channel 和 mainline。

解决：

- M55：用 `applications/model_result_publisher.*` 发布 `MSG_TYPE_AI_INFERENCE_RESP`。
- M33：用 `applications/m33/m55_model_bridge.*` 消费 IPC 结果，再调用 control layer 的 `control_publish_m55_model_result()`。
- NanoPi：用 `m33_model_status.py` 解析 `0x323` 并发布 `/rehab_arm/model_state`。

技巧：

- `0x323` 是模型建议帧，marker 为 `0xB5`，flags bit7 必须代表 suggestion_only。
- `/rehab_arm/model_state.control_boundary` 必须保持 `model_suggestion_only_not_motion_permission`。
- 没有烧录 M33/M55 前，只能说本地代码地基已补，不能说上板链路已通过。

状态：

- 2026-06-04 已上板验证到 CAN：M33/M55 都已启动，NanoPi `candump` 抓到 `0x323#B5...` 连续模型建议帧。
- 早期一次复测中 `/rehab_arm/model_state` publisher 存在但没有新 `0x323` 样本，`echo --once` 等不到数据；这只是“没有新样本”，不是 topic 缺失。
- 后续已通过 M55 shell `req_snap` 验证完整闭环：`M55 -> M33 request -> M33 sensor snapshot -> M55 model_input_bridge -> M33 0x323 -> NanoPi /rehab_arm/model_state`，ROS JSON 包含 `source=m33_m55_bridge_can_0x323` 和 `control_boundary=model_suggestion_only_not_motion_permission`。

### ROS2 topic 看不到但进程存在时先查 ROS_DOMAIN_ID

现象：

- NanoPi 上 `ps -ef` 能看到 `psoc_can_bridge_node.py` 正在跑，`candump` 也能看到 `0x322` 和 `0x330~0x334`。
- 但 `ros2 node list` 只显示空或只显示 `/parameter_events`、`/rosout`，容易误判 bridge 没发布 topic。

根因：

- 当前 NanoPi 和仿真主机通过 `~/.rehab_arm_ros2_network` 使用 `ROS_DOMAIN_ID=42`。
- 如果新开的 SSH shell 没有 source 这个文件，ROS CLI 默认在 domain 0 查询，自然看不到 domain 42 的节点。

解决：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
ros2 node list
ros2 topic list -t
```

仿真主机同理：

```bash
source /opt/ros/jazzy/setup.bash
source ~/.rehab_arm_ros2_network
source ~/桌面/Medical-Rehabilitation-Manipulator/rehab_arm_ros2_ws/install/setup.bash
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
```

通过标准：

- NanoPi 能看到 `/rehab_arm_psoc_bridge`。
- 仿真主机和 NanoPi 都能看到 `/medical_arm_6dof_shadow_sim`、`/medical_arm_shadow_relay`。
- 仿真主机能 echo 到 6DOF `/joint_states`。

技巧：

- 先看运行进程环境：`tr '\0' '\n' < /proc/<pid>/environ | grep ROS_DOMAIN_ID`。
- 不要因为 domain 查错就重写 launch 或另起 demo。

### PSE84 外部 flash 烧录必须带工程 qspi_config.cfg

现象：

- OpenOCD 使用 `target/infineon/pse84xgxs2.cfg` 和 `PSE84_SMIF.FLM` 时，看起来命令能运行，但写 M33 `0x60340400` 会出现 `no flash bank found for address 0x60340400`，随后 `wrote 0 bytes`。
- 如果只看 OpenOCD 退出码，容易误以为烧录成功。

环境：

- Windows RT-Thread Studio，PSoC Edge E84 `PSE846GPS2DBZC4A`。
- OpenOCD: `D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin\openocd.exe`
- 工程生成的 QSPI bank 配置：`libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource/qspi_config.cfg`

根因：

- Cat1D OpenOCD 脚本在加载 target cfg 时会 `source [find qspi_config.cfg]`，然后根据 `SMIF_BANKS` 注册 `0x60000000` 外部 flash bank。
- 命令行没有把工程 `GeneratedSource` 加入 `-s` 搜索路径时，`qspi_config.cfg` 找不到，`cat1d.cm33.smif1_ns` 不会注册。

解决：

```powershell
& 'D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin\openocd.exe' `
  -s 'D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/scripts' `
  -s 'D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/flm/cypress/cat1d' `
  -s 'D:/RT-ThreadStudio/workspace/yiliao_m33/libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource' `
  -f interface/kitprog3.cfg `
  -c 'set QSPI_FLASHLOADER D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/flm/cypress/cat1d/PSE84_SMIF.FLM' `
  -f target/infineon/pse84xgxs2.cfg `
  -c 'transport select swd' `
  -c 'init; flash banks; shutdown'
```

通过标准：

- `flash banks` 必须列出 `cat1d.cm33.smif1_ns (cmsis_flash) at 0x60000000`。
- 真实烧录必须看到非 0 写入量，例如 M33 `wrote 565248 bytes`、M55 `wrote 946176 bytes`。

技巧：

- Windows OpenOCD Tcl 参数优先用正斜杠路径，避免反斜杠转义。
- M33 SCons 生成的 raw hex 是 `0x08340400` 运行地址；烧到外部 flash 前先用 edgeprotecttools relocation 输出 `0x60340400` 的 `build/rtthread.hex`。
- `edgeprotecttools run-config` 当前 secure merge 可能因本机缺 `proj_cm33_s_signed.hex` 失败；只要 relocation 已成功输出 `build/rtthread.hex`，在板上已有 secure/extended boot 的情况下可先烧这个 non-secure relocated hex。

### CANSimple 主机查询帧不能刷新 M33 电机 fresh 时间戳

现象：

- NanoPi 发 `cansimple get-error --node 3` 后，抓包只有主机 TX `0x063#00`，没有 3 号真实 `0x061/0x069`。
- 但 M33 `0x330` 短暂变成 `flags=0x00`，看起来像 motor3 有新鲜反馈。

环境：

- M33 `ctrl_update_motor_feedback_cansimple()` 会看到标准帧 CANSimple ID。
- NanoPi SocketCAN/M33 在同一 CAN 总线上，主机发出的查询帧也可能被 M33 接收。

根因：

- 旧逻辑进入 CANSimple 解析后，在 switch 前就设置 `fb.timestamp = rt_tick_get()`。
- 因此任何属于 node3 的标准帧，只要没有被前面的特殊分支返回，都可能刷新 motor3 timestamp，即使它只是主机发出的查询帧或未知命令。

解决：

- M33 改为只在真实反馈内容有效时刷新 timestamp：
  - heartbeat `0x061` 且长度足够。
  - MIT feedback。
  - encoder estimate `0x069`。
  - torque feedback。
- `get-error` 请求、address 请求、未知 CANSimple 命令不更新 `s_motor_feedback[]`。

技巧：

- 验证 fresh 必须同时看原始反馈帧和 M33 聚合帧：没有 `0x061/0x069` 时，`0x330` 不应清 stale。
- CANSimple 主机命令帧不能作为电机在线证明。

状态：

- 已烧录复测通过，并在后续重复烧录后再次确认：发送 `0x063#00` 后，`0x330` 48 条全部保持 `flags=0x10`；没有真实 `0x061/0x069` 时 M33 不再假 fresh。

### M33 只在有新鲜反馈时发 0x330 会让平台误判“无遥测”

现象：

- NanoPi 和仿真主机可以看到 `0x321/0x322`，但 `/rehab_arm/motor_state` 没有样本。
- 只读 presence report 显示 `valid_m33_motor_status_count=0`，同时 `target_0x320_count=0`。

环境：

- M33 电机状态帧合同：`0x330~0x337`，8 字节，byte0=`0xB3`。
- 当前 M33 配置 7 个电机槽位，实际周期帧为 `0x330~0x336`，`0x337` 预留。

根因：

- 旧 M33 遥测线程只发布 `CONTROL_M33_MOTOR_STATUS_FRESH_MS` 内有电机反馈的槽位。
- 如果电机未上电、active-report 未打开、反馈没进缓存，NanoPi 看到的不是“stale 状态”，而是完全没有电机状态帧，平台和仿真主机无法判断是缺反馈还是固件没跑。

解决：

- M33 改为周期发布所有已配置槽位。
- 没有新鲜反馈时，payload 保留对应 `motor_id`，位置/速度为 0，温度为 `0xFF`，`flags bit4=stale_or_no_feedback`。
- NanoPi parser 保留 stale 帧到 `/rehab_arm/motor_state`，但不把 stale 帧转成 `/joint_states`。

技巧：

- `/rehab_arm/motor_state` 可以显示“这个槽位缺反馈”；`/joint_states` 只能放真实新鲜姿态。
- 后续平台 three.js/URDF 预览要优先看 `data_fresh`，不要把 stale 的 0 rad 当真实姿态。

状态：

- 代码和 ROS parser 已更新；M33 需要用户编译烧录后上电只读验证。

### 0x330 遥测 ID 必须按 ROS 关节槽位，不要按 M33 内部 motor slot

现象：

- 用户烧录后，M33 已稳定发 `0x330~0x336`，presence checker 通过。
- 但 `/rehab_arm/motor_state` 中 `0x330` 的 `motor_id=1`、`0x331` 的 `motor_id=2`。
- 平台/仿真如果直接按 `0x330 -> shoulder_lift_joint` 显示，会把内部旧槽位当成正式关节，导致真实电机和机械臂关节错位。

环境：

- 正式 ROS 机械臂是 5 个关节：ROS joint `0..4`。
- 当前真实电机是 motor slot `3/4/5/6/7`。
- NanoPi parser 约定 `0x330..0x334` 对应 ROS joint `0..4`。

根因：

- M33 第一版常驻遥测循环遍历了 `CONTROL_MOTOR_JOINT_COUNT` 内部槽位 `1..7`。
- 这适合底层调试，但不适合作为正式 ROS/仿真/平台统一状态合同。

解决：

- M33 遥测循环改为遍历 `CONTROL_ROS_JOINT_COUNT`。
- 每个 status slot 先通过 `ctrl_ros_joint_to_motor_joint()` 映射到真实 motor slot，再读取对应 `s_motor_feedback[motor_joint - 1]`。
- 新合同：`0x330..0x334` 的 byte2 应为 `3/4/5/6/7`；`0x335..0x337` 预留。

技巧：

- 验收时不要只看 `0x330` 是否存在，还要看 byte2 的 motor_id 是否符合正式 ROS 映射。
- 如果 `0x330` 是 motor_id `1`，说明跑的是旧映射固件，不能接仿真姿态或平台 three.js。

状态：

- 已重新烧录验证：`0x330..0x334` 的 byte2 为 `03/04/05/06/07`，`/rehab_arm/motor_state` 关节名和 motor_id 对齐；stale 帧不生成 `/joint_states`。

### M33 槽位 stale 但 active-report 后仍无原始电机帧

现象：

- M33 周期发 `0x330..0x334`，且 motor_id 映射正确。
- 所有帧 byte3 都是 `0x10`，表示 `stale_or_no_feedback`。
- 被动抓包没有 3 号 `0x061/0x069`，也没有 7 号 `0x180007FD/0x188007FD`。
- 通过 M33 `0x320#060401` telemetry-only active-report 打开 joint4/motor7 后仍无 7 号原始反馈。
- NanoPi 直接 telemetry-only snapshot 打开 motor7 active-report 也无 `0x180007FD`。

环境：

- NanoPi `can0` 正常，`ERROR-ACTIVE`，1Mbps。
- M33 heartbeat/status 在线，示例：`0x321#2A -> 0x322#A52A070001020100`。

根因判断：

- 这不是 NanoPi parser 问题，也不是 M33 `0x330` 映射问题。
- 如果 M33 和 NanoPi 都只能看到 M33 自己的聚合 stale 帧，说明电机原始反馈源当前没有出现在 CAN 总线上。
- 常见原因是电机侧未上电、驱动未在线、CAN 分支/连接/终端问题、或者该电机当前未接受 active-report 请求。

解决：

- 现场先确认电机侧供电和驱动状态。
- 被动抓包先等 3 号 `0x061/0x069` 或 7 号 `0x180007FD/0x188007FD` 出现，再要求 M33 stale 位清零。
- 不要用位置/速度目标来“试探”反馈链路；先把原始反馈证明出来。

技巧：

- `0x330..0x334` 存在只说明 M33 发布线程在线；是否有真实电机反馈要看 stale 位和原始电机帧。
- M33 stale 位不清零时，`/joint_states` 不发布是正确行为，不要为了显示姿态把 stale 0 位姿放进去。

状态：

- 已定位到电机原始反馈未出现；等待现场电机侧供电/在线状态确认。

### 灵足 4~7 Get_ID 全无回复但 CAN 控制器健康

现象：

- `nanopi_can_master.py probe --motor 7` 发送 `0000FD07#0000000000000000`，无 7 号回复。
- `probe --start 4 --end 7` 对 4/5/6/7 发送 Get_ID，也无任何电机回复。
- 抓包中只有 M33 `0x330..0x334` stale 帧和 NanoPi 发出的 probe 帧。
- `ip -details -statistics link show can0` 仍显示 `ERROR-ACTIVE`，tx/rx error `0/0`，bus-off/error-pass 都为 0。

环境：

- NanoPi MCP2518FD `can0` classic CAN 1Mbps。
- M33 在线，heartbeat 可回 `0x322`。
- 灵足 4/5/6/7 按私有扩展帧协议探测。

根因判断：

- 不是 NanoPi SocketCAN 挂了，也不是总线整体 bus-off。
- M33 能持续发帧、NanoPi 能发 probe，说明主干 CAN 控制器工作。
- 4~7 全部无回复时，优先怀疑电机侧供电、驱动状态、CAN 支路/接线、终端、节点 ID 或电机侧协议状态。

解决：

- 现场先确认电机驱动板供电和指示灯。
- 查 4~7 所在 CAN 支路是否真的接入同一总线，CANH/CANL 是否反接，GND 是否共地。
- 确认终端电阻和线束没有只接到 M33/NanoPi 一段。
- 在没有看到任一原始电机帧前，不要继续用位置/速度命令试探。

状态：

- 已完成非运动探测；等待现场硬件侧确认。

### MCP2518FD 驱动加载了，但没有 can0

现象：

```bash
ip -details link show can0
# Device "can0" does not exist.

lsmod | grep -E "mcp|can"
# mcp251xfd 已加载

dmesg | grep -Ei "mcp251|mcp251xfd|spi3"
# Failed to read Oscillator Configuration Register (osc=0x00000000)
# error -ENODEV: Failed to detect MCP2518FD
```

环境：

- NanoPi M5
- MCP2518FD SPI CAN 模块
- SPI 设备节点能看到，例如 `spi3.0`

排查：

- 内核模块存在不等于 CAN 设备存在。
- `/sys/bus/spi/devices` 能看到 SPI 设备，也不等于 MCP2518FD 芯片通信正常。
- `dmesg` 里 `Failed to read Oscillator Configuration Register` 是关键。

根因：

- 驱动探测 MCP2518FD 失败，可能原因包括供电不稳、晶振/时钟不工作、SPI 接线/片选/中断/设备树配置不对、模块未正确上电。

解决：

- 先查供电和共地。
- 再查 SPI 的 CS/SCK/MISO/MOSI 和 INT。
- 再查设备树里的 oscillator frequency、interrupt GPIO、spi bus、cs。
- 不要只看 `lsmod`，必须看 `ip link` 和 `dmesg`。

技巧：

- `lsmod` 只能说明驱动加载，不说明设备探测成功。
- `can0` 不存在时，优先看 `dmesg`，不要直接改 ROS 代码。

相关命令：

```bash
ip -details link show can0
lsmod | grep -E "mcp|can"
ls /sys/bus/spi/devices
dmesg | grep -Ei "mcp251|mcp251xfd|spi"
```

状态：

- 已记录。后续如果再次出现，按硬件/设备树优先排查。

### CAN 总线调试要先证明有心跳

现象：

- ROS 节点或控制脚本发命令，但电机不动。
- 不确定是协议错、CAN 线错、波特率错还是目标节点不在线。

排查：

- 先把 `can0` 拉起来。
- 先 `candump` 或 `nanopi_can_master.py monitor`。
- 对 CANSimple 节点，先找 heartbeat。

当前已知：

- `node_id=3` 的 CANSimple heartbeat 是标准帧 `0x061`。

技巧：

- 没看到 heartbeat 前，不要调控制参数。
- 没看到 RX 前，不要急着改协议 payload。
- 有一个独立观察者很重要，例如 `candump can0`。

相关命令：

```bash
ip -details link show can0
candump can0
~/nanopi_can_master.py monitor --iface can0 --seconds 5
```

状态：

- 已记录。正式控制前继续坚持这个顺序。

## CAN 协议与电机 ID

### 0x320 的 joint id 是 ROS 关节号，不是电机 ID

现象：

- 发送 `0x320#03072C0103000000` 试图让 7 号电机到 `+30°`，现场没有动。
- CAN 上能看到 M33 在线、`0x320` 已发送、7 号 active-report 存在，但 `0x180007FD` 和 `0x336` 没有随目标变化。
- 直接用 `nanopi_can_master.py private speed --motor 7 --vel 0.30 --kd 1.0`，7 号能动，原始反馈和 M33 `0x336` 都变化。

环境：

- NanoPi `can0` classic CAN 1Mbps，`ERROR-ACTIVE`
- M33 正式控制入口：`0x320`
- 7 号灵足 EL05 私有协议直驱可用

根因：

- `0x320` byte1 表示 ROS trajectory joint id，不是真实电机 ID。
- M33 旧代码把 ROS joint id 用 `ros_joint + 1` 映射到 motor slot，导致 ROS `0..4` 打到 motor `1..5`，没有覆盖真实 `3..7` 电机组合。
- 手动发 `joint=7` 会被 M33 当作未知 ROS joint，而不是电机 7。

解决：

- M33 本地工程已改为显式映射：

```text
ROS joint 0 shoulder_lift_joint      -> motor slot 3
ROS joint 1 elbow_lift_joint         -> motor slot 4
ROS joint 2 shoulder_abduction_joint -> motor slot 5
ROS joint 3 upper_arm_rotation_joint -> motor slot 6
ROS joint 4 forearm_rotation_joint   -> motor slot 7
```

- 后续要通过正规链路动 7 号，应发：

```bash
python3 /home/pi/nanopi_can_master.py m33 target --iface can0 --joint 4 --deg 30 --rpm 3 --torque-ma 0
```

技巧：

- 调试时要区分三层 ID：ROS joint id、M33 motor slot、厂家 motor/node id。
- `nanopi_can_master.py private --motor 7` 的 `7` 是厂家电机 ID；`m33 target --joint 4` 的 `4` 是 ROS 关节号。
- 看到 `0x320` 发出但电机不动时，先查 M33 是否拒绝 unknown joint，再查映射表。

状态：

- M33 源码已修并烧录后复测：`0x320#03042C0103000000` 会触发 M33 输出 `0x0300FD07` 和 `0x01800007` 到 motor7。映射问题已基本确认修复。
- 现场反馈发生剧烈转动。已发送软件 stop，并把 M33 默认 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE` 改回 `0`，避免未标定 `0x320` 绝对位置目标继续输出。
- 后续重点转为 motor7 的零点、目标角、MIT 参数和真实输出角标定；未完成前禁止再次发 ROS 位置目标到电机。

### 未标定绝对位置目标会造成剧烈转动

现象：

- `m33 target --joint 4 --deg 30 --rpm 3 --torque-ma 0` 经 M33 映射后触发 motor7 私有 MIT 控制帧。
- 现场反馈发生剧烈转动。

根因：

- 7 号当前没有建立可信零点、方向、当前位置到关节输出角的关系。
- M33 把 ROS joint/output 目标换算成 motor-side 绝对位置目标后发给私有 MIT 控制；如果电机内部当前位置参考和外部关节零点不一致，`+30°` 可能变成很大的绝对位置追踪动作。

解决：

- 立即发送 M33 stop 和 private stop。
- 默认关闭 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE`。
- 后续只允许使用低速、短时、可停止的速度脉冲做方向/比例标定；不要直接使用绝对位置目标。

技巧：

- 绝对位置控制必须排在零点、方向、反馈比例和限位全部确认之后。
- 正规链路打通不等于可以发位置目标。先证明“发到了”，再证明“单位正确”，最后才做位置闭环。

状态：

- 已采取软件停止和默认禁用措施；等待重新编译烧录禁用版 M33。

### 减速比必须在 NanoPi、文档、M33 三处一致

现象：

- 7 号电机用直接调试命令跑 3 秒，现场视频和用户目测约 `150°` 输出转动。
- 这说明现阶段不能把脚本里的速度参数、私有协议 raw 角度字段和真实关节输出角度简单画等号。
- 进一步检查发现 M33 配置里 joint3 仍是 `10:1`，joint4/5/6/7 仍是 `1:1`，与已确认型号不一致。

环境：

- NanoPi SocketCAN 调试工具：`nanopi_can_master.py`
- M33 本地工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`
- 当前确认电机：3 号伺泰威 `48:1`，4/5 灵足 RS00 `10:1`，6/7 灵足 EL05 `9:1`

根因：

- 历史配置默认值没有随着真实电机型号确认同步。
- 厂家协议 raw 值、转子侧单位、减速后输出侧单位混在一起时，容易造成“看起来角度限位是 60 度，实际转了很多”的风险。

解决：

- M33 `applications/control/control_layer_cfg.h` 已同步减速比：joint3 `48.0f`，joint4/5 `10.0f`，joint6/7 `9.0f`。
- 文档和 NanoPi 遥测也记录相同型号/减速比。
- 正式路径必须统一使用 joint/output-side 单位，M33 内部再按减速比转换为 motor-side 单位。

技巧：

- 看到电机“明显转多了”时，先查单位层：输出关节角、转子角、厂家 raw 编码、脚本参数、减速比。
- 未校准前，不能用单一 raw 反馈字段做停止条件。
- 调试直控可以证明“能动”，不能证明“正式安全角度映射正确”。

状态：

- 已修正 M33 配置；等待 M33 重新编译、烧录和现场复测。

### Windows 命令行编译 M33 需要 ARM 工具链进 PATH

现象：

- `scons -j4` 提示 `scons` 不是可识别命令。
- `mingw32-make -j4` 能进入 Debug 构建入口，但目标被判断为最新。
- 强制重编 `applications/control/control_layer.o` 时调用 `arm-none-eabi-gcc`，随后失败：系统找不到指定的文件。

环境：

- Windows PowerShell
- RT-Thread Studio 生成的 `Debug/makefile`
- 本机能找到 `mingw32-make.exe`，但当前 shell PATH 找不到 `arm-none-eabi-gcc`

根因：

- RT-Thread Studio IDE 可能自带/配置了交叉编译器，但当前命令行环境没有继承 ARM GCC 路径。

解决：

- 用 RT-Thread Studio 直接构建，或把 IDE 使用的 `arm-none-eabi-gcc` 所在目录加入 PowerShell PATH 后再运行 `mingw32-make`。

技巧：

- `mingw32-make -j4` 返回 up to date 不等于刚改的头文件已重编。
- 需要确认时可以强制指定目标：`mingw32-make applications/control/control_layer.o -B`。

状态：

- 未修复；等待本机工具链 PATH 配好或使用 IDE 构建。

### 不要把旧文档 CAN ID 当成当前真实链路

现象：

- 旧文档里出现过旧规划 ID。
- 当前现场真实链路已经变成 `node_id=3`、`motor_id=4/5/6/7`、`0x320/0x321/0x322`、`0x7C2/0x7C3`。

根因：

- 项目经历过多轮方案变化，旧规划文档和当前现场硬件链路不一致。

解决：

- 主 README 和主架构文档只记录当前真实链路。
- 旧文档只能作为历史资料，不能作为当前实现依据。

技巧：

- 当前 CAN ID 只认主 README 和 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`。
- 机械关节绑定还没确认前，不要把 `motor_id=4/5/6/7` 写死为正式关节。

状态：

- 已从主 README 和主架构文档移除旧规划 ID。

### 调试直控协议不能进入正式 ROS bringup

现象：

- `nanopi_can_master.py` 能直接让电机动。
- 容易误以为正式 ROS 节点也应该直接发同样的电机 CAN 帧。

根因：

- 调试工具用于 bring-up 和诊断，正式系统需要 M33 做安全责任方。

解决：

- 调试路径：

```text
NanoPi debug tool -> direct CANSimple/private motor frame -> motor
```

- 正式路径：

```text
JointTrajectory -> NanoPi -> CAN 0x320/0x321 -> M33 -> motor
```

技巧：

- 能直控电机只说明 CAN 和协议可用，不说明正式安全链路完成。
- ROS bringup 不启动 `private` 或 `cansimple` 直控运动逻辑。

状态：

- 已写入 README 和架构文档边界。

## ROS2 与 Python 节点

### `ros2 run` 找不到 Python 节点

现象：

```bash
ros2 run rehab_arm_sim_mujoco mujoco_sim_node
# 找不到可执行

ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py
# 也可能找不到

ls install/rehab_arm_sim_mujoco/lib/rehab_arm_sim_mujoco
# 能看到 mujoco_sim_node.py
```

排查：

- `ros2 pkg executables rehab_arm_sim_mujoco` 是否能列出节点。
- 源文件是否有 shebang。
- 源文件是否有 executable bit。

根因：

- `install(PROGRAMS ...)` 安装 Python 脚本时，脚本本身需要可执行权限。
- Windows 工作区创建文件时容易没有 Linux executable bit。

解决：

```bash
git add --chmod=+x rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py
chmod +x /home/pi/rehab_arm_ros2_ws/src/rehab_arm_sim_mujoco/rehab_arm_sim_mujoco/mujoco_sim_node.py
colcon build --symlink-install --packages-select rehab_arm_sim_mujoco
source install/setup.bash
ros2 pkg executables rehab_arm_sim_mujoco
```

技巧：

- 看到 install 目录有文件，不代表 `ros2 run` 能发现它。
- 先用 `ros2 pkg executables 包名` 判断 ROS 认不认识这个可执行。

状态：

- `rehab_arm_sim_mujoco` 已修复 executable bit，`ros2 pkg executables` 能看到 `mujoco_sim_node.py`。
- `rehab_arm_control` 也遇到同类风险，已给 `demo_trajectory_node.py` 和 `vla_task_planner_node.py` 设置 executable，`ros2 pkg executables rehab_arm_control` 能看到两个节点。

### `timeout` 结束 ROS2 Python 节点时出现 shutdown 异常

现象：

```text
rclpy._rclpy_pybind11.RCLError: failed to shutdown: rcl_shutdown already called
rclpy.executors.ExternalShutdownException
```

环境：

- ROS2 Jazzy
- Python `rclpy`
- 用 `timeout 4 ros2 run ...` 做短时间运行测试

根因：

- `timeout` 结束进程时，ROS context 可能已经 shutdown。
- 节点 finally 里再次 `rclpy.shutdown()` 会触发二次 shutdown。
- Jazzy 可能抛 `ExternalShutdownException`。

解决：

- shutdown 前检查：

```python
if rclpy.ok():
    rclpy.shutdown()
```

- spin 捕获：

```python
from rclpy.executors import ExternalShutdownException

try:
    rclpy.spin(node)
except (KeyboardInterrupt, ExternalShutdownException):
    pass
```

技巧：

- `timeout` 是很好的节点冒烟测试工具，但要让节点优雅处理外部终止。
- 运行测试通过不应留下 Python traceback。

状态：

- 已修复并在 NanoPi 上验证：
  - `timeout 4 ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py` 能干净结束。
  - 节点启动日志正常，无 Python traceback。
- `rehab_arm_psoc_bridge` 还额外遇到 `rclpy._rclpy_pybind11.RCLError: failed to initialize wait set`，已通过捕获 `RCLError` 修复，`timeout 4 ros2 run rehab_arm_psoc_bridge ...` 能干净结束。

### Bridge 打印 TX heartbeat 不代表总线 ACK 成功

现象：

`rehab_arm_psoc_bridge` 启动后能打印：

```text
PSoC CAN bridge ready on can0
TX 321 01
```

但 CAN 统计显示：

```text
TX packets: 0
TX errors/dropped 增加
```

并且没有看到 M33 的 `0x322` 回复。

环境：

- NanoPi `can0`
- 1Mbps
- `ERROR-ACTIVE`
- `rehab_arm_psoc_bridge` 只发 heartbeat，不发轨迹

根因：

- ROS 节点成功调用 `sock.send()` 只能说明帧写入 SocketCAN。
- `TX packets` 不增加且 dropped 增加，说明帧没有成功发到总线或没有被 ACK。
- 可能原因包括 M33/PSoC 没上电、没接入总线、固件未运行、波特率不一致、总线缺少 ACK 节点、接线/终端异常。

解决：

- 不要继续发轨迹。
- 先用原始工具对照：

```bash
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
candump can0
ip -details -statistics link show can0
```

- 只有看到 `0x322` 回复或 TX packets 正常增长，才算 heartbeat 链路通过。

技巧：

- 应区分“应用层尝试发送”和“CAN 总线发送成功”。
- 对 CAN heartbeat 验证，至少要看一种总线层证据：`0x322` 回复、TX packets 增长、独立设备 candump 观察到帧。

状态：

- bridge 应用层启动和 heartbeat 尝试已通过。
- M33 回复/总线 ACK 未通过，下一步排查 PSoC/M33 在线状态和 CAN ACK。

### M33 heartbeat 未回复时要让 ROS 明确暴露 limited 状态

现象：

- `rehab_arm_psoc_bridge` 能打印 heartbeat：

```text
TX 321 01
TX 321 02
TX 321 03
TX 321 04
```

- 但没有 `0x322` 回复。
- `nanopi_can_master.py heartbeat --iface can0 --seq 7 --wait 1` 也只看到 TX，没有 RX。
- `can0` TX packets 不增加，TX errors/dropped 增加。

根因：

- 当前 M33/PSoC heartbeat/status 链路未通，可能是硬件未在线、固件未运行 heartbeat 任务、波特率/接线/ACK 问题。
- 软件如果只打印 TX，操作者容易误以为 bridge 正常。

解决：

- 在 `rehab_arm_psoc_bridge` 增加：
  - `status_timeout_sec` 参数，默认 `2.5`
  - `heartbeat_tx_count`
  - `status_rx_count`
  - `last_status_time`
  - 诊断定时器
- 当发出 heartbeat 但没有收到 `0x322` 时，发布：

```json
{"state":"limited","detail":"no PSoC status after 4 heartbeats","source":"psoc_bridge"}
```

技巧：

- bridge 的健康状态不能只看进程是否启动。
- PSoC/M33 未回复时，ROS safety topic 必须显式表达 limited/fault，方便 App、工作站和数据记录系统发现问题。

状态：

- 已实现并在 NanoPi 上验证 `/rehab_arm/safety_state` 能输出 limited。

### PSoC/M33 没有 ACK/0x322 时先确认电池电量

现象：

- NanoPi bridge 或调试脚本能尝试发送 heartbeat：

```text
TX 321 01
```

- `nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1` 没有收到 `0x322`。
- `can0` 仍是 `ERROR-ACTIVE`，但 TX packets 不增长，TX dropped/errors 增加。

环境：

- NanoPi `can0`
- 1Mbps classic CAN
- PSoC/M33 作为正式控制主站和 heartbeat/status 回复方

排查：

- ROS2 bridge 已能启动并调用 SocketCAN 发送。
- `can0` 已经 UP，说明 NanoPi 侧 CAN 接口存在。
- 没有 `0x322`，且 TX packets 不增长，说明总线层没有成功 ACK。

根因：

- 用户现场确认：电池没电，导致 PSoC/M33 或相关 CAN 节点未正常在线/供电不足，因此无法 ACK NanoPi heartbeat，也无法回复 `0x322`。

解决：

- 先给电池充电或更换电池。
- 确认 PSoC/M33、CAN 收发器和电机侧节点都正常上电。
- 再复测：

```bash
ip -details -statistics link show can0
~/nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1
```

技巧：

- CAN “发不出去/没有 ACK” 不一定是协议错，电源是第一检查项。
- 看到 `TX 321` 只能说明应用层尝试发送；看到 `0x322`、TX packets 增长或独立 CAN 工具观察到帧，才算总线层验证通过。

状态：

- 已确认并复测通过。
- 电池恢复后，`nanopi_can_master.py heartbeat --iface can0 --seq 1 --wait 1` 能收到：

```text
RX STD 0x00000322 [8] A5 01 07 00 48 EA 6D 00
```
- 2026-05-25 设备重新上电后再次复测：
  - `can0` 拉起到 `UP/LOWER_UP/ERROR-ACTIVE/1Mbps`。
  - 手动发送 `0x321` seq 1/2/3，均收到 `0x322`。
  - `can0` 错误计数器 `tx 0 rx 0`，`bus-off/error-pass` 均为 0。

### 上电后 can0 可能存在但仍是 DOWN/STOPPED

现象：

- NanoPi 上能看到 `can0`，但它还不能收发：

```text
can0: <NOARP,ECHO>
state DOWN
can state STOPPED
```

环境：

- NanoPi M5
- MCP2518FD / `mcp251xfd`
- classic CAN 1Mbps

处理：

```bash
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ip -details link show can0
```

通过标准：

```text
can0: <NOARP,UP,LOWER_UP,ECHO>
can state ERROR-ACTIVE
bitrate 1000000
berr-counter tx 0 rx 0
```

技巧：

- “设备存在”不等于“总线已工作”；每次上电后先确认 `UP/LOWER_UP/ERROR-ACTIVE`。
- `ERROR-ACTIVE` 且错误计数为 0 后，再做 heartbeat，不要直接发轨迹。

状态：

- 2026-05-25 已验证。

- ROS `rehab_arm_psoc_bridge` 也能发布 PSoC 来源的 `ok` safety state，说明这次无回复确实是供电问题，不是 ROS bridge 协议问题。
- 后续 bridge 安全门控测试中再次出现没电：正常 `status_timeout_sec` 下 bridge 持续 `no PSoC status after N heartbeats`，用户确认又没电了。低电量时停止测试，先恢复供电。
- 2026-05-25 用户烧录 M33 后，NanoPi `192.168.2.66` 真实局域网不可达；后续用户确认原因是忘记给设备上电。上电后 NanoPi SSH 恢复，`can0` 可拉起并收到 M33 V2 `0x322`。

技巧补充：

- 烧录完成不等于系统已上电运行；烧录后测试前先确认 NanoPi、M33、CAN 收发器三者都已上电。
- 如果 M33 串口在 Windows 上可见，但 NanoPi 不在线，说明“调试器/烧录器在线”和“整机控制链路在线”不是一回事。

### Bridge 门控拒绝轨迹时要同时看日志和 candump

现象：

- 测试 `rehab_arm_psoc_bridge` 轨迹安全门控时，发布了 `/arm_controller/joint_trajectory`。
- PSoC/M33 无新鲜 `0x322 ok` 状态。

验证：

- bridge 日志出现：

```text
safety limited: rejected trajectory: no PSoC status received
```

- 同时 `candump can0,320:7FF` 没有任何输出。

结论：

- 这表示 bridge 在不安全状态下拒绝轨迹，并且没有发送 `0x320`，符合穿戴设备“默认不动”的要求。

技巧：

- 只看 ROS topic 可能受发现时序影响；关键安全测试要同时看节点日志和 CAN 原始帧。
- 拒绝轨迹时的验收标准不是“有 limited 日志”一个条件，还要确认总线上没有 `0x320`。

状态：

- 已在 NanoPi 非运动条件下验证通过。
- 电池恢复后又验证了一种 PSoC 在线但轨迹超限的情况：

```text
safety limited: trajectory point 0 joint shoulder_lift_joint 99.000 outside [-0.700, 1.400]
```

- 同时 `candump can0,320:7FF` 为空，说明超限拒绝发生在发送 `0x320` 之前。

### 合法轨迹默认也要 dry-run，不要默认发送 0x320

现象：

- PSoC/M33 已经回复 `0x322 ok`。
- 轨迹也在软件限位内。
- 但 M33 侧 `0x320` 解析、日志、限幅和拒绝原因还没有完成对照。

解决：

- `rehab_arm_psoc_bridge` 增加 `enable_target_tx`，默认 `false`。
- 默认情况下合法轨迹只打印：

```text
DRY-RUN 320 joint=shoulder_lift_joint data=0300390005000000
```

- `candump can0,320:7FF` 应为空。

技巧：

- 对穿戴设备，合法轨迹也不等于可以发到控制主站；必须先有 M33 侧日志和安全裁决可观察。
- 只有在 M33 日志固件准备好、用户确认烧录并允许后，才临时打开 `enable_target_tx:=true`。

状态：

- 已在 NanoPi 上验证 dry-run：合法单关节轨迹只生成一个 shoulder dry-run 目标，没有发送 `0x320`。
- 同时修正了单关节轨迹会给未命令关节生成目标的问题。

### 对照 M33 日志前先用解码工具统一 payload 理解

现象：

- NanoPi dry-run 会打印 `DRY-RUN 320 ... data=0300390005000000`。
- M33 侧后续也需要解析同一组 bytes。
- 如果双方对端序、单位、缩放或关节编号理解不一致，可能出现日志看似正常但目标值错误。

解决：

- 新增协议文档 `docs/PSOC_CAN_PROTOCOL_V1.md`。
- 新增解码工具：

```bash
ros2 run rehab_arm_psoc_bridge decode_psoc_cmd.py 0300390005000000
```

已验证输出：

```text
joint_id: 0
joint_name: shoulder_lift_joint
deg_x10: 57
target_deg: 5.70000
target_rad: 0.09948
rpm: 5
torque_ma: 0
```

技巧：

- M33 串口日志应按同样字段打印，逐项对照。
- 对照通过前不要打开 `enable_target_tx:=true`。

状态：

- 本地和 NanoPi 均已验证解码工具。
- 也已新增并验证编码工具：

```bash
ros2 run rehab_arm_psoc_bridge encode_psoc_cmd.py shoulder_lift_joint 0.1
```

- 输出 payload `0300390005000000`，再用解码工具能反查为同一目标。
- 超限输入会被编码工具拒绝，不输出 payload。

### M33 日志固件第一版必须 logging-only

现象：

- 下一步需要 M33 侧接收真实 `0x320`，但系统是穿戴设备，不能因为“只是对照协议”就让电机动。

解决：

- 新增 `docs/M33_0X320_LOGGER_GUIDE.md`。
- M33 当前阶段收到 `0x320` 后只做：
  - 解析 payload。
  - 打印字段。
  - 打印 `decision/reason/safety_state`。
- 默认 `decision=reject`，`reason=logging_only_no_motor_output`。

技巧：

- 在 M33 日志、限幅、安全状态机全部可观察前，不要让 M33 把 `0x320` 连接到电机执行层。
- 需要烧录时由用户烧录；烧录前 NanoPi 保持 `enable_target_tx=false`。

状态：

- 已完成 M33 logging-only 参考指南，尚未烧录 M33。

### M33 安全判断不能长期藏在打印函数里

现象：

- M33 第一版 logging-only 固件能打印 heartbeat、joint、limit、rpm、torque 检查结果。
- 但这些判断最初集中在 `ctrl_log_ros_command_only()` 中，容易让人误解成“靠打印做安全”。

根因：

- 第一阶段为了确认 M33 是否正确解析 `0x320`，先把所有字段和判断都打印出来。
- 这适合做 bring-up 对照，但不适合成为正式安全状态机。

解决：

- 在 M33 `applications/control/control_layer.c` 中新增结构化安全评估：
  - `control_ros_safety_assessment_t`
  - `ctrl_assess_ros_command_safety()`
  - `CONTROL_ROS_SAFETY_*`
  - `CONTROL_ROS_DECISION_*`
  - `CONTROL_ROS_REJECT_*`
- 让安全判断先生成 `state/decision/reason`，日志函数只输出这个结果。
- 当前仍保持 `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`，所以合法帧也会 `decision=reject`，最终 `no_motor_output`。

技巧：

- bring-up 阶段可以多打印，但安全判断必须能脱离打印函数独立存在。
- 后续真实控制路径只能消费结构化 `assessment`，不能重新写一套散乱判断。
- 每次新增安全条件，要先进 `ctrl_assess_ros_command_safety()`，再考虑日志和状态上报。

状态：

- 本地 M33 已完成第一版结构化改造并编译通过，等待烧录后复测。
- 用户烧录后已完成非运动复测：合法 `0x320` 单帧得到 `safety_state=logging_only decision=reject reason=logging_only_no_motor_output` 和 `final action=no_motor_output logging_only=1`，说明安全评估已经脱离纯打印并形成结构化结果。

### 拒绝用例要绕过 NanoPi bridge 才能测到 M33 本体

现象：

- ROS bridge 默认会拒绝超限轨迹，不会把危险 `0x320` 发到 CAN。
- 这对正式系统是正确的，但如果要验证 M33 安全状态机是否真的能拒绝危险帧，就不能只用 ROS topic 测。

解决：

- 在 M33 logging-only、驱动断开、不穿戴条件下，用 NanoPi raw SocketCAN 直接发送单帧 `0x320`。
- 每个用例同时记录：
  - `candump can0,320:7FF,321:7FF,322:7FF`
  - M33 `COM26` 串口
  - `ip -details -statistics link show can0`

已验证：

```text
0300840305000000 -> reason=target_out_of_limit
0309390005000000 -> reason=unknown_joint
0300390005000100 -> reason=torque_out_of_limit
heartbeat age 3211ms + 0300390005000000 -> reason=heartbeat_timeout
030039001f000000 -> reason=velocity_out_of_limit
0100 -> reason=unsupported_command
heartbeat age 3211ms + 030084031f000100 -> reason=heartbeat_timeout
```

技巧：

- 正式路径里 NanoPi bridge 和 M33 都要有安全门；测试 M33 本体时需要有意识地绕过 NanoPi 门控，但必须保持 M33 `logging_only`。
- 每个危险用例都要确认最终还有 `final action=no_motor_output logging_only=1`。
- heartbeat 超时用例要先停止 bridge，避免 bridge 持续发 `0x321` 把 M33 heartbeat 刷新掉。
- 多错误优先级要单独测：当 heartbeat 超时和多个限位同时失败时，当前首要 reason 应该是 `heartbeat_timeout`。

状态：

- 第一轮和第二轮拒绝矩阵已通过，未给电机驱动上电，未做运动测试。

### 安全拒绝原因不能只留在串口里

现象：

- M33 串口能看到 `reason=target_out_of_limit` 等具体拒绝原因。
- 但 NanoPi/ROS 只看 `/rehab_arm/safety_state` 时，如果 `0x322` byte6 固定为 `logging_only_no_motor_output`，上层系统无法知道最近一次真正拒绝原因。

解决：

- M33 保存最近一次 ROS safety assessment 的 detail_code。
- `0x322` V2 byte6 使用最近一次 detail，而不是固定 `10`。
- NanoPi `psoc_status.py` 更新 detail 名称，与 M33 reason 对齐：
  - `2 -> unsupported_command`
  - `3 -> unknown_joint`

技巧：

- 串口适合 bring-up，但 ROS/App/服务器要依赖结构化状态。
- 每次新增 M33 reason，都要同步更新 `psoc_status.py`、协议文档和单元测试。
- detail_code 只表示首要拒绝原因；其他失败项可以继续留在 audit 日志或未来扩展状态帧里。

状态：

- M33 已本地实现并编译通过，NanoPi parser 单元测试 17 个通过，等待用户烧录后做非运动验证。
- 用户烧录后第一次非运动验证未通过：NanoPi `can0` 正常，能发 `0x321/0x320`，但无 `0x322`，COM26 也无输出。当前判断为 M33 应用未在线或烧录后未正常启动，尚未验证 detail_code 动态变化。

### 烧录后无 0x322 且串口静默，先怀疑应用没启动

现象：

```text
TX 321 01
NO RX
TX 321 02
NO RX
TX 321 03
NO RX
```

同时：

- `candump` 能看到 NanoPi 发出的 `0x321` 和 `0x320`。
- `can0` 仍为 `ERROR-ACTIVE`，错误计数为 0。
- Windows `COM26` 打开成功，但没有启动日志，发送换行也没有 shell/日志响应。

判断：

- 这不是 NanoPi parser 问题，因为没有任何 `0x322` 到达。
- 这也不是 ROS topic 问题，因为 raw SocketCAN heartbeat 都没有回复。
- 当前优先怀疑 M33 应用未运行、烧录后未复位到应用、烧录了错误镜像，或 M33 控制板供电/复位状态异常。

处理：

1. 现场按一下 M33 reset，或给 M33 控制板断电重上电。
2. 重测 raw heartbeat，只看 `0x321 -> 0x322`，不要发 `0x320`。
3. 如果仍无 `0x322`，重新烧录最新产物，优先使用：

```text
D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.bin
```

4. 烧录后确认串口有启动日志或 heartbeat 有 `0x322`，再继续 detail_code 验证。

状态：

- 已记录。本轮未给电机驱动上电，未做运动测试。

### 发送真实 0x320 单帧时必须同时看 NanoPi TX 和 M33 串口

现象：

- 用户已烧录 M33 logging-only 固件，并确认电机驱动电源断开。
- NanoPi 临时打开 `enable_target_tx:=true` 发单帧 `0x320`。

NanoPi 侧已验证：

```text
TX 320 0300390005000000
can0  320   [8]  03 00 39 00 05 00 00 00
```

技巧：

- 这只能证明 NanoPi 和 CAN 总线发出了 `0x320`，不能证明 M33 正确解析。
- 下一步必须看 M33 串口日志是否包含 `RX 320 dlc=8 data=0300390005000000`。
- 如果 M33 没有日志，优先查 M33 CAN filter、标准帧/扩展帧配置、DLC、CAN RX 回调是否被调用。
- 如果 M33 字段不一致，优先查 little-endian、字段偏移和单位缩放。

状态：

- NanoPi/CAN 侧单帧发送已通过。
- 已从本机 Windows `KitProg3 USB-UART (COM26)` 读取到 M33 日志：

```text
[control] ros cmd direct apply failed, cmd=3 joint=0 ret=-22
```

- 说明 M33 收到了 `cmd=3 joint=0`，但当前固件不是 logging-only 对照格式，而且可能进入了 direct apply 路径。
- 已停止继续发送 `0x320`，等待 M33 固件改为 logging-only。

### M33 出现 direct apply 日志时必须停止 0x320 测试

现象：

```text
[control] ros cmd direct apply failed, cmd=3 joint=0 ret=-22
```

环境：

- 电机驱动电源已断开。
- NanoPi 单帧发送 `0x320 data=0300390005000000`。
- M33 串口通过本机 Windows `COM26` 读取，115200 baud。

判断：

- `cmd=3 joint=0` 说明 M33 已经收到并识别了部分字段。
- `direct apply failed` 说明 M33 当前代码路径可能尝试把 ROS/CAN 命令交给控制应用层。
- 这不符合当前 logging-only 阶段要求。

处理：

- 不再继续发 `0x320`。
- 电机驱动继续断电。
- M33 固件应改为收到 `0x320` 后只打印字段和安全拒绝：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 joint_id=0 joint=shoulder_lift_joint deg_x10=57 target_deg=5.7 target_rad=0.09948 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output
safety_state=limited
```

状态：

- 已修复并复测通过。
- 用户烧录 M33 logging-only 固件后，再次通过 ROS bridge 发送同一个单帧 `0x320`。
- M33 串口输出：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output safety_state=limited
```

- 未再出现 `ros cmd direct apply failed`。
- 本轮未给电机驱动上电，未做运动测试。

### M33 logging-only 改完后必须本地编译通过再让用户烧录

现象：

- 需要把 M33 `0x320` 从 direct apply 路径切到 logging-only。
- 直接在命令行运行 `mingw32-make -C Debug all -j2` 时最初找不到 `arm-none-eabi-gcc`。

环境：

- Windows 本机工程：`D:\RT-ThreadStudio\workspace\yiliao_m33`
- RT-Thread Studio 自带 ARM GCC。

排查：

- 本机找到了可用编译器：

```text
D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin\arm-none-eabi-gcc.exe
```

解决：

- 只在当前 PowerShell 会话临时加 PATH，不改系统环境：

```powershell
$env:Path='D:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin;' + $env:Path
mingw32-make -C Debug all -j2
```

- 编译通过后才允许进入“请用户烧录”阶段。

技巧：

- 不要让用户烧录未经本地编译验证的固件。
- logging-only 模式下 `0x320` 必须在解析后立即返回，不能进入 `ctrl_apply_ros_command()` 或任何电机控制路径。
- 短帧日志打印应先把 payload 补零到 8 字节，避免串口日志读到旧数据。

状态：

- M33 本地编译已通过。
- 用户已烧录并完成单帧对照验证。
- 本次新增的安全补丁目标日志为：

```text
RX 320 dlc=8 data=0300390005000000
cmd=0x03 name=set_target joint_id=0 deg_x10=57 target_mrad=99 rpm=5 torque_ma=0
decision=reject reason=logging_only_no_motor_output safety_state=limited
```

### Windows 到 NanoPi 远程脚本要注意 CRLF

现象：

- 从 Windows PowerShell 用 here-string 通过 SSH 发送多行 bash 脚本到 NanoPi。
- 脚本末尾执行 `ip -details -statistics link show can0` 时，远端报：

```text
Device "can0\r" does not exist.
```

根因：

- Windows CRLF 换行里的 `\r` 被带到了 bash 参数中，`can0` 变成了 `can0\r`。

解决：

- 硬件/CAN 关键命令复查时，用单独 SSH 命令或先去掉 CRLF。
- 本次单独复查：

```bash
ip -details -statistics link show can0
```

确认 `can0` 为 `UP/LOWER_UP/ERROR-ACTIVE`，`bus-errors/error-pass/bus-off` 均为 0。

技巧：

- Windows 远程发多行 shell 脚本时，失败信息里如果出现奇怪的路径或设备名，要怀疑隐藏的 `\r`。
- 对安全验收相关的最后状态，尽量单独再查一次，避免被脚本换行问题污染结论。

状态：

- 已记录。本次 `0x320` 对照本身不受影响，CAN 和 M33 串口日志均已验证。

### Windows 的 Meta 虚拟网卡会误导 NanoPi 连通性判断

现象：

- 用户烧录 M33 后准备复测 NanoPi/M33 链路。
- `ssh pi@192.168.2.66` 一开始超时，后续出现 `kex_exchange_identification: Connection closed by remote host`。
- `Test-NetConnection 192.168.2.66 -Port 22` 显示 `TcpTestSucceeded=True`，但详情里源地址是：

```text
InterfaceAlias : Meta
SourceAddress  : 198.18.0.1
NextHop        : 198.18.0.2
```

排查：

- 本机真实局域网地址是 `192.168.2.9` 和 `192.168.2.10`。
- 强制从无线源地址测试：

```powershell
ssh -b 192.168.2.9 -o ConnectTimeout=8 pi@192.168.2.66 "hostname"
ping -S 192.168.2.9 -n 1 192.168.2.66
```

- 结果真实无线源地址到 `192.168.2.66` 超时，ARP 中也没有 `192.168.2.66`。

根因：

- Windows 路由把未绑定源地址的连接送进了 `Meta/198.18.0.x` 虚拟网卡或代理路径。
- 这个路径上的端口连通性不能证明 NanoPi 在真实 `192.168.2.0/24` 局域网在线。

解决：

- 验证 NanoPi 时优先强制源地址或明确真实网卡：

```powershell
ssh -b 192.168.2.9 pi@192.168.2.66 "hostname"
ping -S 192.168.2.9 -n 3 192.168.2.66
arp -a 192.168.2.66
```

- 只有真实 `192.168.2.x` 源地址能 SSH 到 NanoPi，才继续 `can0`、heartbeat 和 `0x320` 测试。

技巧：

- `Test-NetConnection` 通过时一定看 `InterfaceAlias` 和 `SourceAddress`。
- 不要把 `198.18.0.x` 代理/虚拟网卡结果当作 NanoPi 局域网已恢复。
- 网络路径不确定时，不发 CAN，不做硬件测试。

状态：

- 已记录。当前 M33 已烧录，但 NanoPi 真实局域网 SSH 未恢复，因此未发送 `0x321/0x320`。

### ROS bridge 验证前要清理旧进程

现象：

- 已同步并重建新版 `rehab_arm_psoc_bridge`。
- `ros2 topic echo /rehab_arm/safety_state` 仍看到旧格式 JSON，没有 `protocol_version` 字段。

排查：

- NanoPi 上还有旧 bridge 进程：

```bash
pgrep -af 'psoc_can_bridge_node|rehab_arm_psoc_bridge'
```

根因：

- CAN raw socket 和 ROS topic 都可能同时存在多个 bridge 进程。
- 旧进程继续发布 `/rehab_arm/safety_state`，会让测试看起来像新版没有生效。

解决：

```bash
kill <旧 bridge pid>
colcon build --symlink-install --packages-select rehab_arm_psoc_bridge
```

技巧：

- 每次验证 bridge 行为前先 `pgrep`。
- 如果怀疑是旧进程，清理后再看 `candump`、bridge 日志和 ROS topic。

状态：

- 已记录。本次清理旧进程后，NanoPi 能看到新版 `0x322` parser 输出 `protocol_version:1`。

### `ros2 topic echo` 太早启动时显式指定消息类型

现象：

```text
WARNING: topic [/rehab_arm/safety_state] does not appear to be published yet
Could not determine the type for the passed topic
```

环境：

- 远程脚本里先启动 `ros2 topic echo --once`，再启动短时 bridge。
- topic 发布器还没完成发现，echo 无法推断消息类型。

解决：

```bash
ros2 topic echo --once /rehab_arm/safety_state std_msgs/msg/String
```

技巧：

- 短时自动化测试里显式指定 ROS message type，比等待 topic discovery 更稳定。
- 如果 topic 本身是 JSON 字符串，抓到一条后再看里面的 `state/protocol_version/detail`。

状态：

- 已记录。后续 bridge topic 验证优先显式指定 `std_msgs/msg/String`。
- 2026-06-04 `nanopi_live_telemetry_check.sh` 已显式指定 `/rehab_arm/safety_state`、`/rehab_arm/motor_state`、`/joint_states` 和 `/sim/medical_arm/joint_states` 的消息类型。

### `ros2 topic echo --once` 发现 topic 后仍可能错过 MuJoCo shadow 首帧

现象：

- NanoPi `ros2 topic list -t` 已能看到 `/sim/medical_arm/joint_states [sensor_msgs/msg/JointState]`。
- 单次 `timeout 10 ros2 topic echo --once /sim/medical_arm/joint_states sensor_msgs/msg/JointState` 偶尔只输出 ROS discovery warning，没有拿到消息。
- 手工重跑或等一会儿后可以 echo 到 6 个 medical arm joint。

环境：

- NanoPi 通过无线 ROS2 接收仿真主机 `rehab-arm-sim-host-shadow.service` 发布的 MuJoCo shadow topic。
- 产品 NanoPi bridge 复用 `rehab-arm-nanopi-readonly.service`，不另启第二个 bridge。

判断：

- 这是短时自动化脚本里的 discovery/timing 竞态，不等于 MuJoCo 节点必然挂掉。
- 不能只凭一次 `echo --once` timeout 就判定仿真主机、DDS 网络或 MuJoCo 模型失败。

解决：

- 自动化脚本先等待 topic 出现在 `ros2 topic list`。
- 对 MuJoCo shadow 采样用多次 `echo --once` 重试，并检查期望 joint 名，例如 `jian_xuanzhuan_joint`。
- 给无线 ROS2 shadow 检查留更长超时，例如：

```bash
USE_EXISTING_BRIDGE=1 CHECK_SIM_SHADOW=1 ACTIVE_REPORT_MOTOR=none \
  SNAPSHOT_SECONDS=5 ECHO_TIMEOUT_SECONDS=15 \
  /home/pi/nanopi_live_telemetry_check.sh
```

技巧：

- 自动验收看最终语义：`/sim/medical_arm/joint_states` 里必须有 6 个 medical arm joint，并且 `name/position/velocity/effort` 长度一致。
- 普通只读验收仍必须同步抓 `can0,320:7FF`，确保没有意外目标帧。

状态：

- 2026-06-04 已修复 `scripts/nanopi_live_telemetry_check.sh`，远端实测 PASS：NanoPi `/joint_states forearm_rotation_joint=1.463`，MuJoCo `/sim/medical_arm/joint_states` 有 6 轴且 `jian_xuanzhuan_joint=1.0472`，`0x320` 抓包为空。

### V2 status limited 是安全通过，不是可运动

现象：

- M33 V2 status 固件烧录后，NanoPi 能收到：

```text
RX 322 [8] a501070001010a00
```

- ROS `/rehab_arm/safety_state` 输出：

```json
{"protocol_version":2,"state":"limited","control_mode":"logging_only","detail":"logging_only_no_motor_output"}
```

判断：

- 这说明 M33 在线、heartbeat/status 链路正常、V2 parser 正常。
- 但 `state=limited` 和 `control_mode=logging_only` 明确表示当前不是可运动状态。

处理：

- 当前阶段只允许继续做日志、安全状态机和单帧对照。
- 不要因为 heartbeat/status 通过就给电机驱动上电或发布运动轨迹。

状态：

- 已验证并记录。下一步继续设计 M33 `0x320` 安全审核日志，默认仍不输出电机控制。

补充：

- M33 上报 `limited/logging_only` 时，NanoPi bridge 默认会拒绝轨迹，这是正确安全行为。
- 如需做 M33 logging-only 审计单帧测试，才可以临时使用：

```bash
-p enable_target_tx:=true -p require_psoc_ok_for_trajectory:=false
```

- 这个参数组合只能用于电机驱动断开、外骨骼不穿戴、M33 固定拒绝输出的单帧审计；不能作为正式运动 bringup 配置。

### ROS 关节编号和 M33/电机编号不要混用

现象：

- NanoPi bridge 的 `0x320` payload 使用 ROS 关节编号，例如 `shoulder_lift_joint -> joint_id=0`。
- M33 控制层和底层电机驱动里可能还有电机 ID、CANSimple node_id 或私有 MIT motor_id。
- 如果把 ROS joint_id 当成真实电机 ID，后续一旦打开真实控制路径，可能驱动错误关节。

正确边界：

- `0x320` 的 `joint_id` 当前是 ROS 5 关节 0-based 逻辑编号。
- 当前已知真实电机链路仍只记录为 `node_id=3` 和 `motor_id=4/5/6/7`，机械关节绑定待确认。
- M33 必须保存一张独立的“ROS joint_id -> 安全审核 -> 真实电机通道”映射表。
- 在映射表、方向、限位、急停和单关节空载验证完成前，不允许把 `0x320` 直接接到底层电机输出。

技巧：

- 串口日志要同时打印 `joint_id` 和最终映射到的 motor/channel；没有映射时打印 `joint_known=0` 或拒绝原因。
- 当前 logging-only 审核日志里的 `limit_01deg` 是 ROS 关节限位，不等于电机原始编码器限位。
- 真实运动前必须逐个关节确认方向：正角度命令、机械运动方向、编码器反馈方向三者一致。

状态：

- 已记录。当前 M33 安全审核日志仍固定 `decision=reject`，不会进入真实电机控制路径。

### 没硬件时也要守住协议回归测试

场景：

- 用户不在现场，不能给硬件上电。
- 仍然可以推进不会触碰 CAN/电机的协议工具质量。

做法：

- 新增离线单元测试：

```bash
python -m unittest discover -s rehab_arm_ros2_ws\src\rehab_arm_psoc_bridge\test -v
```

- 覆盖 `encode_psoc_cmd.py` 和 `decode_psoc_cmd.py`。

状态：

- 已验证 10 个测试全部通过。

### NanoPi 看不到 M33 串口时不要误判为 M33 没日志

现象：

- 用户让 NanoPi 侧查看 M33 日志。
- NanoPi 上没有 `/dev/ttyUSB*`、`/dev/ttyACM*`、`/dev/serial/by-id/*`。
- 也没有正在运行的 `minicom/picocom/screen` 串口查看进程。

结论：

- M33 串口没有接到 NanoPi，不能从 NanoPi 直接查看。
- 串口日志大概率在用户烧录/调试用电脑或调试器连接的串口上。

同时确认：

```text
TX STD 0x00000321 [1] 04
RX STD 0x00000322 [8] A5 04 07 00 F6 E7 04 00
```

- `can0` 为 `ERROR-ACTIVE`，错误计数器 `tx 0 rx 0`，说明 CAN 链路仍然正常。

技巧：

- “看不到串口日志”要先分清是 M33 没打印，还是串口根本没接到当前主机。
- 如果要让 NanoPi 查看 M33 日志，需要把 M33 UART/USB-CDC 接到 NanoPi，或者提供调试电脑远程访问。

### SSH 远端 bash 里后台任务会影响 source 环境

现象：

一条 SSH 命令里先 source ROS 环境，再后台启动节点，再执行 `ros2 topic`，结果后面的命令找不到 `ros2`：

```text
bash: line 1: ros2: command not found
timeout: failed to run command 'ros2': No such file or directory
```

排查：

- 原命令大致是：

```bash
cd ws && . /opt/ros/jazzy/setup.bash && . install/setup.bash && timeout 10 ros2 run ... & pid=$!; ros2 topic list
```

- `&` 的优先级导致前面的链路被放进后台，后面的 `ros2 topic list` 没有继承 source 后的环境。

解决：

- 只把需要后台运行的节点命令放进括号：

```bash
cd /home/pi/rehab_arm_ros2_ws
. /opt/ros/jazzy/setup.bash
. install/setup.bash
(timeout 10 ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py >/tmp/rehab_sim_node.log 2>&1) &
pid=$!
sleep 2
ros2 topic list
ros2 topic echo --once /joint_states
kill $pid 2>/dev/null || true
```

技巧：

- SSH 远端一行命令里混用 `&&`、`;`、`&` 时要特别小心。
- 后台运行 ROS 节点时，用 `( ... ) &` 包住节点命令，避免把环境 setup 链路也放进后台。
- 从 Windows PowerShell 通过 SSH 管道发送多行 bash 脚本时，注意去掉 CRLF 里的 `\r`；否则远端可能出现路径后带 `$'\r'` 或临时脚本找不到的问题。
- 不要在 source ROS setup 前开启 `set -u`；`/opt/ros/jazzy/setup.bash` 可能访问未定义环境变量。

状态：

- 已记录。后续远程测试 ROS 节点时使用括号后台法。

## 架构边界

### App BLE 和 HTTP 容易混

现象：

- 文档容易写成 App 通过 HTTP 控制 NanoPi，再控制电机。
- 但实际 App 的近端实时控制是 BLE 连接英飞凌。

正确边界：

```text
实时近端链路: App <-> BLE <-> 英飞凌 M33/M55
高层 AI 链路: App <-> HTTP <-> NanoPi/OpenClaw
```

技巧：

- BLE 可以承载训练操作、状态显示、标注、急停请求。
- HTTP/OpenClaw 只做高层 AI、报告、训练建议和远程服务。
- HTTP 不做实时电机闭环控制。

状态：

- 已写入 README 和主架构文档。

### 总服务器不是实时控制链路

现象：

- 项目里还有一个总服务器，当前是开发工具服务器，未来会扩展为总控台。
- 容易误放到控制闭环里。

正确边界：

- 总服务器管理设备、数据、模型、实验、远程协作。
- 总服务器不直接发 CAN。
- 总服务器不绕过 M33。
- 总服务器掉线时，本地真机控制和安全仍要能工作。

技巧：

- 总服务器接口先按非实时设计。
- 它可以下发配置、任务、报告请求，但不能直接下发底层电机控制量。

状态：

- 已写入 README、主架构文档和进度文档。

### 全量数据上传主链路不要分散到多个实时节点

现象：

- M33、M55、NanoPi、App、仿真主机和总服务器都可能看到一部分数据，容易设计成每个节点各自上传。
- 这样会带来 session 对齐困难、时间戳不一致、断网补传复杂、职责边界混乱。

正确边界：

- 第一版全量上传主链路选 NanoPi。
- NanoPi 汇总 M33 的电机、传感、安全和 M55 模型摘要，再同步给仿真主机和总服务器。
- M55 WiFi 可上传语音、OpenClaw、模型摘要或诊断信息，但不承担第一版全量数据主链路。
- App 可做账号、报告和非实时标注同步，但实时近端状态仍由 M33 BLE 提供。

技巧：

- 先用 NanoPi 做 session_id、时间戳对齐、本地落盘和断网补传。
- 高频数据先本地记录，服务器保存索引和文件，不把服务器放进实时闭环。

状态：

- 已写入 README、主架构文档、使用手册和数据流图。

### VLA 数据来源要在高层汇聚，不能直接吃 CAN

现象：

- 容易把 VLA 想成直接读取 CAN 数据并输出控制命令。
- 这会让高层 AI 越过仿真、规划和 M33 安全边界。

正确边界：

- VLA 输入来自服务器历史数据、仿真主机视觉/仿真状态、App 用户目标和 NanoPi 汇总的机器人状态。
- VLA 输出只能是 `task_goal`、任务约束或规划建议。
- VLA 不直接发 CAN，不输出电机力矩、速度、电流或裸位置命令。

技巧：

- VLA 输出后必须经过运动规划器生成 `JointTrajectory`。
- `JointTrajectory` 再经 NanoPi 到 M33，由 M33 做最终安全审核。

状态：

- 已写入 README、主架构文档、使用手册和数据流图。

### 远程 VLA 适合复杂任务分解，不适合底层实时控制

现象：

- 当 VLA、仿真主机和 NanoPi 不在同一局域网时，VLA 只能通过服务器接入。
- 这条链路有网络延迟和抖动，但复杂任务又需要视觉、语音、历史上下文和状态汇聚。

正确边界：

- NanoPi 采集摄像头关键帧、目标/遮挡物摘要和机器人状态，上传服务器。
- M55/英飞凌采集语音，上传语音文本、音频摘要和模型结果。
- 服务器把视觉、语音、机器人状态、历史数据和标注上下文提供给 VLA。
- VLA 输出复杂任务计划，例如“先移开遮挡物，再拿目标物品”。
- 服务器下发到 NanoPi 的是分段任务、阶段目标或训练配置，不是 CAN 帧或底层电机命令。

技巧：

- 远程 VLA 做“任务理解和任务分解”，本地 NanoPi/仿真主机做轨迹生成，M33 做安全裁决。
- 被遮挡目标任务应拆成可验证阶段：识别遮挡物、规划移开遮挡物、确认目标可见、再规划接近/拿取目标。
- 每个阶段都要可取消、可超时、可人工确认。

状态：

- 已写入 README、主架构文档、使用手册和新版数据流图。

## 文档维护技巧

### `0x322 detail_code` 要用“前后两次 heartbeat”验证

现象：

- M33 的 `0x322` byte6 用来上报最近一次 ROS safety assessment 的首要拒绝原因。
- 直接发送危险 `0x320` 后不会自动看到状态变化，必须再发一次 `0x321` heartbeat 触发下一帧 `0x322`。

环境：

- NanoPi `can0`，classic CAN 1Mbps。
- M33 detail_code 固件，`CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`。
- 电机驱动断开，无运动测试。

验证：

- 初始 heartbeat 返回：

```text
RX 322 [8] a571070001010a00
detail_code=10 detail=logging_only_no_motor_output
```

- 发送超限 `0x320` 后，再发 heartbeat，返回：

```text
TX 320 [8] 0300840305000000
RX 322 [8] a572070001010400
detail_code=4 detail=target_out_of_limit
```

- M33 `COM26` 同时打印：

```text
safety_state=limited decision=reject reason=target_out_of_limit
final action=no_motor_output logging_only=1
```

技巧：

- 动态 detail 的验收要同时看三处：`candump`、NanoPi parser、M33 串口。
- `0x322` byte6 从 `0A` 变为 `04`，才说明 M33 已把最近一次拒绝原因带回 NanoPi。
- 只要 M33 仍是 logging-only，看到 `target_out_of_limit` 也不能理解为可运动状态；它只是更清晰的拒绝原因。

状态：

- 已验证通过。
- `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`。
- 未给电机驱动上电，未做运动测试。

### `0x322 detail_code` 会保留最近一次拒绝原因

现象：

- 完成 `target_out_of_limit` 验证后，再发一次普通 heartbeat，`0x322` 仍返回：

```text
RX 322 [8] a581070001010400
detail_code=4 detail=target_out_of_limit
```

- 这不是新错误，而是 M33 当前设计会保留最近一次 ROS safety assessment 的 detail。

验证：

- 发送 torque 超限帧：

```text
TX 320 [8] 0300390005000100
```

- 下一次 heartbeat 返回：

```text
RX 322 [8] a582070001010600
detail_code=6 detail=torque_out_of_limit
```

技巧：

- 判断 detail 是否“动态更新”，要看新危险帧之后 byte6 是否被覆盖，而不是要求每次 heartbeat 自动清零。
- 如果未来希望安全状态更像实时状态机，可以再设计一条明确的“清除最近拒绝原因/恢复默认 detail”规则；当前阶段先保留最近一次拒绝原因，便于追踪最后一个安全拒绝。

状态：

- `torque_out_of_limit` 抽样验证已通过。
- 本轮未查看 COM26 实时串口，结论基于 NanoPi 收到的 M33 `0x322` 回包和 `can0` 健康状态。
- 电机驱动未上电，未做运动测试。

### heartbeat 超时优先级必须能通过 `0x322` 看见

现象：

- M33 收到普通目标前，如果 NanoPi heartbeat 已超过超时窗口，应该优先拒绝为 `heartbeat_timeout`。
- 这类问题不能只靠串口看，因为后续 App、服务器和 ROS 侧也需要知道为什么被拒绝。

验证：

- 先发一次 heartbeat，确认链路在线：

```text
TX heartbeat_91 321 [1] 91
RX 322 [8] a591070001010600
```

- 等待 `3.2s`，超过当前 M33 `2500ms` heartbeat timeout。
- 发送一个普通目标：

```text
TX 320 [8] 0300390005000000
```

- 再发 heartbeat，下一帧 `0x322` 返回：

```text
RX 322 [8] a592070001010100
detail_code=1 detail=heartbeat_timeout
```

技巧：

- heartbeat timeout 用例要刻意停止 heartbeat，不要让后台 ROS bridge 或其他脚本持续发送 `0x321`。
- 测试前后都要看 `ip -details -statistics link show can0`，确认不是 bus-off、error-passive 或电池/ACK 问题造成的假失败。
- 超时拒绝通过后，仍应恢复正常 heartbeat 再继续下一项测试。

状态：

- 已验证通过。
- `can0` 复查为 `UP/LOWER_UP/ERROR-ACTIVE`，`berr-counter tx 0 rx 0`。
- 未给电机驱动上电，未做运动测试。

### App/服务器不要把 `detail_code` 当成实时 fault

现象：

- `0x322 detail_code` 当前会保留最近一次 ROS safety assessment 的结果。
- 如果 App 或服务器只看 `detail=heartbeat_timeout`，可能误以为当前还在持续超时；如果只看 `detail=none`，也可能误以为可以运动。

正确边界：

- `state` 是当前总体安全状态。
- `control_mode` 是当前控制模式。
- `detail/detail_code` 当前语义是 `last_safety_assessment`。
- 可运动判断必须至少同时满足后续定义的 `state=ok`、`control_mode=armed/active`、M33 已解除 logging-only、急停/限位/供电均通过。

解决：

- NanoPi parser 保留旧字段，同时新增：

```json
{
  "detail_semantics": "last_safety_assessment",
  "last_assessment_detail_code": 1,
  "last_assessment_detail": "heartbeat_timeout"
}
```

技巧：

- UI 展示可以写成“最近一次拒绝原因：heartbeat_timeout”，不要写成“当前故障：heartbeat_timeout”。
- 服务器保存数据时同时存 `state/control_mode/detail_semantics/detail`，方便后续标注和追溯。

状态：

- 已在 NanoPi parser 和协议文档中明确。
- 本地 17 个测试通过，NanoPi 7 个 parser 测试通过。
- 真实 `0x322` 已解析出 `detail_semantics=last_safety_assessment`。

### 上层先看 `motion_allowed`

现象：

- App、服务器、VLA、仿真主机如果各自组合 `state/control_mode/detail`，容易判断不一致。

规则：

- `/rehab_arm/safety_state.motion_allowed=false` 时，任何上层都不能请求真实运动。
- 当前 logging-only 阶段必须一直是 `false`。
- 后续即使 `motion_allowed=true`，M33 仍然是最终安全裁决方。

状态：

- NanoPi parser 和 bridge 本地 safety payload 已输出 `motion_allowed`。

### ROS2 Python 节点要确认可执行位

现象：

- `colcon build` 通过，安装目录里也有 `data_recorder_node.py` 链接。
- 但 `ros2 pkg executables rehab_arm_psoc_bridge` 一开始没有显示新节点。

原因：

- 新增 Python 节点文件没有执行位。

解决：

```bash
chmod +x rehab_arm_psoc_bridge/data_recorder_node.py
```

并在 Git 中保留执行位。

状态：

- NanoPi 已验证 `ros2 pkg executables rehab_arm_psoc_bridge` 能看到 `data_recorder_node.py`。

### Windows 远程发布 ROS JSON 时引号容易被 PowerShell 解析坏

现象：

- 从 Windows PowerShell 里通过 `ssh` 执行 `ros2 topic pub`，消息内嵌 JSON 时出现 `ParserError`。

技巧：

- 这类测试优先写成 NanoPi 本地脚本，或先测试 helper/节点注册。
- 不要把复杂 JSON、PowerShell、SSH、ROS YAML 四层引号揉在一个命令里。

### NanoPi 端口通不等于 SSH 命令可执行

现象：

- `Test-NetConnection 192.168.2.66 -Port 22` 显示 `TcpTestSucceeded=True`。
- 但 `ssh pi@192.168.2.66 "echo online"` 超时。

判断：

- 这说明网络端口可达，但 SSH 登录/会话建立卡住。
- 不要在这种状态下继续判定 ROS、CAN 或 colcon 失败。

状态：

- 本次 metadata 数据记录改动已完成本地测试。
- NanoPi 同步验证暂缓，等 SSH 命令能正常返回后再做。

补充：

- 后续 NanoPi SSH 恢复后，metadata recorder 已同步、构建并验证通过。

### ROS2 节点不要用 `self.handle` 做普通成员名

现象：

- `data_recorder_node.py` 启动时报错：

```text
AttributeError: handle cannot be modified after node creation
```

原因：

- `rclpy.node.Node` 已经有只读属性 `handle`。

解决：

- 文件句柄成员改名为 `self.log_handle`。

状态：

- 已修复，NanoPi 上 `data_recorder_node.py` 可写出 `session_metadata`。

### `timeout` 停 ROS2 节点时要处理 `ExternalShutdownException`

现象：

- 用 `timeout 3s ros2 run ... data_recorder_node.py` 做短验证时，数据已写入，但退出留下 traceback。

解决：

- `main()` 同时捕获 `KeyboardInterrupt` 和 `ExternalShutdownException`。

状态：

- 已修复，短运行退出不再打印 traceback。

### recorder 的数据闭环至少要验证一条真实 topic

现象：

- 单元测试和 `colcon build` 通过，不代表 ROS topic 已能落盘。

技巧：

- 启动 `data_recorder_node.py` 后发布一条假 `/joint_states`。
- 检查 JSONL 同时包含 `session_metadata` 和 `/joint_states` 的 `topic_message`。

状态：

- NanoPi 已验证 `/joint_states` 可记录 `name/position/velocity/effort/stamp`。

### 仿真 motor_state 是遥测桥，不是控制器

现象：

- 总控台和数据记录需要 `/rehab_arm/motor_state`。
- 但没有真机电机状态或不能上电时，容易卡在硬件链路上。

解决：

- 使用 `joint_state_motor_state_node.py` 把 `/joint_states` 转成 `/rehab_arm/motor_state`。
- 这适合仿真、离线标注、总控台表格联调和 recorder 测试。

技巧：

- 这个节点的 `control_boundary` 是 `telemetry_only_not_motor_command`。
- 它不发 CAN、不下发 `0x320`、不代表电机真实在线。
- 真机版本仍要以后用 M33 汇总的电机反馈来发布 `/rehab_arm/motor_state`。

状态：

- 本地和 NanoPi 单测通过。
- NanoPi ROS 冒烟测试已确认假 `/joint_states` 能生成 `/rehab_arm/motor_state`。

### JSONL checker 要同时测 PASS 和 FAIL

现象：

- `/tmp/joint_recorder_verify.jsonl` 只有 `session_metadata` 和 `/joint_states`。
- checker 返回 FAIL，缺少 `/rehab_arm/safety_state` 和 `/rehab_arm/sensor_state`。

结论：

- 这是正确行为；单关节测试文件不是完整 session。

技巧：

- checker 验证时至少准备一份完整 JSONL，包含三类 topic。
- 生成测试 JSONL 时用 `json.dumps()`，不要手写多层 SSH/PowerShell JSON 转义。

状态：

- NanoPi 已验证完整 JSONL 返回 `ok=true`。

### launch 短运行验证不要太短

现象：

- `timeout 3s ros2 launch ... data_collection.launch.py` 只看到进程启动，未稳定写出 JSONL。
- 改成 `timeout 10s` 后正常写出 `session_metadata`。

技巧：

- launch 会先启动 launch service，再启动节点；短验证至少给 10 秒。
- 验证 recorder 时优先检查 JSONL 第一行，而不是只看 launch 进程启动。

### `timeout ros2 launch` 可能不会让远程 SSH 干净返回

现象：

- NanoPi 上 `colcon build --packages-select rehab_arm_bringup` 通过。
- 通过 SSH 执行 `timeout 10 ros2 launch rehab_arm_bringup sim_data_collection.launch.py ...` 后，本地 SSH 命令没有按预期返回。
- 随后短时间内新的 SSH 命令也超时。

判断：

- 这不像代码编译错误，更像 launch 子进程、ROS daemon 或远程会话没有被 `timeout` 干净回收。
- 在板子刚恢复上电或发热明显时，不应反复启动高频仿真/记录进程。

技巧：

- 远程验证 launch 时优先用后台启动、显式记录 PID、再显式 shutdown/kill 的脚本。
- 如果 SSH 已经卡住，先等板子恢复或现场重启，不要继续压测。
- 这类卡住不代表可以进入真机 CAN 控制；本轮仍然不发 `0x320`。

状态：

- 已记录。`sim_data_collection.launch.py` 已通过本地语法检查和 NanoPi 构建，但短跑 JSONL 完整性验证待 SSH 恢复后继续。

### 仿真也要周期性发布 safety_state

现象：

- `sim_data_collection.launch.py` 首轮短跑能写出 JSONL。
- JSONL 包含 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/sensor_state`。
- `check_recording.py` 失败，提示缺少 `/rehab_arm/safety_state`。

根因：

- 仿真节点原本只在收到轨迹时发布 safety。
- 离线采集 launch 启动后如果不发布轨迹，recorder 永远收不到 safety topic。

解决：

- `mujoco_sim_node.py` 增加默认 `safety_state=ok`、`safety_detail=simulation ready`。
- 在 timer 中每 1 秒周期发布一次 `/rehab_arm/safety_state`。

技巧：

- 仿真和真机都应持续发布安全状态；上层不应靠“没消息”猜系统是否安全。
- 数据采集完整性检查能及时暴露这类系统接口缺口。

状态：

- 本地已修复并通过语法检查。
- NanoPi 复测被 SSH 超时阻塞，待板子稳定后继续。

### NanoPi 不在线时先补本地静态保护

现象：

- NanoPi SSH 返回 `connect to host 192.168.2.66 port 22: Connection timed out`。
- 不能继续做远端 `colcon build` 或 ROS launch 验证。

技巧：

- 不在线时不要反复压测板子。
- 可以先补不依赖 ROS 安装的本地静态测试，检查 package metadata、launch 文件关键节点和参数是否存在。
- 这不能替代 NanoPi 真 ROS launch，但能防止启动入口被后续提交无意改坏。

状态：

- 已为 `rehab_arm_bringup` 新增本地静态测试。
- 本地 bringup 2 tests passed；NanoPi 复测仍待恢复。

### PowerShell 会提前解析远端 `$(...)`

现象：

- 从 Windows PowerShell 里执行 SSH 远端命令：

```powershell
ssh pi@192.168.2.66 "kill -INT $(cat /tmp/sim_data_collection_launch.pid)"
```

- PowerShell 把 `$(cat ...)` 当成本地表达式执行，报错路径类似：

```text
Cannot find path 'D:\tmp\sim_data_collection_launch.pid'
```

解决：

- 用 PowerShell 单引号包住远端命令，或避免在远端命令里直接写 `$()`。

技巧：

- Windows -> SSH -> bash 有两层 shell；凡是 `$()`、引号和 JSON 混在一起时，优先拆成更简单的远端命令。

状态：

- 已记录。本次 launch 验证改用更简单的 `timeout -s INT`。

### `pkill -f` 可能杀掉当前 SSH 命令

现象：

- 远端命令里先执行：

```bash
pkill -f 'ros2 launch rehab_arm_bringup sim_data_collection.launch.py'
```

- 但同一条 SSH 命令后面也包含这个字符串，`pkill -f` 可能匹配并杀掉当前 shell，导致命令无输出退出。

解决：

- 先用 `pgrep -af` 查看残留 PID，再显式 `kill <pid>`。
- 或把清理命令和启动命令拆成两次 SSH，不要让待匹配字符串出现在当前命令行里。

状态：

- 已记录。本次残留节点按 PID 清理后继续验证。

### ROS2 订阅节点 SIGINT 时可能出现 shutdown race

现象：

- `timeout -s INT ros2 launch ...` 停止仿真采集时，`data_recorder_node.py` 和 `joint_state_motor_state_node.py` 偶发 traceback：

```text
RuntimeError: Unable to convert call argument '0' to Python object
```

判断：

- 这是 ROS2 Jazzy/rclpy 在 SIGINT 时，订阅 executor 正在取消息的退出竞争。
- 数据文件已经写出并且 checker 可通过，但日志污染会误导后续测试。

解决：

- 在两个订阅节点的 `main()` 中只抑制这个已知 shutdown runtime error。
- 不吞普通运行时错误。

状态：

- 已修复并在 NanoPi 复测：`TRACEBACK_COUNT=0`。
- `check_recording.py` 同时返回 `ok=true`。

### 动态采集要验证关节范围，不只看 topic 存在

现象：

- `check_recording.py ok=true` 只能证明基础 topic 齐全。
- 如果 demo 轨迹没有发布，或者仿真没有接到 `/arm_controller/joint_trajectory`，JSONL 仍可能只是静止数据。

技巧：

- 动态采集时同时检查：
  - launch 日志是否出现 `Published multi-joint demo JointTrajectory`。
  - 每个关节的 `position` min/max span 是否大于一个小阈值。
  - `/rehab_arm/motor_state` 数量是否和 `/joint_states` 基本同步。

状态：

- NanoPi 已验证 5 个关节均有运动 span，且 `check_recording.py ok=true`。

### CSV 导出用于离线分析，不是控制链路

规则：

- `export_recording_csv.py` 从 JSONL 导出 `joint_states.csv` 和 `motor_states.csv`。
- CSV 是给标注、画曲线、训练前检查、Excel/pandas/MATLAB 用的离线数据格式。
- CSV 不应被任何节点当成实时控制输入直接下发到 M33 或电机。

状态：

- 本地和 NanoPi 已验证 CSV 导出。

### 数据摘要工具和完整性检查职责不同

规则：

- `check_recording.py` 回答“基础 topic 是否齐全”。
- `summarize_recording.py` 回答“这段数据质量如何”，例如 topic 频率、关节运动范围、motor_state 条目数、安全状态分布。
- `validate_recording_quality.py` 回答“这段数据能不能进入下一步流程”，例如 CI、标注、回放或上传前验收。

技巧：

- 动态 demo 采集后应同时跑两个工具。
- `check_recording.py ok=true` 但 `moving_joint_count=0`，说明采到了数据但没有运动变化。
- `motor_entry_count_min/max` 可帮助总控台快速发现 motor_state 是否缺条目。
- 当前 logging-only/离线采集阶段，质量门默认不允许 `motion_allowed=true`；如果后续真机阶段真的进入可运动状态，必须显式传 `--allow-motion-allowed-true`，并先确认 M33 安全语义已经完成。

状态：

- 本地已新增摘要工具并通过单元测试。
- NanoPi 已构建通过。
- NanoPi 复测时发现 `/tmp/rehab_sim_collection/sim_demo_motion.jsonl` 因重启消失；重新采集后摘要工具验证通过，`moving_joint_count=5`。
- 本地已新增质量门工具并通过单元测试；硬件全断电时只做离线验证，不做 NanoPi/CAN 复测。

### manifest summary 默认不要破坏旧同步格式

规则：

- `build_manifest.py` 默认仍生成旧 manifest 字段，避免影响已有 `sync_dry_run.py` 和 `sync_upload.py`。
- 只有显式加 `--include-summary` 时，才把每个 session 的 `summary` 嵌入 manifest。

技巧：

- 给总控台、标注或人工检查用 `manifest_with_summary.json`。
- 给已经上线的旧同步流程时，可以继续用普通 `manifest.json`。
- 后续如果服务器确认支持 summary，再把上传示例切换到带 summary manifest。

状态：

- 本地和 NanoPi 已验证 `--include-summary`。
- 旧默认 manifest 单测仍确认不含 `summary` 字段。
- `sync_dry_run.py` 已验证会把 manifest 中的 `summary` 原样放进 `/sessions/manifest` 计划请求。

### `/tmp` 里的验证文件可能在重启后消失

现象：

- NanoPi 在线且负载正常。
- 但运行摘要工具时报：

```text
No such file or directory: /tmp/rehab_sim_collection/sim_demo_motion.jsonl
```

根因：

- `/tmp` 是临时目录，设备重启或清理后验证文件可能消失。

技巧：

- 临时验证可以继续用 `/tmp`。
- 需要跨重启保留的数据应写到 `/home/pi/rehab_arm_logs` 或明确的持久目录。
- 复测摘要工具时，如果文件不存在，先重新跑一次 `sim_data_collection.launch.py` 生成 JSONL。

状态：

- 已记录。本次重新生成 `sim_demo_motion.jsonl` 后摘要验证通过。

### 数据文件名要让服务器不用猜

规则：

- 默认 session 文件名使用 `<robot_id>__<device_id>__YYYYmmddTHHMMSSZ.jsonl`。
- metadata 里保留同样的 `session_id`，并带 `schema_version`、`source`、`sync_status`。
- 服务器同步前只需要扫描文件名和第一行 metadata，就能建立索引。

### manifest 的 `ok=false` 不一定是程序错

现象：

- 对只含 `session_metadata` 的短验证文件运行 `build_manifest.py`，输出 `ok=false`。

判断：

- 这是正确行为；该文件缺少 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/sensor_state`。
- manifest 用于同步前筛选，缺数据的 session 不应进入标注/同步流程。

### 服务器同步先做 API 草案，不直接上传

规则：

- 第一版服务器同步只接收 manifest 和 JSONL 文件。
- 不下发 CAN、电流、力矩、速度、裸角度或 M33 override。
- 上传入口默认必须是 dry-run，只有显式 `--execute` 才能联网。
- 真正使用 `--execute` 要等服务器 endpoint 确认后再做。

### `urlopen` 超时参数必须用关键字

现象：

- 本地假服务器收到第 1 个 POST，但 `sync_upload.py --execute` 结果失败。
- 错误为 `message_body should be a bytes-like object or an iterable, got <class 'float'>`。

根因：

- `urllib.request.urlopen(req, timeout_sec)` 的第二个位置参数是 `data`，不是 timeout。

解决：

- 使用 `urllib.request.urlopen(req, timeout=timeout_sec)`。

状态：

- 已修复，Windows 和 NanoPi 均完成 4 个 POST 闭环。

### PowerShell 传远程 bash 脚本要小心 CRLF

现象：

- 通过 PowerShell here-string 传脚本到 NanoPi 后，`tail` 报路径带 `$'\r'`。

技巧：

- 复杂远程验证优先用远程 Python 读文件或确保脚本转换为 LF。
- 生成 JSON/manifest 时优先用远程 Python `json.dumps()`，不要手写多层转义。
- 远程 Python 片段里尽量少写包含嵌套引号的 f-string；`format()` 更不容易被 Windows PowerShell、SSH 和 bash 多层引号干扰。

### USB 摄像头先看 `lsusb`，不要只看 `/dev/video*`

现象：

- NanoPi 有很多 `/dev/video*`，但 `ffmpeg -f v4l2 -i /dev/video0` 报 `No such device`。
- `/dev/video22`、`/dev/video31` 能列格式，但 ffmpeg 报 `Not a video capture device`。
- `lsusb` 只看到 Linux root hub，没有看到 UVC 摄像头设备。

判断：

- 当前没有真正枚举出 USB 摄像头。
- 很多 `/dev/video*` 是 Rockchip ISP/MIPI/编码器管线节点，不等于 USB 摄像头可采集节点。

技巧：

- USB 摄像头优先看 `lsusb` 是否出现摄像头设备，再看 `v4l2-ctl --list-devices`。
- UVC 摄像头通常会显示 `uvcvideo` 相关设备，且 `/dev/videoX` 可被 ffmpeg 打开。
- 深度摄像头后续要同时确认 RGB、Depth、IR 节点和 SDK 支持，不要只验证 RGB。

当前状态：

- 已新增 `camera_keyframe_node.py`，等待摄像头正确枚举后复测。

### 哈希测试不要依赖文本换行

现象：

- `file_sha256()` 单测在 Windows 通过，但同步到 NanoPi 后失败。
- Windows `write_text('...\n')` 可能写成 CRLF，Linux 写成 LF，导致同一测试的 SHA256 不同。

解决：

- 哈希测试使用 `write_bytes(b'...')` 固定文件内容。

技巧：

- 跨 Windows/Linux 验证二进制摘要、协议 payload、CAN frame bytes 时，不要用文本模式生成测试输入。

状态：

- 已修复，Windows 本地和 NanoPi 单测均通过。

### 进度和踩坑要分开

规则：

- `docs/PROJECT_PROGRESS.md` 记录当前进展、验证结果、下一步。
- `docs/TROUBLESHOOTING_AND_LESSONS.md` 记录踩坑、排查方式、技巧。
- 架构改变写 `docs/REHAB_ARM_SYSTEM_ARCHITECTURE.md`。
- 面向新读者的入口写 `README.md`。

技巧：

- 进度文档回答“现在做到哪里”。
- 踩坑文档回答“以后遇到同类问题怎么少走弯路”。

### 仿真电脑不要直接从复杂 launch 开始排错

现象：

- 新 Linux 仿真主机刚搭好时，直接运行 MuJoCo/采集 launch 可能同时暴露 ROS2、MuJoCo、URDF、Python 包路径和数据工具多个问题。

技巧：

- 先运行 `ros2 run rehab_arm_sim_mujoco check_sim_env --pretty`。
- 如果 `readiness=ready_with_fallback_sim`，说明 ROS2 数据链路可先跑通，但真实 MuJoCo Python 包还没装好。
- 如果 `ok=false`，先看 `errors`，逐项修 ROS2 包、URDF 路径或采集工具导入。
- 在 Windows 开发机上看到 `rclpy is required but not available` 是正常现象，说明这台机器不是 ROS2 仿真运行环境；真正仿真主机应在 Linux + ROS2 环境下通过。
- 只有这个自检通过后，再运行 `sim.launch.py` 或 `sim_data_collection.launch.py`。

状态：

- 已新增自检工具；它只读环境，不访问 CAN，不命令 M33 或电机。

### 仿真自检报告只能作为平台数据资产

现象：

- 平台需要知道仿真主机是否具备 ROS2、URDF、MuJoCo/fallback 和采集工具，但不能把这种“准备度”误解成真机运动许可。

技巧：

- 用 `check_sim_env --output sim_readiness_report.json` 生成只读报告。
- 平台接收端只写入 `simulation_readiness` 最新状态和事件日志。
- UI 文案必须写清楚它是研发准备度，不是 M33 运动许可。
- 如果 `readiness=ready_with_fallback_sim`，可以先跑 ROS topic/数据采集链路；等 MuJoCo 安装好再跑真实 MuJoCo 仿真。

状态：

- 已在工具和平台接口中保留 `simulation_readiness_only_not_motion_permission` 边界。

### 测试 demo 和临时报告不要污染项目

现象：

- 单元测试如果把 `sim_readiness_report.json`、截图、样例 session 或 demo 输出写进源码目录，后面会越积越乱。

技巧：

- 单元测试使用系统临时目录生成输出，测试结束自动删除。
- 只有可复用代码、正式测试、正式文档可以提交；临时 demo 数据、QA 截图、一次性报告不要提交。
- 如果确实需要保留验证证据，优先写进文档摘要，不把生成文件留在仓库里。

状态：

- `check_sim_env --output` 测试已改为 `TemporaryDirectory()`，不会留下测试报告文件。

### 平台上传工具默认必须是 dry-run

现象：

- 仿真主机、NanoPi、服务器之间的工具如果默认联网，容易误把一次测试变成真实上传或真实动作。

技巧：

- `upload_sim_readiness` 默认只打印上传计划。
- 只有加 `--execute` 才会 POST 到平台。
- 这类上传只能走数据资产接口，必须保留 `simulation_readiness_only_not_motion_permission` 边界。
- 上传前先看 dry-run 里的 URL、`device_id`、`robot_id` 和 report 内容。

状态：

- 已新增 `upload_sim_readiness`，单测使用 fake opener，不连真实服务器，不生成持久 demo 文件。

### CANSimple 闭环后 0x069 可能从全 0 变成有效估计值

现象：

- 电机上电后，`0x069` encoder estimate 一开始可能全 0。
- 发送 CANSimple closed-loop 后，`0x069` 变成非零 float 数据。

技巧：

- 不要把第一次从 0 跳到非零的 position estimate 全部当成真实运动量；它可能包含控制器进入闭环后的估计值恢复。
- 做小幅度运动时，必须同时保存 raw CAN log，记录发送的 `0x67/0x6B/0x6D` 和后续 `0x061/0x069`。
- 调试后立刻发 `vel=0` 和 `idle`，再确认 `can0` 仍是 `ERROR-ACTIVE` 且错误计数为 0。

状态：

- 已对 CANSimple `node_id=3` 做极小速度测试并保存日志；未触碰 private MIT `motor_id=4`。

### 原始 CAN 日志要转成统一 motor_state JSONL

现象：

- `candump -tz can0` 原始日志适合保留证据，但不方便直接给总控台、标注工具、质量门和训练前分析使用。
- CANSimple `0x069` 是 turns/turns/s，不能直接当作 ROS 常用 rad/rad/s。

技巧：

- 用 `candump_motor_telemetry` 把 CANSimple `0x061/0x069`、M33 `0x330~0x337` 和已确认的灵足 active-report 离线转换成 `/rehab_arm/motor_state` JSONL。
- 转换后保留 `control_boundary=telemetry_only_not_motor_command`，提醒后续工具这只是遥测数据，不是控制许可。
- 输出文件用临时目录做验证；只有代码、测试和文档进入仓库，不提交真实采集 JSONL 或 demo 数据。
- 闭环刚建立后的 encoder estimate 跳变可能包含估计器恢复，应在分析报告里单独标注。

状态：

- 已新增离线转换器和单元测试，并用真实 NanoPi tiny-motion candump 日志做过临时目录验证。

### 平台接入检查不能被理解成运动许可

现象：

- 平台页面会显示 Linux 开发板、runner、ROS/仿真、摄像头、CAN/串口和最近上传状态。
- 这些状态容易被误读成“系统已经可以动真机”。

技巧：

- 平台接入检查只做研发链路判断：设备是否在线、数据是否上传、仿真报告是否存在、采集/标注是否可继续。
- UI 文案必须持续写明：状态只读，不下发 ROS、CAN、M33 或电机命令。
- 真实运动许可只来自 M33 安全状态机；平台、服务器、VLA、仿真报告和 NPC 建议都不能绕过 M33。

状态：

- 平台 robotics 页面已增加只读 `接入检查` 面板，文档已记录安全边界。

### Linux 开发板 manifest 只能做只读发现

现象：

- 开发板接入平台时需要扫描 `can*`、串口、USB、摄像头、ROS2 环境。
- 如果扫描脚本顺手 bring up CAN、启动 ROS launch 或打开设备流，容易把“接入发现”变成“隐式控制/占用设备”。

技巧：

- `board_manifest` 只读 `/sys/class/net`、`/dev` 和命令可用性。
- 输出必须保留 `control_boundary=board_discovery_only_not_motion_permission`。
- 上传前先人工检查 manifest，确认 `device_id`、`robot_id`、接口列表和安全边界正确。
- 真机运动许可仍只看 M33 安全状态机，不看平台 manifest。

状态：

- 已新增 `board_manifest` 和单元测试；尚未接入平台上传接口。

### 开发板注册先 dry-run 再 execute

现象：

- 平台 `/devices/register` 当前只接收精简字段，不能直接保存完整 `linux_board_manifest_v1`。
- 如果直接把完整 manifest 作为注册 payload 发送，后端可能忽略额外字段，导致用户误以为完整能力清单已经保存。

技巧：

- 先用 `board_manifest_sync_dry_run` 生成请求计划，确认真正会发的是精简注册字段。
- 完整 manifest 的平台持久化要单独做后端接口或扩展 schema，不能假装已完成。
- dry-run 阶段只输出 JSON，不联网；后续加 `--execute` 时必须保留显式开关。

状态：

- 已新增 dry-run 计划工具；真实上传仍未启用。

### 完整 board manifest 要和 session manifest 分开

现象：

- `rehab_arm_manifest_v1` 表示一次数据采集 session 的文件、质量门和同步状态。
- `linux_board_manifest_v1` 表示一台 Linux 开发板的静态/半静态能力，例如 CAN、串口、摄像头、ROS2。
- 如果都塞进 `/sessions/manifest`，平台页面会把“板子能力”和“数据采集质量”混在一起。

技巧：

- 平台后端用独立 `/devices/{device_id}/board-manifest` 保存开发板能力。
- dashboard 同时返回 `manifest` 和 `board_manifest`，前者用于数据质量/标注，后者用于设备接入检查。
- 前端接入检查可以用 `board_manifest` 判断硬件能力，但不能把它当作实时数据或运动许可。

状态：

- 平台已新增 full board manifest 存储；ROS dry-run 已规划对应请求。

### 开发板 manifest 上传必须显式执行

现象：

- 用户需要把真实 NanoPi/Jetson/x86 开发板能力同步到平台。
- 如果上传命令默认联网，容易误传错误 `device_id`、`robot_id` 或把测试环境数据写入云端。

技巧：

- `board_manifest_sync_upload` 默认行为仍是 dry-run；不加 `--execute` 只打印计划请求。
- 真正上传前先人工检查 `linux_board_manifest_v1` 和两条请求 URL。
- 单元测试用 fake opener 验证 HTTP 请求，不对真实服务器写入 demo 数据。

状态：

- 已新增显式 `--execute` 上传命令；尚未在真实 NanoPi 上执行云端上传。

### 仿真 topic 合同不等于 topic 正在运行

现象：

- `check_sim_env` 可以输出 `/arm_controller/joint_trajectory`、`/joint_states`、`/rehab_arm/safety_state` 等标准 topic 合同。
- 用户可能误以为自检报告里有 topic 名，就代表这些 topic 已经实时发布，甚至可以直接控制真机。

技巧：

- `topic_contract` 只说明仿真主机、NanoPi、平台采集标注和 VLA 后续应遵守的接口名称和消息类型。
- 判断 topic 是否真的运行，还要用 `ros2 topic list`、`ros2 topic echo --once`、launch 日志和数据采集 JSONL 验证。
- 真机运动许可仍只来自 M33 安全状态机，不能从仿真报告或平台页面推断。

状态：

- `check_sim_env` 已加入 `topic_contract.control_boundary=simulation_topic_contract_not_motion_permission`。

### JSONL topic profile 是进入标注前的第一道门

现象：

- `check_recording.py ok=true` 的默认检查只要求基础 topic。
- 真机电机遥测、视觉/VLA 数据、纯仿真数据对 topic 的要求不同，手动写 `--required-topic` 容易漏项。

技巧：

- 用 `--topic-profile simulation_minimum` 检查基础仿真/采集数据。
- 用 `--topic-profile hardware_telemetry` 检查电机数据是否包含 `/rehab_arm/motor_state`。
- 用 `--topic-profile perception_vla` 检查视觉/VLA 数据是否包含 `/rehab_arm/model_state` 和 `/rehab_arm/camera_keyframe`。
- profile 检查只回答“这段 JSONL 是否包含该流程最小 topic 集”，不回答数据质量、运动幅度或安全许可；后面仍要跑 `validate_recording_quality.py` 和 M33 安全链路检查。

状态：

- `check_recording.py` 已支持 topic profile preset，并有 CLI 单测覆盖缺 `motor_state` 的失败路径。

### 质量门和 manifest 也要使用同一个 topic profile

现象：

- 只在 `check_recording.py` 用 `--topic-profile` 会造成两套口径：topic 齐全性检查知道 `hardware_telemetry`，但质量门或 manifest 里的 `quality_report` 可能仍按默认基础 topic 通过。

技巧：

- `validate_recording_quality.py` 也使用 `--topic-profile hardware_telemetry` 或 `--topic-profile perception_vla`。
- `build_manifest.py --include-quality-report` 同样带上 `--topic-profile`，让平台直接读取 `quality_report.topic_profile`、`required_topics` 和 `schema_check.missing_topics`。
- profile 仍只是数据验收口径，不是运动许可；真机运动必须由 M33 安全状态机允许。

状态：

- 已统一接入 `validate_recording_quality.py`、`build_recording_quality_report()` 和 `build_manifest.py --include-quality-report`。

### 视觉/VLA 数据不能只检查 topic 存在

现象：

- `perception_vla` profile 能确认 JSONL 里至少出现过 `/rehab_arm/model_state` 和 `/rehab_arm/camera_keyframe`。
- 但复杂任务规划、遮挡物处理、后续标注和训练需要足够多的关键帧；只有一帧通常不够。

技巧：

- 离线质量门使用 `--topic-profile perception_vla --min-camera-keyframes N`。
- `N` 根据采集任务调整；短冒烟测试可以小，正式标注数据要更严格。
- 该检查只看 JSONL topic 数量，不证明图片文件存在、清晰或深度有效；图片质量和标注质量要另做检查。
- 如果新增 `/rehab_arm/model_state` 后旧 perception/VLA 测试失败，先补一条 `rehab_arm_model_state_v1` 样本，而不是降低 topic profile 要求。

状态：

- 已加入 `--min-camera-keyframes`，可用于单文件质量门和 `build_manifest.py --include-quality-report`。

### 摄像头关键帧文件检查只能在图片已同步后开启

现象：

- JSONL 里的 `image_path` 可能是 NanoPi 本机路径，例如 `/home/pi/rehab_arm_frames/f1.jpg`。
- 在开发电脑或平台主机上离线检查时，如果图片文件还没同步过来，直接启用文件检查会把所有关键帧报成 missing。

技巧：

- 先用 `--topic-profile perception_vla --min-camera-keyframes N` 检查消息数量。
- 确认图片文件已同步到本机后，再加 `--require-camera-files --camera-base-dir <frame-root>`。
- `camera_file_check.hash_mismatch_count>0` 表示 JSONL 中记录的 sha256 和本地文件不一致，不能进入正式标注/训练。

状态：

- 已加入可选的本地文件存在和 sha256 检查；默认关闭，避免跨机器路径误报。

### 标注队列必须从质量门之后生成

现象：

- 如果平台或人工直接从普通 `manifest.json` 开始标注，缺 topic、缺 motor_state、缺关键帧或图片 hash 错误的数据也可能混进训练集。

技巧：

- 先生成 `manifest_with_quality.json`。
- 再运行 `build_annotation_queue.py` 生成 `rehab_arm_annotation_queue_v1`。
- 平台默认只展示 `items`；把 `skipped_sessions` 作为质量问题提示，不要静默丢弃。

状态：

- 已新增离线 annotation queue 工具；它只转换 manifest，不联网、不控制硬件。

### 标注 CSV 模板不是训练集

现象：

- `export_annotation_template.py` 会生成可填写的 CSV，但刚导出的行默认 `annotation_status=pending`，label 列为空。
- 如果直接把这个模板当训练集，会把空标签或未审核数据混进模型训练。

技巧：

- CSV 模板只用于人工或平台标注入口。
- 训练前必须再做一次标注结果校验，确认 `annotation_status`、必填 label、备注和质量门都满足要求。
- CSV 里的 session 路径和标签仍是离线数据，不应被任何控制节点消费。

状态：

- 已新增 CSV 模板导出；下一步应做 completed annotation CSV 校验。

### 电机数据接收要区分被动上报、查询回复和周期上报开关

现象：

- NanoPi `can0` 正常且 `ERROR-ACTIVE` 时，被动 `candump` 只看到 `0x061` 和 `0x069`，容易误判只有一个电机在线。
- 实测 `0x061/0x069` 是 CANSimple node 3 的周期状态；私有协议电机 4/5/6/7 不一定默认主动上报。

技巧：

- 先被动抓包确认总线健康，再发非运动 Get_ID probe。4/5/6/7 会用扩展帧 `0x000004FE`、`0x000005FE`、`0x000006FE`、`0x000007FE` 类回复。
- 需要连续状态时，可以用私有 active-report 打开周期上报，实测 4/5/6/7 分别是 `0x180004FD`、`0x180005FD`、`0x180006FD`、`0x180007FD`，约 100Hz。
- 测试结束要关闭 active-report，避免总线长期高频刷帧影响后续调试。
- 正式机器人路径仍应由 M33 聚合/转发并发布 ROS `/rehab_arm/motor_state`；NanoPi 直接私有 active-report 只是调试手段。

状态：

- 已确认 NanoPi 能接收 4/5/6/7 周期电机状态；M33 `active-report` 转发路径还未打通。

### 灵足主动上报不要在型号未确认前强行换算工程单位

现象：

- 实测 4/5/6/7 会发 `0x180004FD`、`0x180005FD`、`0x180006FD`、`0x180007FD`。
- 本地 RobStride 示例里同类 payload 可按位置、速度、扭矩、温度解码，但不同型号的速度/扭矩量程不同。

技巧：

- 默认保留 `raw_position_u16`、`raw_velocity_u16`、`raw_torque_u16`、`raw_temperature_u16` 和原始 CAN 数据。
- 只有确认 motor ID 对应 `RS00/RS01/RS02/RS03/RS04/RS05/RS06/EL05` 后，才按对应型号量程输出 rad、rad/s、Nm、摄氏度。
- 数据采集和平台展示可以先显示 raw 值和 `engineering_decode=raw_only_actuator_type_unconfirmed`，不要把未知型号伪装成真实物理量。

状态：

- `candump_motor_telemetry.py` 已按 raw-first 方式处理灵足 active-report。

### 飞书在线链接可能只返回登录页，但本地可能已有离线页

现象：

- 直接访问用户提供的飞书 docx 链接时，HEAD 返回 404。
- 加浏览器 UA 后能下载 HTML，但内容是 passport 登录页，不是文档正文。
- 本项目本地 `D:\电机上位机\肩关节电机资料` 已经保存过三份飞书离线 HTML，里面能读到伺泰威/肩关节产品、用户、协议资料。

技巧：

- 不要从登录页推断协议字段。
- 先搜本地离线资料目录，再判断是否需要在线登录。
- 如果没有离线页，让文档拥有者把飞书权限改成公开可读，或导出 PDF/Word/Markdown 到本地目录后再解析。
- 若只拿到在线登录页但没有离线副本，文档内容应标记为未验证。

状态：

- 已找到本地离线页和学习整理，并已把可确认的 CANSimple 命令、对象/参数项、硬件接口和开发入口补入 `docs/MOTOR_PROTOCOLS.md`。
- 已确认协议页里的核心帧规则：标准 11-bit CAN ID，`can_id = (node_id << 5) + cmd_id`，8 字节小端数据，float32 按 IEEE754 编码。
- 从飞书离线 HTML 抽取内容时，直接 `grep`/`Select-String` 容易输出整页压缩脚本；更稳的做法是解析 HTML 内的 Feishu block JSON，再按 table 的 `rows_id`、`columns_id`、`cell_set` 还原表格。

### CANSimple heartbeat 扩展字节先 raw-first，不要过早命名

现象：

- 伺泰威 node 3 heartbeat `0x061` 实测 payload 类似 `00 00 00 00 08 80 CE 00`。
- byte0..3 和 byte4 可明确用于 axis error / axis state。
- 本地 M33 调试代码曾把 byte5/byte6/byte7 打印为 `flags/temp/life`，但协议表标题写的是 `Motor_Flag/Encoder_Flag/Controller_Flag/Traj_Done/Life`，二者还没完全对齐。

技巧：

- 数据采集可以保留 `heartbeat_byte5/6/7`。
- 在厂家字节级说明和 M33 现场验证前，不要把 byte6 当成可靠温度，也不要把 byte5 当成完整安全位。
- 平台和训练数据中标记 `heartbeat_extension_decode=raw_only_vendor_fields_unconfirmed`。

状态：

- `candump_motor_telemetry.py` 已按 raw-first 方式保留 heartbeat 扩展字节。

### CANSimple 不要把所有命令都假设成 8 字节 DLC

现象：

- 离线协议说明和示例强调 classic CAN 8 字节数据区。
- 但本地 M33 / NanoPi 调试实现中，`Set_Input_Torque` 只发送 4 字节 `float32 torque_nm`。
- 若后续固件或测试工具强制所有 CANSimple 命令都是 DLC=8，可能导致与当前可工作的调试路径不一致。

技巧：

- CANSimple 帧应按 `cmd_id` 建立 payload 合同。
- `Set_Input_Pos` 是 8 字节：`float32 pos_rev + int16 vel_ff_scaled + int16 torque_ff_scaled`。
- `Set_Input_Vel` 和 `Set_Limits` 是 8 字节双 float。
- `Set_Input_Torque` 当前按 4 字节 float 记录，正式执行前再做厂家表和现场实测确认。
- 文档中区分“classic CAN 最多 8 字节”和“某条命令实际 DLC”。

状态：

- `docs/MOTOR_PROTOCOLS.md` 已补充本地 M33/NanoPi 控制 payload 表。

### M33 汇总遥测要和 safety/status 分开

现象：

- `0x322` 已经承担 M33 总体 safety/status、control mode 和最近拒绝原因。
- 多个电机的角度、速度、温度、fault 标志无法可靠塞进单个 `0x322` 8 字节帧。

技巧：

- 保留 `0x322` 只表达安全状态和运动许可相关摘要。
- 为 M33 汇总后的每关节/电机遥测预留独立帧，例如 `0x330~0x337`。
- NanoPi 侧先写 parser 和单元测试，把字段标记为 `proposed_firmware_pending`，等 M33 固件实现后再接入 ROS topic。

状态：

- NanoPi 侧已新增 `psoc_motor_status.py` 和 7 个离线单元测试。
- `psoc_can_bridge_node.py` 已接入只读发布路径，收到合法 `0x330~0x337` 后发布 `/rehab_arm/motor_state`。
- 同一批 `0x330~0x337` 会同步发布 `/joint_states`，用于 RViz、MuJoCo 和平台 3D 预览；仍然只是遥测。
- M33 遥测会刷新 bridge 内部 `current_positions`，用于后续轨迹前置处理，但运动许可仍只看 `0x322` 和 M33 安全状态机。
- `m33_motor_status_smoke.py` 可先 dry-run，再用 `--execute` 向 `vcan0` 或明确选择的 CAN 口发送合成遥测帧验证链路。

### 合成遥测 smoke 工具默认必须干跑

现象：

- 为了验证 bridge 是否发布 `/rehab_arm/motor_state`，需要能在 M33 固件未上报 `0x330~0x337` 前制造测试帧。
- 但直接往真实 `can0` 发测试帧容易和现场调试混淆。

技巧：

- smoke 工具默认只打印 JSON dry-run 计划。
- 只有显式传 `--execute` 才会打开 SocketCAN。
- 先用 `vcan0` 验证 ROS bridge 和 recorder，再考虑真实 `can0`。
- 工具只允许发遥测帧，不发 `0x320` 控制帧。

状态：

- `m33_motor_status_smoke.py` 已按 dry-run-first 方式实现并测试。
- 该工具可写最小 JSONL，并已验证能通过 `hardware_telemetry` 质量门。
- 使用 `--output-jsonl` 时 stdout 会携带同一份 `quality_report`，平台可以直接读取，不需要另造质量判断规则。

### 真 CAN 采集时先确认哪些电机实际在线

现象：

- NanoPi `can0` 健康，`ERROR-ACTIVE`，1Mbps，tx/rx error counters 为 0。
- 被动抓包和 live snapshot 能稳定看到 3号伺泰威 `0x061/0x069`。
- 给 7号灵足临时打开 active-report 后，能稳定看到 `0x180007FD` 约 100Hz。
- 4/5/6 在本次 session 中无 Get_ID 回复，也无 active-report。

根因：

- 用户确认 4/5/6 已关闭/断电，所以它们没有回复是预期现象，不是解析器或 CAN 总线故障。

技巧：

- 先看 `ip -details link show can0`，确认 `ERROR-ACTIVE` 和 error counter。
- 再短时抓真实 CAN，按 ID 计数：`0x061/0x069` 对应 3号伺泰威，`0x180007FD` 对应 7号灵足 active-report。
- 对没有上电的电机，不要继续堆协议修改；先确认电源和驱动在线状态。
- `live_socketcan_motor_snapshot.py --enable-active-report 7` 只开临时状态上报，结束自动关闭，不是运动命令。
- 如果加 `--output-jsonl`，可以直接得到 recorder/platform 可读取的两行 JSONL：`session_metadata` 和 `/rehab_arm/motor_state`。
- 从 Windows PowerShell 远程 SSH 执行时，双引号里的 `$(date -u ...)` 会被 PowerShell 当成本机表达式先解析，可能导致远端文件名丢时间戳。固定文件名或先进入远端 shell 更稳。

状态：

- 已在 NanoPi 真 CAN 验证 3号和 7号遥测可采集；4/5/6 本轮因关闭不参与判断。

### M33 `0x330~0x337` 上报依赖新鲜电机反馈缓存

现象：

- M33 固件补了 `0x330~0x337` 发布线程后，NanoPi 不一定立刻看到这些帧。
- 手动运行 M33 shell `cmd_m33_motor_status_once` 可能输出 `sent=0`。

根因：

- M33 上报线程只读取 `s_motor_feedback[]` 中 1000ms 内更新过的缓存。
- 如果电机未上电、active-report 没打开、CAN 没收到 `0x061/0x069` 或 `0x180007FD`，M33 不会把旧数据伪装成实时状态。

技巧：

- 先用 NanoPi `candump` 看原始电机帧是否存在。
- 再看 M33 串口 `cmd_motor_fb <joint>` 或 `cmd_m33_motor_status_once`。
- `0x330~0x337` byte0 必须是 `B3`；没有 `B3` 不要让 NanoPi parser 当正式 M33 motor status。
- 这条链路是遥测，不是运动许可；`0x322` safety/status 仍然是正式安全裁决入口。

状态：

- M33 侧代码已准备，等待用户烧录后真 CAN 验证。

### 烧录后先看 M33 状态，再看电机缓存

现象：

- 烧录 M33 后，NanoPi `candump -L can0,330:7F8` 一开始可能没有任何 `0x330~0x337`。
- 但发送 NanoPi heartbeat 后可以收到 `0x322#A501070001010A00`。

根因：

- `0x322` 证明 M33 CAN 通信活着。
- `0x330~0x337` 还需要 M33 收到新鲜电机反馈缓存；没有电机主动上报时，M33 不会发布旧状态。

技巧：

- 先发无运动 heartbeat：`cansend can0 321#01`，监听 `0x322`。
- 再短时打开 7号灵足 active-report：`live_socketcan_motor_snapshot.py --iface can0 --duration 5 --enable-active-report 7`。
- 看到 `0x180007FD` 后，M33 应该开始发对应 slot 的 `0x336#B3...`。
- 这一步只验证遥测；不要发 `0x320`，不要发布 `/arm_controller/joint_trajectory`。

状态：

- 已验证 7号灵足 active-report 能触发 M33 发布 `0x336#B3...`，约 10Hz。

### `ros2 topic echo --once` 早于 topic 出现时要指定类型

现象：

- bridge 已发布 `/rehab_arm/motor_state`，但命令可能输出：

```text
WARNING: topic [/rehab_arm/motor_state] does not appear to be published yet
Could not determine the type for the passed topic
```

根因：

- `ros2 topic echo --once /topic` 启动瞬间如果 topic 还没有出现在 graph 里，CLI 无法自动推断类型并直接退出。

技巧：

- 对短时硬件验收命令显式写消息类型：

```bash
ros2 topic echo --once /rehab_arm/motor_state std_msgs/msg/String
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
```

状态：

- 显式类型后已看到 `/rehab_arm/motor_state` JSON 字符串；`/joint_states` 已看到 `m33_status_slot_6`。

### Bash 严格模式加载 ROS setup 时要临时关闭 nounset

现象：

- `nanopi_live_telemetry_check.sh` 使用 `set -euo pipefail` 后，执行 `source /opt/ros/jazzy/setup.bash` 报错：

```text
AMENT_TRACE_SETUP_FILES: unbound variable
```

根因：

- ROS setup 脚本内部会读取未定义环境变量；这和 bash `set -u` 冲突。

技巧：

- source ROS 和 workspace setup 前后临时切换：

```bash
set +u
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
set -u
```

状态：

- 已在 `scripts/nanopi_live_telemetry_check.sh` 中修复，并在 NanoPi 真 CAN 验收通过。

### 轨迹门控只认 `motion_allowed=true`

现象：

- 旧版 `0x322` V1 可以解析成 `state=ok`。
- 但 V1 没有明确表达 M33 已经完成上电、自检、急停、限位、控制模式等运动许可检查。

根因：

- 对穿戴式机械臂，`state=ok` 只能说明状态包格式兼容或无错误码，不能等价于“允许运动”。
- 真正允许运动必须由 M33 在 `0x322` 中显式给出 `motion_allowed=true`。

技巧：

- NanoPi bridge 轨迹门控应使用 `motion_allowed` 作为唯一正向许可。
- V1 `state=ok`、V2 `logging_only`、`limited`、`fault`、`emergency_stop` 都必须拒绝轨迹。
- 当前 M33 返回 `state=limited/control_mode=logging_only/detail=logging_only_no_motor_output` 时，发布合法轨迹也应看到：

```text
safety limited: rejected trajectory: PSoC motion_allowed is not true, protocol_version=2, state=limited, control_mode=logging_only, detail=logging_only_no_motor_output
```

状态：

- 已加入 `safety_gate.py` 和单元测试；NanoPi 真 CAN 验证拒绝轨迹且 `can0,320:7FF` 无任何目标帧。

### `state=ok/armed` 仍要看 `detail_code`

现象：

- 如果只用 `state=ok` 和 `control_mode=armed/active` 判断可运动，可能忽略 M33 最近一次安全评估里的拒绝原因。

根因：

- 当前 `0x322` V2 byte6 是 `detail_code`，语义是 `last_safety_assessment`。
- 如果这个字段还是 `motor_fault`、`target_out_of_limit`、`logging_only_no_motor_output` 等非 `none`，说明 M33 还没有给出干净的运动许可。

技巧：

- NanoPi parser 的 `motion_allowed=true` 最小条件必须是：
  - `error_code=0`
  - `state=ok`
  - `control_mode=armed/active`
  - `detail_code=none`
- M33 后续进入 `armed` 前，要先清掉或覆盖最近拒绝原因，并把真实安全检查结果反映到 `detail_code`。

状态：

- 已收紧 parser 并加入测试：`ok/armed/detail=motor_fault` 仍解析为 `motion_allowed=false`。

### Pre-arm 检查表默认失败才是安全默认

现象：

- M33 新增 `cmd_m33_prearm_check` 后，当前阶段预期输出 `ready=0`。

根因：

- 当前固件仍然 `CONTROL_ROS_COMMAND_LOGGING_ONLY=1U`。
- 急停输入、供电输入、最终限位确认都还没有接入真实硬件合同。
- 并非所有参与运动的电机都有新鲜反馈。

技巧：

- `cmd_m33_prearm_check` 只用于观察，不改变状态。
- 先看 `PREARM_MODE`，再看 `PREARM_INPUTS`，最后看 `PREARM_MOTORS`。
- `fresh_mask` 表示 M33 最近收到反馈的关节/电机槽位，不是运动许可。
- 只有当 M33 未来能稳定给出 `ready=1`，并且 `0x322` 同时满足 `motion_allowed=true` 合同时，NanoPi 才可能进入真实轨迹测试。

状态：

- M33 代码已编译通过；等待用户需要时烧录后现场查看。

### Pre-arm `fresh_mask=0` 说明检查瞬间没有满足新鲜反馈

现象：

- 烧录后运行 `cmd_m33_prearm_check` 输出：

```text
PREARM_MOTORS: required_mask=0x0000007F fresh_mask=0x00000000 ... fresh_ok=0
```

根因：

- pre-arm 使用 M33 缓存里的新鲜电机反馈判断。
- 如果运行串口命令时电机没有持续上报，或 active-report 已经关闭并超过 freshness 窗口，`fresh_mask` 就会是 0。
- 这不表示 CAN 坏；同一次上电已经通过 NanoPi live telemetry check 看到 `0x336`。

技巧：

- 需要验证 motor freshness 时，先让目标电机持续上报，再立刻运行 `cmd_m33_prearm_check`。
- 当前默认 `CONTROL_PREARM_REQUIRED_JOINT_MASK=0x7F` 要求 7 个槽位都有新鲜反馈；如果现场只上电 7 号，后续应先把 required mask 改成当前测试所需的最小集合。
- `ready=0` 是安全默认；不要为了让它变 1 而临时跳过急停、供电、限位确认。
- 新增的 `cmd_m33_prearm_check 0x40` 只用于本次诊断 slot6 freshness；它不修改默认配置，也不代表可运动。

状态：

- 已记录。下一步应先做“测试用 required mask”而不是开放运动。

### Pre-arm 诊断 mask 要和 active-report 同时测

现象：

- 第一次并发测试 `cmd_m33_prearm_check 0x40` 时，远端命令路径写错，7号 active-report 没有真正打开，结果仍是 `fresh_mask=0`。
- 修正远端工作目录后，7号 active-report 打开 8 秒，M33 输出 `fresh_mask=0x00000040 fresh_ok=1`。

根因：

- `cmd_m33_prearm_check 0x40` 只改变 required mask，不会主动打开电机上报。
- 必须在 M33 缓存 freshness 窗口内运行命令。

技巧：

- 正确顺序：
  1. NanoPi 打开 `live_socketcan_motor_snapshot.py --enable-active-report 7 --duration 8`。
  2. 在窗口内发一次 `cansend can0 321#xx` 保持 heartbeat 新鲜。
  3. M33 串口运行 `cmd_m33_prearm_check 0x40`。
- 看到 `fresh_mask=0x40 fresh_ok=1` 只说明 slot6 telemetry 新鲜，不表示 pre-arm ready。

状态：

- 已验证 slot6 freshness 可观测；`ready` 仍保持 0。

### Pre-arm 安全输入要区分“已确认”和“当前安全”

现象：

- 急停、供电、限位这些输入还没有接真实 GPIO/ADC。
- 如果只用 `*_CONFIRMED=1` 表示“这一路做过验证”，后续可能忘记同时检查当前电平/电压/限位状态。

根因：

- 穿戴式设备的安全输入有两个不同问题：这路输入是否已经接线并验证过，以及此刻它是否处于安全状态。
- 二者不能混成一个布尔值。

技巧：

- M33 pre-arm 需要同时满足 `confirmed=1` 和 `safe_now=1`。
- 当前默认 `source=unwired`、`confirmed=0`、`safe_now=0`，所以 `ready=0` 是正确结果。
- `cmd_m33_safety_inputs` 只打印合同，不改变模式，不允许输出。
- `cmd_m33_prearm_check` 的 `PREARM_INPUT_DETAIL` 用来快速确认哪一路还没有接入或当前不安全。

状态：

- 已在 M33 侧加入诊断命令和收紧后的 ready 条件。
- 用户烧录后已验证：`cmd_m33_safety_inputs` 显示三路安全输入均为 `source=unwired confirmed=0 safe_now=0`，`cmd_m33_prearm_check 0x40` 在 7 号 telemetry 新鲜时仍保持 `ready=0`。

### 安全输入先写映射合同，再接真实输入

现象：

- 急停、电源/电压、限位都非常关键，但当前还没有确认具体 pin、ADC channel、硬限位类型或常开/常闭逻辑。

技巧：

- 先维护 `docs/M33_SAFETY_INPUT_MAPPING.md`，把输入源、确认条件、当前安全条件和失败 detail 写清楚。
- 真实固件读取要一项一项加，先只读 raw value，再转 `safe_now`，最后才接入 pre-arm。
- 不要为了推进 `armed` 状态而把 `confirmed` 写死为 1；没有现场验证时必须保持失败。

状态：

- 已新增映射合同文档。下一步等真实接线信息后，先做急停只读诊断。

### 40Pin 安全输入只接 3.3V 逻辑

现象：

- 已从 40Pin RPI 兼容排针中预选 pin 11 作为急停诊断输入。
- 用户确认只有急停需要接 GPIO；电源 OK 不管，限速和限位后续由自己在 M33 代码里设置。

技巧：

- GPIO 只接 3.3V 逻辑，不能直接接电池、电机母线或 5V。
- 急停优先用常闭链路，断线也应读成不安全。
- 电源 OK 当前标记为 `not_used_no_power_ok_input`，不作为接线或实现任务。
- 限速和限位先作为 M33 代码配置，等用户根据真实机械结构写入代码后再确认。
- 选 pin 或写软限位不等于确认安全，固件第一步只能打印 raw value/配置状态，不能让 `confirmed=1` 或 `motion_allowed=true`。

状态：

- 已记录 estop pin 选择和电气语义；尚未实现或验证 GPIO 读取。

### 限速限位先作为 M33 代码配置项

现象：

- 用户明确限速、限位后续由自己直接改 M33 代码设置，不接 GPIO。

技巧：

- pre-arm 要分别暴露位置限位、速度限制、扭矩/电流限制，不要只用一个模糊的 `limits_confirmed`。
- 默认必须是 `confirmed=0 safe_now=0`，这样用户还没填真实参数前不会误进入运动许可。
- 串口看 `PREARM_CODE_LIMITS`，确认三类限制各自状态。

状态：

- M33 已预留 `PREARM_CODE_LIMITS` 输出；等待后续烧录验证。

### 开发台架小幅运动也必须保留 M33 审核

现象：

- 为了尽快打通 `ROS2 JointTrajectory -> NanoPi -> M33 -> motor`，开发阶段需要允许小幅真实运动。
- 原 logging-only 路径只打印不执行；直接关闭 logging-only 会暴露真实执行路径的问题。

根因：

- M33 之前在非 logging-only 分支里存在“入队一次 + 直接执行一次”的结构，可能导致同一条 `0x320` 被执行两次。
- NanoPi/ROS 使用 `0-based` joint id，M33 底层电机关节函数使用 `1-based` joint id，关闭 logging-only 前必须显式转换。

技巧：

- 用 `CONTROL_DEVELOPMENT_BENCH_MOTION_ENABLE=1U` 表示台架开发模式，不把它和正式穿戴 pre-arm 混在一起。
- 台架运动也必须先过 M33 审核：关节号、位置、速度、扭矩/电流、heartbeat。
- 当前开发限位是 `-60°~+60°`，速度 `-5~+5 rpm`，`torque_ma=0`。
- 禁止把这种台架模式当作人体穿戴许可；正式模式仍需要急停和最终限速/限位/限流安全确认。

状态：

- M33 已修正为审核通过后单次直接应用；已编译 `control_layer.o`，未烧录验证。

### SSH 端口可连但握手被远端关闭时不要继续动电机

现象：

- 烧录 M33 后，Windows 主机尝试 `ssh pi@192.168.2.66`。
- 一开始连接超时，后续 TCP 能建立，但 SSH 在 banner/key exchange 前被远端关闭或 reset。
- 典型输出：

```text
kex_exchange_identification: Connection closed by remote host
Connection closed by 192.168.2.66 port 22
kex_exchange_identification: read: Connection reset
Connection reset by 192.168.2.66 port 22
```

判断：

- 这不是 ROS 或 CAN 协议问题，首先是 NanoPi 网络/SSH 服务可用性问题。
- 在不能远程看 `can0`、`candump`、ROS bridge 和 M33 状态日志时，不应发送 `0x320` 或运动轨迹。

排查顺序：

- 现场确认 NanoPi IP 是否仍是 `192.168.2.66`。
- 在 NanoPi 本机执行 `hostname -I`、`sudo systemctl status ssh`、`sudo systemctl restart ssh`。
- 如果 SSH 仍被 reset，查看 `sudo journalctl -u ssh -n 80 --no-pager`。
- SSH 恢复后先运行只读检查：`ip -details link show can0`、短时间 `candump -L can0`、ROS `/rehab_arm/safety_state`。

状态：

- 当前远程验收被 SSH 阻塞；没有发送运动命令。

### 先证明 0x322 为 ok/armed，再发 0x320

现象：

- M33 开发台架固件刚烧录后，NanoPi bridge 能发 `0x321`，但如果 `0x322` 仍是 `A5xx070001020A00`，NanoPi 会拒绝轨迹。
- 修正启动 detail 后，`0x322` 变为 `A5xx070000030000`，bridge 才允许 `enable_target_tx=true` 的轨迹下发。

技巧：

- `0x322#A5xx070000030000` 是当前台架开发模式的放行状态：`safety=ok`、`mode=armed`、`detail=none`。
- 发布轨迹前先抓包确认 `0x321/0x322` 连续稳定，CAN 为 `ERROR-ACTIVE`。
- 对 3 号伺泰威，当前正规链路是 `shoulder_abduction_joint` -> ROS joint id `2` -> M33 motor joint `3`。
- 3 号小幅验证帧：`0x320#03020B0005000000`，约等于 joint2 目标 `1.1°`、`5 rpm`、`torque_ma=0`。
- 更明显但仍在边界内的 3 号验证帧：`0x320#0302AD0105000000`，约等于 joint2 目标 `42.9°`、`5 rpm`、`torque_ma=0`。
- 用户要求超过当前限位的角度时，不要绕过 M33/bridge 限位；先给出当前可执行上限内的动作，后续再通过代码审查和烧录调整限位。

状态：

- 已实测 motor3 正规链路能从 ROS trajectory 触发 M33 电机输出。

### motor7 当前只能算直接 CAN 调试，不算正式路径

现象：

- 用户允许开发阶段动 7 号。
- 当前 ROS bridge 只映射 5 个 ROS 关节，M33 对 `0x320` 的 ROS joint id 也只接受 `0..4`，还没有正式映射到 M33 motor joint7。

技巧：

- 如果必须临时验证 7 号，只能明确标为 debug direct CAN：
  - `nanopi_can_master.py private speed --motor 7 --vel 0.05 --kd 1.0`
  - 短时间后必须发送 `nanopi_can_master.py private stop --motor 7`
- 直接 private CAN 绕过 M33 `0x320` 安全审核，不能作为正式机器人开发路径。
- 打开 7 号 active-report 后要关掉，避免总线一直刷 `0x180007FD`。

状态：

- 已短促验证 motor7 private CAN 指令和反馈；下一步应把 7 号接入正式 `0x320` 映射。

### CANSimple 命令帧出现不等于 3号电机真的动了

现象：

- ROS/M33 给 motor3 发出 `0x320#0302AD0105000000` 后，CAN 上能看到 `0x067/0x068`。
- 用户现场反馈 3号没有明显运动。
- 进一步检查时，M33 对 motor3 的 `0x332` 状态帧仍是 `B3 xx 03 00 00 00 00 00`，没有有效位置/速度/温度变化。

判断：

- `0x067/0x068` 很可能只是 M33 发出的 CANSimple 命令或 SocketCAN echo，不是电机已经进入 closed-loop 的证据。
- 如果没有 CANSimple heartbeat、encoder estimate、error/status 回复或 M33 缓存状态变化，就不能认为 motor3 被真正控制。

技巧：

- 3号调试下一步先证明 motor3 自己在线：
  - 查 CANSimple heartbeat 或厂家状态帧。
  - 查 node id 是否仍是 3。
  - 确认驱动电源、使能状态、错误码和 closed-loop 状态。
  - 不要靠 `can0` 仍为 `ERROR-ACTIVE` 判断目标电机 ACK，因为总线上其他节点也可能 ACK。

状态：

- 当前 motor3 正规链路已能把命令发到 M33，但 motor3 执行/反馈未打通。

### motor7 直接 CAN pulse 后要恢复安静

现象：

- 为了让动作更明显，motor7 直接 private CAN 速度从 `0.05 rad/s` 提到 `0.30 rad/s`，保持约 1s。
- active-report 打开后总线会持续出现 `0x180007FD` 或 `0x188007FD`。

技巧：

- 测试后必须发送 `private stop --motor 7`。
- 测试后关闭 active-report：`private active-report --motor 7` 不带 `--enable-report`。
- 如果临时启动了 `enable_target_tx=true` 的 ROS bridge，测试结束后停掉，避免后续误发轨迹。

状态：

- 已执行 stop，关闭 7号 active-report，并停止 ROS bridge。

### 直接电机调试后必须做 quiet check

现象：

- motor7 再次直接 private CAN 测试时，运动阶段能看到 `0x188007FD` 反馈变化，M33 聚合帧 `0x336` 也跟着变化。
- 如果 active-report 没有关掉，后续总线会持续刷反馈帧，容易误判为正式控制链路仍在运行。

技巧：

- 每次直接调试 7号后按固定顺序收尾：`private stop --motor 7`，再运行 `private active-report --motor 7` 关闭主动上报。
- 收尾后运行 `timeout 1 candump -L can0 | head -20`，期望没有持续 `0x180007FD/0x188007FD`。
- 同时查 `ps -ef | grep -E '[p]soc_can_bridge|[r]os2'`，确认没有 `enable_target_tx=true` 的 ROS bridge 遗留。
- `can0` 需要保持 `ERROR-ACTIVE` 且错误计数为 0；否则下一次动作前先排 CAN 物理层或供电。

状态：

- 已完成一次 motor7 复测并确认 stop 后总线安静。

### motor7 反馈 ID 的电机号不总在同一个字段形态，角度映射不能直接信

现象：

- 7号静止主动上报常见为 `0x180007FD`。
- 7号运动反馈会出现 `0x188007FD`。
- 如果只匹配 `data2 == 0x0007`，会漏掉 `0x8007` 这种运动反馈，导致软件以为角度没有变化。
- 修正 ID 匹配后，软件解出的相对变化约为 `55°`，但用户现场观察到实际转了很多圈。

技巧：

- 解 7号 private feedback 时，扩展帧格式为 `type/data2/data1`。
- 对 7号反馈应匹配 `(data2 & 0xFF) == 7` 且 `data1 == 0xFD`，不要只匹配完整 `data2 == 0x0007`。
- 不要把当前脚本里的 `data[0:2] -> -12.57~12.57 rad` 当作输出轴角度或关节角度；它可能是电机内部截断位置、单圈字段、编码器原始映射，或还缺少减速比/多圈累计。
- 在完成实物标定前，7号角度限位不能依赖这个字段，只能使用人工观察、低速短时、外部编码器/限位、或 M33 中经过验证的角度来源。

状态：

- 7号 private feedback 的 ID 识别规则已验证；角度数值映射已被现场观察推翻，后续必须重新标定。

### 7号标定优先用定时低速脉冲，不用未知角度闭环

现象：

- 用户要求观察 7号实际转角。
- 由于反馈角度映射不可信，不能再用“解码到 60°自动停”作为控制条件。

技巧：

- 标定阶段用固定速度和固定时间：例如 `5 rpm` 跑 `3s`，再立即 stop。
- 现场记录实际输出端角度或圈数，再反推真实比例。
- 每次脉冲后关闭 active-report，并用短 `candump` 确认没有 `0x180007FD/0x188007FD` 持续刷屏。

状态：

- 已完成 `5 rpm / 3s` 的 7号定时标定脉冲；用户确认输出面约转 `150°`。
- 这意味着当前 direct private speed 命令 `5 rpm` 对应可见输出端约 `50°/s`，即约 `8.33 rpm`。不要把命令名或脚本参数直接当真实输出 rpm。
- 下一轮建议在输出面贴一条明显胶带或画线，并固定手机视角，再做同样的 `5 rpm / 3s` 标定。

### 先查官方型号和减速比，再解释实测速度

现象：

- 7号 `5 rpm / 3s` 目测约 `150°`，和“命令名就是输出端 5 rpm”的直觉不一致。
- 用户提醒必须查官方资料和减速比。

结论：

- 3号伺泰威减速比为 `48:1`，但目前还没现场看到它真实运动。
- 4号、5号是灵足 RS00，官方减速比 `10:1`。
- 6号、7号是灵足 EL05，官方减速比 `9:1`。
- 资料来自本地官方 RobStride 产品规格书、RS00/EL05 使用说明书，以及现场型号确认。

技巧：

- 减速比只能解释电机侧和输出侧的机械比例；不能自动证明 CAN `speed` 参数、MIT feedback 位置字段或 active-report 位置字段就是输出轴物理角度。
- 对 6/7 号 EL05，后续需要单独补 EL05 的量程、参数表和反馈字段，不能直接套 RS00 的 ROS 示例量程。
- 对 3号伺泰威，在现场未看到动作前，不要把“命令帧发出”写成“控制已打通”。

状态：

- 已把 3/4/5/6/7 型号和减速比写入项目文档；下一步在代码中建立 RS00/EL05 分型号表。

### EL05 不要套用 RS00 的工程量程

现象：

- 本地 `robstride_ros_sample` 有 RS00~RS06 的示例量程，但没有单独 EL05 枚举。
- 6号、7号已经确认是 EL05，且 7号反馈角度映射已被现场观察推翻。

技巧：

- NanoPi 侧可以记录 `actuator_type=EL05` 和 `gear_ratio=9.0`。
- 在确认 EL05 官方量程/字段前，6/7号 active-report 的 position、velocity、torque 继续保持 `None`，只保留 raw 字段。
- 4/5号 RS00 可以使用现有 RS00 示例量程做临时工程解码，但正式 M33 侧仍要再次限幅和标定。

状态：

- 已在 `candump_motor_telemetry.py` 中按该策略实现，并用单测覆盖。

### 3号 CANSimple 命令发出不等于执行已打通

现象：

- 3号伺泰威减速比为 `48:1`，但目前还没现场看到它真实运动。
- 直接 CANSimple 测试已发送 clear errors、closed-loop、velocity mode/input velocity、zero velocity、idle。
- CAN 上能看到命令帧 `0x078`、`0x067`、`0x06B`、`0x06D`，但 M33 聚合状态 `0x332` 仍为零。

判断：

- 当前只能证明 NanoPi 到 CAN 总线的命令发送成功。
- 仍不能证明 3号驱动已经进入 closed-loop、编码器有效、刹车释放、功率级使能或反馈协议已被 M33 正确解析。

技巧：

- 继续加大速度前，先找 3号真实 heartbeat/status/encoder feedback 帧。
- 减速比 `48:1` 需要在规划侧处理：输出端角度/速度乘以 48 后才是电机侧命令量。
- 若以输出端 `5 deg/s` 为目标，电机侧约为 `4.19 rad/s`；这次使用 `4.0 rad/s` 电机侧命令属于温和台架测试。

状态：

- 3号已执行直接 CANSimple温和速度测试并退回 idle；执行/反馈仍未确认。

### 绝对位置控制必须先过软件零点标定门

现象：

- 7号通过 M33 正式路径收到 `30°` 绝对目标后，现场出现剧烈转动。
- 后续查 RobStride 官方示例，帧 `01800007#855481370F5C3333` 按 EL05 映射约为 `30°` 目标、`0.475 rad/s`、`Kp=30`、`Kd=1`，编码本身不像是把 `30°` 写成几百度。

判断：

- 更可能的问题是机械零位、方向、当前位置参考和真实输出角度比例未标定。
- 在这种状态下，任何绝对位置闭环都会让电机去追一个软件认为正确、机械上却不一定安全的位置。

技巧：

- 标定前，M33 必须拒绝 ROS `set_target` 和 `motor_pos` 这类绝对位置控制。
- `m33_joint_calib [joint]` 用来确认 `calibrated/direction/gear/zero_offset`。
- `0x322 detail_code=11` 表示 `joint_uncalibrated`，NanoPi ROS 必须把它解析为 `motion_allowed=false`。
- 标定时优先使用低速短脉冲、人工观察和外部标记，先确认方向和比例，再启用小角度位置闭环。

状态：

- 已在 M33 添加默认未标定门；所有关节默认 `calibrated=0`。
- 后续需要烧录后验证：合法 `0x320 set_target` 应被拒绝为 `joint_uncalibrated`，不应再发出电机位置帧。

### 验证 joint_uncalibrated 前要先刷新 heartbeat

现象：

- 烧录 `daf78140` 后，第一次向 M33 发送合法 `0x320 set_target` 得到 `detail_code=1 heartbeat_timeout`，不是预期的 `joint_uncalibrated`。
- 随后按 `heartbeat -> target -> heartbeat` 顺序重测，得到 `0x322#A540070001010B00`，即 `detail_code=11 joint_uncalibrated`。

原因：

- M33 的安全评估先检查 NanoPi heartbeat 是否新鲜。
- 如果 heartbeat 过期，安全机在更早一层拒绝，不会继续走到“关节是否标定”的检查。

技巧：

- 验证某个具体拒绝原因时，先发一帧 `0x321` heartbeat，让 heartbeat 条件通过。
- 然后立刻发目标帧，再发下一帧 heartbeat 读取 `0x322` byte6。
- 如果目标是验证 `joint_uncalibrated`，过滤 `candump` 时要确认没有对应电机控制帧，例如 7号没有 `01800007`、`0300FD07`、`180007FD/188007FD`。

状态：

- 已现场验证：合法 7号目标在未标定状态下被拒绝为 `joint_uncalibrated`，没有下发 7号电机控制帧。

### 标定遥测和运动命令要分开

现象：

- 下一步需要通过 M33 正式链路读取 7号当前位置/原始反馈。
- 直接使用 ROS 绝对目标不安全，直接 NanoPi private active-report 又绕过 M33 正式链路。

策略：

- 允许 `0x320 active-report` 作为 calibration telemetry 通过 M33。
- 不允许 `enable/zero/mode/target` 因此一起通过。
- M33 日志用 `apply_calibration_telemetry_only` 标记这种非运动遥测动作。

技巧：

- 开遥测前先发 heartbeat，避免被 `heartbeat_timeout` 拦截。
- 采集完必须关闭 active-report，并用短 `candump` 确认没有持续 `180007FD/188007FD`。
- 过滤 CAN 时要同时确认没有 7号控制帧 `01800007`。

状态：

- 已在 M33 代码中加入遥测例外，待烧录后验证。

### M33 active-report 遥测验证通过后仍要区分原始反馈和聚合状态

现象：

- 烧录 `9e1573d7` 后，通过 `0x320#060401` 成功打开 7号 active-report。
- 抓包出现 `0x180007FD` 原始主动上报和 `0x336` M33 聚合状态。
- 关闭 active-report 后，`0x180007FD/0x188007FD` 停止，但 `0x336` 仍周期性出现。

判断：

- `0x180007FD/0x188007FD` 是电机原始 active-report；关闭后应该停止。
- `0x336` 是 M33 聚合/缓存状态发布，关闭 active-report 后仍可能继续发最近缓存值，这是正常状态输出，不代表电机还在持续主动上报。

技巧：

- 验证关闭 active-report 是否成功，应重点看 `180007FD/188007FD` 是否消失。
- 同时确认没有 `01800007` 或 `0300FD07`，避免把遥测入口误变成运动控制入口。
- 如果 SSH wrapper 超时，先补发关闭 active-report，再读 `/tmp/*.candump` 文件做事后分析。

状态：

- 已现场验证：M33 formal `active-report` telemetry path 可用，且没有 7号运动控制帧。

### 标定观测报告不能当成运动标定证明

现象：

- `0x180007FD` 原始主动上报和 `0x336` M33 聚合状态都能显示位置字段。
- 这些字段能证明“遥测链路通了”，但不能证明“物理关节角度已经正确映射”。

原因：

- 7号曾经出现过软件角度看似接近限位、现场实际转动明显更多的情况。
- RobStride private protocol 的 `+/-12.57 rad` 字段映射是电机侧协议范围，不等于本项目已经完成输出关节零点、方向和比例标定。

技巧：

- 用 `calibration_observation <candump.log> --pretty` 先做无运动报告。
- 报告里的 `safe_to_use_as_motion_proof` 必须保持 `false`，它只用于确认有无遥测、有无误发运动帧。
- 只有人工确认机械零点、方向、小角度正反向和 M33 限位后，才允许把对应关节的 `CALIBRATED` 改为 `1U`。

状态：

- 已加入自动化测试，能检测 `01800007` 这类 7号运动控制帧并让报告 `ok=false`。

### 未装机阶段可以先用直接台架配置

现象：

- 当前机械臂还没有装机，用户希望先“随便一个零点”打通正式 M33 运动链路。

策略：

- 在未装机、空载、有人观察的阶段，允许直接把 7号设为 `CALIBRATED=1`、`ZERO_OFFSET=0` 来快速打通链路。
- 仍保留 M33 的 heartbeat、joint limit、rpm limit、torque/current limit 检查。
- 装机或穿戴前必须撤销这种台架配置，重新做机械零点、方向、限位和急停验收。

技巧：

- 临时零点后只测 `+5°/-5°`，用肉眼确认方向和幅度，再考虑更大角度。
- 只要方向/幅度不符合预期，立刻停止，不要用更大目标“试出来”。

状态：

- M33 已改为 7号直接台架标定配置，待烧录后现场验证。

### 正式路径打通不等于物理标定完成

现象：

- M33 台架版本烧录后，NanoPi `m33 target --joint 4 --deg 5 --rpm 1` 成功产生 7号厂家控制帧。
- CAN 上可见 `0x0300FD07`、`0x01800007`，stop 后可见 `0x0400FD07`。

判断：

- 这说明 `NanoPi -> 0x320 -> M33 safety gate -> motor7 private protocol` 这条链路已经能发命令。
- 但它不能证明物理方向、零点和输出角度比例是正确的。

技巧：

- 每次正式路径小角度试动后，马上发 `m33 stop --joint 4`。
- 先让现场观察者确认 `+5°` 的方向和大概幅度，再测 `-5°`。
- 如果方向反了，优先改 `CONTROL_MOTOR_JOINT7_DIRECTION`；如果幅度不对，再回到减速比/协议量程/机械输出映射排查。

状态：

- CAN 链路已现场验证，物理运动效果待用户确认。

### RobStride 参数位置反馈可能不等于可见输出轴运动

现象：

- Direct MIT 和 official CSP flow 都能让 CAN feedback/M33 `0x336` 的位置字段变化。
- 用户现场反馈 small direct target 没有可见运动。
- Official CSP flow 后 `0x336` 从约 `0.554 rad` 变化到约 `1.050 rad`，但仍需用户确认可见输出是否真的动了。

判断：

- 这排除了“完全没有发到电机”的问题，因为 enable、parameter write、feedback 都出现了。
- 当前不能继续把 `0x336 pos_mrad` 当作已经验证的输出关节角。

技巧：

- RobStride 位置模式应优先按官方参数流验证：`run_mode=5`、enable、`limit_spd(0x7017)`、`loc_ref(0x7016)`。
- 下一步读取 `0x7019 mechPos` 等官方机械/负载端参数，与现场视频标记对齐。
- 只有当“读数变化”和“可见输出轴变化”一致后，才能把该字段接入 M33 关节状态和安全限位。

状态：

- Official CSP CAN flow 已跑通；物理输出映射未完成。

### Motor7 RobStride 位置单位已按输出侧角度处理

现象：

- Official CSP 从约 `3.0 rad` 回到 `1.0 rad`，理论变化 `1.997 rad = 114.4°`。
- 用户现场确认看到的也是约 `114.4°`，而不是除以 `9` 后的约 `12.7°`。

根因/判断：

- 对 7号 EL05 当前 CAN 参数接口来说，`loc_ref` 和反馈位置已经对应可见输出侧角度。
- M33 原来把 ROS joint 角度乘以 `gear_ratio=9` 再发给 RobStride，这会把正式路径目标放大。

修正：

- 7号正式 ROS 映射临时改为 `CONTROL_MOTOR_JOINT7_GEAR_RATIO=(1.0f)`。
- 当前台架零点用 `CONTROL_MOTOR_JOINT7_ZERO_OFFSET_RAD=(1.0f)`，让 ROS joint4 `0°` 对齐最后确认的台架姿态。

状态：

- 待烧录后验证 formal path `joint4 +5°` 是否实际输出约 `5°`。

### Lingzu 正式位置控制优先走 CSP 参数流

现象：

- 7号 official CSP flow 能产生可见约 `114.4°` 输出运动。
- M33 formal path 之前使用 MIT 控制帧，虽然 CAN 帧发出，但 fixed-scale retest 只到约 `1.009 rad`，没有到 `1.087 rad` 目标。

判断：

- 对 4/5/6/7 灵足 RobStride 电机，正式 `0x320 set_target` 不应继续依赖 MIT frame 作为位置模式。
- 应使用官方 CSP 参数流：`run_mode=5`、enable、`limit_spd(0x7017)`、`loc_ref(0x7016)`。

修正：

- M33 `control_joint_motor_set_target()` 改为调用 `control_motor_position_control(..., csp_mode=true)`。
- 4/5/6/7 的 formal ROS 映射比例临时统一为 `1.0f`，按输出侧角度处理。

状态：

- 待烧录后验证。

### Motor3 CANSimple 速度参数是电机侧，输出端要按 48:1 看

现象：

- Direct `cansimple vel --node 3 --vel 0.5` 数据通了，但输出端可能不明显。
- Direct `--vel 8.0` 跑约 `2s` 后，M33 `0x332` 输出角从约 `0.739 rad` 到 `1.147 rad`，变化约 `23.4°`。

判断：

- NanoPi direct CANSimple `--vel` 是电机侧 rad/s，不是输出关节侧 rad/s。
- 3号保留 48:1 映射是合理的：输出角约等于电机侧角度除以 48。

修正：

- M33 3号台架配置保持 `CONTROL_MOTOR_JOINT3_GEAR_RATIO=(48.0f)`。
- 当前台架姿态作为临时零点：`CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(55.1f)`。
- 放开台架 formal：`CONTROL_MOTOR_JOINT3_CALIBRATED=1U`。

状态：

- 待烧录后验证 formal joint0 小角度控制。

### 不要把 RobStride 的输出轴单位结论套到伺泰威 CANSimple

现象：

- 7号 RobStride/EL05 经 CSP `loc_ref` 实测后，确认该路径在当前台架上按输出侧角度理解。
- 3号伺泰威也在做 formal path 标定，用户提醒不要盲目 `x48`。

判断：

- 两类电机协议不能混用结论。
- RobStride formal CSP 的 `loc_ref` 已被现场观察验证为输出侧角度。
- 伺泰威 CANSimple/ODrive-like 的 `Set_Input_Pos`、`Get_Encoder_Estimates` 在 ODrive 官方协议里都是 `rev/rev_s` 单位，不是“输出轴度数”接口。

技巧：

- 对 3号，如果继续使用 CANSimple，M33 里保留 `joint -> motor protocol` 的减速比换算。
- 如果希望 3号像 RobStride CSP 那样直接按输出轴角度发命令，应单独做伺泰威 MIT/output-axis RAD 协议路径，先低速台架验证，再进 formal path。
- 现场看到幅度不对时，不要直接把 `gear_ratio` 改成 `1.0`；先确认当前命令到底是 CANSimple、MIT 还是 CANOpen。

状态：

- 已记录源驱动路线：ODrive CAN protocol 与 `odriverobotics/ros_odrive`。

### 3号 direct 能动但 formal 不动时先看 0x322 detail

现象：

- Direct CANSimple 对 3号发送“当前位置 + 输出约 5°”后，`0x069` 从约 `7.66448 rev` 到 `8.33206 rev`，折算输出约 `5.0069°`。
- 但 `m33 target --joint 0 --deg 5 --rpm 1` 没有触发 M33 发 `0x06C Set_Input_Pos`。
- 随后的 heartbeat 回复 `0x322 = A5 79 07 00 01 02 0B 00`。

判断：

- byte6/detail code `0x0B` 是 `JOINT_UNCALIBRATED`。
- 这说明 M33 安全状态机拦截了 formal path，电机没有收到 formal 位置命令。
- 此时不能继续怀疑 CANSimple 公式本身；direct path 已证明 3号能按 `rev` 单位移动。

技巧：

- formal path 不动时，先发一次 heartbeat，看 `0x322` 的 detail code。
- 如果 detail 是 `0x0B`，需要烧录包含对应 `CONTROL_MOTOR_JOINTx_CALIBRATED=1U` 的 M33 bench 固件，或继续让 formal path 保持安全关闭。
- 不要为了绕过这个状态直接把安全门删掉；台架调试可以临时开 gate，但文档里必须标清这是未装机 bench 配置。

状态：

- 3号 direct CANSimple 已验证；formal M33 仍受当前板端固件 calibration gate 阻挡。

### 3号 formal 发了位置帧但几乎不动时检查 Set_Limits 第二字段

现象：

- 烧录 bench firmware 后，formal `m33 target --joint 0 --deg 5` 不再被 `JOINT_UNCALIBRATED` 拦截。
- CAN 上能看到 `0x06B`、`0x06F`、`0x067`、`0x06C`。
- 但 `0x069` 只变化约 `0.00408 rev`，折算输出约 `0.03°`。

判断：

- M33 的 CANSimple position path 原先把 `Set_Limits` 第二个 float 写成 `0.0`。
- 对伺泰威/ODrive-like 位置模式，这个字段不能作为可用限流长期为 0，否则位置目标可能发出但几乎没有执行能力。

修正：

- M33 commit `ed1cfc49` 增加 `CONTROL_CANSIMPLE_POSITION_LIMIT_CURRENT=(5.0f)`。
- 位置目标仍发 `Torque_FF=0`，只是 `Set_Limits` 提供非零限流。

状态：

- 待烧录 `ed1cfc49` 后复测 formal joint0。

### 3号大角度前必须先确认 0x061/0x069 在线

现象：

- direct 30° timed velocity attempt 发送了 `clear`、`closed-loop`、`velocity`、`idle` 命令。
- 该次测试期间没有捕获到 3号 `0x061/0x069`，只看到 M33 `0x332` 缓存状态。

判断：

- 没有 `0x061/0x069` 时不能仅凭 TX 命令帧判断 3号已执行。
- 先前 direct +5° 成功依赖 `0x069` 明确变化；同样标准也必须用于 30°验证。

技巧：

- 大角度前先被动监听 1~3 秒，确认 node3 heartbeat/encoder 在线。
- 如果 node3 反馈缺失，先恢复 closed-loop/反馈，再做位置测试；不要把 M33 缓存状态当成电机实时反馈。

### 3号没有 0x061/0x069 时不要继续盲发动作

现象：

- 用户确认 3号 30°尝试没有动。
- 被动监听 2 秒没有任何 3号帧。
- 主动发 node3 `Get_Error/Clear/Closed-loop/Idle` 后，只看到 M33 `0x332`，没有 3号 `0x061/0x069`。
- M33 heartbeat 仍正常，NanoPi `can0` 仍为 `ERROR-ACTIVE`。

判断：

- NanoPi CAN 和 M33 通信是活的，但 3号 Sitaiwei 当前没有作为 CANSimple node3 响应。
- M33 `0x332` 是聚合/缓存状态，不能替代 3号实时 CANSimple 反馈。

技巧：

- 先查 3号供电、使能、CANH/CANL、节点 ID、协议模式、是否被上位机切换过通信协议。
- 恢复标准是先被动看到 `0x061` heartbeat 和 `0x069` encoder estimate。
- 没有恢复前，不要继续尝试 30°、90°或 formal path 大动作。

### 3号驱动重启后旧 zero_offset 会把小角度放大

现象：

- node3 恢复在线后，formal `+5°` 触发了完整 CANSimple position path。
- `Set_Limits` 已发非零限流 `5.0f`。
- 但 `0x069` 从 `0 rev` 到约 `5.594 rev`，折算输出约 `41.96°`。

判断：

- 3号驱动/编码器重启后 `0x069 position_rev` 回到了 `0`。
- M33 仍保留旧临时零点 `55.1 rad`，导致 formal `+5°` 叠加旧零点后目标约 `9.436 rev`。
- 这不是 48:1 换算错，而是 bench zero offset 已经过期。

修正：

- M33 commit `abedf348` 将当前未装机台架 3号零点改为 `CONTROL_MOTOR_JOINT3_ZERO_OFFSET_RAD=(0.0f)`。

技巧：

- 伺泰威驱动每次重启/重新归零后，都要重新确认 `0x069 position_rev`，不能沿用上一次的 M33 零点。
- 大角度前必须先用 formal `+5°` 验证零点和方向。
- 这只是台架排故办法；正式机械臂必须做持久化机械零点或上电 homing。
- 旧版 `m33_joint_calib` 曾打印固件侧零点来源；当前路线已取消这类 M33 零点标注，不再把它作为正式依据。

### App、平台、M33、M55 不要各写一套患者参数

现象：

- 医疗康复机械臂需要按不同患者设置 ROM、限速、辅助等级、疼痛/疲劳策略和训练模式。
- 如果 App、平台、NanoPi、M33 和 M55 各自维护参数，现场会出现版本不一致和安全责任不清。

判断：

- 必须使用同一份 versioned Patient Device Profile。
- M33 只接收安全子集，M55 只接收模型子集，平台/App 负责编辑同一份源 profile。
- 第一版不要引入患者相对坐标系；先用机器人坐标系加 patient ROM limit 和 `rom_percent` 训练特征。

技巧：

- 同一设备同一时间只允许一个 active profile。
- 每条训练数据都记录 `profile_id/profile_version/session_id/machine_calibration_id/model_version`。
- VLA 和 M55 都只能输出建议或任务计划，不能直接写底层电机命令。

### M33 不做零点标注源

现象：

- 调试 3号/7号时曾经把临时零点写进 M33，导致驱动重启、台架姿态变化或上位机标注思路变化后，M33 固件里的零点和实际电机绝对角度容易不一致。

判断：

- 如果电机官方协议已经提供可信输出侧绝对角度，M33 不应该再维护一套零点标注。
- 零点、患者 ROM、训练模式、患者限速和标注元数据应该由上位机/平台/App 的统一 Patient Device Profile 管理。
- M33 只接收安全子集，做限位、限速、限流、急停、故障和通信超时裁决。

技巧：

- 不要在正式 M33 协议里新增 `session_zero`、`zero_source` 这类第二套零点语义。
- NanoPi 的 `m33 zero` 不作为正式接口使用；如需台架排故，另建显式 debug 工具，且不得进入正式 bringup。

状态：

- 已撤掉本轮新增的 M33 session zero 入口，并去掉 M33 诊断里的 `zero_source/zero_policy` 输出。

### App 和平台双控制不是双安全裁决

现象：

- 项目需要 App 蓝牙近端控制，也需要平台/服务器远端监控、数据采集、标注和后续总控台。

判断：

- App 和平台都只能提出控制请求或参数草案，不能各自持有一套独立安全权威。
- M33 必须是最终安全裁决方；任何远端延迟、断网、平台状态通过，都不能替代本地急停、限位、限速、限流和故障保护。

技巧：

- App BLE 优先做近端 start/pause/stop/estop request、模式切换和患者反馈。
- 平台优先做 profile draft/review、训练计划、数据/标注/模型管理和远程 stop/pause request。
- 冲突时取更保守状态；只有 M33 回报 `motion_allowed=true`，界面才能显示真实执行中。

### 电机遥测不能提升运动许可

现象：

- `0x330~0x337` 能生成 `/rehab_arm/motor_state` 和 `/joint_states`，平台/仿真/RViz 可以看到机械臂姿态。

判断：

- 遥测新鲜、姿态正常、温度正常，只说明“能看到状态”，不说明“可以动”。
- NanoPi、App、平台、VLA 都必须以 M33 `0x322 motion_allowed=true` 作为运动候选许可；legacy `state=ok` 和 motor telemetry 都不能替代它。

技巧：

- 离线先跑 `test_m33_ros_contract.py`，确认 limited/logging-only + 合法遥测仍然 `motion_candidate_allowed=false`。
- 真机联调时先看 `/rehab_arm/safety_state.motion_allowed`，再看 `/joint_states` 是否新鲜。
- 从 candump 离线验收时，也必须先看 `safety_state_count` 和 `motion_allowed_counts`；只有 `motor_state_count/joint_state_count` 不足以证明系统可以进入运动测试。
- 如果只读 heartbeat 抓包已经出现 `motion_allowed=true`，把它当作“开发台架 armed 状态”处理，不要因为没有发运动命令就忽略这个安全状态；下一步应先区分 bench mode 和正式 clinical mode。
- `bench_armed` 必须和正式 `armed/active` 分开。台架能动不等于可穿戴；NanoPi parser 默认应让 `bench_armed` 的 `motion_allowed=false`。
- NanoPi 上 `ros2 run` 的可执行名要以 `ros2 pkg executables rehab_arm_psoc_bridge` 为准；当前现场工作区使用 `psoc_can_bridge_node.py`，不是无后缀的 `psoc_can_bridge_node`。
- formal clinical 开关默认关闭是安全设计，不是功能缺失。只有 pre-arm ready 才能上报正式 `armed`；如果返回 `prearm_not_ready`，应补安全输入和参数，不要在 NanoPi 侧绕过。

### 离线数据工具测试要在临时目录释放前读取输出

现象：

- `test_build_replay_plan_cli_writes_filtered_plan` 第一次失败，错误为 `FileNotFoundError`，路径位于系统临时目录。

判断：

- CLI 已经写出文件，但测试在 `TemporaryDirectory()` 上下文退出后才读取，临时目录已被清理。

技巧：

- 测试离线导出工具时，要在 `with tempfile.TemporaryDirectory()` 作用域内读取输出文件。
- 这类错误不代表 JSONL/replay 功能失败，先检查测试生命周期。

### 上电只读数据采集不要强制要求 C8T6

现象：

- NanoPi 上电后，`can0`、M33 heartbeat、`0x332` 电机聚合状态、`/joint_states`、`/rehab_arm/motor_state` 都正常。
- 但 `check_recording.py` 默认要求 `/rehab_arm/sensor_state`，在 C8T6 未连接或未发 `0x7C2/0x7C3` 时误判整份记录失败。

判断：

- 上电只读检查的目标是验证 NanoPi、CAN、M33、ROS 状态桥和基础数据记录，不等价于完整硬件遥测验收。
- C8T6/传感器联调应作为下一层检查，不能阻塞基础电机/M33 状态链路确认。

修正：

- 新增 `poweron_readonly` topic profile，只要求 `/joint_states`、`/rehab_arm/safety_state`、`/rehab_arm/motor_state`。
- 完整硬件遥测仍使用 `hardware_telemetry`，继续要求 `/rehab_arm/sensor_state`。

技巧：

- 每次真实采集使用新的 `session_id`； recorder 以追加方式写文件，重复 session 会把多次记录混在一起。
- `bench_armed` 仍按 `motion_allowed=false` 处理；只读采集通过不代表可以运动。

状态：

- NanoPi 真实日志 `/home/pi/rehab_arm_logs/poweron-readonly-20260527-1923.jsonl` 已用 `poweron_readonly` 验证通过。

### NanoPi ROS Jazzy 环境缺 `ament_package`

现象：

- 在 NanoPi 上执行 `colcon build --packages-select rehab_arm_psoc_bridge` 失败。
- 报错包含 `ModuleNotFoundError: No module named 'ament_package'`，CMake 路径来自 `/opt/ros/jazzy`。

判断：

- 这是 NanoPi ROS/Python 构建环境问题，不是 CAN、M33 或 bridge 业务代码失败。
- 当前 `ros2 run` 仍可使用已有 install；纯 Python 文件可临时同步到 install 目录验证逻辑，但这不是长期方案。

技巧：

- 先确认 `/opt/ros/jazzy/setup.bash`、`python3 -V`、`python3 -c "import ament_package"`。
- 如果 `ament_package` 存在于 `/opt/ros/jazzy/lib/python3.12/site-packages`，但构建时仍找不到，先把这个路径补进 `PYTHONPATH`。
- `rehab_arm_ros2_ws/build_ros2.sh` 已加入自动补路径逻辑，优先用该脚本构建，不要长期依赖手动复制 install 文件。

状态：

- NanoPi 已验证 `./build_ros2.sh --packages-select rehab_arm_psoc_bridge` 可正常完成。
- `nanopi_live_telemetry_check.sh` 也已加入同样逻辑，现场只读验收脚本可直接使用。

### Windows here-string 远程执行会给参数带入 `\r`

现象：

- 通过 PowerShell here-string 管道到 `ssh ... bash -s` 时，`ros2 run ... --topic-profile poweron_readonly` 报 `invalid choice: 'poweron_readonly\r'`。

判断：

- 这是 Windows CRLF 进入远端命令参数造成的，不是 ROS 参数解析或 profile 名称错误。

技巧：

- 远端多行脚本适合做构建、复制、较长流程；但带枚举参数的最后验收命令，优先用单行 SSH 或在远端脚本内清理 CRLF。
- 如果看到候选值里明明有同名选项，却提示 `invalid choice`，优先检查参数末尾是否有隐藏 `\r`。

### PowerShell 中 `ssh -o` 可能被误解析

现象：

- 在 PowerShell 里直接运行复杂 `ssh -o BatchMode=yes ...` 命令时，报错类似：
  `A value that is not valid (BatchMode=yes) was specified for the outputFormat parameter.`

判断：

- PowerShell 把 `-o` 当成自己的参数解析了，命令没有真正发到 NanoPi。

技巧：

- 简单远程命令可以用 `ssh.exe --% -o BatchMode=yes ...`。
- 复杂多行远程命令优先用 PowerShell here-string 管道到 `ssh.exe --% ... bash -s`。
- 如果命令里包含枚举参数，注意上一条 CRLF 问题，必要时用单行 SSH 重跑最后的验证命令。

### NanoPi 半量同步 ROS 包会让 CMake install 失败

现象：

- 只把本地最新 `CMakeLists.txt` 同步到 NanoPi 后，`colcon build` 报：
  `ament_cmake_symlink_install_programs() can't find ... jsonl_replay_node.py`。

判断：

- NanoPi 源码目录比本地旧，新的安装列表引用了板子上还没有的脚本。
- 这不是 motion report 或 CMake 语法错误，而是半量同步导致源码和安装列表不一致。

技巧：

- 修改 ROS 包安装列表时，要同步整个 package 源码目录，至少同步 `rehab_arm_psoc_bridge/`、`test/`、`CMakeLists.txt` 和 `setup.py`。
- 新增 `install(PROGRAMS ...)` 脚本后，确认源文件有可执行位；否则 symlink 存在但 `ros2 run` 会报 `No executable found`。
- 本地新脚本入 Git 时可用 `git add --chmod=+x <script.py>`。

### 人不在现场时不要执行台架运动序列

现象：

- 用户允许“动电机没关系”，但同时说明自己不在现场。

判断：

- 医疗康复外骨骼最终要穿在人身上，远程无人看护时不应该继续发真实动作，即使是台架开发阶段。

技巧：

- 远程无人现场时，只允许做 dry-run 计划、日志复盘、数据工具、仿真和文档。
- `bench_motion_sequence.py` 默认只输出计划；真实执行必须同时带 `--execute --confirm-onsite`。
- 执行后必须保存 candump，并用 `motion_test_report.py` 检查 target、CSP、stop、无 MIT 旧帧，再决定下一步。

### 电机工具要统一配置，但执行分级放行

现象：

- 如果每个电机各写一套测试命令，后面很容易出现 3号、7号能跑，4/5/6 却映射、限位和文档不同步。

判断：

- 所有电机应该进入同一张 profile 表，包含 `motor_id -> joint_id -> joint_name -> vendor/model -> test_status`。
- 但统一配置不等于全部允许运动。当前只允许执行 3号和 7号，4/5/6 只能 dry-run 计划。

技巧：

- `bench_motion_sequence.py --list-motors --pretty` 是查看当前权威测试表的入口。
- 如果误对 4/5/6 加 `--execute --confirm-onsite`，工具应拒绝，并提示不在 allowlist。
- 要放开 4/5/6，必须先补机械限位、方向、小角度台架验证和风险记录，不要直接改 allowlist。

### ROS Python 工具既要支持包导入，也要支持直接脚本运行

现象：

- 把公共代码抽到 `motor_profiles.py` 后，单元测试里的直接命令 `python bench_motion_sequence.py ...` 返回 `1`，但包内导入测试能通过。

判断：

- 直接运行脚本时，`sys.path` 指向脚本所在目录，不一定能解析 `from rehab_arm_psoc_bridge...` 这种包导入。
- ROS `console_scripts` 和 `ros2 run` 更接近包导入路径，台架调试时直接 `python script.py` 更接近本地脚本路径。

技巧：

- 需要同时支持两种入口的工具，可以先尝试包导入，再在 `ModuleNotFoundError` 时回退到同目录导入。
- 每次重构 ROS Python 工具后，同时跑单元测试和直接脚本 CLI 测试，避免 NanoPi 台架调试时入口坏掉。

### Windows `py_compile` 可能被旧 `__pycache__` 锁住

现象：

- 本地运行 `python -B -m py_compile ...` 时出现：
  `[WinError 5] 拒绝访问。: '__pycache__\\patient_profile.cpython-311.pyc.<tmp>' -> '__pycache__\\patient_profile.cpython-311.pyc'`

判断：

- 单元测试和 CLI 已通过，问题发生在 pyc 临时文件替换阶段，属于 Windows 本地生成缓存被占用或权限异常，不是 Python 源码语法错误。

技巧：

- 只清理当前包目录内的生成缓存 `rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/__pycache__`，确认路径在仓库内后再删除。
- 清理后重跑 `python -B -m py_compile ...`；如果通过，按缓存问题记录，不要改业务代码。

### ROS2 Jazzy 跨机器发现需要设置发现范围

现象：

- 仿真主机到 NanoPi 的 `/chatter` 能收到，但 NanoPi 到仿真主机的 `/rehab_net_test` 一开始显示 topic 尚未发布。

判断：

- 两边已经同网段且 ping 通，问题更像 ROS2 DDS discovery 配置，而不是 IP 路由。
- Jazzy 会提示 `ROS_LOCALHOST_ONLY is deprecated`，并建议使用 `ROS_AUTOMATIC_DISCOVERY_RANGE` 和 `ROS_STATIC_PEERS`。

技巧：

- 两边统一写入：
  `ROS_DOMAIN_ID=42`、`ROS_LOCALHOST_ONLY=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`。
- 重新启动 publisher/subscriber 后，NanoPi -> 仿真主机测试通过。
- 如果 topic 还未被发现，可显式指定类型：
  `ros2 topic echo /rehab_net_test std_msgs/msg/String --once`。

### `ros2 run` 找不到脚本时先查可执行位

现象：

- 仿真主机上 `ros2 run rehab_arm_sim_mujoco check_sim_env --pretty` 报 `No executable found`。
- `install/rehab_arm_sim_mujoco/lib/rehab_arm_sim_mujoco/check_sim_env.py` 文件存在，但 `ros2 pkg executables rehab_arm_sim_mujoco` 只列出 `mujoco_sim_node.py`。

判断：

- `install(PROGRAMS ...)` 只会把带可执行权限的脚本注册为 ROS2 executable。
- `check_sim_env.py` 和 `upload_sim_readiness.py` 在 Git 中是 `100644`，所以安装后文件存在但 `ros2 run` 不认。

技巧：

- 用 `git ls-files -s <script.py>` 查模式。
- 用 `git add --chmod=+x <script.py>` 修正入库权限。
- 远端临时验证可以 `chmod +x src/.../script.py` 后重建对应包。

### 仿真主机无法直接 fetch GitHub 时可以用 Git bundle 同步

现象：

- 仿真主机仓库 origin 是 `git@github.com:...`，`git fetch` 报无法读取远端仓库。
- 临时 HTTPS fetch 又报 `gnutls_handshake() failed: The TLS connection was non-properly terminated`。

判断：

- 仿真主机访问 GitHub 的 SSH key 或网络/TLS 环境未配置好，但局域网 SSH/SFTP 可用。

技巧：

- 在本机创建 bundle：
  `git bundle create %TEMP%/rehab_arm_feature.bundle feature/rehab-arm-ros2-architecture`
- 用 SFTP 上传到仿真主机 `/tmp/rehab_arm_feature.bundle`。
- 在仿真主机仓库中：
  `git fetch /tmp/rehab_arm_feature.bundle feature/rehab-arm-ros2-architecture`
  然后 checkout/fast-forward 到 `FETCH_HEAD`。

### 仿真主机能看到 topic 但 `/motor_state` 没样本时先查 `0x330~0x337`

现象：

- 仿真主机能发现 `/rehab_arm/motor_state`、`/joint_states`、`/rehab_arm/safety_state` 等 topic。
- `/rehab_arm/safety_state` 有样本，但 `/rehab_arm/motor_state` 和 `/joint_states` 等不到样本。
- 只读 candump 只看到 `0x321` 和 `0x322`。

判断：

- ROS2 DDS 已通，NanoPi bridge 已启动，M33 安全状态链路也通。
- 当前缺的是 M33 电机状态遥测帧；bridge 期望 `0x330~0x337`，8 字节，marker `0xB3`。

技巧：

- 用 `check_m33_motor_status_presence.py <candump> --pretty` 专门判断：
  `0x321/0x322` 是否存在、`0x330~0x337` 是否存在、只读检查中是否误发 `0x320`。
- 如果报告 `valid_m33_motor_status_count=0` 且 `target_0x320_count=0`，这是安全的“缺遥测”状态，不是运动链路故障。
- 先让 M33 固件补齐或打开 `0x330~0x337` 电机状态上报，再继续仿真主机 `/joint_states` 对齐。

### M33 有 stale 电机帧不等于真实电机反馈已回来

现象：

- M33 按 `0x330~0x334` 发布了 5 个电机状态槽位。
- payload 中 flags 带 `0x10` stale，NanoPi `/rehab_arm/motor_state` 能显示电机条目，但 `/joint_states` 不应该发布这些 stale 姿态。
- 被动 candump 看不到 3号 CANSimple `0x061/0x069`，也看不到 4~7号灵足 `0x180004FD~0x180007FD` 主动上报。

判断：

- ROS2、NanoPi、M33 状态链路可能是好的；真正缺的是电机侧原始反馈源。
- stale 帧只能证明 M33 的槽位表和 ROS 映射还活着，不能证明电机供电、CAN 分支、节点 ID 或驱动状态正确。

技巧：

- 用 `feedback_source_readiness <candump> --pretty` 同时看 raw motor feedback 和 M33 fresh/stale。
- `raw_motor_feedback_ready=false` 时，不要继续发轨迹或调 ROS parser，先查电机侧供电、共地、CANH/CANL、终端、电机 ID、驱动使能状态。
- `m33_joint_state_ready=false` 时，仿真主机不要期待 `/joint_states`；这可以避免把 0 rad 或 stale 姿态误当成真实机器人状态。
- 现场少敲命令时，用 `/home/pi/nanopi_motor_feedback_readiness.sh`；默认纯被动只读，`SEND_M33_HEARTBEAT=1` 只发一次 NanoPi 心跳，`RUN_NON_MOTION_PROBES=1` 才做非运动查询。

### `can0` ERROR-ACTIVE 但 candump 0 帧时不要继续调 ROS

现象：

- `ip -details -statistics link show can0` 显示 `ERROR-ACTIVE`，tx/rx error 都是 `0`。
- 被动 candump 0 帧。
- 发送一次 NanoPi heartbeat `0x321#55` 后，仍然没有 M33 `0x322` 或 `0x330~0x334`。

判断：

- NanoPi CAN 控制器本身健康，但总线上当前没有可见响应节点。
- 这不是 `/joint_states`、DDS、MuJoCo 或平台问题；优先查 M33 是否供电、是否运行到 CAN 任务、是否复位后没有启动、CAN 收发器是否使能。

技巧：

- 先运行 `/home/pi/nanopi_motor_feedback_readiness.sh`，再运行 `SEND_M33_HEARTBEAT=1 /home/pi/nanopi_motor_feedback_readiness.sh`。
- 如果第二个仍然 0 帧，暂停 ROS 轨迹开发，先恢复 M33 `0x322` 心跳回复。

更新 2026-06-03：

- NanoPi `can0` 可拉起到 `ERROR-ACTIVE`、1Mbps，MCP2518FD `dmesg` 初始化正常。
- 被动 `candump -L can0` 仍为 0 帧。
- 发送 M33 heartbeat `0x321` 只有 TX，没有 `0x322`，且 `TX errors/dropped`、`bus-off/re-started` 增加。
- 发送 7 号 EL05 非运动 stop/clear-fault 也只有 TX，没有 7 号 active-report 或 M33 `0x334`。
- 判断升级为：NanoPi CAN 控制器工作，但当前总线上没有任何在线节点 ACK/反馈，优先查 M33/电机侧供电、共地、CANH/CANL、终端、线束分支、收发器使能和驱动在线状态。
- 在恢复至少一个 ACK/反馈节点前，不要继续发 7 号 active-report、位置、速度、力矩或 ROS `0x320`。

### stale 电机槽位不能作为轨迹起点

现象：

- M33 可能持续发布 `0x330~0x334`，但 flags 里带 stale。
- 如果 NanoPi 把 stale 槽位写入 `/joint_states` 或用作 `current_positions`，仿真主机和规划器会以为机器人真实姿态已知。

判断：

- 康复外骨骼不能用“猜的当前位置”开始闭环运动。
- 正式链路必须先有 M33 `motion_allowed=true`，再有 fresh 电机反馈，才允许轨迹进入 bridge。

技巧：

- `psoc_can_bridge_node.py` 默认启用 `require_fresh_motor_status_for_trajectory=true`。
- 干跑或台架排查时可以临时关闭 fresh 闸门，但必须同时保持 `enable_target_tx=false`，只验证 ROS 消息流，不发 `0x320`。

### `0x321` 不能按 CANSimple 解析

现象：

- readiness 报告里出现 `cansimple_heartbeats_by_node: {"25": 1}`。
- 同一份 candump 里实际发送的是 NanoPi heartbeat `0x321`，不是 CANSimple 节点 25。

判断：

- 标准 ID `0x321` 按 CANSimple 拆分会得到 `node=25, cmd=1`，但在本项目中它是 NanoPi->M33 heartbeat。
- 工具不能只按位域猜协议，必须先排除项目保留 ID。

技巧：

- 在解析 CANSimple 前先排除 `0x320/0x321/0x322` 和 `0x330~0x337`。
- 现场 readiness 报告里只允许真实 `0x061/0x069` 计入 3号 CANSimple feedback。

### M33 `state=ok` 不等于允许 ROS 轨迹

现象：

- ROS bridge dry-run 能收到 `/joint_states`、`/rehab_arm/motor_state`、`/rehab_arm/safety_state`。
- 发布最小 `JointTrajectory` 后，bridge 拒绝：`PSoC motion_allowed is not true, protocol_version=2, state=ok, control_mode=bench_armed, detail=none`。

判断：

- 这是正确的 fail-closed 行为。NanoPi 不能用 `state=ok` 代替明确的 `motion_allowed=true`。
- 下一步应在 M33 安全状态机里定义何时置位 `motion_allowed`，而不是绕过 NanoPi gate。

技巧：

- 用 `enable_target_tx=false` 做 dry-run 轨迹验证，candump 必须保持 `0x320` 为空。
- 真机运动前必须同时满足 fresh 电机反馈和 M33 `motion_allowed=true`。

### 台架 `bench_armed` 只能显式 dry-run 放行

现象：

- M33 返回 `state=ok/control_mode=bench_armed/detail=none`。
- 默认 NanoPi bridge 仍拒绝轨迹。

判断：

- `bench_armed` 是开发台架状态，不是正式可穿戴状态。
- 为了继续验证 ROS 轨迹接口，可以显式设置 `allow_bench_motion_for_trajectory=true`，但应先保持 `enable_target_tx=false`。

技巧：

- 台架干跑命令必须同时包含：
  `-p enable_target_tx:=false -p allow_bench_motion_for_trajectory:=true`。
- 合格输出是 bridge 日志 `accepted ... trajectory points` 和 `DRY-RUN 320 ...`，同时 candump 中没有真实 `0x320`。
- 真实运动需要用户明确授权现场安全，不能把 dry-run 参数当成运动许可。

### 仿真主机密码登录不能用 Windows ssh 非交互传密码

现象：

- `ssh cal@192.168.2.46` 在 Windows 非交互命令里返回 `Permission denied (publickey,password)`。
- 本机没有 `sshpass`、`plink` 或 `Posh-SSH`。

判断：

- Windows 自带 OpenSSH 不适合在自动化脚本里直接传密码。
- 当前可用方案是 Python `paramiko`，后续更好的方案是在仿真主机配置 SSH key。

技巧：

- 临时自动化可以用 `paramiko.SSHClient().connect(..., password='1')` 跑 ROS 命令。
- 长期协作应把本机公钥加入 `cal@192.168.2.46:~/.ssh/authorized_keys`，避免每次靠密码。

### 跨机器 ROS dry-run 需要清理旧 bridge

现象：

- NanoPi 上残留多个 `psoc_can_bridge_node.py` 进程。
- 同一个 `/arm_controller/joint_trajectory` 可能被多个 bridge 订阅，导致日志混乱。

判断：

- 每次跨机器 dry-run 前只能保留一个 NanoPi bridge。

技巧：

- 测试前先执行 `pkill -f psoc_can_bridge_node.py || true`。
- 测试后也要清理 bridge 和 `candump -L can0,320:7FF`，避免后台进程影响下一轮。

### 官方 MuJoCo 远程 SSH/headless 渲染优先用 EGL

现象：

- 仿真主机通过 SSH 运行官方 MuJoCo Python 包时，默认 GLFW 渲染会因为没有图形桌面报 `DISPLAY environment variable is missing`。
- `osmesa` 只有系统装好 OSMesa 相关库才可用。

判断：

- 这不是 MuJoCo 安装失败，也不应该退回旧 `mujoco-py`。
- 本项目仿真主机使用官方 `mujoco` Python 包，headless 渲染统一走 `MUJOCO_GL=egl`。

技巧：

- 安装命令：`python3 -m pip install --user --break-system-packages mujoco`。
- 在仿真主机 `~/.rehab_arm_ros2_network` 里固定：`export MUJOCO_GL=egl`。
- 验证命令：`ros2 run rehab_arm_sim_mujoco check_sim_env.py --strict-mujoco --pretty`，通过标准是 `readiness=ready_with_mujoco`、`checks.mujoco.ok=true`、`errors=[]`。
- 当前已在 `cal@192.168.2.46` 验证官方 `mujoco 3.9.0` 可导入、可 `mj_step`，并能用 EGL 渲染非空 RGB 帧。
- 临时 smoke 脚本如果创建 `mujoco.GLContext`/`mujoco.Renderer` 后不显式关闭，Python 退出时可能打印 EGL 析构 warning；正式仿真/采集代码应显式释放 renderer/context，避免日志误判。

### 第一版 MuJoCo actuator 动力学不稳定时先退到限速运动学

现象：

- 最小 MJCF 使用 MuJoCo position actuator 后，节点日志出现 `Nan, Inf or huge value in QACC`。
- `/joint_states` 中部分旋转关节冲出配置限位，不能作为康复机械臂仿真基线。

判断：

- 这是仿真模型/执行器参数不成熟，不是 ROS topic 合同问题。
- 穿戴式康复机械臂主线优先要稳定、可标注、限位一致的数据流；真实执行器动力学可以在 URDF/MJCF、质量、阻尼和 actuator 参数明确后再逐步加。

技巧：

- 第一版 `rehab_arm_sim_mujoco.mujoco_backend` 使用 MuJoCo model + `mj_forward`，但关节推进由代码按 `joints.yaml` 同款限速/限位做 kinematic step。
- 合格标准：节点日志包含 `backend=mujoco-model`，发布 `JointTrajectory` 后 `/joint_states` 到达目标附近，且没有 `Nan, Inf or huge value`。
- 后续引入真实 actuator 前，必须先写测试或短时验证，确认关节不会越限、不会爆速度。

### MuJoCo 模型要通过 package share 或 `model_path` 替换

现象：

- 如果 MJCF 只写死在 Python 代码里，后续导入真实 URDF/MJCF/mesh 时必须改节点代码，容易污染仿真逻辑。

判断：

- 正规机器人仿真流程应该把模型当资源资产管理，节点只负责加载模型、订阅轨迹、发布状态。

技巧：

- 默认模型文件：`rehab_arm_sim_mujoco/models/rehab_arm_minimal.xml`。
- 安装后位置：`install/rehab_arm_sim_mujoco/share/rehab_arm_sim_mujoco/models/rehab_arm_minimal.xml`。
- 临时替换模型：`ros2 run rehab_arm_sim_mujoco mujoco_sim_node.py --ros-args -p model_path:=/absolute/path/to/model.xml`。
- 如果 `model_path` 指向不存在的文件，后端会退回内置最小模型；正式验证时要确认日志和安装路径，避免误以为加载了真实模型。

### 远程运动测试不要让 CAN 全量日志堵住 SSH

现象：

- NanoPi 远程执行 `nanopi_can_master.py ... --wait 2.2` 时，命令没有正常返回。
- `ps -ef` 能看到残留的远程 `bash -lc ... m33 target ...` 进程。
- `can0` 本身仍是 `ERROR-ACTIVE`，不是总线故障。

判断：

- `nanopi_can_master.py` 在 `--wait > 0` 时会打印等待窗口内收到的 CAN 帧；总线周期状态帧较多时，SSH stdout 管道可能被填满，导致远程命令卡住。
- 这会污染下一轮测试，必须先清掉残留进程，再继续发任何运动命令。

技巧：

- 远程真实运动测试优先使用 `--wait 0` 只发送命令。
- 需要证据时单独启动带过滤器的 `candump -L`，例如只抓 `0x320/0x322/0x331`。
- 发现卡住后先执行 `pkill -f nanopi_can_master.py || true`，再确认 `ps` 无残留、`can0` 仍 `ERROR-ACTIVE`。

### `limit_cur` 不等于电流命令

现象：

- 5号电机速度模式下写入 `limit_cur(0x7018)=3.0A` 后，电源电流仍约 `0.1A`。
- 电机只动小角度就卡住，继续提高限流没有明显出力改善。

判断：

- `0x7018 limit_cur` 只是允许的电流上限，不会强制电机输出该电流。
- MIT `torque` 前馈帧也不等同于厂家官方 current mode；如果没有正确 run mode 或电流参考，电源电流可能仍然上不去。
- 真正 current-mode 验证应按厂家协议写 `run_mode(0x7005)` 和 `iq_ref(0x7006)`，并确认当前型号的 run mode 编号。

技巧：

- 不要在速度模式里盲目继续加 `limit_cur`。
- 先补软件工具：读回 `run_mode/limit_cur/limit_spd`，解码 active-report 中的实际电流/力矩。
- current-mode 阶跃要从很小电流开始，每步 1~2 秒，并准备立即 stop/disable。

### 纯 current mode 不适合做目标运动控制

现象：

- motor5 使用 `run_mode=3`、`iq_ref=-0.5A/-0.7A` 可以动。
- 空载时速度体感偏快；一给阻力又容易不动。

判断：

- current mode 是固定电流/力矩倾向，不负责目标角度和目标速度。
- 机器人关节更适合先给目标位置/速度约束，再用驱动内部闭环在电流上限内补偿阻力。

技巧：

- RobStride/Lingzu 台架调试优先使用官方 CSP：`run_mode=5`、`limit_cur(0x7018)`、`limit_spd(0x7017)`、`loc_ref(0x7016)`。
- `nanopi_can_master.py private csp` 已封装这条调试路径；默认 `--hold` 后自动 stop。
- 如果需要观察保持目标，必须显式加 `--leave-enabled`，并且只允许非穿戴台架有人值守时使用。

### CSP stop 前先慢速回收

现象：

- CSP 目标动作结束后直接 stop，电机会立刻退出保持/卸力。
- 对机器人关节调试来说，这种“突然卸力”体感不好，也不利于形成正式运动流程。

判断：

- 更合理的台架动作是：目标位置保持一段时间，然后低速回收到安全位置，最后 stop。
- 但回收位置不能默认假设为机械零点；不同装配/患者限位下，错误回零本身可能危险。

技巧：

- 使用 `private csp --return-deg <angle> --return-spd <rad_s> --return-hold <seconds>`。
- 建议先用小角度和低回收速度，例如 `--return-deg 0 --return-spd 0.05 --return-hold 8`。
- 正式 M33 安全状态机也应采用“受限回收/停止流程”，而不是任何状态下立即卸力。

### 不要把外部调试电机 7 号写进机械臂映射

现象：

- 早期文档和台架工具曾把 `motor_id=7` 放进 5 关节示例映射。
- 当前机械臂实物口径已更新：7 号没有装在机械臂上，只是外部调试电机。

判断：

- MuJoCo、VLA、患者 profile、M33 正式关节映射和服务器状态语义都不能再把 `motor_id=7` 当作机械臂关节。
- 当前 `medical_arm.zip` 6 关节映射草案应以 `docs/JOINT_MOTOR_MAPPING_DRAFT.md` 为准。

技巧：

- 后续 AI 或脚本如果看到旧的 `forearm_rotation_joint -> motor_id=7`，必须当作历史台架示例，不得迁移到正式机械臂。
- 真实机械臂腕部是后加 4015 小电机 `motor_id=1/2`，但两个电机分别对应 `wanbu_zongxiang_joint` 或 `wanbu_hengxiang_joint` 还未确认，不能提前写死。
- 7 号是 EL05，可以临时作为 MuJoCo shadow/台架 demo actuator 验证数据流；但必须标为 `temporary_mujoco_shadow_and_external_bench_only`。

### RobStride 的 `gear_ratio=1.0` 才是当前关节命令换算

现象：

- 用户纠正：4/5/6/7 的 RobStride CSP 当前 formal path 使用 `gear_ratio=1.0` 是对的。
- 早先把 RS00/EL05 的 `10:1/9:1` 作为当前关节目标换算依据，会导致重复乘减速比、目标角被放大。

根因：

- 伺泰威 CANSimple/ODrive-like 和灵足 RobStride CSP 的命令单位不同。
- 3 号伺泰威走电机协议侧 rev 单位，需要按减速/协议比例换算。
- 4/5/6/7 RobStride CSP 的 `loc_ref` 在当前 M33 formal path 中按输出端 joint rad 使用，因此当前关节命令比例应保持 `1.0`。
- RS00/EL05 的 `10:1/9:1` 是驱动内部型号资料和诊断上下文，不应再乘到 `loc_ref` 关节目标上。

解决：

- `motor_profiles.py` 使用 `joint_command_ratio` 表示当前 formal/shadow 关节目标换算比例。
- 4/5/6/7 的 `joint_command_ratio=1.0`；3 号伺泰威的 `joint_command_ratio=48.0`。
- RS00/EL05 的内部减速信息改用 `drive_internal_reduction_ratio` 记录，避免误认为正式关节换算比例。
- 7 号标记为 `temporary_mujoco_shadow_and_external_bench_only`，允许做 MuJoCo shadow/demo actuator，不进入 medical_arm 6DOF 正式映射。

技巧：

- 后续看电机表时，控制换算先看 `joint_command_ratio` 和 `command_position_semantics`。
- `drive_internal_reduction_ratio` 只用于型号资料、诊断和解释驱动内部结构，不用于额外倍乘 RobStride CSP `loc_ref`。
- 不要把 7 号 EL05 的台架 shadow 结论迁移成 medical_arm 正式关节映射；也不要把伺泰威 3 号的 CANSimple 换算规则套到 RobStride。

### 不要把 demo/smoke/fallback 当主线 readiness

现象：

- 仓库里存在多个带 `demo`、`smoke`、`synthetic`、`bench`、`fallback` 语义的入口。
- 旧 `demo_trajectory_node.py` 会发布 5 关节 `/arm_controller/joint_trajectory`，早期 README 曾把它放在 Real NanoPi Bridge 后面作为示例。
- 当前 6 关节 `medical_arm.zip` 模型使用 `jian_hengxiang_joint`、`jian_zongxiang_joint`、`jian_xuanzhuan_joint`、`zhou_zongxiang_joint`、`wanbu_zongxiang_joint`、`wanbu_hengxiang_joint`，与旧 5 关节 bridge 不一致。

判断：

- demo 只证明 topic 或数据工具能跑，不证明 6 关节机械臂、M33 映射、真实限位或 VLA planner 正确。
- synthetic/smoke telemetry 可以验证 recorder 和 parser，但不能被当成 fresh motor feedback。
- fallback 仿真可以验证 ROS 节点合同，但不能称为真实 MuJoCo 模型验证。

技巧：

- 每次启动节点前先分类：`mainline`、`shadow-sim`、`dry-run`、`bench-debug`、`offline-demo`。
- 分类不清时按 `offline-demo` 或只读处理。
- `demo_trajectory_node.py` 不得作为 6 关节主线 planner，不得作为真机正常测试入口。
- 对真实 NanoPi/M33，先做只读状态，再做 `enable_target_tx=false` dry-run；任何 `0x320` 必须用 candump 单独证明没有发出或经过明确安全审查。

### 有 M33 motor status 不等于可以期待 `/joint_states`

现象：

- NanoPi `can0` 已经是 1Mbps `ERROR-ACTIVE`，能抓到 `0x330~0x334` 周期帧。
- `check_m33_motor_status_presence.py` 显示 `valid_m33_motor_status_count=570`。
- 但 `fresh_m33_motor_status_count=0`、`stale_m33_motor_status_count=570`，仿真主机和 NanoPi 都没有稳定 `/joint_states` 样本。

判断：

- 当前电机未接或真实原始电机反馈不存在，M33 发送的是 stale 状态槽位。
- `psoc_can_bridge_node.py` 会发布 `/rehab_arm/motor_state` 供诊断，但会过滤 stale 数据，不发布 `/joint_states`。
- 这不是 DDS 或 bridge 故障，而是安全门控正确生效。

技巧：

- 用 `feedback_source_readiness.py <candump>` 看 `safe_to_expect_joint_states`。
- 当输出 `safe_to_expect_joint_states=false` 时，不要关闭 `require_fresh_motor_status_for_trajectory` 来“凑出”运动链路。
- 当前正确下一步是接入真实电机反馈或修正 M33 fresh/stale 语义，再观察 `/joint_states`。

### `bench_armed` 和 fresh feedback 是两道不同的门

现象：

- 默认参数下，仿真主机发布一条测试 `JointTrajectory`，NanoPi bridge 拒绝：
  `PSoC motion_allowed is not true, protocol_version=2, state=ok, control_mode=bench_armed, detail=none`。
- 临时设置 `allow_bench_motion_for_trajectory:=true` 后，bridge 仍拒绝：
  `no fresh M33 motor feedback received`。
- 两轮 candump 都显示 `0x320=0`。

判断：

- `bench_armed` 不是正式穿戴运动许可，默认必须拒绝。
- 即使为了台架 dry-run 显式允许 `bench_armed`，fresh feedback gate 仍会阻止没有真实反馈的轨迹进入发送队列。

技巧：

- 调试时不要一次关闭多道门。先看是 PSoC/M33 motion gate 拒绝，还是 fresh feedback gate 拒绝。
- 任何台架参数放宽都必须保持 `enable_target_tx=false`，直到单独安全审查通过。

### M55 TFLM 能跑不等于 CAN 全链路已通

现象：

- 上电后 `req_m7` 可以返回：M33 发 motor7 snapshot，M55 收到 snapshot，真实 TFLM wake slot 加载并推理，M55 结果回到 M33。
- 同一窗口里 M33 仍打印 `m55_model_bridge ... can_ret=-255`。
- M33 CAN 日志反复出现 `direct tx pending ... psr=0x0000077b txbto=0x00000000`。
- NanoPi `can0` 是 1Mbps `ERROR-ACTIVE`，但 `candump` 看不到 `0x322/0x323/0x330~0x334`，RX packets 为 0，TX errors 很高。

判断：

- M33/M55 IPC、M55 小模型部署、M55->M33 结果回传已经过硬件验证。
- 当前失败边界在 CAN 总线完成发送/ACK 之前，不在 VLA、ROS、MuJoCo 或 TFLM。
- `txbrp` 长时间 pending 且 `txbto=0`，同时 NanoPi 自己发 `cansend` 也没有任何 RX/ACK，是典型 CAN 物理层或收发器未使能问题。

排查顺序：

- 确认 M33、NanoPi CAN 模块、电机 7/外部节点确实接在同一对 CANH/CANL 上。
- 确认所有 CAN 节点共地。
- 断电测 CANH/CANL 之间电阻：两端终端约 60 ohm，单端约 120 ohm，开路或过低都先修硬件。
- 上电测收发器 VCC/VIO/STBY/EN/TXD/RXD；TXD 有跳变但 CANH/CANL 没有时，优先查收发器供电和 standby/enable。
- 确认 CANH/CANL 没接反。显性位时 CANH 应上升、CANL 应下降。
- 修复后先用 `timeout 5 candump -L can0` 看到任意帧，再测 `0x321 -> 0x322`，最后才测 `req_m7 -> 0x323`。

技巧：

- 不要因为 M55 模型输出正常就跳过 CAN 物理层。当前医疗臂主线仍要求 `M55 -> M33 -> CAN -> NanoPi -> ROS` 状态闭环。
- NanoPi 只读 service 在线只说明 ROS bridge 进程在跑；没有 `candump` 帧时，先查 CAN，不查 MuJoCo。
- M33 的 `drv_can.c` 已加入 pending buffer 取消和寄存器日志，后续看到 `psr/txbrp/txbto/txbcf` 时要和 NanoPi `ip -details -statistics link show can0` 一起看。

状态更新：

- 2026-06-04 后续复测已恢复。通过标准是 NanoPi RX packets 增长、TX/RX errors 为 0、`candump` 可见 `0x330~0x334`、`0x321 -> 0x322`、`req_m7` 后可见 `0x323#B5...`。
- 恢复后继续验证 ROS 层：`/joint_states` 应有 `forearm_rotation_joint`，`/rehab_arm/model_state` 是事件型 topic，必须先启动 `ros2 topic echo --once` 再触发 `req_m7`，否则容易错过单帧事件。
- MuJoCo shadow 验收看 `/sim/medical_arm/joint_states`，必须是 6 个 medical arm joint；安全验收仍要求 `candump can0,320:7FF` 无输出。
- 脚本化验收优先用现有 `/home/pi/nanopi_motor_feedback_readiness.sh`。如果它显示 `missing_lingzu_motors: [4,5,6]` 但 `raw_motor_feedback_ready=true`、`m33_joint_state_ready=true`，这表示当前只有 7 号 bench 电机在线，不是 ROS/MuJoCo 故障。

### 6DOF MuJoCo shadow 要发布完整关节，但不能伪造硬件在线

现象：

- 只有外部 7 号 EL05 接入时，NanoPi `/joint_states` 当前只发布 legacy `forearm_rotation_joint`。
- MuJoCo medical_arm 6DOF 模型需要 6 个目标关节：`jian_hengxiang_joint`、`jian_zongxiang_joint`、`jian_xuanzhuan_joint`、`zhou_zongxiang_joint`、`wanbu_zongxiang_joint`、`wanbu_hengxiang_joint`。

判断：

- 为了让 MuJoCo 主线始终看到完整 6 关节 trajectory，relay 可以给未接关节发布明确占位角。
- 这不是 fresh hardware feedback，不能写成真实电机已接入，也不能绕过 NanoPi/M33 的真机安全门。

解决：

- `medical_arm_shadow_relay_node.py` 默认 `publish_full_target=true`。
- 当前只把 `forearm_rotation_joint -> jian_xuanzhuan_joint` 作为真实来源映射，其他关节来自 `placeholder_positions_json`。
- 后续每接入一个真实电机，先让 NanoPi `/joint_states` 发布输出端关节，再把对应 source->target 补进 `joint_map_json`。

技巧：

- 验证主线时看 `/sim/medical_arm/joint_trajectory` 是否包含 6 个 joint，而不是只看某一个关节是否动。
- 文档和日志必须区分 `mapped live joint` 与 `placeholder joint`。
- 在有 ROS 环境的机器上，`trajectory.points[0].positions` 可能是 `array('d')`；单测断言时用 `list(...)`，兼容本地 fallback 和真实 ROS message。

### M33 对上状态要分 legacy 槽位和 medical_arm 6DOF

现象：

- M33 当前 `0x330~0x334` 是 legacy 5 槽位，ROS joint `0..4` 当前映射到 motor slot `3/4/5/6/7`。
- medical_arm MuJoCo 是 6 个 joint，走 `/sim/medical_arm/*` shadow topic。
- 7 号外部 EL05 可以让 `0x334 -> /joint_states forearm_rotation_joint -> jian_xuanzhuan_joint` 链路跑通。

判断：

- 这说明 M33/NanoPi/MuJoCo 的 shadow 数据流已通，但不等于 M33 已经有完整 medical_arm 6DOF 正式协议。
- 后续每个真实关节必须分别证明：M33 fresh 状态、NanoPi 输出端 joint state、MuJoCo target 映射、方向/零点/传动比、M33 安全限位。

技巧：

- 教程和日志里用“7 号外部电机 shadow 已对上”，不要写“6DOF 真机已对上”。
- 只读/hardware shadow 阶段不能出现 `0x320`；只有单独进入 7 号小幅台架测试时才允许抓到 `0x320`。
- 上电联调按 `docs/M33_NANOPI_MUJOCO_POWERON_TEST_GUIDE.md` 分层执行，失败时停在当前层，不跨层排错。

### 产品自启动服务只能自动状态上报，不能自动运动

现象：

- 真实产品上电后应自动启动，不应依赖 SSH 手动运行 `ros2 run ...`。
- 但如果把 `enable_target_tx=true` 写进 systemd，开机后任何上游误发布轨迹都可能变成真实 `0x320`。

判断：

- 上电自启动应先产品化“只读状态服务”和“安全状态发布”，不是产品化“自动运动”。
- 当前 NanoPi systemd 模板固定 `enable_target_tx=false`，只负责 M33/CAN 到 ROS2 状态上报。
- 仿真主机 hardware shadow 自启动是研发模式，不是产品必须服务。

技巧：

- 检查产品服务时先看 `journalctl -u rehab-arm-nanopi-readonly.service`，日志必须包含 `enable_target_tx=False`。
- 自启动验收时同时运行 `candump can0,320:7FF`，普通上电状态下必须没有 `0x320`。
- 后续要做真实运动授权，应新增单独的运动授权状态机，不要直接改只读 service。

### NanoPi systemd 应由 root 配 CAN、普通用户跑 ROS2

现象：

- 手动以 `pi` 用户运行 `ros2 run rehab_arm_psoc_bridge psoc_can_bridge_node.py ... enable_target_tx:=false` 可以发布 `/rehab_arm/motor_state` 和 `/joint_states`。
- 直接让 systemd/root 跑完整 ROS2 bridge 时，容易遇到 ROS2 日志目录、DDS 用户环境或 rclpy logging 相关问题。
- 把 service 改成 `User=pi` 后，如果启动脚本仍调用普通 `sudo mkdir/chmod/ip link`，又会报 `sudo: a terminal is required to read the password`。

判断：

- SocketCAN 初始化需要 root 权限；ROS2 bridge 更适合使用和手动调试一致的 `pi` 用户环境。
- 这两个职责应拆开，不要让一个脚本在 systemd 非交互环境里临时 sudo。

解决：

- `rehab-arm-nanopi-readonly.service` 使用 `ExecStartPre=+/usr/local/bin/setup_nanopi_can.sh`，加号表示该预启动步骤以 root 权限运行。
- service 主进程使用 `User=pi`，并设置 `Environment=SKIP_SOCKETCAN_SETUP=1`。
- `start_nanopi_product_readonly.sh` 只创建 `/home/pi/.ros/log`，不再用 sudo 创建 ROS 日志目录；所有 root CAN 工作都交给 `setup_nanopi_can.sh`。

技巧：

- 验收先看 `systemctl is-active rehab-arm-nanopi-readonly.service` 和 `journalctl -u rehab-arm-nanopi-readonly.service -n 80 --no-pager`。
- service 日志里应能看到 ROS bridge 参数 `enable_target_tx:=false`。
- 再用 `ros2 topic echo --once /rehab_arm/motor_state`、`ros2 topic echo --once /joint_states`、`timeout 2 candump -L can0,320:7FF` 做状态和无运动帧确认。

### MCP2518FD 上电后可能需要重载驱动

现象：

- NanoPi 上电后 `can0` 不存在。
- `dmesg` 出现 `mcp251xfd spi3.0: Failed to detect MCP2518FD`。
- 重载驱动后 `can0` 出现，并可配置为 1Mbps `ERROR-ACTIVE`。

判断：

- 这是 SPI/CAN 控制器上电探测层的问题，不是 ROS2、M33 协议或 MuJoCo 问题。
- 没有 `can0` 时不要继续排 ROS topic 或 VLA。

解决：

```bash
sudo modprobe -r mcp251xfd
sudo modprobe mcp251xfd
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 1000000 restart-ms 100 berr-reporting on
sudo ip link set can0 up
ip -details -statistics link show can0
```

当前产品自启动模板已把这段恢复逻辑收敛到 `deploy/scripts/setup_nanopi_can.sh`。

技巧：

- `can0 ERROR-ACTIVE` 且 `berr-counter tx 0 rx 0` 只是控制器健康；还要继续验证 M33 heartbeat 和 fresh motor feedback。
- 只有看到 `0x321 -> 0x322`、`0x330~0x334`、必要时 7 号 `0x180007FD -> 0x334 fresh`，才说明链路到了 M33/电机反馈层。

### MuJoCo JointState 的数组长度必须跟当前 profile 一致

现象：

- `medical_arm_6dof` shadow 输出 6 个 `name/position/velocity`，但 `effort` 只有 5 个元素。

判断：

- 节点仍用旧 5DOF `JOINT_NAMES` 常量生成 effort，而不是按当前 `self.joint_names`。
- 这不会发真机运动，但会污染 ROS message 合同，后续记录器、服务器或 VLA 解析可能出错。

解决：

- `mujoco_sim_node.py` 使用 `msg.effort = [0.0] * len(self.joint_names)`。
- `test_mujoco_backend.py` 增加静态合同，防止回退到旧 5DOF 常量。

技巧：

- 每次新增 profile 时检查 `/sim/medical_arm/joint_states` 的 `name/position/velocity/effort` 长度一致。

### 电机直连 CAN 可见不等于 M33 主线已通

现象：

- NanoPi `candump` 能看到 3 号 CANSimple `0x061/0x069`。
- NanoPi 直接发送私有协议 active-report 后，4/5/6 能回 `0x180004FD/0x180005FD/0x180006FD`。
- 但 NanoPi `heartbeat 0x321` 没有收到 M33 `0x322`，也没有 M33 聚合状态 `0x330~0x334`。
- ROS `/rehab_arm/safety_state` 显示 `limited`，detail 类似 `no PSoC status after ... heartbeats`。

判断：

- 这说明电机 CAN 物理层和若干电机节点在线，但 M33 当前没有作为主站把状态聚合到 NanoPi。
- 不能把“电机直连能看到反馈”写成“正式 `M33 -> NanoPi -> ROS -> MuJoCo` 已打通”。

解决：

- 先保留 direct CAN 结果作为电机接线证明。
- 下一步查 M33 是否上电、M33 CAN 线是否接到同一总线、M33 固件是否运行当前 CAN 聚合任务、M33 收发器 enable/standby 是否正确。
- 只有同时看到 `0x321 -> 0x322` 和 `0x330~0x334`，才继续期待 `/joint_states`、MuJoCo hardware shadow 或 VLA 使用这些关节。

状态：

- 2026-06-08 实测：3/4/5/6 电机 CAN 层可见；7 号未见反馈；M33 主线未回 `0x322/0x330~0x334`。
- 2026-06-08 用户发现此前缺少共地；共地修正后复测仍没有 M33 `0x322/0x330~0x334`，说明共地是必要条件但当前还不是唯一问题。继续查 M33 供电、固件是否运行、CANH/CANL 是否接在同一 bus、M33 CAN 收发器 EN/STBY、终端电阻和接口方向。
- 2026-06-08 后续复测已恢复 M33 主线：`0x321 -> 0x322` 和 `0x330~0x334` 可见；4/5/6 开 active-report 后分别进入 M33 fresh aggregate slot `0x331/0x332/0x333`，ROS `/joint_states` 发布 4 个 legacy joints。7 号仍 stale。

### PowerShell 远程 SSH 命令里的 `$变量` 会被本地提前展开

现象：

- 从 Windows PowerShell 执行双引号包裹的 SSH 命令：

```powershell
ssh pi@192.168.2.66 "for m in 4 5 6 7; do ... $m ...; done"
```

- 远端实际收到的 `$m/$DUMP/$id` 为空，导致命令变成 `--motor` 空值或 `grep -c " #"`，脚本可能卡住。

解决：

- PowerShell 侧用单引号包裹远端脚本，或显式转义 `$`。
- 长命令尽量拆成可独立验证的小步骤，不要把后台 `candump`、循环发命令、统计 grep 全塞进一个未验证的远程一行。

状态：

- 2026-06-08 已踩到一次；清理残留进程后改用 PowerShell 单引号重跑，成功完成 4/5/6/7 active-report 检查。

### MSH_CMD_EXPORT 的描述文本不要带逗号或分号

现象：

- M55 `wifi` 工程新增 shell 命令后，第一次 `scons` 编译失败。
- 失败点出现在 `MSH_CMD_EXPORT(...)` 展开附近，同时 `atol` 未声明。

判断：

- RT-Thread 的 `MSH_CMD_EXPORT(command, desc)` 宏描述参数应保持简单文本；描述里放逗号、分号容易被宏展开解析成异常 token。
- 命令参数解析使用 `atol` 时必须包含 `<stdlib.h>`。

解决：

- `official_voice_service.c` 添加 `<stdlib.h>`。
- 把命令描述改成简单英文句子，不在 `MSH_CMD_EXPORT` 的第二个参数里放逗号或分号。

状态：

- 2026-06-09 已修复，`wifi` 工程 `scons -j4` 通过；同步到 GitHub `M55` 分支 commit `3ed3c09`。

### LLM API key 只能放服务器环境变量，不能给 NanoPi/M55/App

现象：

- 设备总控台需要把语音、摄像头、肌电/电机摘要送到大语言模型，但 NanoPi/M55/App 都不应该持有模型 API key。

判断：

- 正确边界是 `NanoPi/App/浏览器 -> 平台 API -> 大模型 provider`。
- 平台只返回高层建议、模型状态建议、dry-run 轨迹候选；M33 仍是最终安全权限。

解决：

- 平台 `rehab_arm` 模块使用服务端环境变量配置 OpenAI-compatible relay：
  - `REHAB_ARM_MODEL_RELAY_BASE_URL`
  - `REHAB_ARM_MODEL_RELAY_MODEL`
  - `REHAB_ARM_MODEL_RELAY_API_KEY`
  - `REHAB_ARM_MODEL_RELAY_EXTERNAL_ENABLED=true`
- API 响应必须保持 `api_key_exposed_to_device=false`。
- 返回内容若包含 `can_frame`、`motor_current`、`motor_torque`、`raw_motor_position`、`raw_motor_velocity`、`m33_safety_override`、`direct_motor_command` 等字段，必须阻断或降级为安全外壳。

状态：

- 2026-06-09 平台后端测试已覆盖：外部 provider 成功、provider 低层输出被拦截、API key 不回传。

### M55 有 PDM/I2S 源码不代表 `mic0/sound0` 已注册

现象：

- M55 烧录新 `official_voice_service` 后，`voice_pipeline_status` 命令存在。
- 但执行 `pdm_mic_self_test 3` 打印 `[official_voice] mic0 not found`。
- 执行 `official_voice_speaker_test 1` 打印 `[official_voice] sound0 not found`。

判断：

- `libraries/HAL_Drivers/drv_pdm.c` 和 `drv_i2s.c` 在工程里存在，但 SCons 只有在 `BSP_USING_AUDIO` 打开时才编译它们。
- 仅有 `RT_USING_AUDIO` 只能启用 RT-Thread audio 框架，不能自动注册板级 `mic0/sound0`。
- M55 的 `.config` 和 `rtconfig.h` 都要同步；只改 `.config` 时，旧 `rtconfig.h` 会让 SCons 继续跳过驱动。

解决：

- M55 分支打开：
  - `CONFIG_BSP_USING_AUDIO=y`
  - `CONFIG_BSP_USING_AUDIO_PLAY=y`
  - `CONFIG_BSP_USING_AUDIO_RECORD=y`
  - `CONFIG_ENABLE_STEREO_INPUT_FEED=y`
- `rtconfig.h` 同步定义：
  - `BSP_USING_AUDIO`
  - `BSP_USING_AUDIO_PLAY`
  - `BSP_USING_AUDIO_RECORD`
  - `ENABLE_STEREO_INPUT_FEED`
- 清理旧 `build`、`rt-thread.elf`、`rtthread.hex`、`rtthread.map` 后重编，确认日志里出现 `drv_i2s.o`、`drv_pdm.o`、`drv_es8388.o`。
- 重新烧录后执行 `list device`，必须看到 `mic0 Sound Device` 和 `sound0 Sound Device`。

状态：

- 2026-06-09 已上板验证：`pdm_mic_self_test 3`、`official_voice_speaker_test 1`、`local_voice_listen 5` 均返回 `ret=0`，并且语音活动结果经 `0x323` 到 NanoPi `/rehab_arm/model_state`。

### M55 外部 flash 烧录要选 `cat1d.cm33` target 并 halt

现象：

- M55 `rtthread.hex` 起始地址正确为 `0x60580400`，OpenOCD `flash banks` 也列出 `cat1d.cm33.smif1_ns`。
- 直接执行 `flash write_image erase ... rtthread.hex` 或显式 binary 地址仍打印 `Warn : no flash bank found for address 0x60580400`，随后 `wrote 0 bytes`。
- 改成 `targets cat1d.cm33` 后能找到 bank，但如果没有 `reset init`，会失败为 `Target not halted` / `failed erasing sectors ...`。

判断：

- PSE84 的 SMIF flash bank 挂在 `cat1d.cm33` 下；即使 `ENABLE_CM55=1` 且 OpenOCD 检测到 CM55，当前 active target 不是 `cat1d.cm33` 时，`flash write_image` 仍可能找不到对应 bank。
- `0x60580400` 不是 4 KB 对齐地址，OpenOCD 会自动向前 padding 到 `0x60580000`；这是正常提示，不是失败条件。

解决：

```powershell
$env:PATH='D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin;' + $env:PATH
arm-none-eabi-objcopy -I ihex -O binary D:\RT-ThreadStudio\workspace\wifi\rtthread.hex D:\RT-ThreadStudio\workspace\wifi\rtthread_m55.bin

& 'D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin\openocd.exe' `
  -s 'D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/scripts' `
  -s 'D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/flm/cypress/cat1d' `
  -s 'D:/RT-ThreadStudio/workspace/wifi/libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource' `
  -c 'set QSPI_FLASHLOADER D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/flm/cypress/cat1d/PSE84_SMIF.FLM' `
  -c 'set ENABLE_CM55 1' `
  -f interface/kitprog3.cfg `
  -f target/infineon/pse84xgxs2.cfg `
  -c 'transport select swd' `
  -c 'init; reset init; targets cat1d.cm33; flash banks; flash write_image erase D:/RT-ThreadStudio/workspace/wifi/rtthread_m55.bin 0x60580400 bin; verify_image D:/RT-ThreadStudio/workspace/wifi/rtthread_m55.bin 0x60580400 bin; reset run; shutdown'
```

状态：

- 2026-06-09 已用该流程烧录 M55：`wrote 1200128 bytes`，`verified 1196292 bytes`。
- OpenOCD 退出阶段可能仍打印 KitProg3 acquire 噪声；是否成功以非 0 写入量和 verify 字节数为准。

### M55 voice activity must be calibrated before treating confidence as meaningful

现象：

- 默认阈值 `peak=1200 avg_abs=70 streak=3` 在一次现场测试中没有触发 `local_voice_listen 4`，但降低到 `voice_thresholds 300 80 3` 后能触发并发出 `0x323`。
- 静音校准窗口 `voice_calibrate 2` 观察到 `peak=879 avg_abs=357`，建议 `voice_thresholds 1518 555 3`。

判断：

- 当前实现是 PDM activity detector，不是最终 wake word/ASR 模型；`confidence` 只表示当前阈值下的活动强度，不代表语义可信度。
- 用低阈值验证出口可以接受，但不能作为正式唤醒配置留在现场。

解决：

- 每次换环境、换麦克风位置或重启后，先安静执行 `voice_calibrate 2`，按建议执行 `voice_thresholds <peak> <avg_abs> <streak>`。
- 验证出口时可临时降低阈值触发一次；验证后调回校准值或重启。
- 下一阶段应迁移官方 local voice 的 wake/command model 或项目自训 int8 模型，仍通过 `M55 -> M33 -> CAN 0x323 -> NanoPi /rehab_arm/model_state` 输出。

状态：

- 2026-06-09 已验证低阈值触发后，M55 串口打印 `publish_ret=0`、`can_ret=0`，NanoPi CAN 抓到 `0x323`，ROS `/rehab_arm/model_state` 收到 `suggestion_only=true` 的 JSON。

### M33 non-secure hex must be relocated before external-flash burn

现象：

- M33 build output `Debug/rtthread.hex` starts at `0x08340400`.
- Burning that address directly to external flash is wrong for this board setup; OpenOCD needs the programmable external-flash alias around `0x60340400`.
- The existing post-build also prints `arm-none-eabi-objcopy: interleave must be positive`; make ignores it, so a successful build does not prove the hex is relocated.

判断：

- The non-secure runtime alias `0x08340400` must be relocated with EdgeProtectTools region mapping `0x08000000 -> 0x60000000`.
- Keep a raw hex and a relocated hex separate; do not overwrite the raw build artifact during debugging.

解决：

- Generate raw hex from ELF:

```powershell
arm-none-eabi-objcopy -O ihex D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread.elf D:\RT-ThreadStudio\workspace\yiliao_m33\Debug\rtthread_raw.hex
```

- Run EdgeProtectTools `hex-relocate` into `Debug\rtthread_relocated.hex`.
- Verify the relocated file starts with `:020000046034...`.
- Burn `rtthread_relocated.hex`; the 2026-06-09 validation wrote `569344 bytes` and verified `565512 bytes`.

状态：

- 已验证。OpenOCD shutdown 阶段可能仍有 KitProg3 acquire 噪声，成功判据是非 0 write 和 verify 字节数。

### COM26 FINSH shell can drop characters under heavy log output

现象：

- Sending long M55 shell commands like `official_voice_map_id 401 880` through COM26 sometimes arrived as `oficial_voie_map_id 40 880`.
- The command failed or confidence lost digits, even though M55/M33 firmware was healthy.

判断：

- COM26 carries mixed M33/M55 logs and FINSH input. During boot or frequent logging, pasted commands can lose characters.

解决：

- Prefer short aliases for bench tests. `ov_map <map_id> <confidence>` was added as the short official voice map-id test command.
- Send characters slowly, at least 50 ms between characters; if confidence is important, re-check serial echo before trusting the numeric value.
- For ROS/CAN outlet validation, trust the decoded `0x323` payload and `/rehab_arm/model_state` more than the typed command line.

状态：

- 已验证：`ov_map 401 880` produced `0x323#B50A040108830300` and `/rehab_arm/model_state` decoded `m55_voice_asr_v1 / voice_start_request`.

### NanoPi ROS bridge uses ROS_DOMAIN_ID=42 in current bench startup

现象：

- `ros2 topic echo --once /rehab_arm/model_state` with default environment reported that the topic was not published.
- The bridge process was actually running and publishing, but under `ROS_DOMAIN_ID=42`.

判断：

- The current bench bridge process environment includes `ROS_DOMAIN_ID=42`.
- Running ROS CLI commands without the same domain will look like an empty graph.

解决：

```bash
export ROS_DOMAIN_ID=42
source /opt/ros/jazzy/setup.bash
source /home/pi/rehab_arm_ros2_ws/install/setup.bash
ros2 topic list -t | grep /rehab_arm/model_state
```

状态：

- 已验证：with `ROS_DOMAIN_ID=42`, `/rehab_arm/model_state` exists and decoded official voice map-id frames.

### LLM/VLA calls must go through platform model relay, not direct provider keys

现象：

- The command-center VLA needs voice intent, camera summary, EMG summary, safety state and wiring state to ask a large model for high-level rehab suggestions.

判断：

- Device-side code, App, NanoPi, M55, M33 and AI agents must not request, store or call provider API keys directly.
- Correct path is platform-scoped relay: `POST /api/rehab-arm/v1/projects/{project_id}/devices/{device_id}/model/relay`.

解决：

- Use project `fd6a55ed-a63c-44b3-b123-96fb3c154966`, device `nanopi-m5`, robot `rehab-arm-alpha`.
- Only request `high_level_task`, `model_state_suggestion`, and `dry_run_joint_trajectory_candidate`.
- Forbid `can_frame`, `motor_current`, `motor_torque`, `raw_motor_position`, `raw_motor_velocity`, `m33_safety_override`, and `direct_motor_command`.
- If `provider.external_call_ok=false`, safely show advice unavailable/config missing/safety filtered; do not generate or execute real motion locally.

状态：

- Boundary documented in `SERVER_SYNC_API_DRAFT.md` and `VOICE_WAKE_TTS_PORTABILITY_GUIDE.md`.

### M33 串口 console 开着不等于 4/5/6/7 active-report 已开

现象：

- NanoPi 和 ROS 能看到 M33 `0x330~0x334` 聚合槽位，但 4/5/6/7 带 stale，`/joint_states` 只发布 fresh 的关节。
- 用户怀疑之前为了减少串口日志或刷屏，把某个开关关掉了。

判断：

- `yiliao_m33/rtconfig.h` 仍启用 `RT_USING_CONSOLE`、`uart2`、FINSH/MSH，代码层没有关闭 M33 串口总开关。
- `control_layer_init()` 未自动打开 4/5/6/7 active-report；它只启动 CAN RX、ROS 命令和 M33 聚合状态发布线程。
- `CONTROL_CALIBRATION_ACTIVE_REPORT_ENABLE=1` 只是允许 `0x320 active-report` 作为 telemetry-only 命令通过 M33 安全审核，不代表上电默认打开。
- 历史交接文档记录 4/5/6 active-report 是临时打开验证后再关闭，避免持续刷 CAN/日志。

解决：

- 判定 4/5/6/7 是否真实在线时，区分三种帧：M33 stale 聚合帧 `0x331~0x334`、电机原始 active-report `0x180004FD~0x180007FD`、ROS `/joint_states` fresh 输出。
- 只读阶段不要发 active-report 命令；若要证明硬件当前在线，必须在现场安全确认后短时打开对应电机 active-report，并立即关闭。

状态：

- 代码审计完成。当前结论是“active-report 很可能处于关闭/未触发状态，或对应电机未上电/未接入”，不是 ROS 伪造，也不是串口 console 被整体关闭。

### M33 shell 现场确认：CAN/RX 活着但 4/5/6/7 缓存为空

现象：

- 接回英飞凌开发板后，`COM26 @115200` 能进入 M33 FINSH shell。
- `cmd_m33_prearm_check` 返回 `fresh_mask=0x00000004`，只说明 joint3 fresh。
- `cmd_motor_fb 4`、`cmd_motor_fb 5`、`cmd_motor_fb 6`、`cmd_motor_fb 7` 均返回 `id=0 ... tick=0`。

判断：

- M33 没死：`help`、`ps`、状态命令都响应。
- CAN RX 没死：`cmd_control_debug` 显示百万级 `rx_total` 和持续 NanoPi heartbeat 计数。
- 同一条 `can0` 上还能被动抓到 `0x061/0x069` 和 `0x7C2/0x7C3`，说明 3号 CANSimple 和 C8T6/F103 传感节点都在发帧。
- 4/5/6/7 不是被 ROS 过滤掉才没了，而是 M33 自己也没有缓存到这些电机的原始 fresh 反馈。

解决：

- 继续只读时，以 `cmd_m33_prearm_check` 的 `fresh_mask`、`cmd_motor_fb <joint>` 的 `tick`、NanoPi `candump` 的 `0x18000xFD` 原始帧三者交叉判断。
- 若现场确认安全并允许短时遥测测试，下一步才可以逐个打开 4/5/6/7 active-report，并立即关闭；这一步会改变总线状态，不能归类为只读。

状态：

- 已验证。当前 blocker 收敛到 4/5/6/7 电机反馈源/active-report/供电接线层，不是 M33 shell、M33 CAN RX 或 NanoPi heartbeat 主线。

### 短时 active-report 能区分“默认不上报”和“电机无响应”

现象：

- 只读被动抓包时 4/5/6/7 都没有自然 `0x18000xFD`。
- 逐个发送 telemetry-only active-report 开/关后，4/5 和 6/7 表现不同。

判断：

- motor4/motor5：active-report 打开后能收到 `0x180004FD/0x180005FD`，M33 `0x331/0x332` 进入 fresh，说明 4/5 在线，之前只是默认不上报。
- motor6/motor7：active-report 打开后仍没有 `0x180006FD/0x180007FD`，M33 `0x333/0x334` 仍 stale，说明 6/7 当前仍未响应遥测请求。

解决：

- 4/5 后续标定前可用短时 active-report 获取当前位置，但结束必须关闭，避免总线持续刷帧。
- 6/7 不要直接进入运动测试；先查电机供电、CAN 分支、节点 ID、接线、终端、驱动在线状态，以及是否和 4/5 使用同一私有协议/ID 编码。

状态：

- 已验证。active-report 收尾 quiet check 没有持续 `0x18000xFD/0x18800xFD`，只剩 M33 stale 聚合帧。

### 6号插不稳会伪装成 active-report 无响应

现象：

- 6号第一次 probe 时没有 `0x180006FD`，M33 `0x333` 一直 stale。
- 用户随后确认 6 号物理连接没插稳。
- 重新插稳后，6 号 active-report 立刻恢复，`cmd_motor_fb 6` 读到非零位置与 tick。

判断：

- 对 6 号这种私有协议电机，`no active-report` 不能直接等于“协议坏了”。
- 先排物理接触、供电、共地，再判断协议层。

状态：

- 已验证为接触假阴性；前一轮对 6 号的无响应结论作废。

### 全链路采集要同时看 raw CAN、M33 聚合和 ROS joint_states

现象：

- 3/4/5/6 在同一采集窗口内都能形成 raw feedback 与 M33 fresh 聚合状态。
- 7 号没有 raw `0x180007FD/0x188007FD`，所以 M33 `0x334` 和 ROS 都不会把它当 fresh。

判断：

- 合格证据不是只看 `/joint_states`，而是三层同时成立：raw motor frame、M33 `0x330~0x334` fresh slot、ROS `/joint_states` 关节输出。
- stale slot 会进入诊断状态，但不会进入 `/joint_states`，这是正确行为。

状态：

- 已验证：3/4/5/6 可采集；7 号仍需查物理/驱动/节点 ID。

### C8T6/F103 能主动发传感帧不等于 ACK 控制链路稳定

现象：

- 采集窗口中能看到 `0x7C2/0x7C3`，但 `f103_ping` 和 `sensor_rate` 后只看到 M33 发 `0x7C0`，没有 `0x7C1`。
- M33 `CTRL_DBG_F103` 中 `ack=0`，后续 sensor/health 计数也未继续增长。

判断：

- 协议 ID 两边一致：C8T6 代码和 M33 都使用 `0x7C0` 控制、`0x7C1` ACK、`0x7C2` 传感、`0x7C3` 健康。
- 当前问题不是 NanoPi CAN0 或 M33 CAN TX；`candump` 能看到 M33 的 `0x7C0`。
- 更像 C8T6 供电/接线/收发器/固件运行状态间歇不稳，或者 C8T6 当前没有稳定接收/处理 `0x7C0`。

状态：

- 部分验证：C8T6 曾主动上报；ACK/控制链路未通。下一步现场查 C8T6 电源、GND、CANH/CANL、收发器 EN/STB，并看 C8T6 串口或调试器侧是否收到 `0x7C0`。

### MuJoCo shadow 服务 active 不等于 `/sim/medical_arm/joint_states` 正在发布

现象：

- `rehab-arm-sim-host-shadow.service` 显示 `active (running)`。
- `/sim/medical_arm/joint_trajectory` 仍存在，因为 `medical_arm_shadow_relay_node.py` 还在。
- `/sim/medical_arm/joint_states` 却提示 `does not appear to be published yet`。

判断：

- 这不是 `JointTrajectory` 命令格式问题，也不一定是 MuJoCo 模型不能动。
- 2026-06-17 远程检查时，`journalctl -u rehab-arm-sim-host-shadow.service` 显示 `mujoco_sim_node.py` 曾以 `process has finished cleanly` 退出，只剩 relay 节点造成“服务还活着但仿真输出没了”的半残状态。
- 如果硬件 shadow relay 在运行，它还会持续把真实 `/joint_states` 转发到 `/sim/medical_arm/joint_trajectory`，手动发布同 topic 的测试目标可能被覆盖。

解决：

- 单独验证 MuJoCo 时，用隔离 topic 启动临时节点，例如 `/codex_mujoco_test/joint_trajectory` 和 `/codex_mujoco_test/joint_states`。
- 判断是否真动了，以 `ros2 topic echo --once <test_joint_states>` 读回 position 为准。
- 2026-06-17 已验证临时纯仿真节点：`jian_hengxiang_joint` 可从 `0.0 -> 0.2 -> 0.0`，日志为 `backend=mujoco-model`。

状态：

- MuJoCo 模型动作链路已验证；常驻 shadow 服务需要后续处理节点退出后的监督/重启问题。

### 未标定前的路径规划只能先做 MuJoCo joint-space smoke test

现象：

- 用户希望先跳过标定，直接试路径规划。
- 当前 3/4/5/6 主线可读/可小幅动，但还没有完整的机械零位、正方向、软限位和末端坐标标定。

判断：

- 未标定时不能把 planner 输出解释为真实末端空间路径，也不能说某个目标点一定安全可达。
- 可以先验证 JointTrajectory 格式、时间单调性、关节名、MuJoCo 模型响应和 dry-run gate。

解决：

- 使用隔离 topic，例如 `/codex_path_test/joint_trajectory`，只驱动 MuJoCo 临时节点。
- 轨迹幅度保持很小，并且最后回零。
- 不发布到 `/arm_controller/joint_trajectory`，不进入 NanoPi/M33 真机路径。

状态：

- 2026-06-17 已验证 6DOF MuJoCo-only 三点小路径；中途 joint_states 有连续变化，最终回零。该测试证明仿真路径格式可用，不证明真机标定或末端规划正确。

### 当前姿态可作为工程临时零点，但不能写成临床零点

现象：

- 用户希望先不做完整标定，直接推进路径规划和主线补齐。
- 当前 `/joint_states` 只稳定读到 `shoulder_lift_joint=0.067 rad`，4/5/6 需要短时遥测窗口才能补全当前姿态。

判断：

- 可以把当前上电姿态当作 `engineering zero`，用于 planner、MuJoCo dry-run、数据记录和小幅相对轨迹。
- 这不能替代真实机械零点、方向标定、软限位、患者 ROM 或 M33 safety 配置。

解决：

- 新增 `medical_arm_6dof_temporary_calibration.yaml`，把已观测 3 号基线写成 `0.067 rad`，其他关节保留 TODO。
- 主线教程明确：planner 和 profile 可以记录候选参数，最终执行安全仍统一由 M33 裁决。

状态：

- 文档和 YAML 已落地；未放开真机自动执行。

### 文档清理先审计再删除

现象：

- 仓库 `docs/` 里同时存在当前主线文档、早期教程、历史修复说明、OpenClaw/HTTP 旁线和临时提示词。
- 直接删除容易误删硬件调试历史、协议来源或后续排障线索。

解决：

- 新增 `docs/DOCUMENTATION_CLEANUP_AUDIT.md`，先把文档分成必须保留、协议/安全、当前教程、建议归档/合并四类。
- 对已经在 Git 里跟踪的历史文档，先建议移动到 `docs/archive/`，确认没有入口引用后再删。
- 对未跟踪且已被新教程覆盖的重复草稿，可以直接删除。

状态：

- 已删除未跟踪重复草稿 `docs/MUJOCO_QUICKSTART_JOINT_TRAJECTORY.md`；其余文档仅列审计清单，未批量删除。

### 外部平台仓库不要和本仓库历史 `ai` 分支混淆

现象：

- 服务器平台、设备总控台、XiaoZhi relay、model relay 的最新工作不在本仓库历史 `ai` 分支里。
- 如果只看本仓库分支名，容易把旧 `ai` 分支误当成当前平台主线。

判断：

- 2026-06-17 已核对当前平台仓库为 `D:\ai-collab-product`，远端为 `https://github.com/wenjunyong666/ai-.git`，分支为 `ai/game-loop-core`。
- 本仓库 `feature/rehab-arm-ros2-architecture` 只记录它和机械臂协议、安全边界、文档入口的关系，不承载平台源码。

解决：

- 写平台相关索引前，先用 `git remote -v` 和 `git branch --show-current` 核对本地路径、远端和分支。
- `docs/AI_PROJECT_STRUCTURE_GITHUB.md` 只写稳定仓库/分支/文档入口/责任边界，不写平台功能进度日志。

状态：

- 已在主索引中补入外部平台仓库条目；无代码行为变更。

### 稳定索引不要记录本机 checkout 状态

现象：

- `docs/AI_PROJECT_STRUCTURE_GITHUB.md` 是给所有后续 AI 使用的稳定入口，但一旦写入 `D:\...` 本机路径、某个目录当前是不是 Git checkout、某个 burn workspace 当前状态，就会把临时环境事实伪装成长期项目结构。
- 后续 AI 容易把“这台机器今天的 checkout 状态”误读成 GitHub 仓库事实。

解决：

- 稳定索引只保留 GitHub remote、branch、文档入口、责任边界和正式/仿真/调试路线。
- 本机完整路径、dirty worktree、烧录工作区、临时 checkout 状态放到 `docs/ai-handoffs/` 下的日期化 handoff。

状态：

- 2026-06-17 已把 M55/C8T6/main integration 本机 checkout 表移动到 `docs/ai-handoffs/adjacent-subsystem-checkouts-2026-06-17.md`，主索引只保留稳定 GitHub 分支入口。

### XiaoZhi TTS 记账不能覆盖整段会话状态

现象：

- 平台或 LVGL 侧只看到 XiaoZhi 一直处于连接中、思考中或不完整状态。
- 后端 WebSocket 已经收到录音、ASR/LLM 或 TTS 事件，但最新设备状态可能只剩最后一次 TTS 记账结果。

根因：

- 如果把 `xiaozhi_ws_tts` 事件直接写成最新 `xiaozhi_session`，会覆盖前面累积的 listen/audio/asr/reply 字段。
- 前端和设备侧需要的是一个合并后的会话快照，而不是最后一个事件类型。

解决：

- 平台仓库 `D:\ai-collab-product` 已在 commit `ccf7fd33` 修复：`record_xiaozhi_ws_event()` 写入 merged `xiaozhi_session_v1`，保留音频字节数、时长、official audio path、兼容模式、ASR 状态、LLM entry 状态和 TTS provider 状态。
- 后续 UI/LVGL/设备 QA 应读取 session 快照判断 `listen_start/listen_stop/thinking/speaking/error`，不要只看最后一条 TTS 事件。
- 2026-06-17 后续平台文档已明确：前端/LVGL 应直接消费 `xiaozhi_session_v1.ui_state` 和 `last_error`，不要再从 `event` 或最后一条 WebSocket 消息推导动画状态。

状态：

- 2026-06-17 平台后端回归通过：`54 passed, 33 warnings`。该修复只稳定服务器侧状态，不等于已经验证 M55 麦克风、唤醒词、扬声器和官方 Opus 全链路都完成。
- 2026-06-17 追加验证：XiaoZhi 专项 `5 passed`，平台相关回归 `55 passed, 33 warnings`；最新平台文档提交为 `9567e960`。

### 云端部署健康检查可能被旧 build 环境变量误导

现象：

- 云端仓库已经 `git pull` 到最新提交，但 `/api/health` 仍显示旧的 `deployment.build_sha`。

根因：

- 云端启动脚本会从当前 shell 环境读取 `AI_COLLAB_BUILD_SHA`。如果 shell 里残留旧值，健康接口会继续显示旧 SHA，即使代码已经更新。

解决：

- 重启云端服务时显式传入最新部署元数据，例如 `AI_COLLAB_BUILD_SHA=9567e960 AI_COLLAB_BUILD_REF=ai/game-loop-core RESTART=1 ./scripts/start-cloud-prod.sh`。
- 部署验收必须同时看 `git rev-parse --short HEAD` 和 `/api/health` 的 `deployment.build_sha`。

状态：

- 2026-06-17 已修正并验证：云端 API/Web proxy health 都报告 `build_sha=9567e960`，alignment check 返回 `ok=true`。

### XiaoZhi UI 也不能从最后一条 event 反推用户状态

现象：

- 后端已经写入 `xiaozhi_session_v1.ui_state`，但 Web/LVGL 如果仍显示最后一条 `event` 或 `kind`，用户会看到“等待连接”“一直思考”之类的误导状态。
- TTS 记账、listen_stop、reply、disconnect 等事件的到达顺序不等于当前可交互状态。

解决：

- 平台 Web command-center 已改为优先读取 `xiaozhi_session_v1.ui_state` 和 `last_error`；`event`/`kind` 只作为输入输出流细节。
- LVGL 侧也应按同一 contract 绑定动画：`listening` 显示录音、`wake_detected` 显示唤醒确认、`thinking` 显示思考、`speaking` 显示播报、`idle` 显示待机、`error` 显示错误。

状态：

- 2026-06-17 前端代码已更新，`npm run build:web` 已通过；等待云端部署和真实板端 XiaoZhi WebSocket QA。

### Next 云端构建会被旧 `.next-prod/types` 污染

现象：

- 云端已经 fast-forward 到新提交，但 `npm run build:web` 在类型检查阶段失败。
- 报错形如 `.next-prod/types/app/projects/[id]/model-relay-lab/page.ts: Cannot find module .../model-relay-lab/page.js`，实际源码并不是本次改动导致的 TypeScript 错误。

根因：

- `apps/web/tsconfig.json` 长期包含 `.next-prod/types/**/*.ts` 或 `.next-dev-*` 这类生成目录。
- Next 新构建会先做类型检查，旧发布产物里的类型入口还引用已经变化或未部署的页面文件，导致构建被历史缓存污染。

解决：

- 平台仓库 commit `e52e81b3` 修复：`apps/web/scripts/build.cjs` 构建前会清理生成的 `.next-*` include，只保留标准 `.next/types/**/*.ts`；`apps/web/tsconfig.json` 不再固定包含 `.next-prod/types`。
- 云端部署时如遇同类问题，先清理 `apps/web/.next-prod` 和 `apps/web/.next-build-staging-*`，再运行 `npm run build:web`。

状态：

- 2026-06-17 已在云端验证：清理旧产物后 Web 构建通过，API/Web 重启成功，公网 alignment 返回 `ok=true` 且 `build_sha=e52e81b3`。

### XiaoZhi WebSocket `listen_stop` 1006 可能是云端 Settings schema 漂移

现象：

- XiaoZhi WebSocket 可以连接并收到 `hello/listen start/listen detect`，但在 `listen stop` 后连接异常关闭，客户端看到类似 `1006`。
- 云端 API 日志出现 `AttributeError: 'Settings' object has no attribute 'rehab_arm_model_relay_api_key'`，栈位置在 `apps/api/app/modules/rehab_arm/service.py` 的 model relay request 记录逻辑。

根因：

- 云端 `.env` 已经配置了 `REHAB_ARM_MODEL_RELAY_*`、XiaoZhi ASR/TTS provider 字段，但平台代码里的 `Settings` 类没有提交这些字段，导致部署后的服务对象缺属性。
- 本地工作区可能已经有未提交修复，因此只看本地文件容易误判为“配置没问题”。必须确认对应字段已经进入提交并部署到云端。

解决：

- 平台仓库 `D:\ai-collab-product` commit `ad905a13` 已修复：`apps/api/app/settings.py` 增加 model relay、XiaoZhi ASR、XiaoZhi TTS settings 字段。
- 部署时显式设置 `AI_COLLAB_BUILD_SHA=ad905a13 AI_COLLAB_BUILD_REF=ai/game-loop-core RESTART=1 ./scripts/start-cloud-prod.sh`，再用 alignment check 验证公网 Web/API 同步。
- 端到端 QA 时服务端不会主动首发 XiaoZhi `hello`；客户端应先发送 `hello`，再等待服务端 `hello` 回包，然后依次发 `listen start/detect/stop`。

状态：

- 2026-06-17 已修复并验证：云端 alignment 返回 `ok=true`，临时项目/设备/token 的 WebSocket QA 收到 `stt`、`llm`、`chat`、`tts start`、大量二进制 TTS 音频帧、`tts stop`、`listen stop`，云端日志无新的 traceback。

### M55 XiaoZhi 收到 TTS 帧但 `pcm_reject` 增长

现象：

- M55 侧 `m55qa_status` 显示网络和 WebSocket 已通：`xz_ws=1`、`xz_token=1`，录音会进入 `xz_listening`。
- 模型回复后没有正常扬声器输出，状态计数类似 `tts_fwd=0/0`、`tts_fail=1`、`pcm_reject=1`。

根因：

- 当前云端 XiaoZhi TTS 二进制帧实际是 60 ms PCM-like 帧。协议 v1 是 `1920` 字节 payload；协议 v3 是 `00 00 07 80` 头加 `1920` 字节 payload。
- M55 端原始 PCM 判定要求 `peak > 8`。TTS 的首个 60 ms 帧可能接近静音，导致整个回放链路在第一帧就被当成“不是 raw PCM”拒绝。

解决：

- M55 commit `928ac48` 修改 `applications/voice_service.c`：精确 60 ms PCM 帧或其整数倍允许低幅/静音通过；非标准长度仍保留幅度检查，避免把真正的 Opus/随机二进制直接当 PCM 播放。
- 如果后续平台真正切到官方 Opus 帧，仍应优先走 `xiaozhi_opus_decoder_decode()`，只有 Opus 解码失败且数据看起来像 PCM 时才走 PCM fallback。

状态：

- 2026-06-18 已提交并推送 M55 分支，且同步到 `D:\RT-ThreadStudio\workspace\wifi` 烧录工作区。尚未完成本机全编/烧录/实机听感 QA。

### M55 WiFi 保存要等 M55 ACK，当前走 append-only FAL 记录

现象：

- 在 `m55qa_wifi_ssid` / `m55qa_wifi_password` 能正常回 ACK 的情况下，执行 `m55qa_wifi_save` 仍可能把 shell 卡住，后续串口状态不再稳定。
- 这类卡死会让人误以为是 WiFi 扫描、连接或密码本身有问题。
- `m55qa_wifi_save ret=0` 容易被误读成“已经保存成功”，但它只表示 M33 把 IPC 消息排队成功。

环境：

- M55 烧录/QA 工作区：`D:\RT-ThreadStudio\workspace\wifi`
- 代码来源：`D:\RT-ThreadStudio\workspace\_m55_ref_repo`
- 当前串口 QA：`COM4 KitProg3 USB-UART @115200`

根因：

- `wifi_config_service.c` 历史上曾在 FAL 和 DFS 文件持久化之间切换，但 DFS `/flash/rehab_wifi.cfg` 依赖 `filesystem` 分区和 littlefs 挂载；当前镜像没有证明 `/flash` 是可靠可写路径。
- 旧的 FAL 擦写式保存如果每次 save 都擦分区，容易把 WiFi 保存问题放大成卡死/重启后的不确定状态。
- M33 侧 `m55qa_* ret=0` 是 IPC 发送成功，不是 M55 持久化成功；真正结果要看后续 `[m55_model_bridge] voice_ack ... cmd=1012/1014 result=...`。

解决：

- 当前稳定策略改为使用现有 `wifi_cfg` FAL 分区里的 append-only 记录日志：正常保存只追加带校验的小记录，不在每次保存时擦整分区。
- 保存验证必须等 M55 侧 ACK，例如 `cmd=1012 result=0`；只看到 `m55qa_wifi_save ret=0` 不能算通过。
- 复位后再看 `m55qa_status`，合格条件是无需重新输入 SSID/密码即可看到 `saved=1 auto=1 wlan=1 ready=1 ip!=0.0.0.0`。

技巧：

- 看到“保存会死”时，先把持久化和连接问题拆开，不要继续扩大到 LVGL 或 XiaoZhi。
- 先让 `m55qa_status` 能稳定读回，再谈后续语音和 UI。
- 如果状态里 `saved=1 auto=1 storage=0`、`wlan=1 ready=1` 且有 IP，说明当前 WiFi 基线已经足够支撑后续 XiaoZhi 语音链路排查；不要又回头重复怀疑 WiFi 扫描。

状态：

- 2026-06-18 已改为 append-only FAL 记录并完成构建/烧录；最新状态显示 `saved=1 auto=1 storage=0`、`wlan=1 ready=1`、SSID `B131`、IP `192.168.3.32`。
- 仍需补一轮明确的 reset/autoconnect QA：复位后不手动输入 WiFi，确认自动加载 FAL 记录并联网。

### M55 本机 SCons 构建要用 RT-Thread Studio 自带 GCC `bin` 路径

现象：

- `python -m SCons -j4` 使用默认 `rtconfig.py` 会报 `the toolchain path (C:\Users\XXYYZZ) is not exist`。
- 手动设置 `RTT_EXEC_PATH=D:\arm-gcc\bin` 后能找到 `arm-none-eabi-gcc.exe`/`g++.exe`，但编译失败：`cannot execute 'cc1plus'` 或 `cannot execute 'cc1'`。

根因：

- `rtconfig.py` 里的 GCC 路径仍是占位符。
- `D:\arm-gcc` 不是这个工程实际使用的 RT-Thread Studio 工具链路径。它可能不完整，也可能只是误用的旁路工具链。
- RT-Thread Studio 自带完整工具链在 `D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin`，其上级目录内能找到 `cc1.exe` 和 `cc1plus.exe`。

解决：

- 不要把 `D:\arm-gcc\bin` 当作已验证路径。
- 使用：

```powershell
$env:RTT_EXEC_PATH='D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin'
$env:RTT_ROOT='D:\RT-ThreadStudio\workspace\wifi\rt-thread'
python -m SCons -j4
```

- 注意 `RTT_EXEC_PATH` 要指向 `bin` 目录；如果只指到 `...\mingw`，SCons 会报“系统找不到指定的文件”。

状态：

- 2026-06-18 已纠正并验证：使用 RT-Thread Studio 自带 `...\mingw\bin` 后，`python -m SCons -j4` 构建通过。

### M55 带资源烧录后 OpenOCD 收尾 acquisition 失败不等于前面没写入

现象：

- `program_with_resources.bat` 的 OpenOCD 日志显示 `rtthread.hex` 和 `whd_resources_all.bin` 都已经完成 erase/program。
- 随后在 reset/run 或 debug-domain tear-down 阶段出现 `kitprog3: failed to acquire the device`、`Acquisition in Test Mode FAILED`。

判断：

- 该错误出现在两个镜像写入完成之后，不能直接判定为 M55 或 WiFi 资源没有烧进去。
- 后续应以串口 boot log、`m55qa_status`、WiFi scan/connect/save/autoconnect 验证实际运行状态。

状态：

- 2026-06-18 已观察到该现象；仍需上板串口 QA 确认复位后的运行状态。

### M55 XiaoZhi 烧录后 token 会回到编译值，采集前要主动重连

现象：

- WiFi 已经正常，`m55qa_status` 能看到 `saved=1 auto=1 storage=0`、`wlan=1 ready=1`、IP `192.168.3.32`，但 XiaoZhi 连接在烧录或复位后又失败。
- 烧录后状态可能退回编译进镜像的旧 token，表现为 `token_len=420`、`xz_errno=-403`。
- 重新写入新 token 后，`m55qa_capture_on` 过去会因为 WebSocket 已断开直接失败或一直停在“小智连接中”。

环境：

- M55 正式仓库：`D:\RT-ThreadStudio\workspace\_m55_ref_repo`，branch `M55`。
- M55 烧录/QA 工作区：`D:\RT-ThreadStudio\workspace\wifi`。
- 串口：`COM4 KitProg3 USB-UART @115200`。
- 云端 WebSocket：`106.55.62.122:8011` 的 rehab-arm XiaoZhi endpoint。

根因：

- M55 烧录会恢复编译进镜像的 XiaoZhi token；如果这个 token 已过期或和云端密钥不匹配，云端会拒绝，板端看到 `-403`。
- M33 的 `m55qa_* ret=0` 仍然只是命令发送成功，不能当作 M55 业务状态成功；token 分片、commit、reconnect 都要等 M55 ACK。
- 启动录音前如果 WebSocket 已经掉线，直接进入 listen 会失败；采集入口必须先检查连接并尝试 `voice_service_reconnect_xiaozhi()`。

解决：

- 不要把 token 明文写进聊天或文档。使用本地新 token 文件并通过串口 ACK-paced 分片写入：`m55qa_xz_token_begin`、多次 `m55qa_xz_token_part <48-char chunk>`、`m55qa_xz_token_commit`、`m55qa_xz_reconnect`。
- 每片都等 M55 ACK，例如 begin `cmd=1004 result=0`、part `cmd=1005 result=0`、commit `cmd=1006 result=0`、reconnect `cmd=1003 result=0`。
- `D:\RT-ThreadStudio\workspace\wifi\applications\voice_service.c` 已验证采集前重连逻辑；2026-06-18 已同步到正式 M55 repo `applications\voice_service.c`。

状态：

- 2026-06-18 重新写入新 token 后，状态恢复为 `xz_ws=1 xz_token=1 token_len=480 xz_stage=70 xz_errno=0`。
- `m55qa_capture_on` 已能返回 `cmd=1 result=0`，说明采集入口不再因 stale WebSocket 立刻失败。
- 仍未完成：采集期间/之后连接仍可能掉到 `xz_ws=0 xz_stage=80 xz_errno=-1`，需要继续查协议版本与音频格式闭环。

### XiaoZhi 官方 Opus 路线和当前 PCM TTS/ASR 兼容路线不能混着假装已闭环

现象：

- 云端能看到板端 `hello`、`listen_start`、`audio_frame`，说明 M55 已经把 XiaoZhi 事件和音频发到了平台。
- PC 云端探针用协议 v3、文本 transcript、不带音频时，可以完整走到 `stt -> llm -> chat -> tts start -> binary PCM frames -> tts stop`。
- 真板语音仍不能算完全打通：板端上传的是 Opus/PCM 取决于编译宏，云端当前对真实 Opus ASR 返回 `opus_decode_not_configured`；云端 TTS 仍返回 PCM-like 60 ms 帧。

根因：

- `xiaozhi_voice_relay.h` 当前仍是 `XIAOZHI_PROTOCOL_VERSION 1U`，而代码里已经有 v3 binary header 支持；协议选择和云端/官方路线还没有完全统一。
- 官方方向是 Opus，但当前云端缺少 Opus ASR decode；同时 TTS 下行如果仍是 PCM，而板端按 Opus 解码，会导致扬声器噪声、无声或回放失败。
- 只看到 `hello/listen/audio_frame` 不能证明“小智已完成”；还必须看到 ASR、LLM、TTS、扬声器播放和状态动画都闭环。

解决方向：

- 官方优先路线：把板端协议/音频切到官方一致的 v3/Opus，并在云端补齐 Opus ASR decode 与 TTS Opus encode，或明确下行帧格式协商。
- 快速验收路线：临时使用 `pcm_s16le` 兼容链路，让真实板端语音先走通 ASR/LLM/TTS/扬声器，再回到官方 Opus 优化。
- 无论走哪条，LVGL 只应显示状态：唤醒、录音、思考、播放、错误；长回答主要走扬声器，不应把大段回答塞进小屏。

状态：

- 2026-06-18 已确认当前还差“协议/音频格式一致性 + ASR/TTS 编解码闭环”，不是 WiFi 扫描问题。
- 下一步应先选一条音频闭环路线并实机 QA，再回到 LVGL 动画和字库补齐。

### M55 本地构建要显式指定 RT-Thread Studio 的 GCC `...\mingw\bin`

现象：

- 在 `_m55_ref_repo` 里直接跑 `python -m SCons -j4`，会报 `the toolchain path (C:\Users\XXYYZZ) is not exist`。
- 这个默认路径是 `rtconfig.py` 里的占位符，不是可用工具链。

环境：

- M55 formal repo：`D:\RT-ThreadStudio\workspace\_m55_ref_repo`
- 正确工具链：`D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin`

解决：

```powershell
$env:RTT_EXEC_PATH='D:\RT-ThreadStudio\platform\env_released\env\tools\gnu_gcc\arm_gcc\mingw\bin'
$env:RTT_ROOT='D:\RT-ThreadStudio\workspace\wifi\rt-thread'
python -m SCons -j4
```

技巧：

- 不要把 `D:\arm-gcc\bin` 当成已验证工具链。
- 如果构建已经进入 LVGL/TensorflowLiteMicro 等大包编译，说明工具链已经走对了，后面再看是否真正编完。

状态：

- 2026-06-18 已复核：默认路径失败，显式指定 RT-Thread Studio GCC 路径后，构建进入长编阶段但本次会话未等到最终结束。

### M55 XiaoZhi 现在卡在音频闭环，不是 WiFi 扫描

现象：

- 过去一直在查 WiFi 扫描、保存和自动连接，但最新状态里已经有 `saved=1 auto=1 wlan=1 ready=1 ip=...`，XiaoZhi 也能连上云端。
- 真正没收尾的是 `wake -> listen -> thinking -> speak` 的板端闭环和扬声器输出。

环境：

- M55 formal repo：`D:\RT-ThreadStudio\workspace\_m55_ref_repo`
- Burn workspace：`D:\RT-ThreadStudio\workspace\wifi`

判断：

- WiFi 不再是当前 blocker。
- 现在要查的是 protocol / audio format / TTS 播放 / LVGL 状态展示的收口。

技巧：

- 以后看到 `xz_ws=1`、`xz_token=1`、`saved=1`、`ready=1` 时，优先看音频链路，不要再回头反复怀疑扫描。

状态：

- 2026-06-18 已确认：当前主问题是音频闭环和板端 QA，WiFi 已经不是主要障碍。

### NanoPi SSH 在密钥协商前关闭时先不要误判成代码问题

现象：

- 从 Windows 工作站执行 `ssh pi@192.168.2.66` 可以连到 22 端口，但远端在认证前关闭连接。
- `ssh -vvv -o BatchMode=yes -o PreferredAuthentications=publickey -o ConnectTimeout=8 pi@192.168.2.66 "true"` 输出 `kex_exchange_identification: Connection closed by remote host`。

环境：

- NanoPi 旧记录地址：`pi@192.168.2.66`。
- 本地 SSH 配置只有 Host/User 映射，没有特殊 ProxyCommand 或密钥覆盖。

判断：

- 这不是 ROS2 摄像头节点、VLA 协议或本地密钥选择阶段的问题；连接在密钥认证前就被远端关闭。
- 优先查 NanoPi 是否在线但 `sshd` 异常、连接数/防护限制、板端负载过高、网络侧 IP 冲突，或需要串口/本地屏幕重启 `sshd`。

修复方向：

- 能接触板子时先跑 `sudo systemctl status ssh`、`sudo journalctl -u ssh -n 100`、`ip addr`、`who`、`last -n 20`。
- SSH 恢复后再做双 USB 摄像头枚举：`lsusb`、`v4l2-ctl --list-devices`、`ls -l /dev/video*`。

状态：

- 2026-06-22 远程只读登录未成功，NanoPi 双 USB 摄像头枚举未验证。

### NanoPi 双 USB 摄像头插上但没有 `/dev/video45` 时先恢复旧用户态路径

现象：

- NanoPi `pi@192.168.3.36` 的 `lsusb` 能看到两只 `1bcf:2281 SPCA2281 Web Camera`。
- 用户拔插两只 USB 摄像头后，`lsusb` 仍能看到两只摄像头；USB 层不是“没插上”。
- `lsusb -t` 显示两只摄像头的接口都是 `Class=Video, Driver=[none]`。
- `dmesg` 对每只摄像头都出现 `uvcvideo: disagrees about version of symbol module_layout`。
- 旧脚本 `/home/pi/nanopi_ros/README_CAMERA.md` 和 `/home/pi/.openclaw/workspace/camera_*.py` 明确把 USB 摄像头写成 `/dev/video45`。
- 当前系统没有 `/dev/video45` 或 `/dev/video46`；OpenCV 打开 `45/46/0/1/2/22/31` 都失败。

判断：

- 不要先改内核。用户确认此前摄像头能驱动，且旧工程已经以 video45 为可用路径。
- 当前不是摄像头未插；更准确的说法是：两只 USB 摄像头已枚举，但现有 `uvcvideo` 没有绑定成功，所以没有生成过去的 UVC video 节点。
- Rockchip 自带 `/dev/video22`、`/dev/video31` 是 ISP mainpath 节点，当前 `ffmpeg` 报 `Not a video capture device`，不应把它们当 USB 摄像头。
- 运行内核是 `6.1.141`；板上存在 `/lib/modules/6.1.141` 和 `/lib/modules/6.1.141.can-new` 两套已有模块目录，且都有 `uvcvideo.ko`。当前登录用户无 `sudo` 密码，无法临时验证加载 alternate existing module。

已验证：

- `stereo_rgb_yolo_context_v1` 平台上传链路已通，NanoPi 能把 probe payload POST 到平台并得到 `ok=true`。
- 只差真实左右图像文件来源；拿到左右 JPEG 后就能进入 VLA-V 软件链路。

下一步：

- 需要现场/root 权限时，优先只临时尝试加载板上已有的 alternate `uvcvideo.ko` 或恢复此前匹配的模块状态；不要进入编译/替换内核路线。
- 每次操作后运行：`lsusb -t`、`dmesg | tail -n 100`、`ls -l /dev/video45 /dev/video46 /dev/video*`、`python3 /home/pi/.openclaw/workspace/camera_fps.py 45`。
- 一旦 video45/46 恢复，先用 OpenCV/ffmpeg 保存 `/tmp/left.jpg` 和 `/tmp/right.jpg`，再运行 `stereo_vision_context.py` 上传 perception-only VLA-V payload。

补充验证：

- 2026-06-22 用 sudo 临时 `insmod /lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko` 后，两只摄像头都绑定到 `uvcvideo`。
- 实际可采集节点是 `/dev/video45` 和 `/dev/video47`；`/dev/video46`、`/dev/video48` 会被列为 Video Capture 类型但不是可用图像采集口，OpenCV 会报不是 capture device。
- 最小抓帧命令：

```bash
ffmpeg -hide_banner -loglevel error -y -f v4l2 -input_format mjpeg -video_size 640x480 -i /dev/video45 -frames:v 1 -update 1 /tmp/left.jpg
ffmpeg -hide_banner -loglevel error -y -f v4l2 -input_format mjpeg -video_size 640x480 -i /dev/video47 -frames:v 1 -update 1 /tmp/right.jpg
```

- 用真实左右图执行 `stereo_vision_context.py --upload` 后，平台返回 `ok=true`。这说明 VLA-V 的真实双 RGB 图像输入路径已验证，剩余是封装、标定、检测/粗深度估计和重启后的模块加载策略。
- 已新增可重复入口：

```bash
cd /home/pi/rehab_arm_ros2_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run rehab_arm_psoc_bridge stereo_camera_capture_upload.py \
  --project-id fd6a55ed-a63c-44b3-b123-96fb3c154966 \
  --api-base http://106.55.62.122:8011 \
  --upload \
  --pretty
```

- 如果重启后 `uvcvideo` 又没有绑定，先临时加 `--ensure-uvc-module`。这个选项只加载板上已有的 `/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko`，不是编译/替换内核。

状态：

- 2026-06-22 已临时打通并封装 CLI。该 `insmod` 不持久，重启后需要重新加载或另行做持久化决策。

### NanoPi ROS2 包构建失败时检查源码同步，而不是先怀疑新脚本

现象：

- NanoPi 上执行 `colcon build --packages-select rehab_arm_psoc_bridge --symlink-install` 时失败。
- 报错类似：`ament_cmake_symlink_install_programs() can't find '/home/pi/rehab_arm_ros2_ws/src/rehab_arm_psoc_bridge/rehab_arm_psoc_bridge/build_voice_pipeline_plan.py'`。

根因：

- NanoPi 源码工作区不是完整同步的当前 Git 分支状态；`CMakeLists.txt` 已经列出若干 helper 脚本，但 NanoPi 目录里缺少这些文件。
- 这不是双摄脚本本身的语法或摄像头链路问题。

解决：

- 从本地当前分支同步缺失的 `rehab_arm_psoc_bridge/*.py` helper 脚本到 NanoPi 源码目录。
- 重新执行 `colcon build --packages-select rehab_arm_psoc_bridge --symlink-install`。
- 通过后运行 `ros2 pkg executables rehab_arm_psoc_bridge | grep stereo`，应看到 `stereo_camera_capture_upload.py` 和 `stereo_vision_context.py`。

状态：

- 2026-06-22 已修复 NanoPi 源码同步缺口，并验证 `ros2 run rehab_arm_psoc_bridge stereo_camera_capture_upload.py ... --upload` 可抓真实双摄图并上传平台。
