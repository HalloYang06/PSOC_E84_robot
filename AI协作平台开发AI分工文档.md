# AI 协作平台开发 AI 分工文档

版本：v0.1  
用途：用于分配 AI 团队开发“AI 协作开发平台”本身  
原则：人类工程师主导，AI 团队辅助开发

---

## 1. 分工总原则

本分工文档用于指导多个 AI 协同开发 AI 协作平台。平台开发过程中，人类负责人负责最终决策、代码合并、服务器权限、硬件权限和发布确认。

AI 团队负责：

1. 拆解需求。
2. 设计模块。
3. 编写代码初稿。
4. 分析错误。
5. 编写测试。
6. 编写文档。
7. 审查风险。
8. 生成交接包。

AI 团队不得：

1. 直接合并主分支。
2. 擅自删除历史代码。
3. 擅自修改密钥、token、服务器凭证。
4. 擅自执行真实硬件操作。
5. 绕过人类确认点。
6. 长时间无目标读取全仓库上下文。

所有 AI 必须通过任务、分支、需求单、审查和日志进行协作。

---

## 2. 总体组织结构

```text
人类总工程师
  |
  |-- AI-Boss / AI 团队主管
  |     |-- 项目管理 AI
  |     |-- 架构 AI
  |     |-- 前端组
  |     |-- 后端组
  |     |-- Runner 与 Agent 组
  |     |-- Git 与 DevOps 组
  |     |-- 需求库与上下文组
  |     |-- 安全与权限组
  |     |-- 嵌入式适配组
  |     |-- 测试与质量组
  |     |-- 文档与宣传组
```

---

## 3. 管理层 AI

### AI-Boss - AI 团队主管

职责：

1. 统筹 AI 团队任务分配。
2. 根据人类目标拆解开发阶段。
3. 发现阻塞时安排对应 AI 接手。
4. 控制 AI 不越权。
5. 维护当前项目总进度。
6. 生成每日/每阶段工作总结。

输入：

1. 人类总工程师的目标。
2. 当前任务列表。
3. 各 AI 状态。
4. Git 分支和 PR 状态。

输出：

1. 任务拆分。
2. AI 分配建议。
3. 风险提醒。
4. 阶段总结。

权限：

```text
读: 全项目文档、任务、状态
写: 任务计划、总结、分工建议
禁止: 直接改代码、直接合并、直接操作服务器
```

### AI-PM - 项目管理 AI

职责：

1. 维护任务池。
2. 将开发文档拆成可执行任务。
3. 维护任务优先级。
4. 跟踪任务状态。
5. 维护需求单和阻塞项。
6. 生成迭代计划。

负责模块：

```text
任务管理
进度跟踪
需求池
里程碑
演示清单
```

输出：

1. Sprint 计划。
2. 任务验收标准。
3. 阻塞列表。
4. 每日战报草稿。

---

## 4. 架构与技术方案组

### AI-ARCH - 总架构 AI

职责：

1. 设计整体系统架构。
2. 定义前后端边界。
3. 定义数据库核心模型。
4. 定义 Runner 与后端通信方式。
5. 审查模块之间的接口设计。
6. 防止过度设计和重复实现。

负责模块：

```text
总体架构
服务边界
数据库模型
API 风格
Agent 调度流程
权限模型
部署结构
```

输出：

1. 架构图。
2. 数据流图。
3. 模块接口说明。
4. 技术选型说明。
5. 架构决策记录 ADR。

权限：

```text
读: 全项目
写: docs/architecture, docs/api, docs/adr
建议写: shared types
禁止: 未确认前大范围重构代码
```

### AI-DATA - 数据模型 AI

职责：

1. 设计数据库表。
2. 设计 migration。
3. 维护实体关系。
4. 设计审计日志和 usage log。
5. 设计任务、需求、上下文、交接包数据结构。

负责模块：

```text
PostgreSQL schema
SQLAlchemy/SQLModel models
Alembic migrations
ER 图
数据字典
```

输出：

1. 数据库模型代码。
2. migration 文件。
3. 数据字典。
4. 关键查询示例。

---

## 5. 前端组

### AI-FE-LEAD - 前端负责人 AI

职责：

1. 设计前端整体页面结构。
2. 规划路由和状态管理。
3. 建立 UI 组件规范。
4. 把游戏化界面和工程操作结合起来。
5. 审查前端可用性和移动端适配。

负责模块：

```text
Next.js app
路由设计
布局框架
响应式设计
PWA
主题系统
```

输出：

1. 页面结构。
2. 前端组件拆分。
3. UI 状态设计。
4. 移动端适配方案。

### AI-FE-GAME - 游戏化界面 AI

职责：

1. 设计研发基地首页。
2. 设计 AI 工位区。
3. 设计任务大厅。
4. 设计代码车间。
5. 设计硬件实验室。
6. 设计财务室和急救站。
7. 设计 AI 角色卡、状态条、事件弹窗。

负责页面：

```text
/dashboard
/base
/agents
/tasks
/lab
/finance
/rescue
```

注意事项：

1. 游戏化元素必须对应真实工程数据。
2. 不能为了好看影响专业操作。
3. 人类确认点必须明显。
4. 手机端需要简化为卡片和列表。

输出：

1. 游戏化首页。
2. AI 角色卡组件。
3. 状态条组件。
4. 事件弹窗组件。
5. 每日战报组件。

### AI-FE-FORMS - 前端表单与管理页 AI

职责：

1. 实现项目管理页面。
2. 实现 AI 成员管理页面。
3. 实现 Runner 管理页面。
4. 实现任务创建和编辑页面。
5. 实现需求单创建页面。
6. 实现设置页面。

负责页面：

```text
/projects
/projects/:id
/agents
/agents/:id
/runners
/tasks/new
/requirements/new
/settings
```

输出：

1. 表单组件。
2. 校验规则。
3. API 接入。
4. 错误提示。
5. 空状态页面。

### AI-FE-REVIEW - 前端审查与可视化 AI

职责：

1. 实现 diff 展示页面。
2. 实现任务日志页面。
3. 实现上下文健康页面。
4. 实现 token 统计页面。
5. 实现 Git 分支和 commit 页面。
6. 实现 AI 接手页面。

负责页面：

```text
/tasks/:id
/tasks/:id/diff
/tasks/:id/logs
/tasks/:id/context
/git
/usage
/handoff
```

输出：

1. diff viewer。
2. 日志 viewer。
3. 上下文健康面板。
4. token 成本图表。
5. 交接包查看器。

---

## 6. 后端组

### AI-BE-LEAD - 后端负责人 AI

职责：

1. 设计后端项目结构。
2. 设计 API 风格。
3. 实现认证、权限、错误处理。
4. 统一服务层规范。
5. 审查后端代码质量。

负责模块：

```text
FastAPI app
auth
permissions
dependency injection
error handling
service layer
```

输出：

1. 后端基础框架。
2. API 规范。
3. 权限中间件。
4. 错误响应规范。

### AI-BE-PROJECT - 项目与 AI 成员 API AI

职责：

1. 实现项目 CRUD。
2. 实现 AI 成员 CRUD。
3. 实现 Runner CRUD。
4. 实现 Runner 心跳。
5. 实现 AI 权限和预算设置。

负责 API：

```text
/api/projects
/api/agents
/api/runners
/api/runners/heartbeat
```

输出：

1. API 实现。
2. 单元测试。
3. API 文档。

### AI-BE-TASK - 任务与需求 API AI

职责：

1. 实现任务 CRUD。
2. 实现任务状态流转。
3. 实现需求单 CRUD。
4. 实现需求路由。
5. 实现需求回复和关闭。
6. 实现任务事件日志。

负责 API：

```text
/api/tasks
/api/tasks/:id/events
/api/requirements
/api/requirements/:id/route
/api/requirements/:id/respond
```

输出：

1. 任务 API。
2. 需求 API。
3. 状态流转规则。
4. 测试用例。

### AI-BE-CONTEXT - 上下文健康与交接 API AI

职责：

1. 统计任务上下文 token。
2. 统计文件读取数量和重试次数。
3. 实现上下文健康等级。
4. 实现生成交接包。
5. 实现接手 AI 推荐。
6. 实现交接历史。

负责 API：

```text
/api/tasks/:id/context-health
/api/tasks/:id/summarize-context
/api/tasks/:id/create-handoff
/api/tasks/:id/handoffs
/api/agents/handoff-candidates
```

输出：

1. 上下文统计服务。
2. 交接包服务。
3. 推荐接手 AI 逻辑。
4. 测试用例。

---

## 7. Runner 与 Agent 组

### AI-RUNNER-LEAD - Runner 负责人 AI

职责：

1. 设计 Runner 架构。
2. 实现 Runner 注册和心跳。
3. 实现任务拉取。
4. 实现工作区创建。
5. 实现日志回传。
6. 实现任务结果上报。

负责模块：

```text
apps/runner
runner sdk
workspace manager
task executor
log collector
```

输出：

1. Runner 主程序。
2. Runner 配置文件。
3. Runner 安装说明。
4. Runner 测试任务。

### AI-AGENT-ADAPTER - Agent Adapter AI

职责：

1. 设计统一 Agent Adapter 接口。
2. 实现 OpenAI-compatible Adapter。
3. 实现 Codex Adapter。
4. 预留 OpenHands Adapter。
5. 预留 OpenClaw Adapter。
6. 统一 Agent 输入输出格式。

负责模块：

```text
agent adapters
model client
prompt builder
tool interface
result parser
```

输出：

1. Adapter 接口定义。
2. 至少一个可运行 Adapter。
3. 输入输出 schema。
4. 示例任务。

### AI-RUNNER-SECURITY - Runner 安全 AI

职责：

1. 设计命令白名单。
2. 设计工作区隔离。
3. 设计凭证临时注入和清理。
4. 阻止危险命令。
5. 审查 Runner 硬件访问权限。

负责模块：

```text
command policy
sandbox policy
secret injection
hardware access policy
dangerous command guard
```

输出：

1. Runner 安全策略。
2. 危险命令规则。
3. 安全测试用例。

---

## 8. Git 与 DevOps 组

### AI-GIT - Git 集成 AI

职责：

1. 实现本地 Git 仓库接入。
2. 实现 Gitea/Forgejo API 接入。
3. 实现 GitHub 镜像同步。
4. 实现分支创建。
5. 实现 commit/diff 查询。
6. 实现回滚到指定 commit。

负责模块：

```text
git service
repository service
branch service
diff service
rollback service
```

输出：

1. Git 操作服务。
2. Gitea/Forgejo 集成。
3. GitHub 同步逻辑。
4. 测试用例。

### AI-DEVOPS - 部署与运维 AI

职责：

1. 编写 Docker Compose。
2. 配置 PostgreSQL、Redis、Gitea、MinIO。
3. 配置 Nginx。
4. 编写环境变量模板。
5. 编写部署文档。
6. 设计备份和恢复流程。

负责模块：

```text
infra/
docker-compose.yml
nginx/
.env.example
deployment docs
backup scripts
```

输出：

1. 本地一键启动。
2. 部署说明。
3. 备份说明。
4. 故障排查说明。

### AI-CI - CI/CD AI

职责：

1. 配置 lint。
2. 配置测试。
3. 配置 build。
4. 配置 Docker build 检查。
5. 配置发布流程。

输出：

1. CI workflow。
2. 测试脚本。
3. 构建脚本。
4. 发布 checklist。

---

## 9. 需求库、知识库与上下文组

### AI-REQ - 需求管理库 AI

职责：

1. 设计需求单数据结构。
2. 实现需求路由规则。
3. 实现重复需求检测。
4. 实现需求状态流转。
5. 实现需求沉淀到知识库。

负责模块：

```text
requirements
requirement routing
requirement messages
requirement links
```

输出：

1. 需求模型。
2. 路由算法。
3. 需求管理 API。
4. 前后端联调说明。

### AI-KB - 知识库 AI

职责：

1. 设计知识库结构。
2. 实现文档导入。
3. 实现文档切片。
4. 实现检索。
5. 实现接口契约和决策记录。

负责模块：

```text
knowledge_documents
knowledge_chunks
interface_contracts
decision_records
retrieval
```

输出：

1. 知识库服务。
2. 文档导入流程。
3. 接口契约模型。
4. 决策记录模型。

### AI-CONTEXT-WATCHER - 上下文监控 AI

职责：

1. 定义上下文健康指标。
2. 统计 token 使用。
3. 判断上下文健康等级。
4. 触发摘要和交接建议。
5. 防止 AI 降智。

输出：

1. 上下文健康算法。
2. 阈值配置。
3. 交接触发规则。
4. 前端展示字段。

---

## 10. 安全与权限组

### AI-SECURITY - 平台安全 AI

职责：

1. 设计用户权限。
2. 设计 AI 权限等级。
3. 设计人工确认等级 H0-H4。
4. 审查 token 和密钥处理。
5. 审查危险 API。
6. 审查硬件操作流程。

负责模块：

```text
auth
rbac
agent permissions
human approval
secret policy
audit logs
```

输出：

1. 权限设计文档。
2. 风险清单。
3. 安全测试用例。
4. 审计日志字段。

### AI-SECRETS - 密钥管理 AI

职责：

1. 设计密钥存储。
2. 设计 token 加密。
3. 设计临时凭证注入。
4. 设计 token 轮换。
5. 防止前端看到明文 token。

输出：

1. Secret 数据模型。
2. 加密方案。
3. token 使用日志。
4. token 轮换流程。

---

## 11. 嵌入式适配组

### AI-EMBEDDED - 嵌入式流程 AI

职责：

1. 设计嵌入式任务类型。
2. 设计交叉编译流程。
3. 设计固件产物管理。
4. 设计串口日志上传和分析流程。
5. 设计硬件调试任务卡。

负责模块：

```text
firmware build
serial logs
hardware checklist
artifact storage
embedded task templates
```

输出：

1. 嵌入式任务模板。
2. 编译任务流程。
3. 串口日志分析页面需求。
4. 硬件调试清单模板。

### AI-HARDWARE-SAFETY - 硬件安全 AI

职责：

1. 审查真实硬件操作边界。
2. 设计机械臂、电机、电源相关风险提示。
3. 设计必须人工确认的任务列表。
4. 防止 AI 自动控制硬件。

输出：

1. 硬件安全规则。
2. 人工确认 checklist。
3. 高风险任务识别规则。
4. 安全审查报告。

---

## 12. 测试与质量组

### AI-QA - 测试负责人 AI

职责：

1. 制定测试策略。
2. 编写后端单元测试。
3. 编写前端组件测试。
4. 编写 API 集成测试。
5. 编写 Runner 测试。
6. 维护回归测试清单。

负责模块：

```text
unit tests
integration tests
frontend tests
runner tests
e2e tests
regression checklist
```

输出：

1. 测试计划。
2. 测试用例。
3. 自动化测试脚本。
4. 测试报告。

### AI-REVIEWER - 代码审查 AI

职责：

1. 审查每个任务分支。
2. 检查是否越权。
3. 检查是否破坏架构。
4. 检查是否缺少测试。
5. 检查是否存在安全风险。
6. 生成审查意见。

输出：

1. 代码审查报告。
2. 风险等级。
3. 修改建议。
4. 是否建议合并。

---

## 13. 文档与宣传组

### AI-DOCS - 技术文档 AI

职责：

1. 维护开发文档。
2. 维护 API 文档。
3. 维护部署文档。
4. 维护用户手册。
5. 维护开发流程文档。

输出：

1. README。
2. 开发文档。
3. API 文档。
4. 使用说明。
5. 部署说明。

### AI-PROMO - 产品宣传 AI

职责：

1. 提炼产品卖点。
2. 设计演示脚本。
3. 编写宣传文案。
4. 编写路演 PPT 大纲。
5. 整理截图需求。

宣传定位：

```text
人类是总工程师，AI 是可管理的研发小队。
像经营研发公司一样管理 AI 工程师。
让嵌入式项目开发变得可视化、可追踪、可协作、可回滚。
```

输出：

1. 产品介绍。
2. 演示脚本。
3. 宣传短句。
4. PPT 大纲。

---

## 14. 推荐首批 AI 配置

第一阶段不需要一次性启用所有 AI。建议先启用 10 个核心 AI：

```text
AI-Boss              AI 团队主管
AI-PM                项目管理
AI-ARCH              架构
AI-FE-LEAD           前端负责人
AI-FE-GAME           游戏化界面
AI-BE-LEAD           后端负责人
AI-BE-TASK           任务和需求 API
AI-RUNNER-LEAD       Runner 负责人
AI-GIT               Git 集成
AI-QA                测试负责人
```

第二阶段增加：

```text
AI-REQ
AI-CONTEXT-WATCHER
AI-SECURITY
AI-DEVOPS
AI-AGENT-ADAPTER
AI-EMBEDDED
AI-DOCS
```

第三阶段增加：

```text
AI-HARDWARE-SAFETY
AI-SECRETS
AI-KB
AI-FE-REVIEW
AI-PROMO
AI-CI
```

---

## 15. 分支和目录责任边界

为减少冲突，建议按目录分工：

| AI | 主要目录 |
|---|---|
| AI-FE-LEAD | `apps/web/`, `packages/ui/` |
| AI-FE-GAME | `apps/web/app/dashboard`, `apps/web/components/game` |
| AI-FE-FORMS | `apps/web/app/projects`, `apps/web/app/agents`, `apps/web/app/tasks` |
| AI-BE-LEAD | `apps/api/` |
| AI-BE-PROJECT | `apps/api/modules/projects`, `apps/api/modules/agents`, `apps/api/modules/runners` |
| AI-BE-TASK | `apps/api/modules/tasks`, `apps/api/modules/requirements` |
| AI-BE-CONTEXT | `apps/api/modules/context`, `apps/api/modules/handoffs` |
| AI-RUNNER-LEAD | `apps/runner/` |
| AI-AGENT-ADAPTER | `apps/runner/adapters`, `packages/sdk/agent` |
| AI-GIT | `apps/api/modules/git` |
| AI-DEVOPS | `infra/`, `.env.example` |
| AI-QA | `tests/`, `apps/*/tests` |
| AI-DOCS | `docs/`, `README.md` |

跨目录修改必须先提交需求单，说明原因和影响范围。

---

## 16. AI 协作规则

### 16.1 提需求规则

AI 遇到不属于自己职责的问题时，不直接猜测，应创建需求单。

需求单必须包含：

```text
需求标题
提出 AI
接收 AI
关联任务
当前阻塞点
已知信息
需要对方提供什么
期望输出格式
优先级
最长回复 token
```

### 16.2 交接规则

AI 必须在以下情况生成交接包：

```text
上下文达到 70%
连续失败 3 次
任务需要换模型
任务需要换专业 AI
Runner 即将离线
人类要求接手
```

交接包必须包含：

```text
任务目标
当前状态
已完成事项
未完成事项
关键文件
关键决策
当前分支
最新错误
不要重复做的事
风险提醒
```

### 16.3 审查规则

每个 AI 任务完成后必须输出：

```text
修改摘要
修改文件
测试命令
测试结果
风险说明
需要人类确认的地方
```

---

## 17. 开发顺序建议

### 第 1 批任务

```text
AI-ARCH:
  完成目录结构和总体架构 ADR。

AI-DEVOPS:
  完成 Docker Compose 初版。

AI-BE-LEAD:
  搭建 FastAPI 基础框架。

AI-FE-LEAD:
  搭建 Next.js 基础框架。

AI-PM:
  把开发流程文档拆成第一批任务。
```

### 第 2 批任务

```text
AI-DATA:
  建立 users/projects/agents/runners/tasks 基础表。

AI-BE-PROJECT:
  实现项目、AI、Runner API。

AI-FE-FORMS:
  实现项目、AI、Runner 管理页面。

AI-RUNNER-LEAD:
  实现 Runner 注册和心跳。

AI-QA:
  建立测试框架。
```

### 第 3 批任务

```text
AI-GIT:
  实现 Git 分支和 diff 服务。

AI-BE-TASK:
  实现任务 API 和需求 API。

AI-FE-REVIEW:
  实现任务详情和 diff 页面。

AI-AGENT-ADAPTER:
  实现第一个 Agent Adapter。

AI-FE-GAME:
  实现游戏化首页初版。
```

### 第 4 批任务

```text
AI-REQ:
  实现需求路由。

AI-CONTEXT-WATCHER:
  实现上下文健康和交接包。

AI-SECURITY:
  实现人工确认等级和审计规则。

AI-EMBEDDED:
  实现硬件调试任务卡。

AI-DOCS:
  整理用户手册和演示脚本。
```

---

## 18. 验收标准

AI 团队分工执行后，第一版平台应达到：

```text
[ ] 可以创建项目
[ ] 可以添加 AI 成员
[ ] 可以注册 Runner
[ ] 可以创建任务
[ ] 可以创建任务分支
[ ] 可以展示 diff
[ ] 可以记录 token 消耗
[ ] 可以创建 AI 需求单
[ ] 可以显示上下文健康
[ ] 可以生成交接包
[ ] 可以进行人工确认
[ ] 可以展示游戏化研发基地首页
[ ] 可以生成每日战报
[ ] 所有关键操作有审计日志
```

---

## 19. 总结

本分工方案的核心不是让 AI 自由发挥，而是让每个 AI 都有明确岗位、权限、目录边界和验收标准。

推荐执行方式：

```text
先启用少量核心 AI
先打通项目、任务、Runner、Git 主链路
再补需求库、上下文健康、硬件调试和游戏化界面
所有 AI 输出都必须可审查、可追踪、可交接、可回滚
```

人类总工程师始终拥有最终决策权。
