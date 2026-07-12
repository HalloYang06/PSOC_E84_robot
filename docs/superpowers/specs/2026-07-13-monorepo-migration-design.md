# PSOC E84 康复机械臂 Monorepo 迁移设计

## 1. 目标

将分散在多个仓库和长期分支中的康复机械臂代码迁移到
`HalloYang06/PSOC_E84_robot` 的单一 `main` 分支。

迁移后的仓库必须同时满足：

- 打开 `main` 即可理解完整产品架构；
- M33、M55、C8T6、ROS、App、平台和 VLA 按目录分层；
- 各子工程仍可独立构建；
- 主线 Git 历史随代码迁入，不使用仅含最新文件的快照导入；
- 原仓库保持不变，继续作为原始提交哈希的追溯来源；
- 实验、台架和历史演示不能混入正式运行入口；
- 真实运动最终必须经过 M33 安全裁决。

目标远端仓库当前为空，最终只推送整理完成的 `main`。迁移过程中可以使用本地临时引用，但不在目标远端保留迁移或历史分支。

## 2. 目标目录

```text
PSOC_E84_robot/
├── README.md
├── docs/
│   ├── architecture/
│   ├── development/
│   ├── migration/
│   ├── protocols/
│   ├── validation/
│   └── superpowers/specs/
├── firmware/
│   ├── m33/
│   ├── m55/
│   └── c8t6/
├── ros/
│   └── rehab_arm_ws/
├── apps/
│   └── mobile/
├── platform/
│   ├── web/
│   ├── api/
│   └── runner/
├── ai/
│   └── vla/
├── tools/
│   ├── build/
│   ├── test/
│   └── bench-debug/
└── .github/workflows/
```

`docs/protocols/` 只保存跨端协议说明。CAN、M33/M55 IPC、App API 和安全逻辑的实际实现仍属于各自工程，不在迁移阶段抽成公共库。

M33 与 M55 第一阶段均保留完整、自包含的 RT-Thread/Infineon 工程。两者当前有大量相同 SDK 文件，但迁移阶段不做 SDK 去重；先保证路径变化后仍能分别构建，再把去重作为独立重构任务评估。

## 3. 来源与基线

执行迁移前再次刷新远端，并确认下列基线没有被新的正式提交替代。

| 目标目录 | 来源 | 审计时基线 | 定位 |
| --- | --- | --- | --- |
| `firmware/m33/` | `ChillAmnesiac/Medical-Rehabilitation-Manipulator` 的 `M33` | `24bae363` | 实时控制、CAN、安全、BLE、M33 侧 IPC |
| `firmware/m55/` | 同仓库的 `M55` | `7298c28e` | Wi-Fi、语音、音频、小模型、M55 侧 IPC |
| `firmware/c8t6/` | 同仓库的 `C8T6` | `28b79a09` | 传感采集与 CAN 节点 |
| `ros/rehab_arm_ws/` | 同仓库的 `feature/rehab-arm-ros2-architecture` | `69450f71` | 正式 ROS2、PSoC bridge、6DOF、MuJoCo shadow |
| `apps/mobile/` | `wenjunyong666/ai-` 的 `app/rehab-arm-mobile-stitch` | `f6c2c026` | 康复 PWA 的 Capacitor/Android 包装 |
| `platform/web/` | 同一 `ai-` 分支 | `f6c2c026` | 康复总控台和康复 PWA Web 入口 |
| `platform/api/` | 同一 `ai-` 分支 | `f6c2c026` | App 当前配套康复 API |
| `platform/runner/` | 同一 `ai-` 分支 | `f6c2c026` | 康复功能运行和部署所需组件 |
| `ai/vla/` | ROS 主线、旧 `ai` 分支及 `ai-` 康复模块 | 逐文件审计 | 高层任务、Schema、视觉和离线工具 |

`codex/rehab-mobile-backend-qa-20260706` 中的 `cloud/rehab-platform` 是补充参考，不作为第二套正式后端整体迁入。只在接口对照后吸收当前 `platform/api` 缺失且已有测试证明的安全或 QA 逻辑。

M33、M55 的临时恢复、延迟、EMG、BLE 和故障排查分支不能按“日期较新”直接替代正式基线。仅当独有提交通过差异审计、构建和相应硬件验证后，才迁入正式目录。

## 4. ROS 与实验代码分类

ROS 正式基线为 `feature/rehab-arm-ros2-architecture`，不是较早的 `NanoPi_ROSNode`。

正式主线包括：

- `rehab_arm_psoc_bridge`；
- 6DOF 关节描述和当前标定配置；
- M33 状态、安全状态和电机状态解析；
- `/arm_controller/joint_trajectory -> NanoPi -> M33` 请求链；
- MuJoCo hardware shadow 和 dry-run 审核能力。

下列内容必须隔离：

- 旧 `demo_trajectory_node.py` 和旧 5 关节启动入口放入 `tools/bench-debug/legacy-5dof/`，不得被正式 launch 引用；
- `nanopi_can_master.py` 属于台架诊断，不得成为穿戴场景运动入口；
- 测试所需的合成 CAN、传感器、EMG 和轨迹数据保留在对应测试的 `fixtures/` 中，并明确标记为 synthetic；
- `ROS_VLA_WebSocket` 只作历史参考，不整体迁入；
- `NanoPi_ROSNode` 分叉后的 VLA 视觉工具逐项审计，正式功能、离线工具和台架工具分别落入 ROS、`ai/vla/` 或 `tools/bench-debug/`。

## 5. App 与平台垂直切片

App 的权威来源是 `wenjunyong666/ai-`，不是旧仓库的 `APP` 分支。

迁移范围必须覆盖康复功能的完整依赖闭包：

- `apps/mobile/rehab-arm-android`；
- `apps/web/public/rehab-arm-mobile` 及康复总控页面；
- `apps/api/app/modules/rehab_arm`、对应数据库模型和测试；
- 上述模块实际依赖的公共认证、数据库、配置、共享包、构建和部署文件；
- 康复 Runner 或运行脚本的必要部分。

不迁入农场游戏、通用平台游戏化实验、无关项目页面、大量历史 QA 截图、已生成 APK 和无关产品文档。依赖闭包以“迁移后 Web/API/App 能从源码构建并通过测试”为判断标准，不能只按文件名包含 `rehab` 进行机械筛选。

旧 `APP` 分支不作为正式 App 来源。其 6,067 个 `app/build` 文件、旧 Compose 直控 UI 和漂移协议不进入新主线。

## 6. Git 历史迁移

每个正式来源先在隔离副本中执行路径级历史重写，使其所有历史提交中的文件从仓库根移动到目标子目录。之后将这些互不相关的历史合并为目标仓库的一个 `main`。

历史迁移必须保留：

- 作者和提交者信息；
- 作者时间和提交时间；
- 提交说明；
- 文件增加、修改、删除和重命名过程；
- 正式主线的父子提交关系。

路径是 Git 提交内容的一部分，因此路径重写后的提交哈希必然变化。原始仓库不做改写，继续保留原哈希。`docs/migration/source-map.md` 记录来源仓库、来源分支、基线提交、目标目录和重写后头提交。

目标远端最终只包含一个 `main`。所有组件历史都是 `main` 的祖先；不推送 `history/*` 或迁移工作分支。应抽查关键文件，确认 `git log --follow -- <path>` 能跨越目录迁移持续显示历史。

## 7. 系统控制边界

唯一正式运动路径为：

```text
App / Web / VLA / planner
  -> 高层请求或 JointTrajectory 候选
  -> NanoPi ROS2 bridge
  -> M33 本地安全审核
  -> 电机
```

M33 是最终安全责任核心。M55、App、Web、API、VLA、服务器、MuJoCo 和 NanoPi 上层逻辑不能绕过 M33 直接授权电机运动。

迁移时整理的 `docs/protocols/` 至少说明：

- CAN `0x320`、`0x321`、`0x322`、`0x323`、`0x330~0x334` 的方向和作用；
- M33/M55 IPC 消息及版本边界；
- App、平台和 NanoPi API 的当前正式入口；
- BLE 只读 profile 与 `ERR:readonly` 行为；
- 急停、heartbeat timeout、限位、限速、限流和故障处理责任。

## 8. README 设计

根 `README.md` 是新仓库的产品入口，必须重新编写，不直接复制任一旧分支 README。内容包括：

1. 项目一句话定位和真实硬件图片或架构图；
2. M33、M55、C8T6、NanoPi、ROS2、MuJoCo、App、平台和 VLA 的职责；
3. 正式数据流和唯一运动控制路径；
4. 当前已经验证、尚未完成和禁止夸大的能力；
5. 顶层目录导航；
6. 各子工程最短构建入口；
7. 协议文档和安全边界入口；
8. mainline、shadow-sim、dry-run、bench-debug、offline-demo、side-channel 分类；
9. 开发、测试和提交规则；
10. 原仓库及迁移来源说明。

README 面向第一次进入仓库的开发者，使用中文为主，术语和命令保持准确。不得把旧 HTTP/App 直控、5 关节 demo、合成状态或 VLA 候选描述成已完成的真机闭环。

## 9. 验证与完成条件

### 9.1 仓库卫生

- 目标远端默认分支为 `main`，没有迁移或历史分支；
- 不提交构建目录、APK、数据库、缓存、密钥或无关截图；
- 根 README、来源映射和协议导航完整；
- 全仓库执行密钥和大文件检查。

### 9.2 历史

- 各正式来源的历史均为 `main` 的祖先；
- 抽查 M33、M55、ROS、App/API 关键文件的 `git log --follow`；
- 作者、时间和提交说明与来源历史一致；
- 来源映射无缺项。

### 9.3 构建与测试

- M33、M55、C8T6 分别从自己的目录独立构建；
- ROS 正式 workspace 完成 `colcon build` 和可运行测试；
- 正式 ROS launch 不引用旧 5 关节或直控工具；
- App 能从 PWA 同步资源并构建 debug APK；
- Web 完成依赖安装、lint、测试和 production build；
- API 完成依赖安装和康复模块测试；
- VLA 测试证明只产生高层任务或候选，不拥有底层执行权限。

若验证失败，先判断是路径迁移回归还是来源分支已有缺陷。迁移提交不得顺手重构功能代码；确需修复时使用独立、可解释的后续提交，并记录验证证据。

## 10. 明确不在本次范围内

- 合并 M33 与 M55 为一个固件镜像或一个 RT-Thread 构建目标；
- 去重两套固件 SDK；
- 补齐尚未完成的 6DOF 真机闭环；
- 把 VLA、App 或服务器升级为运动安全控制器；
- 修复所有旧实验分支；
- 删除或重写原仓库历史；
- 迁入与康复机械臂无关的 `ai-` 平台功能。

