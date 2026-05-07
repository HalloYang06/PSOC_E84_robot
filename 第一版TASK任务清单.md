# 第一版 TASK 任务清单（MVP）

范围说明：本清单只覆盖第一版闭环（项目/AI/Runner/任务/Git/diff/日志/token/上下文健康/交接包/人工确认/审计 + 研发基地首页初版）。不包含长期功能（多租户、插件市场、企业 SSO、复杂自动路由、知识图谱、3D 场景、真实硬件自动控制等）。

字段约定：

```text
任务编号 / 标题 / 目标 / 负责人角色 / 依赖 / 允许修改目录 / 验收标准 / 优先级
```

优先级约定：

```text
P0 必须优先完成，否则无法推进闭环
P1 第一版必做，但可在 P0 后并行
P2 第一版增强项，最后一周完成
```

---

## TASK-001 项目代码骨架初始化

目标：建立第一版平台代码仓库骨架（前端、后端、Runner、共享包、基础脚本），保证团队可并行开发。  
负责人角色：AI-ARCH（结构确认）+ AI-DEVOPS（落地）  
依赖：无  
允许修改目录：`apps/`, `packages/`, `infra/`, `docs/`, `scripts/`, `README.md`  
验收标准：
1. 存在 `apps/web/`, `apps/api/`, `apps/runner/` 目录。
2. 存在 `packages/shared/`（预留共享类型）。
3. 存在 `infra/docker-compose.yml`（可空壳但可启动基础服务后续补齐）。
4. 根目录 `README.md` 包含本地启动占位说明。
优先级：P0

---

## TASK-002 Docker Compose 基础服务（PostgreSQL + Redis）

目标：在 `infra/docker-compose.yml` 启动 PostgreSQL + Redis，提供第一版后端基础依赖。  
负责人角色：AI-DEVOPS  
依赖：TASK-001  
允许修改目录：`infra/`, `.env.example`（如存在）  
验收标准：
1. `docker compose up -d` 可启动 postgres 和 redis。
2. 端口与容器网络配置清晰（本地开发可访问）。
3. 有最小可用的数据库用户/库名配置示例（不含真实密码）。
优先级：P0

---

## TASK-003 后端 FastAPI 骨架与统一错误格式

目标：搭建 FastAPI 项目结构，统一响应/错误格式，预留权限检查与审计日志写入点。  
负责人角色：AI-BE-LEAD  
依赖：TASK-001  
允许修改目录：`apps/api/`  
验收标准：
1. `GET /api/health` 返回成功响应。
2. 统一成功/错误响应格式符合 `AI协作平台后端API规范.md`。
3. 有基础配置加载（环境变量占位）。
优先级：P0

---

## TASK-004 数据库模型与迁移（第一批核心表）

目标：实现第一批核心表和迁移，支撑项目/AI/Runner/任务/审计/使用量记录。  
负责人角色：AI-DATA（主）+ AI-BE-LEAD（协）  
依赖：TASK-002, TASK-003  
允许修改目录：`apps/api/`  
验收标准：
1. 包含至少以下表：`users`, `projects`, `agents`, `runners`, `tasks`, `audit_logs`, `usage_logs`。
2. 迁移可执行到最新版本（upgrade head）且能初始化空库。
3. 每张表有必要索引（如 project_id, agent_id, status, created_at）。
优先级：P0

---

## TASK-005 项目管理 API（Projects CRUD）

目标：实现项目的创建/读取/更新/列表 API。  
负责人角色：AI-BE-PROJECT  
依赖：TASK-003, TASK-004  
允许修改目录：`apps/api/`  
验收标准：
1. `POST /api/projects` 可创建项目。
2. `GET /api/projects` 可列表分页（可先简化分页）。
3. `GET /api/projects/{id}` 可查询详情。
4. `PATCH /api/projects/{id}` 可更新关键字段。
5. 操作写入 `audit_logs`。
优先级：P0

---

## TASK-006 AI 成员管理 API（Agents CRUD）

目标：实现 AI 成员的创建/读取/更新/列表 API，并包含第一版必要字段（角色、模型、权限、预算、线程信息）。  
负责人角色：AI-BE-PROJECT  
依赖：TASK-003, TASK-004  
允许修改目录：`apps/api/`  
验收标准：
1. `POST /api/agents` 可创建 AI。
2. `GET /api/agents` 可列表。
3. `GET /api/agents/{id}` 可详情。
4. `PATCH /api/agents/{id}` 可更新职责/模型/预算/权限/线程信息。
5. 操作写入 `audit_logs`。
优先级：P0

---

## TASK-007 Runner 注册与心跳 API

目标：实现 Runner 注册、心跳、能力上报，支持前端显示在线状态。  
负责人角色：AI-BE-PROJECT  
依赖：TASK-003, TASK-004  
允许修改目录：`apps/api/`  
验收标准：
1. `POST /api/runners/register` 可注册 Runner。
2. `POST /api/runners/heartbeat` 可更新心跳时间与状态。
3. `GET /api/runners` 可查看列表及在线/离线状态。
4. 操作写入 `audit_logs`。
优先级：P0

---

## TASK-008 前端 Next.js 骨架与基础路由

目标：搭建前端项目结构与基础路由，包含基础布局和 API client 占位。  
负责人角色：AI-FE-LEAD  
依赖：TASK-001  
允许修改目录：`apps/web/`, `packages/ui/`（如存在）  
验收标准：
1. 本地可启动前端开发服务器。
2. 具备基础路由：`/base`, `/projects`, `/agents`, `/runners`, `/tasks`（可占位）。
3. 有统一的 API baseUrl 配置（不含密钥）。
优先级：P0

---

## TASK-009 前端项目管理页（Projects UI）

目标：实现项目列表、创建、编辑的前端页面，先满足最小可用。  
负责人角色：AI-FE-FORMS  
依赖：TASK-008, TASK-005  
允许修改目录：`apps/web/`  
验收标准：
1. `/projects` 能展示项目列表。
2. 支持创建项目（表单校验）。
3. 支持编辑项目（基本字段）。
4. 错误/空状态处理基本完善。
优先级：P1

---

## TASK-010 前端 AI 成员管理页（Agents UI）

目标：实现 AI 列表、创建、编辑页面，包含角色、线程信息、权限、预算等字段。  
负责人角色：AI-FE-FORMS  
依赖：TASK-008, TASK-006  
允许修改目录：`apps/web/`  
验收标准：
1. `/agents` 展示 AI 成员列表。
2. 支持新增/编辑 AI（含接入方式、线程名称/链接占位字段）。
3. 支持启用/停用（可先做字段切换）。
优先级：P1

---

## TASK-011 前端 Runner 状态页（Runners UI）

目标：实现 Runner 列表与在线状态展示，能看到能力上报和最后心跳。  
负责人角色：AI-FE-FORMS  
依赖：TASK-008, TASK-007  
允许修改目录：`apps/web/`  
验收标准：
1. `/runners` 展示 Runner 列表。
2. 显示在线/离线状态与最后心跳时间。
3. 展示能力列表（capabilities）。
优先级：P1

---

## TASK-012 任务系统 API（Tasks CRUD + 状态流转）

目标：实现任务创建、指派、状态流转、事件记录，支撑闭环调度。  
负责人角色：AI-BE-TASK  
依赖：TASK-003, TASK-004, TASK-006  
允许修改目录：`apps/api/`  
验收标准：
1. `POST /api/tasks` 可创建任务（含验收标准、模块、优先级、负责人）。
2. `GET /api/tasks` 可列表按状态筛选。
3. `PATCH /api/tasks/{id}` 可更新指派与状态。
4. 状态流转有基本校验（禁止乱跳）。
5. 关键写操作写入 `audit_logs`。
优先级：P0

---

## TASK-013 前端任务列表与任务详情（Tasks UI）

目标：实现任务列表和任务详情页面，能看到状态、负责人、验收标准、关联分支占位。  
负责人角色：AI-FE-REVIEW（或 AI-FE-FORMS 先做 MVP）  
依赖：TASK-008, TASK-012  
允许修改目录：`apps/web/`  
验收标准：
1. `/tasks` 展示任务列表，支持按状态过滤。
2. `/tasks/{id}` 展示详情（验收标准、负责人、状态、最近事件占位）。
3. 支持创建任务（可在列表页弹窗或独立页）。
优先级：P1

---

## TASK-014 Runner 程序 MVP（注册/心跳/拉取任务/回传日志）

目标：实现一个可运行的 Runner：注册、心跳、领取任务、执行受限命令、回传日志与结果。  
负责人角色：AI-RUNNER-LEAD  
依赖：TASK-007, TASK-012  
允许修改目录：`apps/runner/`, `packages/sdk/`（如存在）  
验收标准：
1. Runner 启动后能注册到平台并定时心跳。
2. Runner 能拉取一个待执行任务（可先轮询）。
3. Runner 能在工作区执行一个“安全命令”（例如 `git status` 或 `python -c`）。
4. Runner 能回传日志摘要与结果状态到后端。
优先级：P0

---

## TASK-015 Git 集成 MVP（任务分支记录 + diff/commit 查询）

目标：实现最小 Git 能力：创建任务分支记录、查询 commit、获取 diff（先可只支持本地仓库路径）。  
负责人角色：AI-GIT  
依赖：TASK-012  
允许修改目录：`apps/api/`（git 模块）, `apps/runner/`（如需执行 git 命令）  
验收标准：
1. 任务可关联一个分支名（后端字段）。
2. 后端可返回指定分支最新 commit 信息（占位也行，但要接口打通）。
3. 后端可返回某次提交或分支 diff（最小文本 diff）。
优先级：P1

---

## TASK-016 任务日志与 diff 展示前端（Logs/Diff UI）

目标：前端能查看 Runner 回传的日志与 diff，支持审查流程的最小体验。  
负责人角色：AI-FE-REVIEW  
依赖：TASK-013, TASK-014, TASK-015  
允许修改目录：`apps/web/`  
验收标准：
1. `/tasks/{id}/logs` 可查看日志摘要。
2. `/tasks/{id}/diff` 可查看 diff（最小展示即可）。
3. UI 有加载/空状态。
优先级：P1

---

## TASK-017 Token 使用记录与成本简表（Usage Logs）

目标：实现 token 使用记录接口与前端简表。第一版允许手动录入/估算，不要求自动从模型获取。  
负责人角色：AI-BE-CONTEXT（后端）+ AI-FE-REVIEW（前端）  
依赖：TASK-004, TASK-012  
允许修改目录：`apps/api/`, `apps/web/`  
验收标准：
1. 后端可记录 `usage_logs`（按 task/agent 汇总）。
2. 前端 `/usage` 或在研发基地“财务室”展示今日消耗。
3. 不暴露任何明文密钥。
优先级：P1

---

## TASK-018 上下文健康与交接包 MVP

目标：实现上下文健康显示与交接包保存/查看（手动触发即可）。  
负责人角色：AI-BE-CONTEXT（后端）+ AI-FE-REVIEW（前端）  
依赖：TASK-012, TASK-017  
允许修改目录：`apps/api/`, `apps/web/`  
验收标准：
1. 后端可保存 `context_health` 快照（最小字段：ratio/level/turns）。
2. 后端可创建并保存交接包（handoff package）。
3. 前端能在任务详情中看到上下文健康等级，并能查看交接包内容。
优先级：P1

---

## TASK-019 人工确认（H0-H4）与审计日志串联

目标：实现人工确认记录与“待确认列表”，并保证关键动作写入审计日志。  
负责人角色：AI-SECURITY（规则）+ AI-BE-LEAD（落地）+ AI-FE-LEAD（前端入口）  
依赖：TASK-004, TASK-012  
允许修改目录：`apps/api/`, `apps/web/`  
验收标准：
1. 后端可创建 approval 记录（至少包含：riskLevel、action、taskId、status）。
2. 前端能看到“待确认事项”列表（老板办公室入口）。
3. 任何 approval 相关操作写入 `audit_logs`。
4. 明确阻止 AI 自动执行真实硬件操作（前端提示 + 后端校验占位）。
优先级：P1

---

## TASK-020 研发基地首页 MVP（游戏化工作台）

目标：实现第一版“研发基地”首页的核心面板，使用真实 API 或 mock 逐步替换。  
负责人角色：AI-FE-GAME（主）+ AI-FE-LEAD（协）  
依赖：TASK-008, TASK-009, TASK-010, TASK-011, TASK-013, TASK-017  
允许修改目录：`apps/web/`, `packages/ui/`（如存在）  
验收标准：
1. `/base` 展示顶部状态栏（项目/在线 AI/Runner/token/风险/待确认）。
2. 展示老板办公室卡片（阻塞数、待确认数、建议下一步）。
3. 展示任务大厅卡片（阻塞/待分配/待审查）。
4. 展示 AI 工位卡片（状态、上下文健康、token）。
5. 展示代码车间卡片（分支/测试状态占位即可）。
6. 展示硬件实验室确认卡（明确“AI 不能自动操作硬件”）。
7. 移动端可用，不溢出。
优先级：P2

