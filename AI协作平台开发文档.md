# AI 协作开发平台开发文档

版本：v0.1  
适用项目：嵌入式、机器人、机械臂、ROS、AI 模型、硬件协同开发项目  
当前示例项目：Medical-Rehabilitation-Manipulator 康复机械臂项目

---

## 1. 项目背景

当前团队在开发嵌入式和机械臂项目时，通常存在以下问题：

1. 多人协作依赖会议、聊天记录和人工同步，任务上下文容易丢失。
2. 不同模块负责人需要反复沟通，例如 M33、M55、C8T6、NanoPi、ROS、VLA、App、服务器、硬件设计等。
3. AI 已经可以辅助开发，但每个 AI 的职责、权限、模型、token、运行电脑、可访问仓库都缺少统一管理。
4. GitHub 可以管理代码历史，但不适合承载所有高频 AI 协作、自动测试、局域网设备控制和多 Agent 调度。
5. 嵌入式项目涉及硬件、串口、烧录、传感器、机械臂控制，AI 如果缺少权限边界，存在安全风险。
6. 多 AI 同时工作时，容易出现重复修改、互相覆盖、token 浪费、分支混乱、测试结果不可追踪等问题。

因此需要搭建一个面向嵌入式开发的 AI 协作平台，让人类、AI、代码仓库、设备、任务、日志和权限形成统一工作流。

---

## 2. 平台目标

平台的目标不是替代 GitHub，也不是做一个普通聊天工具，而是建设一个：

**自托管 Git 协作层 + 多 AI Agent 调度系统 + 嵌入式项目知识库 + 安全审查流水线 + 响应式前端管理平台。**

平台的产品定位必须明确为：

**人类工程师主导，AI 团队辅助协作。**

AI 的职责是整理、分析、生成、检查、建议、辅助编码和沉淀知识；人类负责关键决策、硬件调试、真实设备操作、安全确认、最终合并和版本发布。尤其在机械臂、康复设备、电机控制、电源系统等场景中，平台不能设计成让 AI 完全接管开发或直接控制真实硬件。

核心目标：

1. 前端页面可在手机、电脑、开发板浏览器中访问。
2. 可添加多个 AI，并配置 AI 所属电脑、模型、职责、token、权限、可访问目录、预算等参数。
3. 支持多项目、多团队、多 AI 协作维护。
4. GitHub 继续作为远程主仓库或公开仓库，但平台本地维护 Git 镜像和工作分支。
5. 支持随时回退到 GitHub 或本地 Git 历史版本。
6. 支持 OpenClaw、OpenHands、Codex、本地模型、Claude、Qwen、DeepSeek 等不同 AI 工具接入。
7. 支持嵌入式项目的特殊流程：交叉编译、固件烧录、串口日志、ROS 节点、设备状态、仿真测试、硬件安全检查。
8. 为后续产品化打基础，可适配不同机器人、嵌入式和软件项目。
9. 明确人机协作边界，真实硬件调试必须由人类执行，AI 只能提供分析、步骤、检查清单和风险提示。
10. 所有高风险操作必须有人类确认点，平台保留审计记录和回滚路径。

---

## 3. 主要问题分析

### 3.1 Token 消耗问题

多 AI 协作最大成本之一是 token 消耗。典型浪费来源如下：

1. 每个 AI 都重复读取完整代码仓库。
2. 每次任务都把大量无关文件塞进上下文。
3. AI 之间通过长对话同步，而不是通过结构化任务和摘要同步。
4. 同一个问题被多个 AI 重复分析。
5. 日志、编译输出、测试输出没有压缩，直接全部传给模型。
6. 大模型处理简单任务，例如格式化、查找文件、生成简单文档。
7. 缺少预算控制，AI 可以无限重试。

解决策略：

1. 建立项目知识库，只保存稳定上下文，例如架构、模块边界、接口协议、硬件说明。
2. 每个任务只传递相关文件、相关 commit、相关 issue、相关日志摘要。
3. 对日志进行分级压缩：
   - 完整日志保存到对象存储。
   - AI 默认只看到错误摘要、关键堆栈、失败命令。
   - 必要时再按需展开。
4. 任务开始前先做上下文检索，不让 AI 全仓库盲读。
5. 为不同 AI 设置预算：
   - 单任务最大 token。
   - 单日最大 token。
   - 单项目最大费用。
   - 超预算后进入人工确认。
6. 大小模型分层：
   - 小模型：分类、摘要、日志压缩、简单文档。
   - 中模型：代码解释、普通修复。
   - 大模型：架构设计、复杂调试、安全审查。
7. 对 AI 输出做缓存：
   - 相同文件摘要缓存。
   - 相同芯片文档问答缓存。
   - 相同编译错误分析缓存。
8. 平台记录每个 AI、每个任务、每个模型的 token 使用量和成功率。

建议数据库中记录：

```sql
agent_usage_log:
  id
  project_id
  task_id
  agent_id
  model
  input_tokens
  output_tokens
  cached_tokens
  cost
  started_at
  finished_at
  status
```

### 3.2 服务器资源问题

平台涉及 Web 服务、数据库、Git 镜像、队列、Runner、AI 调度、日志存储、构建任务等组件。不同阶段服务器需求不同。

#### MVP 阶段

适合 3-10 人、5-30 个 AI、1-5 个项目。

推荐配置：

```text
CPU: 8 核以上
内存: 16GB-32GB
磁盘: 500GB SSD
系统: Ubuntu Server 22.04/24.04
部署: Docker Compose
网络: 局域网优先，公网访问走 VPN 或反向代理
```

可部署组件：

1. 前端 Next.js。
2. 后端 FastAPI/NestJS。
3. PostgreSQL。
4. Redis。
5. Forgejo/Gitea。
6. MinIO。
7. Agent Orchestrator。
8. 日志服务。

#### 团队扩展阶段

适合 10-50 人、50-200 个 AI、多个项目。

推荐配置：

```text
主服务器:
  CPU: 16-32 核
  内存: 64GB
  磁盘: 2TB NVMe

Runner 服务器:
  按模块拆分
  ROS/仿真/GPU 单独机器
  嵌入式编译单独机器
  文档/RAG 单独机器
```

#### 产品化阶段

建议迁移到 Kubernetes 或轻量 K3s：

1. API 服务水平扩展。
2. Runner 独立节点注册。
3. Git 服务独立存储。
4. PostgreSQL 主从或托管数据库。
5. MinIO/S3 保存日志、构建产物、固件。
6. Prometheus + Grafana 监控资源。

### 3.3 GitHub 限制问题

GitHub 适合保存最终代码、Issue、PR 和公开协作，但不适合承载所有内部 AI 工作流。

常见限制：

1. API 速率限制。
2. Actions 队列和额度限制。
3. 网络访问不稳定。
4. 大量 AI 高频 clone/pull 会浪费带宽。
5. 私有仓库权限管理复杂。
6. 多 AI 并发提交容易造成分支混乱。
7. 硬件测试无法完全放在 GitHub Actions 中执行。

解决策略：

1. 本地部署 Forgejo/Gitea 作为 Git 镜像和协作主入口。
2. GitHub 作为上游或下游远程仓库。
3. AI Runner 默认从局域网 Git 服务拉取代码。
4. 本地 CI 执行编译、测试、仿真、硬件在环测试。
5. 通过定时或手动方式同步到 GitHub。
6. 重要版本打 tag，并推送到 GitHub。
7. 回滚时基于 Git commit/tag，而不是平台私有状态。

推荐分支策略：

```text
main                 稳定版本
develop              日常集成分支
ai/task-123-ros      AI 任务分支
ai/review-123        AI 审查分支
hotfix/xxx           紧急修复
release/v0.1.0       发布分支
```

### 3.4 多 AI 协作冲突问题

问题表现：

1. 多个 AI 修改同一文件。
2. AI 不知道其他 AI 已经完成的任务。
3. 主负责 AI 和复审 AI 权责不清。
4. AI 改了不属于自己模块的代码。
5. 合并前没有测试。

解决策略：

1. 每个任务绑定模块和文件范围。
2. AI 配置可访问目录和可修改目录。
3. 平台在派发任务前做文件锁或软锁。
4. 每个 AI 必须在独立分支工作。
5. 所有合并必须经过：
   - diff 摘要。
   - 自动测试。
   - 审查 AI。
   - 人类确认或规则确认。
6. 平台显示任务依赖关系，避免重复开发。

### 3.5 安全与硬件风险问题

机械臂和嵌入式项目有真实物理风险，例如电机误动作、限位失效、过流、误烧录、误删配置等。

风险：

1. AI 直接控制电机。
2. AI 修改安全限位代码。
3. AI 执行危险 shell 命令。
4. AI 读取或泄漏 token、SSH key。
5. AI 烧录错误固件到设备。
6. AI 在真实机械臂上运行未经验证的控制算法。

解决策略：

1. 权限分级。
2. 硬件操作必须人工确认。
3. AI 默认只允许仿真环境。
4. 固件烧录需要审批。
5. 串口、摄像头、SSH、GPIO、CAN、USB 设备访问需要单独授权。
6. 所有命令记录审计日志。
7. 危险命令默认拦截，例如删除根目录、格式化磁盘、覆盖密钥、强制推送主分支。
8. 安全 AI 独立审查涉及运动控制、电源、电机、限位、急停的代码。
9. 真实硬件调试必须由人类执行，AI 只提供排查建议、检查清单、日志分析和风险提示。
10. AI 不允许绕过人工确认点，不允许自行执行机械臂运动、烧录、上电、电机控制等高风险动作。

权限等级建议：

```text
L0 只读: 只能读取代码、文档、日志。
L1 建议: 可以生成 patch，但不能写入仓库。
L2 开发: 可以创建分支、提交代码、运行测试。
L3 维护: 可以创建 PR、修改 issue、触发 CI。
L4 管理: 可以合并、回滚、修改权限。
L5 硬件控制: 可以访问真实设备，必须额外审批。
```

人工确认等级建议：

```text
H0 无需确认:
  文档摘要、代码解释、日志分类、知识库检索。

H1 轻确认:
  普通代码修改、测试脚本、README 更新、非关键配置修改。

H2 必须确认:
  合并 PR、修改接口协议、修改构建配置、修改 CI 流程。

H3 双重确认:
  烧录固件、修改控制参数、访问真实设备、连接串口执行写操作。

H4 禁止自动执行:
  机械臂真实运动、电源操作、删除关键数据、绕过安全保护、关闭急停逻辑。
```

H3 和 H4 操作必须在前端显示明确风险说明，并要求人类工程师确认实验环境、设备状态、急停准备和回滚方案。

### 3.5.1 人机协作边界问题

本平台不以“完全让 AI 接手开发”为目标。正确边界是：AI 负责辅助研发，人类负责真实世界判断。

人和 AI 的职责划分：

| 工作 | AI 可以做 | 人必须做 |
|---|---|---|
| 需求整理 | 拆任务、归类、生成待办 | 确认真实目标和优先级 |
| 代码开发 | 写初版、修 bug、补文档 | 审查关键逻辑，确认合并 |
| 嵌入式编译 | 跑编译、分析错误 | 确认工具链和硬件环境 |
| 硬件调试 | 分析日志、提出排查步骤 | 接线、上电、测量、烧录确认 |
| 机械臂控制 | 写仿真代码、检查限位逻辑 | 真实设备运动测试和安全监护 |
| 电源/电机 | 查手册、分析风险 | 实测电压电流，确认保护电路 |
| ROS/VLA | 写节点、分析 topic、生成接口 | 确认真机表现和实验结果 |
| 安全审查 | 找风险、列 checklist | 做最终安全判断 |
| Git 操作 | 建分支、生成 PR、总结 diff | 合并主分支、发布版本 |
| 文档 | 写 README、接口文档、报告 | 确认事实和实验数据 |

硬件调试推荐流程：

```text
AI 生成调试建议
  -> 人类查看检查清单
  -> 人类确认实验条件
  -> 人类手动执行硬件操作
  -> 人类上传日志、照片、测量数据或现象描述
  -> AI 分析结果
  -> AI 给出下一步建议
  -> 人类决定是否继续
```

禁止流程：

```text
AI 自动连接真实设备
AI 自动烧录固件
AI 自动让机械臂运动
AI 自动修改安全参数并部署到真机
AI 自动绕过测试和人工确认
```

硬件调试任务卡示例：

```text
任务: M33 电机 PWM 无输出

AI 建议检查:
[ ] 确认电源 24V 正常
[ ] 确认驱动 EN 引脚为高电平
[ ] 确认 MCU PWM 引脚复用配置
[ ] 示波器测量 PA8 是否有 PWM
[ ] 串口查看 motor_init 返回值

等待人类填写:
- PA8 波形:
- EN 引脚电压:
- 电机驱动板状态灯:
- 串口日志:
- 是否有异响/发热:
- 是否允许继续下一步:
```

### 3.6 Token 与密钥管理问题

不能把 token 直接保存在前端，也不能让每个 AI 直接看到完整密钥。

需要管理的密钥：

1. GitHub Token。
2. Git SSH Key。
3. OpenAI/Claude/Qwen/DeepSeek API Key。
4. OpenClaw/OpenHands 服务密钥。
5. 服务器 SSH Key。
6. 设备调试密码。
7. 数据库密码。
8. 对象存储密钥。

解决策略：

1. 前端永远不返回明文 token。
2. 后端加密保存 token。
3. 使用 Vault 或自建加密表。
4. token 按项目、AI、任务分配。
5. 支持 token 轮换。
6. 每次 token 使用记录审计日志。
7. AI 只能通过工具接口间接使用 token。
8. 任务结束后临时凭证失效。

### 3.7 需求管理库与 AI 通信问题

多 AI 协作时，如果每个 AI 都自由聊天、自由询问、自由读取上下文，会导致 token 急剧增加，并且沟通结果难以沉淀。更合理的方式是建立一个需求管理库，让 AI 之间通过结构化需求单进行沟通。

核心原则：

1. 每个 AI 不需要知道所有信息，只需要知道当前任务、自己职责、可联系的其他 AI、相关接口和相关历史结论。
2. AI 有需求时，不直接群发消息，也不读取全项目上下文，而是向指定负责 AI 提交需求单。
3. 平台先查知识库、接口契约库、历史需求库，只有找不到答案时才联系目标 AI。
4. 所有跨 AI 沟通都必须沉淀为可检索记录。
5. 重复出现的问题自动转为知识库条目。
6. 接口类结论进入接口契约库。
7. 架构类结论进入决策记录库。

需求单示例：

```json
{
  "id": "REQ-1024",
  "title": "ROS AI 需要 NanoPi 传感器数据格式",
  "from_agent": "AI11-PC1-ROS",
  "to_agent": "AI10-NanoPi-SDK",
  "project": "Medical-Rehabilitation-Manipulator",
  "module": "nanopi",
  "priority": "high",
  "status": "waiting_response",
  "context_summary": "ROS 节点需要发布传感器 topic，但缺少 NanoPi 输出字段定义。",
  "expected_output": "请给出字段名、单位、频率、异常值范围、示例数据。",
  "related_task": "TASK-231",
  "related_files": [
    "ros/nodes/sensor_bridge.cpp",
    "nanopi/sensor_server/"
  ],
  "max_response_tokens": 3000
}
```

需求路由流程：

```text
AI 提出需求
  -> 平台识别模块和需求类型
  -> 查询接口契约库
  -> 查询历史需求库
  -> 查询项目知识库
  -> 如果已有答案，返回摘要和引用
  -> 如果没有答案，路由给指定负责 AI
  -> 目标 AI 结构化回复
  -> 平台沉淀为需求记录、接口契约或决策记录
```

需求类型建议：

```text
code_request        代码修改需求
interface_request   接口/协议需求
hardware_request    硬件/设备需求
doc_request         文档需求
test_request        测试需求
security_request    安全审查需求
data_request        数据/模型需求
decision_request    架构决策需求
```

AI 通讯录只保存职责边界，不保存长对话：

```yaml
agents:
  AI10:
    name: NanoPi SDK 负责人
    computer: NanoPi-Dev-01
    modules:
      - nanopi
      - sensor_driver
      - device_log
    can_answer:
      - NanoPi 底层驱动问题
      - 传感器数据格式
      - 串口和网络通信
    contact_policy:
      request_type: structured_requirement
      max_context_tokens: 3000
```

AI 之间的通信格式应强制结构化：

```text
需求标题:
提出方:
接收方:
关联任务:
当前阻塞点:
已知信息:
需要对方提供:
期望输出格式:
优先级:
最长回复 token:
```

回复格式：

```text
结论:
可用方案:
需要修改的文件:
接口/参数:
风险:
下一步建议:
是否需要继续沟通:
```

该机制的目标是减少会议式沟通和大上下文复制，让 AI 像真实团队成员一样通过任务单、接口契约和决策记录协作。

### 3.8 AI 上下文过多与接手问题

长时间运行的 AI 容易出现上下文过多、注意力分散、回答质量下降的问题。表现包括：

1. 忘记最初目标。
2. 重复分析已经解决的问题。
3. 忽略最新约束。
4. 开始修改不相关文件。
5. 对代码结构产生错误判断。
6. 测试失败后盲目重试。
7. 输出变长但有效信息变少。

这个问题可以称为“上下文健康度下降”。平台需要提供上下文统计、压缩、交接和接手机制，防止 AI 因上下文过大而降智。

上下文统计指标：

```text
context_tokens_current       当前上下文 token
context_tokens_limit         当前模型上下文上限
context_usage_ratio          上下文占用比例
conversation_turns           当前任务对话轮数
files_loaded_count           已读取文件数量
irrelevant_context_ratio     估算无关上下文比例
repeated_question_count      重复问题次数
failed_retry_count           失败重试次数
last_summary_at              上次摘要时间
handoff_recommended          是否建议交接
```

上下文健康等级：

```text
green   0%-50%   正常，可继续执行
yellow  50%-70%  建议摘要压缩
orange  70%-85%  建议拆分任务或准备交接
red     85%+     强制生成交接包，建议切换 AI 或新会话
```

平台需要提供“AI 接手”能力。任何任务都应允许在中途切换执行 AI，例如：

1. 当前 AI token 消耗过高。
2. 当前 AI 上下文过长。
3. 当前 AI 连续失败。
4. 当前 AI 所属电脑离线。
5. 当前任务需要更强模型。
6. 当前任务需要更专业的负责 AI。
7. 人类手动指定其他 AI 接手。

交接包内容：

```json
{
  "task_id": "TASK-231",
  "handoff_from": "AI11-PC1-ROS",
  "handoff_to": "AI12-ROS-Node-2",
  "goal": "新增 NanoPi 传感器数据 ROS 发布节点",
  "current_status": "已完成 topic 设计，代码编译失败",
  "completed_steps": [
    "确认 NanoPi 数据字段",
    "新增 sensor_bridge.cpp 初版",
    "更新 launch 文件"
  ],
  "remaining_steps": [
    "修复编译错误",
    "补充测试脚本",
    "更新接口文档"
  ],
  "important_context": [
    "NanoPi 数据频率为 100Hz",
    "ROS topic 名称暂定 /rehab/sensors",
    "安全 AI 要求异常值必须限幅"
  ],
  "changed_files": [
    "ros/nodes/sensor_bridge.cpp",
    "ros/launch/sensor_bridge.launch"
  ],
  "current_branch": "ai/task-231-nanopi-ros-sensor",
  "last_error_summary": "编译失败，缺少 sensor_msgs 依赖声明",
  "do_not_repeat": [
    "不要重新设计 topic 名称，已确认",
    "不要修改 nanopi/sensor_server 目录"
  ]
}
```

接手流程：

```text
平台检测上下文健康度下降
  -> 当前 AI 生成交接摘要
  -> 平台保存交接包
  -> 人类或调度器选择接手 AI
  -> 接手 AI 只读取交接包、关键文件、最新 diff 和必要需求记录
  -> 接手 AI 继续在同一任务分支工作
  -> 平台保留完整审计记录
```

为了避免接手 AI 重读全部历史，平台应提供三层上下文：

```text
任务摘要层: 目标、进度、剩余事项、风险
证据引用层: 关键文件、关键 commit、关键需求单、关键日志
完整归档层: 原始对话、完整日志、完整 diff
```

默认只给接手 AI 前两层，只有必要时才打开完整归档层。

---

## 4. 总体架构

```text
用户浏览器
  |
  | HTTP/WebSocket
  v
前端 Web/PWA
  |
  v
后端 API 服务
  |-- PostgreSQL: 项目、任务、AI、权限、审计
  |-- Redis/NATS: 队列、实时状态
  |-- Secret Vault: token、key、凭证
  |-- MinIO: 日志、构建产物、固件、截图
  |-- Forgejo/Gitea: 本地 Git 协作层
  |-- Orchestrator: AI 调度器
          |
          | 任务派发
          v
      Agent Runner
          |-- PC Runner
          |-- NanoPi Runner
          |-- ROS Runner
          |-- OpenClaw Adapter
          |-- OpenHands Adapter
          |-- Codex Adapter
          |-- 本地模型 Adapter
```

---

## 5. 核心模块设计

### 5.1 项目管理模块

功能：

1. 创建项目。
2. 绑定 GitHub 仓库。
3. 绑定本地 Git 镜像仓库。
4. 配置项目类型：
   - 嵌入式。
   - ROS。
   - 机器人。
   - Web/App。
   - AI 模型训练。
5. 配置模块边界。
6. 配置默认分支、开发分支、发布分支。
7. 配置 CI 命令和测试命令。

项目字段示例：

```json
{
  "name": "Medical-Rehabilitation-Manipulator",
  "type": "embedded_robotics",
  "github_url": "https://github.com/xxx/xxx",
  "local_git_url": "ssh://git@gitea.local/team/project.git",
  "default_branch": "main",
  "develop_branch": "develop",
  "description": "康复机械臂项目"
}
```

### 5.2 AI 成员管理模块

AI 成员是平台核心对象。

字段：

```json
{
  "name": "AI11 - NanoPi ROS 主负责人",
  "host": "PC1",
  "agent_type": "openhands",
  "model": "gpt-5.4",
  "responsibility": "负责 NanoPi ROS 节点开发和运行状态监控",
  "allowed_projects": ["Medical-Rehabilitation-Manipulator"],
  "read_paths": ["ros/", "nanopi/", "docs/"],
  "write_paths": ["ros/nodes/", "docs/ros/"],
  "permission_level": "L2",
  "max_tokens_per_task": 100000,
  "max_cost_per_day": 20,
  "status": "active"
}
```

需要支持的 Agent 类型：

1. OpenHands。
2. OpenClaw。
3. Codex。
4. Claude Code。
5. CrewAI。
6. LangGraph 自定义 Agent。
7. 本地 Ollama/OpenAI compatible API。
8. 纯人工成员。

### 5.3 任务管理模块

任务是 AI 协作的最小调度单位。

任务状态：

```text
draft             草稿
ready             待执行
planning          AI 规划中
waiting_approval  等待计划确认
running           执行中
testing           测试中
reviewing         审查中
blocked           阻塞
failed            失败
merged            已合并
rolled_back       已回滚
cancelled         已取消
```

任务字段：

```json
{
  "title": "新增 NanoPi 传感器数据 ROS 发布节点",
  "project_id": "project_001",
  "priority": "high",
  "module": "ros",
  "assignees": ["AI11", "AI12"],
  "reviewers": ["AI3", "human_admin"],
  "branch": "ai/task-123-nanopi-ros-sensor",
  "related_issue": "#35",
  "acceptance_criteria": [
    "新增 ROS topic",
    "通过本地编译",
    "提供测试脚本",
    "更新文档"
  ]
}
```

### 5.4 Agent Runner 模块

每台电脑或开发板可部署 Runner。

Runner 负责：

1. 注册到平台。
2. 上报在线状态。
3. 接收任务。
4. 创建隔离工作区。
5. 拉取代码。
6. 调用指定 AI 工具。
7. 执行测试。
8. 采集日志。
9. 提交代码。
10. 回传结果。

Runner 类型：

```text
general-runner      普通代码任务
embedded-runner     嵌入式编译/烧录
ros-runner          ROS/仿真任务
doc-runner          文档/RAG 任务
hardware-runner     真实硬件任务
gpu-runner          AI 模型训练/推理任务
```

Runner 安全要求：

1. 每个任务独立工作目录。
2. 默认容器隔离。
3. 命令白名单。
4. 资源限制。
5. 硬件访问显式授权。
6. 任务结束清理临时凭证。

### 5.5 Git 集成模块

平台需要支持：

1. GitHub 仓库导入。
2. Forgejo/Gitea 镜像。
3. 分支创建。
4. commit 查询。
5. diff 展示。
6. PR/MR 创建。
7. tag 管理。
8. 回滚。
9. 冲突检测。

推荐流程：

```text
GitHub -> 本地 Gitea/Forgejo 镜像
AI Runner -> 从本地 Git 拉取
AI Runner -> 提交到 ai/task 分支
平台 -> 创建本地 MR
审查通过 -> 合并 develop
平台 -> 同步到 GitHub
稳定版本 -> 打 tag
```

### 5.6 知识库模块

知识库保存项目长期上下文，减少 token 消耗。

内容来源：

1. README。
2. 设计文档。
3. 芯片手册。
4. 原理图说明。
5. ROS 节点说明。
6. 接口协议。
7. 历史任务总结。
8. 代码结构摘要。
9. 编译错误经验库。
10. 机械臂安全规则。

知识库处理方式：

1. 文档切片。
2. 向量索引。
3. 元数据标记模块。
4. 版本绑定 commit。
5. AI 按任务检索相关上下文。

### 5.7 审查与测试模块

每个 AI 代码任务必须产出：

1. 修改文件列表。
2. diff 摘要。
3. 风险说明。
4. 测试命令。
5. 测试结果。
6. 回滚方式。

审查类型：

```text
code_review       代码审查
security_review   安全审查
hardware_review   硬件风险审查
doc_review        文档审查
ci_review         编译测试审查
```

嵌入式测试建议：

1. 编译检查。
2. 静态检查。
3. 单元测试。
4. 仿真测试。
5. 串口日志检查。
6. 硬件在环测试。
7. 人工确认后真实设备运行。

### 5.8 需求管理库模块

需求管理库用于替代 AI 之间无序聊天，是降低 token 消耗的关键模块。

核心功能：

1. 创建结构化需求单。
2. 自动识别需求模块和需求类型。
3. 根据 AI 职责库自动推荐接收方。
4. 支持 AI 对 AI 提需求。
5. 支持人类对 AI 提需求。
6. 支持需求阻塞、转派、升级、关闭。
7. 支持需求与任务、文件、commit、PR、接口契约关联。
8. 支持重复需求检测。
9. 支持需求关闭时自动生成摘要。
10. 支持把高价值结论沉淀到知识库。

需求状态：

```text
draft             草稿
routing           路由中
waiting_response  等待回复
answered          已回复
accepted          已采纳
rejected          已驳回
blocked           阻塞
escalated         已升级给人类或 AI-Boss
closed            已关闭
```

需求处理优先级：

```text
P0 阻塞主任务或硬件安全
P1 阻塞当前开发
P2 普通协作需求
P3 文档或低优先级优化
```

需求路由规则：

1. 如果需求涉及明确模块，优先找模块 owner AI。
2. 如果涉及接口，优先找接口 owner AI。
3. 如果涉及安全，必须抄送安全 AI。
4. 如果涉及硬件操作，必须进入人工审批。
5. 如果找不到负责人，交给项目管理 AI。
6. 如果需求重复，直接返回历史答案，不再消耗目标 AI token。

### 5.9 AI 接手与上下文健康模块

该模块负责监控 AI 的上下文状态，并允许其他 AI 随时接手任务。

核心功能：

1. 统计每个任务当前上下文 token。
2. 统计上下文占用比例。
3. 统计 AI 对话轮数、读取文件数、失败重试次数。
4. 对上下文健康度进行 green/yellow/orange/red 分级。
5. 达到阈值时自动要求 AI 生成任务摘要。
6. 达到高风险阈值时建议或强制交接。
7. 支持手动选择接手 AI。
8. 支持平台自动推荐接手 AI。
9. 支持同一任务分支继续执行，不丢失代码进度。
10. 支持交接包版本管理。

上下文健康规则建议：

```text
context_usage_ratio >= 50%:
  提醒生成短摘要

context_usage_ratio >= 70%:
  要求生成结构化任务进度摘要

context_usage_ratio >= 85%:
  强制生成交接包，建议切换新会话或新 AI

failed_retry_count >= 3:
  建议切换审查 AI 或更强模型

files_loaded_count >= 50:
  建议压缩文件摘要，禁止继续无目的读取

conversation_turns >= 30:
  建议进行任务总结和上下文清理
```

平台推荐接手 AI 时应考虑：

1. AI 职责是否匹配当前模块。
2. AI 所属 Runner 是否在线。
3. AI 当前任务负载。
4. AI 当前 token 预算剩余。
5. AI 历史成功率。
6. AI 是否有写入当前目录的权限。
7. 是否需要更强模型或更低成本模型。

交接包必须包含：

1. 任务目标。
2. 当前状态。
3. 已完成事项。
4. 未完成事项。
5. 关键决策。
6. 关键文件。
7. 当前分支。
8. 最新错误摘要。
9. 不要重复做的事情。
10. 风险和注意事项。

接手 AI 默认只读取：

1. 交接包。
2. 最新 diff。
3. 关键文件。
4. 相关需求单。
5. 相关接口契约。
6. 最新测试失败摘要。

除非接手 AI 明确申请，否则不加载完整历史对话。

---

## 6. 前端页面规划

### 6.1 首页/项目仪表盘

显示：

1. 项目列表。
2. 当前活跃任务。
3. 在线 AI。
4. Runner 状态。
5. Git 同步状态。
6. 待审核代码。
7. token 消耗排行。
8. 最近失败任务。

### 6.2 AI 成员页面

功能：

1. 新增 AI。
2. 编辑 AI 职责。
3. 设置所属电脑。
4. 设置模型。
5. 设置 token。
6. 设置权限。
7. 查看 token 消耗。
8. 暂停/启用 AI。
9. 查看 AI 历史任务。

### 6.3 任务页面

功能：

1. 创建任务。
2. 指派 AI。
3. 查看 AI 计划。
4. 审批计划。
5. 查看执行日志。
6. 查看 diff。
7. 触发复审。
8. 合并或退回。

### 6.4 Git 页面

功能：

1. 查看分支。
2. 查看 commit。
3. 查看 PR/MR。
4. 查看同步状态。
5. 一键同步 GitHub。
6. 一键回滚到指定 commit。

### 6.5 Runner 页面

功能：

1. 查看电脑/开发板在线状态。
2. 查看 CPU、内存、磁盘。
3. 查看当前任务。
4. 查看支持能力。
5. 配置硬件权限。
6. 查看最近错误。

### 6.6 成本与资源页面

功能：

1. token 消耗统计。
2. 模型费用统计。
3. 服务器资源统计。
4. Runner 负载统计。
5. 项目预算告警。
6. AI 成功率排行。

### 6.7 需求中心页面

功能：

1. 查看所有需求单。
2. 查看 AI 提出的需求。
3. 查看人类提出的需求。
4. 查看阻塞中的需求。
5. 按模块、负责人、优先级、状态筛选。
6. 创建结构化需求。
7. 自动推荐接收 AI。
8. 查看需求关联的任务、文件、commit、PR。
9. 将需求结论沉淀为知识库、接口契约或决策记录。
10. 查看重复需求和历史答案。

### 6.8 AI 上下文健康页面

功能：

1. 查看每个运行中任务的上下文 token。
2. 查看上下文占用比例。
3. 查看任务对话轮数。
4. 查看已读取文件数量。
5. 查看失败重试次数。
6. 查看上下文健康等级。
7. 一键生成任务摘要。
8. 一键生成交接包。
9. 一键选择其他 AI 接手。
10. 查看历史交接记录。
11. 查看哪些 AI 正在接近上下文上限。
12. 设置自动交接阈值。

### 6.9 游戏化前端与 AI 团队养成界面

平台前端可以采用“AI 研发公司模拟器”或“AI 打工团队养成经营游戏”的表达方式，让复杂开发流程更直观、更有趣，也方便后续宣传和产品传播。

但游戏化只是表现层，底层仍然必须对应真实工程数据。产品叙事应明确：

```text
你不是被 AI 替代，而是成为 AI 研发团队的总工程师。
AI-Boss 不是最终老板，而是 AI 团队主管。
人类工程师负责关键决策、硬件调试、安全确认和最终发布。
AI 员工负责分析、整理、编码、审查、文档和建议。
```

推荐主界面不是传统表格 dashboard，而是一个“研发基地”：

```text
老板办公室:
  项目总览、预算、风险、重大决策、人类确认点。

任务大厅:
  所有需求、阻塞任务、待分配任务、AI 派单队列。

AI 工位区:
  每个 AI 的状态、职责、所属电脑、上下文健康、当前任务。

代码车间:
  分支、commit、PR、测试流水线、合并状态。

硬件实验室:
  开发板、串口、烧录任务、机械臂、仿真状态、硬件调试清单。

会议室:
  AI 之间的结构化需求沟通、需求单、接口确认。

档案室:
  知识库、接口契约、决策记录、芯片手册、原理图说明。

财务室:
  token 消耗、模型费用、服务器成本、预算告警。

急救站/维修站:
  失败任务、上下文过载、降智风险、AI 接手、回滚操作。
```

AI 角色卡设计：

```text
AI-Boss
职位: AI 团队主管
职责: 任务拆分、人员调度、风险升级
状态: 在线
当前事件: M33 编译失败，需要安排复审 AI
权限: 不允许直接操作硬件，不允许自动合并主分支

AI11 - NanoPi ROS 主负责人
职位: ROS 工程师
所属电脑: PC1
职责: ROS 节点、topic、运行状态
技能: ROS 4/5, C++ 3/5, 调试 4/5
上下文健康: 黄色 63%
当前任务: 新增传感器发布节点
建议: 30 分钟内生成摘要，避免上下文过长

AI3 - 安全检测 AI
职位: 安全主管
职责: 机械臂限位、急停、电源风险
权限: 只读 + 审查
当前状态: 等待审查 2 个 PR
```

AI 状态条建议：

```text
精力条:
  当前任务负载。

上下文条:
  当前上下文 token 占用比例。

预算条:
  今日 token 和模型费用消耗。

专注度:
  当前任务是否清晰，是否出现重复分析。

风险灯:
  是否涉及硬件、安全、主分支、密钥或生产环境。
```

AI 状态颜色：

```text
绿色: 正常工作中。
黄色: 上下文偏多，建议摘要。
橙色: 连续失败，建议复审或交接。
红色: 上下文过载或高风险，必须人工处理。
灰色: Runner 离线。
蓝色: 等待其他 AI 回复需求。
紫色: 等待人类审批。
```

游戏化属性必须映射真实工程指标：

| 游戏化名称 | 真实工程含义 |
|---|---|
| 等级 | 历史任务成功率、模块经验 |
| 体力/精力 | 当前负载、任务数量、上下文占用 |
| 金币/预算 | token 成本、服务器成本 |
| 技能 | 模型能力、工具权限、模块熟练度 |
| 装备 | MCP 工具、编译器、硬件设备、知识库 |
| 工位 | Runner、电脑、开发板 |
| 任务 | issue、requirement、bug、测试任务 |
| 副本 | 一个开发迭代或功能开发任务 |
| Boss 战 | 发布前集成测试、硬件联调、安全评审 |
| 交接班 | handoff package |
| 事故 | 测试失败、Git 冲突、安全风险、硬件异常 |

AI 成长属性：

```text
专业度:
  某个模块的成功经验，例如 ROS、M33、NanoPi、App。

可靠性:
  任务成功率、测试通过率、回滚率、PR 返工率。

沟通力:
  需求单质量、是否找对负责人、回复是否结构化。

成本控制:
  平均 token 消耗、是否优先查知识库、是否重复提问。

上下文管理:
  是否及时摘要、是否容易进入红色上下文区。

安全意识:
  是否触发危险操作、是否主动要求人工确认。

协作指数:
  被其他 AI 采纳的需求数量、协助解决阻塞次数。
```

成长规则示例：

```text
完成 10 次 ROS 任务:
  ROS 专业度 +1。

连续 5 次 PR 无需返工:
  可靠性 +1。

重复问同一个问题 3 次:
  沟通力下降。

上下文红区仍继续乱改:
  触发降智风险警告。

节省 30% token 完成任务:
  成本控制 +1。

主动请求人类确认硬件风险:
  安全意识 +1。
```

事件系统：

```text
突发事件: ROS 编译失败
影响: AI11 当前任务阻塞
建议行动:
- 派 AI12 复查 CMakeLists
- 联系 NanoPi AI 确认数据结构
- 让安全 AI 检查异常值处理

突发事件: AI11 上下文达到 82%
影响: 继续执行可能质量下降
建议行动:
- 生成交接包
- 让 AI13 接手
- 压缩历史上下文

突发事件: token 消耗异常
影响: 今日预算已使用 78%
建议行动:
- 启用小模型摘要
- 暂停低优先级任务
- 合并重复需求

突发事件: 硬件调试需要人工确认
影响: AI 不能继续执行真实设备步骤
建议行动:
- 人类检查接线
- 人类测量电压和波形
- 上传串口日志和照片
```

AI 沟通可以表现为“公司内信”或“内部工单”，但底层仍然是结构化需求单：

```text
AI11 向 AI10 发出需求:
请确认 NanoPi 传感器数据字段。

AI10 回复:
字段定义如下，频率 100Hz，异常值范围如下。

系统提示:
该结论已沉淀为接口契约 nanopi_sensor_stream v0.2。
```

每日战报：

```text
今日 AI 团队日报

完成任务: 8 个
新增 commit: 14 个
通过测试: 11 次
失败任务: 2 个
token 消耗: 36.8 元
节省人工会议: 预计 2.5 小时
最高效 AI: AI10 NanoPi SDK
风险最高模块: ROS 与硬件接口
明日建议: 优先处理 M33 编译链路和传感器接口契约
```

前端视觉风格建议：

1. 不做过度幼稚的卡通，避免影响工程可信度。
2. 推荐“像素风研发基地 + 工业控制台 + 科技实验室”的混合风格。
3. 使用 AI 工位、状态灯、任务公告板、代码流水线、机械臂实验室等视觉元素。
4. 动画应服务状态表达，不能影响操作效率。
5. 手机端优先显示任务、审批、AI 状态和告警。
6. 电脑端展示完整研发基地地图和多面板数据。
7. 开发板端提供轻量状态页，只显示 Runner、任务、硬件调试清单和日志上传入口。

宣传卖点：

```text
不是一个 AI 助手，而是一支可管理的 AI 研发团队。
像经营研发公司一样管理 AI 工程师。
人类是总工程师，AI 是可调度的研发小队。
让嵌入式项目开发变得可视化、可追踪、可协作、可回滚。
```

---

## 7. 后端 API 初步设计

### 7.1 项目 API

```text
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
POST   /api/projects/{id}/sync-github
POST   /api/projects/{id}/rollback
```

### 7.2 AI 成员 API

```text
GET    /api/agents
POST   /api/agents
GET    /api/agents/{id}
PATCH  /api/agents/{id}
POST   /api/agents/{id}/enable
POST   /api/agents/{id}/disable
GET    /api/agents/{id}/usage
```

### 7.3 任务 API

```text
GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/{id}
PATCH  /api/tasks/{id}
POST   /api/tasks/{id}/plan
POST   /api/tasks/{id}/approve-plan
POST   /api/tasks/{id}/run
POST   /api/tasks/{id}/cancel
POST   /api/tasks/{id}/review
POST   /api/tasks/{id}/merge
POST   /api/tasks/{id}/rollback
```

### 7.4 Runner API

```text
POST   /api/runners/register
POST   /api/runners/heartbeat
GET    /api/runners
GET    /api/runners/{id}
PATCH  /api/runners/{id}
POST   /api/runners/{id}/pause
POST   /api/runners/{id}/resume
```

### 7.5 Token 与成本 API

```text
GET    /api/usage/summary
GET    /api/usage/by-agent
GET    /api/usage/by-project
GET    /api/usage/by-model
POST   /api/secrets
PATCH  /api/secrets/{id}
POST   /api/secrets/{id}/rotate
```

### 7.6 需求管理 API

```text
GET    /api/requirements
POST   /api/requirements
GET    /api/requirements/{id}
PATCH  /api/requirements/{id}
POST   /api/requirements/{id}/route
POST   /api/requirements/{id}/respond
POST   /api/requirements/{id}/accept
POST   /api/requirements/{id}/escalate
POST   /api/requirements/{id}/close
POST   /api/requirements/{id}/promote-to-knowledge
GET    /api/requirements/similar
```

### 7.7 上下文健康与 AI 接手 API

```text
GET    /api/tasks/{id}/context-health
POST   /api/tasks/{id}/summarize-context
POST   /api/tasks/{id}/create-handoff
GET    /api/tasks/{id}/handoffs
GET    /api/tasks/{id}/handoffs/{handoff_id}
POST   /api/tasks/{id}/handoffs/{handoff_id}/accept
POST   /api/tasks/{id}/handoffs/{handoff_id}/assign-agent
GET    /api/agents/handoff-candidates
PATCH  /api/projects/{id}/context-policy
```

---

## 8. 数据库核心表

```text
users
teams
projects
repositories
agents
agent_credentials
runners
runner_capabilities
tasks
task_events
task_artifacts
task_reviews
git_branches
git_commits
pull_requests
knowledge_documents
knowledge_chunks
requirements
requirement_messages
requirement_links
interface_contracts
decision_records
context_health_snapshots
handoff_packages
handoff_events
usage_logs
audit_logs
secrets
permissions
```

重点：

1. `audit_logs` 必须记录所有敏感操作。
2. `usage_logs` 必须记录 token 和费用。
3. `task_events` 必须记录任务全过程，方便追溯。
4. `secrets` 只保存加密内容，不返回明文。

---

## 9. 部署方案

### 9.1 MVP Docker Compose

服务：

```text
frontend
backend
postgres
redis
gitea
minio
orchestrator
runner-general
```

建议端口：

```text
80/443   前端入口
8000     后端 API
3000     前端开发服务
5432     PostgreSQL 内部
6379     Redis 内部
3001     Gitea/Forgejo
9000     MinIO API
9001     MinIO Console
```

### 9.2 网络建议

1. 实验室局域网内部署。
2. 外网访问通过 VPN、ZeroTier、Tailscale 或 WireGuard。
3. 不建议直接把 Runner 暴露到公网。
4. 硬件 Runner 只允许从平台服务主动拉任务，避免公网直接访问设备。

### 9.3 备份策略

必须备份：

1. PostgreSQL。
2. Gitea/Forgejo 仓库数据。
3. MinIO 构建产物和日志。
4. Secret Vault。
5. 平台配置文件。

备份频率：

```text
数据库: 每日快照 + 每小时增量
Git 仓库: 每日快照 + GitHub 远程同步
MinIO: 每日快照
Secrets: 每次变更后备份
```

---

## 10. 嵌入式项目适配

### 10.1 机械臂项目模块模板

```text
管理层:
  AI-Boss
  项目管理 AI
  安全 AI

硬件接口层:
  OpenClaw 对接 AI
  芯片文档 AI
  PCB 文档 AI

嵌入式层:
  M33 主负责人 AI
  M33 复审 AI
  M55 主负责人 AI
  M55 复审 AI
  C8T6 主负责人 AI
  C8T6 复审 AI

边缘计算层:
  NanoPi SDK AI
  NanoPi ROS AI
  ROS 节点 AI

上位机层:
  PC1 ROS AI
  运动仿真 AI
  VLA 对接 AI
  服务器 AI

模型层:
  小模型训练 AI
  VLA 模型 AI
  数据管理 AI

应用层:
  手机 App AI
  通信检测 AI

文档与商业:
  文档 AI
  PPT AI
  市场调研 AI
```

### 10.2 硬件任务审批规则

以下任务必须人工审批：

1. 烧录固件。
2. 修改电机控制参数。
3. 修改限位、急停、安全保护逻辑。
4. 访问真实机械臂。
5. 控制电源、电机、舵机、执行器。
6. 删除或覆盖设备配置。
7. 修改生产环境服务器。

---

## 11. MVP 开发路线

### 阶段 1：基础平台

目标：能管理项目、AI、任务、Runner。

功能：

1. 登录和用户管理。
2. 项目管理。
3. AI 成员管理。
4. Runner 注册和心跳。
5. 任务创建和状态流转。
6. 基础日志查看。

### 阶段 2：Git 与任务执行

目标：AI 可以基于任务创建分支并提交代码。

功能：

1. Gitea/Forgejo 集成。
2. GitHub 镜像。
3. 分支创建。
4. Runner 拉取任务。
5. AI 执行命令。
6. 提交 commit。
7. diff 展示。

### 阶段 3：审查、测试和成本控制

目标：平台可以安全管理多 AI 协作。

功能：

1. 自动测试。
2. AI 代码审查。
3. 人工审批。
4. token 统计。
5. 预算限制。
6. 权限系统。
7. 审计日志。

### 阶段 4：嵌入式增强

目标：适配机械臂和嵌入式开发。

功能：

1. 交叉编译任务。
2. 串口日志采集。
3. 固件产物管理。
4. ROS 节点状态。
5. 仿真测试。
6. 硬件操作审批。
7. OpenClaw 接入。

### 阶段 5：产品化

目标：可交付给其他团队使用。

功能：

1. 多组织。
2. 项目模板。
3. AI 角色模板。
4. 插件系统。
5. 安装向导。
6. 监控面板。
7. 私有化部署包。

---

## 12. 推荐开源参考

1. Gitea：轻量自托管 Git 服务，适合作为本地 Git 协作层。
2. Forgejo：Gitea 分支，适合自托管和仓库镜像。
3. OpenHands：AI 软件开发 Agent，可作为代码执行 Agent。
4. LangGraph：适合构建有状态、多步骤、human-in-the-loop 的 Agent 工作流。
5. CrewAI：适合快速定义角色型 AI 团队。
6. AutoGen：适合研究多 Agent 对话协作。
7. GitHub MCP Server：适合让 AI 受控访问 GitHub。
8. Model Context Protocol Servers：适合设计工具接入标准。
9. MinIO：适合保存日志、构建产物、固件。
10. Grafana/Prometheus/Loki：适合监控和日志分析。

---

## 13. 关键风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| token 成本过高 | 使用成本不可控 | 预算、缓存、摘要、小模型分层 |
| AI 自由沟通导致 token 浪费 | 成本增加，结论难追踪 | 需求管理库、职责路由、结构化回复 |
| AI 上下文过长导致降智 | 任务质量下降，错误修改增加 | 上下文健康统计、摘要压缩、AI 接手 |
| 过度宣传 AI 自动开发 | 用户误解产品边界，硬件场景存在安全风险 | 明确人类主导，AI 辅助，硬件调试必须人工确认 |
| 游戏化界面喧宾夺主 | 降低工程效率和专业可信度 | 所有游戏化元素必须映射真实工程数据 |
| AI 误改代码 | 项目不稳定 | 分支隔离、审查、测试、人类审批 |
| AI 操作硬件 | 设备和人员风险 | 硬件权限单独审批，默认仿真 |
| token 泄漏 | 安全事故 | Vault、加密、最小权限、审计 |
| Git 分支混乱 | 合并困难 | 平台统一创建任务分支 |
| 服务器压力大 | 平台卡顿 | Runner 分布式、任务队列、资源限制 |
| GitHub 不稳定 | 开发受阻 | 本地 Git 镜像 |
| 日志过多 | 存储和 token 浪费 | 日志分级、摘要、对象存储 |
| 多 AI 重复工作 | 成本浪费 | 任务锁、模块边界、状态同步 |

---

## 14. 第一版最小可行产品定义

第一版只需要做到：

1. Web 前端可访问。
2. 可以创建项目。
3. 可以添加 AI 成员。
4. 可以配置 AI 所属电脑、模型、职责、token 状态、权限。
5. 可以创建任务并指派给 AI。
6. Runner 可以接收任务并回传日志。
7. 可以接入本地 Git 仓库。
8. AI 可以在任务分支生成代码变更。
9. 前端可以查看 diff。
10. 人工确认后合并。
11. 记录 token 消耗和任务日志。
12. 支持按 commit 回滚。
13. 支持需求管理库，AI 可以向指定负责 AI 提交结构化需求。
14. 支持 AI 通讯录和职责路由。
15. 支持上下文 token 统计和健康等级显示。
16. 支持手动生成交接包，并指定其他 AI 接手任务。
17. 前端提供基础游戏化研发基地界面，包括 AI 工位、任务大厅、代码车间、硬件实验室、财务室。
18. 前端明确展示人类确认点，硬件调试任务必须等待人类填写测量结果和确认。

暂时不做：

1. 自动控制真实机械臂。
2. 完整计费系统。
3. 复杂插件市场。
4. 移动 App。
5. 完整 Kubernetes 部署。
6. AI 自动合并主分支。
7. 复杂 3D 游戏场景。
8. 与真实机械臂的自动运动控制。

---

## 15. 总结

该平台的核心价值是把 AI 从“单次对话工具”升级为“可管理、可审查、可追踪、可回滚的项目成员”。

对于康复机械臂这类项目，平台必须同时服务软件开发、嵌入式开发、硬件调试、ROS 仿真、模型训练和文档协作。因此第一版架构应保持务实：

```text
Next.js 前端
+ FastAPI 后端
+ PostgreSQL
+ Redis
+ Gitea/Forgejo
+ MinIO
+ LangGraph 调度器
+ 多 Agent Runner
+ OpenHands/OpenClaw/Codex Adapter
+ 需求管理库
+ 上下文健康与 AI 接手机制
+ 游戏化研发基地前端
```

这样既能快速启动，也能逐步扩展成产品化平台。

最终产品表达应保持清晰：

```text
人类是总工程师。
AI 是可管理的研发小队。
硬件调试和安全决策必须由人类完成。
游戏化界面让开发更直观、更有趣，但不削弱工程安全和审查流程。
```
