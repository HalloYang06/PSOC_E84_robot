# AI 协作开发平台具体开发流程

版本：v0.1  
定位：研发执行手册  
关联文档：`AI协作平台开发文档.md`

长期需求规划见：`AI协作平台需求详细设计与未来规划.md`

当前执行范围以 `AI协作平台第一版开发入口.md` 为准。第一版先跑通核心闭环，长期规划中的增强功能暂缓开发。

---

## 1. 开发总原则

本平台采用“人类工程师主导，AI 团队辅助协作”的开发模式。

开发过程中必须遵守：

1. 人类负责产品方向、架构确认、安全边界、硬件调试、最终合并和发布。
2. AI 负责需求整理、方案建议、代码初稿、日志分析、测试建议、文档生成和审查辅助。
3. 所有 AI 代码修改必须进入任务分支，不能直接修改主分支。
4. 所有硬件相关操作必须有人类确认点。
5. 真实机械臂、电机、电源、烧录、串口写操作默认不允许 AI 自动执行。
6. token、密钥、服务器权限必须由平台托管，不直接暴露给 AI。
7. 平台所有关键操作必须有审计日志。

---

## 2. 总体开发阶段

平台建议分 6 个阶段开发：

```text
阶段 0: 项目初始化
阶段 1: 基础 Web 平台
阶段 2: Git 和任务协作
阶段 3: AI Runner 和 Agent 接入
阶段 4: 需求管理库与上下文健康
阶段 5: 嵌入式/硬件调试能力
阶段 6: 游戏化前端和产品化增强
```

每个阶段都必须有可运行版本，避免长期只做架构不落地。

---

## 3. 阶段 0：项目初始化

### 3.1 目标

建立代码仓库、开发规范、基础目录和本地运行环境。

### 3.2 推荐技术栈

```text
前端:
  Next.js
  React
  TypeScript
  Tailwind CSS
  PWA

后端:
  FastAPI
  Python
  SQLAlchemy 或 SQLModel
  Alembic

数据库:
  PostgreSQL

队列:
  Redis

Git 服务:
  Gitea 或 Forgejo

对象存储:
  MinIO

Agent 编排:
  LangGraph

部署:
  Docker Compose
```

### 3.3 仓库结构建议

```text
ai-collab-platform/
  apps/
    web/                    前端
    api/                    后端 API
    orchestrator/           AI 调度器
    runner/                 Agent Runner
  packages/
    shared/                 共享类型和工具
    ui/                     前端组件库
    sdk/                    Runner/Agent SDK
  infra/
    docker-compose.yml
    nginx/
    postgres/
    gitea/
    minio/
  docs/
    product/
    architecture/
    api/
    deployment/
  scripts/
  README.md
```

### 3.4 初始化步骤

1. 创建 Git 仓库。
2. 创建 `main` 和 `develop` 分支。
3. 初始化前端项目。
4. 初始化后端项目。
5. 编写 Docker Compose。
6. 启动 PostgreSQL、Redis、Gitea、MinIO。
7. 增加基础 README。
8. 增加 `.env.example`。
9. 配置基础 CI：
   - 前端 lint。
   - 后端测试。
   - Docker build 检查。

### 3.5 验收标准

```text
[ ] 前端可以打开首页
[ ] 后端健康检查接口可访问
[ ] PostgreSQL 可连接
[ ] Redis 可连接
[ ] Gitea/Forgejo 可访问
[ ] MinIO 可访问
[ ] Docker Compose 一键启动
[ ] README 有本地启动说明
```

---

## 4. 阶段 1：基础 Web 平台

### 4.1 目标

完成用户、项目、AI 成员、Runner 的基础管理页面。

### 4.2 后端功能

需要实现：

```text
用户管理:
  登录
  用户列表
  用户角色

项目管理:
  创建项目
  编辑项目
  项目列表
  项目详情

AI 成员管理:
  创建 AI
  编辑 AI
  设置职责
  设置所属电脑
  设置模型
  设置权限等级
  启用/停用 AI

Runner 管理:
  Runner 注册
  Runner 心跳
  Runner 能力上报
  Runner 在线状态
```

### 4.3 前端页面

第一版页面：

```text
/login
/projects
/projects/:id
/agents
/agents/:id
/runners
/settings
```

### 4.4 数据库表

优先实现：

```text
users
projects
agents
runners
runner_capabilities
audit_logs
```

### 4.5 开发流程

1. 后端先定义数据模型。
2. 写数据库 migration。
3. 写 CRUD API。
4. 前端接 API。
5. 加基础表单校验。
6. 加审计日志。
7. 做最小权限控制。

### 4.6 验收标准

```text
[ ] 可以创建项目
[ ] 可以添加 AI 成员
[ ] 可以编辑 AI 职责、模型、所属电脑
[ ] 可以注册 Runner
[ ] Runner 离线/在线状态能显示
[ ] 所有创建和修改操作进入审计日志
```

---

## 5. 阶段 2：Git 和任务协作

### 5.1 目标

让平台具备项目任务、Git 分支、commit、diff、PR/MR 的基础协作能力。

### 5.2 任务管理流程

```text
人类创建任务
  -> 选择项目
  -> 填写目标和验收标准
  -> 选择模块
  -> 指派 AI 或人类
  -> 平台创建任务记录
  -> 平台创建任务分支
  -> Runner 或人类执行
  -> 提交代码
  -> 平台展示 diff
  -> 审查
  -> 合并或退回
```

### 5.3 任务状态

```text
draft             草稿
ready             待执行
planning          规划中
waiting_approval  等待确认
running           执行中
testing           测试中
reviewing         审查中
blocked           阻塞
failed            失败
merged            已合并
rolled_back       已回滚
cancelled         已取消
```

### 5.4 Git 流程

分支规则：

```text
main                    稳定版本
develop                 日常开发
ai/task-任务号-简短名     AI 任务分支
human/task-任务号-简短名  人类任务分支
hotfix/问题名            紧急修复
release/版本号           发布分支
```

每个任务必须绑定一个分支。

### 5.5 GitHub 与本地 Git

推荐流程：

```text
GitHub 远程仓库
  -> Gitea/Forgejo 本地镜像
  -> AI Runner 从本地镜像拉代码
  -> AI 提交到本地任务分支
  -> 平台审查
  -> 合并 develop
  -> 同步到 GitHub
```

### 5.6 后端功能

需要实现：

```text
任务 CRUD
任务状态流转
创建任务分支
查询分支
查询 commit
查询 diff
创建本地 MR
同步 GitHub
回滚到指定 commit
```

### 5.7 前端页面

```text
/tasks
/tasks/:id
/projects/:id/git
/projects/:id/commits
/projects/:id/branches
/projects/:id/reviews
```

### 5.8 验收标准

```text
[ ] 可以创建任务
[ ] 任务可以绑定 AI
[ ] 平台可以创建任务分支
[ ] 可以展示 commit 和 diff
[ ] 可以提交审查
[ ] 可以合并或退回
[ ] 可以按 commit 回滚
```

---

## 6. 阶段 3：AI Runner 和 Agent 接入

### 6.1 目标

让不同电脑、服务器、开发板上的 Runner 能接收任务，并调用不同 AI 工具执行。

### 6.2 Runner 工作流程

```text
Runner 启动
  -> 向平台注册
  -> 定时发送心跳
  -> 上报能力
  -> 拉取待执行任务
  -> 创建隔离工作区
  -> 拉取任务分支
  -> 调用指定 Agent
  -> 采集日志
  -> 运行测试
  -> 提交代码或 patch
  -> 回传结果
```

### 6.3 Runner 类型

```text
general-runner      普通代码任务
embedded-runner     嵌入式编译
ros-runner          ROS/仿真
doc-runner          文档和知识库
hardware-runner     硬件调试辅助
gpu-runner          模型训练/推理
```

### 6.4 Agent Adapter

每种 AI 工具通过 Adapter 接入：

```text
OpenHandsAdapter
OpenClawAdapter
CodexAdapter
ClaudeCodeAdapter
OllamaAdapter
OpenAICompatibleAdapter
CustomHttpAgentAdapter
```

Adapter 统一输入：

```json
{
  "task_id": "TASK-001",
  "project_path": "/workspace/project",
  "branch": "ai/task-001-demo",
  "goal": "修复 ROS 编译错误",
  "context": {
    "summary": "当前任务摘要",
    "related_files": [],
    "requirements": [],
    "constraints": []
  },
  "permissions": {
    "can_write": true,
    "can_run_tests": true,
    "can_access_hardware": false
  }
}
```

Adapter 统一输出：

```json
{
  "status": "success",
  "summary": "完成的工作摘要",
  "changed_files": [],
  "test_commands": [],
  "test_results": [],
  "risk_notes": [],
  "next_steps": []
}
```

### 6.5 安全限制

Runner 必须限制：

1. 工作目录隔离。
2. 命令白名单。
3. 环境变量最小化。
4. token 临时注入。
5. 任务结束清理凭证。
6. 禁止默认访问真实硬件。
7. 禁止强制推送主分支。
8. 禁止执行危险删除命令。

### 6.6 验收标准

```text
[ ] Runner 可以注册和心跳
[ ] Runner 可以领取任务
[ ] Runner 可以创建工作区
[ ] Runner 可以调用至少一种 AI Agent
[ ] Runner 可以回传日志和结果
[ ] Runner 可以提交 patch 或 commit
[ ] Runner 执行过程有审计记录
```

---

## 7. 阶段 4：需求管理库与上下文健康

### 7.1 目标

解决 token 消耗严重、AI 乱沟通、上下文过长导致降智的问题。

### 7.2 需求管理流程

```text
AI 或人类提出需求
  -> 平台生成结构化需求单
  -> 平台识别模块和需求类型
  -> 优先查询知识库、接口契约、历史需求
  -> 如果已有答案，直接返回摘要
  -> 如果没有答案，路由给负责 AI
  -> 负责 AI 结构化回复
  -> 平台沉淀结论
```

### 7.3 需求单字段

```text
标题
提出方
接收方
关联项目
关联任务
关联模块
当前阻塞点
已知信息
期望输出
优先级
最长回复 token
状态
```

### 7.4 AI 通讯录

每个 AI 需要配置：

```text
姓名
职位
所属电脑
负责模块
可回答问题
不可回答问题
可联系范围
默认回复 token 限制
权限等级
```

### 7.5 上下文健康统计

每个运行任务统计：

```text
当前上下文 token
模型上下文上限
上下文占用比例
对话轮数
读取文件数量
失败重试次数
重复问题次数
上次摘要时间
是否建议交接
```

### 7.6 上下文健康等级

```text
green   0%-50%   正常
yellow  50%-70%  建议摘要
orange  70%-85%  建议准备交接
red     85%+     强制生成交接包
```

### 7.7 AI 接手流程

```text
平台检测上下文过长或 AI 连续失败
  -> 当前 AI 生成交接包
  -> 平台推荐接手 AI
  -> 人类确认或平台自动分配
  -> 接手 AI 读取交接包、关键文件和最新 diff
  -> 接手 AI 继续在同一任务分支执行
```

### 7.8 交接包内容

```text
任务目标
当前状态
已完成事项
未完成事项
关键文件
关键决策
当前分支
最新错误摘要
不要重复做的事情
风险提醒
```

### 7.9 验收标准

```text
[ ] AI 可以提交结构化需求单
[ ] 平台可以自动推荐接收 AI
[ ] 需求可以沉淀到知识库或接口契约
[ ] 任务详情显示上下文健康
[ ] 上下文超过阈值可以生成交接包
[ ] 可以指定其他 AI 接手
```

---

## 8. 阶段 5：嵌入式和硬件调试能力

### 8.1 目标

支持嵌入式编译、日志分析、硬件调试辅助，但不让 AI 自动接管真实设备。

### 8.2 嵌入式任务类型

```text
firmware_build       固件编译
static_check         静态检查
serial_log_analyze   串口日志分析
datasheet_qa         芯片手册问答
schematic_review     原理图审查
ros_build            ROS 编译
simulation_test      仿真测试
hardware_checklist   硬件调试清单
firmware_flash       固件烧录，必须人工确认
real_device_test     真机测试，必须人工确认
```

### 8.3 硬件调试流程

```text
人类创建硬件调试任务
  -> AI 分析代码、日志、手册
  -> AI 生成调试检查清单
  -> 人类执行接线、测量、上电、烧录
  -> 人类上传测量结果、照片、串口日志
  -> AI 分析结果
  -> AI 生成下一步建议
  -> 人类确认是否继续
```

### 8.4 人类确认点

必须人工确认：

```text
烧录固件
修改电机控制参数
访问真实机械臂
执行机械臂运动
修改限位和急停逻辑
连接电源和电机
删除设备数据
修改生产服务器配置
```

### 8.5 硬件调试任务卡

前端任务卡字段：

```text
任务名称
设备名称
设备位置
相关代码分支
AI 建议检查项
人类测量结果
上传照片
上传串口日志
风险确认
是否允许下一步
```

### 8.6 验收标准

```text
[ ] 可以创建嵌入式编译任务
[ ] 可以上传和分析串口日志
[ ] 可以生成硬件调试清单
[ ] 固件烧录任务必须出现人工确认
[ ] 真机测试任务必须出现人工确认
[ ] AI 不能绕过确认点继续执行
```

---

## 9. 阶段 6：游戏化前端和产品化增强

### 9.1 目标

把平台前端做成“AI 研发团队养成经营界面”，让开发管理更直观、更有传播性。

### 9.2 主界面区域

```text
老板办公室        项目总览、预算、风险、人类确认点
任务大厅          需求、阻塞、派单、待办
AI 工位区         AI 状态、职责、上下文、当前任务
代码车间          分支、commit、PR、测试流水线
硬件实验室        开发板、串口、烧录、调试清单
会议室            AI 需求单、内部工单、接口确认
档案室            知识库、接口契约、决策记录
财务室            token、模型费用、服务器成本
急救站            失败任务、上下文爆炸、AI 接手
```

### 9.3 游戏化规则

所有游戏化元素必须映射真实工程数据：

```text
等级 = 任务成功率和模块经验
体力 = 当前负载和上下文占用
金币 = token 和服务器成本
技能 = 模型能力、模块熟练度、工具权限
装备 = MCP 工具、编译器、硬件设备
工位 = Runner 或电脑
任务 = issue 或 requirement
事故 = 测试失败、Git 冲突、安全风险
交接班 = handoff package
```

### 9.4 第一版游戏化范围

第一版只做轻量游戏化：

1. 研发基地地图。
2. AI 角色卡。
3. 状态灯。
4. 上下文条。
5. token 预算条。
6. 任务事件弹窗。
7. 每日战报。
8. 硬件实验室确认卡。

暂时不做：

1. 复杂 3D 场景。
2. 复杂角色动画。
3. 抽卡系统。
4. 与真实开发无关的数值养成。

### 9.5 验收标准

```text
[ ] 首页展示研发基地
[ ] AI 工位显示真实任务状态
[ ] token 和上下文以状态条显示
[ ] 任务事件能引导用户处理阻塞
[ ] 硬件实验室明确显示人工确认点
[ ] 游戏化界面不影响专业操作效率
```

---

## 10. 日常使用流程

### 10.1 新项目接入流程

```text
创建项目
  -> 绑定 GitHub 仓库
  -> 创建本地 Gitea/Forgejo 镜像
  -> 设置 main/develop 分支
  -> 配置模块边界
  -> 导入 AI 分工表
  -> 配置 Runner
  -> 配置知识库
  -> 创建第一批任务
```

### 10.2 新 AI 入职流程

```text
创建 AI 成员
  -> 填写名称和职位
  -> 选择模型
  -> 绑定所属电脑或 Runner
  -> 设置职责
  -> 设置可读目录
  -> 设置可写目录
  -> 设置权限等级
  -> 设置 token 预算
  -> 进行测试任务
  -> 启用 AI
```

### 10.3 普通软件任务流程

```text
创建任务
  -> 指派 AI
  -> AI 制定计划
  -> 人类确认计划
  -> AI 创建分支并修改代码
  -> Runner 执行测试
  -> 平台展示 diff
  -> 审查 AI 复查
  -> 人类确认合并
```

### 10.4 跨 AI 需求流程

```text
AI 遇到阻塞
  -> 创建需求单
  -> 平台路由给负责 AI
  -> 负责 AI 回复
  -> 平台沉淀结论
  -> 原任务继续
```

### 10.5 硬件调试流程

```text
创建硬件调试任务
  -> AI 生成检查清单
  -> 人类执行实际测量
  -> 人类上传结果
  -> AI 分析
  -> 人类决定下一步
```

### 10.6 AI 接手流程

```text
上下文过长或 AI 失败
  -> 平台提示风险
  -> 生成交接包
  -> 选择接手 AI
  -> 接手 AI 读取交接包
  -> 接手 AI 继续任务
```

---

## 11. 发布流程

### 11.1 开发版本发布

```text
合并 develop
  -> 跑自动测试
  -> 生成变更日志
  -> 打 dev tag
  -> 部署测试环境
```

### 11.2 稳定版本发布

```text
创建 release 分支
  -> 冻结功能
  -> 跑完整测试
  -> 人类进行安全审查
  -> 生成发布说明
  -> 打版本 tag
  -> 同步 GitHub
  -> 部署正式环境
```

### 11.3 回滚流程

```text
发现问题
  -> 定位版本或 commit
  -> 平台展示影响范围
  -> 人类确认回滚
  -> 回滚到指定 commit/tag
  -> 记录回滚原因
  -> 创建复盘任务
```

---

## 12. 开发优先级建议

第一优先级：

```text
项目管理
AI 成员管理
Runner 注册
任务管理
Git 分支和 diff
token 统计
人工确认点
```

第二优先级：

```text
Agent Adapter
需求管理库
上下文健康
AI 接手
知识库
审查流程
```

第三优先级：

```text
嵌入式编译
串口日志
硬件调试清单
OpenClaw 接入
OpenHands 接入
```

第四优先级：

```text
游戏化研发基地
AI 成长属性
每日战报
产品化部署
插件系统
```

---

## 13. 第一版冲刺计划

建议第一版用 4 周完成。

### 第 1 周

```text
搭建项目结构
完成 Docker Compose
完成用户/项目/AI 管理
完成 Runner 注册和心跳
```

### 第 2 周

```text
完成任务管理
完成 Git 分支创建
完成 commit/diff 展示
完成基础审计日志
```

### 第 3 周

```text
完成 Runner 执行任务
接入一个 AI Adapter
完成任务日志回传
完成 token 统计
完成人工确认点
```

### 第 4 周

```text
完成需求管理库 MVP
完成上下文健康 MVP
完成交接包 MVP
完成游戏化首页初版
完成演示项目接入
```

---

## 14. 第一版演示场景

推荐用康复机械臂项目做演示。

演示流程：

```text
1. 打开游戏化研发基地首页。
2. 显示 AI-Boss、ROS AI、NanoPi AI、安全 AI、文档 AI。
3. 创建任务：新增 NanoPi 传感器数据 ROS 发布节点。
4. ROS AI 发现缺少数据格式，向 NanoPi AI 发需求单。
5. NanoPi AI 回复字段定义，平台生成接口契约。
6. ROS AI 生成代码修改。
7. Runner 执行编译，发现缺少依赖。
8. AI 修复 CMakeLists。
9. 上下文达到黄色，平台提示生成摘要。
10. 安全 AI 审查异常值处理。
11. 人类确认合并。
12. 平台生成每日战报。
```

硬件调试演示：

```text
1. 创建任务：M33 电机 PWM 无输出。
2. AI 生成检查清单。
3. 平台进入硬件实验室界面。
4. 人类填写 PA8 波形、EN 引脚电压、串口日志。
5. AI 分析可能是引脚复用配置错误。
6. AI 生成代码建议。
7. 人类确认后进入普通代码任务流程。
```

---

## 15. 最终验收标准

第一版完成时应满足：

```text
[ ] 平台可本地一键启动
[ ] 前端可在电脑和手机浏览器访问
[ ] 可以创建项目和 AI 成员
[ ] 可以配置 AI 职责、模型、所属电脑、权限和预算
[ ] Runner 可以注册、心跳和执行任务
[ ] 可以创建任务、分支、查看 diff
[ ] 可以记录 token 消耗
[ ] AI 可以通过需求单找指定 AI 沟通
[ ] 平台可以显示上下文健康
[ ] 可以生成 AI 交接包
[ ] 硬件调试有人工确认流程
[ ] 游戏化首页能展示 AI 团队状态
[ ] 所有关键操作有审计日志
[ ] 可以回滚到指定 commit
```

---

## 16. 总结

具体开发时不要一开始追求完整智能化，而要先把“项目、AI、任务、Runner、Git、确认点、日志”这条主链路打通。

第一版最重要的是：

```text
看得见 AI 在做什么。
管得住 AI 能做什么。
查得到 AI 为什么这么做。
接得住 AI 做不下去的任务。
回得去任何一次代码历史。
硬件调试始终由人类掌控。
```

游戏化前端是产品特色，但底层必须始终服务真实工程流程。
