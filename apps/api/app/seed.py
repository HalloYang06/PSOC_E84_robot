from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, select, text, update
from sqlalchemy.orm import Session

from app.db.models.agent import Agent
from app.db.models.approval import Approval
from app.db.models.audit_log import AuditLog
from app.db.models.collaboration_message import CollaborationMessage
from app.db.models.context_health import ContextHealthRecord
from app.db.models.invitation import Invitation
from app.db.models.handoff import Handoff
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.models.project_collaboration import ProjectAIProvider, ProjectComputerNode, ProjectThreadWorkstation
from app.db.models.project_invite import ProjectInvite
from app.db.models.project_member import ProjectMember
from app.db.models.rehab_arm_app import (
    RehabAppAiTrainingDraft,
    RehabAppBleMessage,
    RehabAppDiagnosticUpload,
    RehabAppDeviceBinding,
    RehabAppEmgSummary,
    RehabAppIntentInferenceSummary,
    RehabAppOfflineQueueItem,
    RehabAppPlatformSyncRun,
    RehabAppTrainingPlan,
    RehabAppTrainingPlanSync,
    RehabAppTrainingReport,
    RehabAppTrainingReportReview,
    RehabAppTrainingSession,
    RehabAppUserProfile,
)
from app.db.models.requirement import Requirement, RequirementMessage
from app.db.models.runner import Runner
from app.db.models.task import Task
from app.db.models.task_dispatch import TaskDispatch
from app.db.models.task_event import TaskEvent
from app.db.models.usage_log import UsageLog
from app.db.models.user import User
from app.db.session import engine
from app.modules.projects.service import sync_project_collaboration_inventory


def ensure_schema_extensions() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "task_dispatches" not in table_names:
            TaskDispatch.__table__.create(bind=connection, checkfirst=True)
        for model in (
            RehabAppUserProfile,
            RehabAppDeviceBinding,
            RehabAppTrainingPlan,
            RehabAppTrainingPlanSync,
            RehabAppBleMessage,
            RehabAppTrainingSession,
            RehabAppTrainingReport,
            RehabAppTrainingReportReview,
            RehabAppEmgSummary,
            RehabAppIntentInferenceSummary,
            RehabAppAiTrainingDraft,
            RehabAppDiagnosticUpload,
            RehabAppOfflineQueueItem,
            RehabAppPlatformSyncRun,
        ):
            if model.__tablename__ not in table_names:
                model.__table__.create(bind=connection, checkfirst=True)

        if "rehab_app_training_plan_syncs" in table_names:
            sync_columns = {column["name"] for column in inspector.get_columns("rehab_app_training_plan_syncs")}
            if "plan_version" not in sync_columns:
                connection.execute(text("ALTER TABLE rehab_app_training_plan_syncs ADD COLUMN plan_version INTEGER NOT NULL DEFAULT 1"))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_rehab_app_training_plan_syncs_plan_version ON rehab_app_training_plan_syncs (plan_version)")
                )

        if "tasks" in table_names:
            task_columns = {column["name"] for column in inspector.get_columns("tasks")}
            if "due_at" not in task_columns:
                connection.execute(text("ALTER TABLE tasks ADD COLUMN due_at DATETIME"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_due_at ON tasks (due_at)"))

        if "users" in table_names:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "last_seen_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_seen_at DATETIME"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_last_seen_at ON users (last_seen_at)"))

        if "project_members" in table_names:
            member_columns = {column["name"] for column in inspector.get_columns("project_members")}
            if "last_project_seen_at" not in member_columns:
                connection.execute(text("ALTER TABLE project_members ADD COLUMN last_project_seen_at DATETIME"))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_project_members_last_project_seen_at ON project_members (last_project_seen_at)")
                )
            if "last_project_path" not in member_columns:
                connection.execute(text("ALTER TABLE project_members ADD COLUMN last_project_path VARCHAR(500)"))

        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "requirement_policy" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN requirement_policy JSON"))

        requirement_columns = {column["name"] for column in inspector.get_columns("requirements")}
        if "requirement_type" not in requirement_columns:
            connection.execute(text("ALTER TABLE requirements ADD COLUMN requirement_type VARCHAR(64)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requirements_requirement_type ON requirements (requirement_type)")
            )
        if "follow_up_from_requirement_id" not in requirement_columns:
            connection.execute(text("ALTER TABLE requirements ADD COLUMN follow_up_from_requirement_id VARCHAR(64)"))
        if "target_seat_id" not in requirement_columns:
            connection.execute(text("ALTER TABLE requirements ADD COLUMN target_seat_id VARCHAR(64)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requirements_target_seat_id ON requirements (target_seat_id)")
            )
        if "trigger_kind" not in requirement_columns:
            connection.execute(text("ALTER TABLE requirements ADD COLUMN trigger_kind VARCHAR(32) NOT NULL DEFAULT 'manual'"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requirements_trigger_kind ON requirements (trigger_kind)")
            )
        if "dependency_requirement_id" not in requirement_columns:
            connection.execute(text("ALTER TABLE requirements ADD COLUMN dependency_requirement_id VARCHAR(64)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_requirements_dependency_requirement_id ON requirements (dependency_requirement_id)")
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_requirements_follow_up_from_requirement_id "
                "ON requirements (follow_up_from_requirement_id) "
                "WHERE follow_up_from_requirement_id IS NOT NULL"
            )
        )

        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "collaboration_config" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN collaboration_config JSON"))

        handoff_columns = {column["name"] for column in inspector.get_columns("handoffs")}
        if "project_id" not in handoff_columns:
            connection.execute(text("ALTER TABLE handoffs ADD COLUMN project_id VARCHAR(36)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_handoffs_project_id ON handoffs (project_id)"))

        collaboration_columns = {column["name"] for column in inspector.get_columns("collaboration_messages")}
        if "dispatch_id" not in collaboration_columns:
            connection.execute(text("ALTER TABLE collaboration_messages ADD COLUMN dispatch_id VARCHAR(64)"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_collaboration_messages_dispatch_id "
                    "ON collaboration_messages (dispatch_id)"
                )
            )
        if "dedupe_key" not in collaboration_columns:
            connection.execute(text("ALTER TABLE collaboration_messages ADD COLUMN dedupe_key VARCHAR(128)"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_collaboration_messages_dedupe_key "
                "ON collaboration_messages (dedupe_key) "
                "WHERE dedupe_key IS NOT NULL"
            )
        )


def _has_rows(db: Session, model) -> bool:
    return db.scalar(select(model.id).limit(1)) is not None


def seed_if_empty(db: Session) -> None:
    seeded = False

    seeded_task_events = list(
        db.scalars(select(TaskEvent).where(TaskEvent.message == "Task seeded"))
    )
    if seeded_task_events:
        for event in seeded_task_events:
            event.message = "已写入样板任务"
        db.add_all(seeded_task_events)
        seeded = True

    if not _has_rows(db, Project):
        projects = [
            Project(
                id="proj_rehab_arm",
                name="康复机械臂田块",
                description="真机、安全和接口联动都在这块田里推进，所有真机动作都保留人工确认。",
                project_type="嵌入式机器人",
                requirement_policy={
                    "default_type": "hardware_request",
                    "default_priority": "P1",
                    "default_status": "waiting_response",
                    "default_to_agent": "agent_runner_git",
                    "promote_to_knowledge": True,
                    "knowledge_module": "硬件知识",
                    "allow_human_to_thread": True,
                    "allow_thread_to_thread": True,
                },
                collaboration_config={
                    "thread_workstations": [
                        {"name": "硬件工位", "agent_id": "agent_runner_git", "computer_node": "runner_nanopi", "ai_provider": "local_runner"},
                    ],
                    "ai_providers": [
                        {"id": "manual_codex_thread", "label": "人工线程"},
                        {"id": "local_runner", "label": "本地执行"},
                    ],
                    "computer_nodes": [
                        {"id": "runner_nanopi", "label": "边缘执行节点", "status": "offline"},
                    ],
                },
                github_url="https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator",
                local_git_url="local://rehab-arm",
                default_branch="main",
                develop_branch="develop",
            ),
            Project(
                id="proj_ai_collab",
                name="智能体协作庄园",
                description="把任务、工位、执行节点和账房连起来的基地内核项目。",
                project_type="平台内核",
                requirement_policy={
                    "default_type": "thread_request",
                    "default_priority": "P1",
                    "default_status": "waiting_response",
                    "default_to_agent": "agent_boss",
                    "promote_to_knowledge": True,
                    "knowledge_module": "需求管理库",
                    "allow_human_to_thread": True,
                    "allow_thread_to_thread": True,
                },
                collaboration_config={
                    "thread_workstations": [
                        {"name": "前端工位", "agent_id": "agent_fe_game", "computer_node": "runner_pc1", "ai_provider": "manual_codex_thread"},
                        {"name": "执行工位", "agent_id": "agent_runner_git", "computer_node": "runner_nanopi", "ai_provider": "local_runner"},
                    ],
                    "ai_providers": [
                        {"id": "manual_codex_thread", "label": "人工线程"},
                        {"id": "local_runner", "label": "本地执行"},
                    ],
                    "computer_nodes": [
                        {"id": "runner_pc1", "label": "主控执行节点", "status": "online"},
                        {"id": "runner_nanopi", "label": "边缘执行节点", "status": "offline"},
                    ],
                },
                github_url="https://github.com/wenjunyong666/ai-",
                local_git_url="local://ai-collab",
                default_branch="main",
                develop_branch="develop",
            ),
        ]
        db.add_all(projects)
        db.flush()
        seeded = True

    projects = list(db.scalars(select(Project).order_by(Project.created_at.asc())))
    primary_project = projects[0]
    platform_project = projects[1] if len(projects) > 1 else projects[0]

    if not _has_rows(db, User):
        users = [
            User(
                id="human-chief",
                name="总工程师",
                email="chief@local",
                display_name="总工程师",
                bio="负责验收、真机操作和最终决策。",
                is_active=True,
            ),
            User(
                id="human-hardware",
                name="硬件联络人",
                email="lab@local",
                display_name="硬件联络人",
                bio="负责实验室、烧录和安全确认。",
                is_active=True,
            ),
            User(
                id="user-collab-fe",
                name="前端协作者",
                email="fe@local",
                display_name="前端协作者",
                bio="负责庄园界面、交互与可视化。",
                is_active=True,
            ),
        ]
        db.add_all(users)
        db.flush()
        seeded = True

    users = list(db.scalars(select(User).order_by(User.created_at.asc())))
    chief_user = next((item for item in users if item.id == "human-chief"), users[0])
    hardware_user = next((item for item in users if item.id == "human-hardware"), users[0])
    fe_user = next((item for item in users if item.id == "user-collab-fe"), users[-1])

    if not _has_rows(db, ProjectMember):
        members = [
            ProjectMember(
                project_id=platform_project.id,
                user_id=chief_user.id,
                role="owner",
                status="active",
                is_owner=True,
            ),
            ProjectMember(
                project_id=platform_project.id,
                user_id=fe_user.id,
                role="collaborator",
                status="active",
                is_owner=False,
            ),
            ProjectMember(
                project_id=primary_project.id,
                user_id=hardware_user.id,
                role="hardware",
                status="active",
                is_owner=False,
            ),
        ]
        db.add_all(members)
        seeded = True

    if not _has_rows(db, Invitation):
        invitations = [
            Invitation(
                id="invite-001",
                email="runner@local",
                project_id=platform_project.id,
                role="runner-maintainer",
                invited_by_user_id=chief_user.id,
                token="invite-runner-demo",
                status="pending",
                note="邀请执行节点维护者加入庄园，负责 Runner 与日志回传。",
            ),
            Invitation(
                id="invite-002",
                email="safety@local",
                project_id=primary_project.id,
                role="safety-reviewer",
                invited_by_user_id=hardware_user.id,
                token="invite-safety-demo",
                status="pending",
                note="邀请安全审核人加入康复机械臂田块，负责实验室闸门和真机确认。",
            ),
        ]
        db.add_all(invitations)
        seeded = True

    if not _has_rows(db, Runner):
        runners = [
            Runner(
                id="runner_pc1",
                name="主控执行台",
                host="主控台一号机",
                os="Windows",
                capabilities=["版本拉取", "脚本执行", "文件同步"],
                status="online",
                allow_hardware_access=False,
                max_concurrent_tasks=2,
                last_heartbeat_at=datetime.now(timezone.utc),
            ),
            Runner(
                id="runner_nanopi",
                name="边缘执行台",
                host="香橙派侧机",
                os="Linux",
                capabilities=["传感器读取", "串口转发", "节点适配"],
                status="offline",
                allow_hardware_access=False,
                max_concurrent_tasks=1,
                last_heartbeat_at=None,
            ),
        ]
        db.add_all(runners)
        db.flush()
        seeded = True

    runners = list(db.scalars(select(Runner).order_by(Runner.created_at.asc())))
    primary_runner = runners[0]
    edge_runner = runners[1] if len(runners) > 1 else runners[0]

    if not _has_rows(db, Agent):
        agents = [
            Agent(
                id="agent_boss",
                name="总控主管",
                role="全局统筹",
                provider="manual_codex_thread",
                execution_mode="manual",
                model="线程驾驶舱",
                agent_type="管理层",
                responsibility="压住范围，安排接手和排障。",
                modules=["管理", "调度", "风险"],
                runner_id=primary_runner.id,
                runner_name=primary_runner.name,
                permission_level="L3",
                read_paths=["docs/", "apps/"],
                write_paths=["docs/"],
                max_tokens_per_task=20000,
                max_cost_per_day=5000,
                enabled=True,
                notes="总协调线程。",
            ),
            Agent(
                id="agent_fe_game",
                name="前端造景师",
                role="基地界面",
                provider="manual_codex_thread",
                execution_mode="manual",
                model="线程驾驶舱",
                agent_type="前端",
                responsibility="统一庄园皮肤和基地动线。",
                modules=["前端", "界面", "交互"],
                runner_id=primary_runner.id,
                runner_name=primary_runner.name,
                permission_level="L2",
                read_paths=["apps/web/"],
                write_paths=["apps/web/"],
                max_tokens_per_task=14000,
                max_cost_per_day=3000,
                enabled=True,
                notes="负责游戏化基地视觉。",
            ),
            Agent(
                id="agent_runner_git",
                name="执行与版本官",
                role="执行节点与版本回传",
                provider="local_runner",
                execution_mode="semi_auto",
                model="本地执行节点",
                agent_type="执行层",
                responsibility="补齐任务回传和日志入口。",
                modules=["执行节点", "Git", "日志"],
                runner_id=edge_runner.id,
                runner_name=edge_runner.name,
                permission_level="L2",
                read_paths=["apps/runner/", "apps/api/"],
                write_paths=["apps/runner/"],
                max_tokens_per_task=8000,
                max_cost_per_day=1000,
                enabled=True,
                notes="负责版本与执行链路。",
            ),
        ]
        db.add_all(agents)
        db.flush()
        seeded = True

    agents = list(db.scalars(select(Agent).order_by(Agent.created_at.asc())))
    boss_agent = next((item for item in agents if item.id == "agent_boss"), agents[0])
    fe_agent = next((item for item in agents if item.id == "agent_fe_game"), agents[0])
    runner_agent = next((item for item in agents if item.id == "agent_runner_git"), agents[-1])

    if not _has_rows(db, Task):
        tasks = [
            Task(
                id="TASK-001",
                project_id=platform_project.id,
                title="搭起后端骨架与健康检查",
                description="先把后端最短闭环打通，保证健康检查和统一响应能工作。",
                module="后端机房",
                priority="P0",
                status="running",
                branch="ai/be-lead/TASK-001-api-skeleton",
                related_issue="TASK-001",
                assignee_agent_id=boss_agent.id,
                reviewers=["人类总工程师"],
                acceptance_criteria=["健康检查可访问", "统一返回格式已落地", "数据库会话骨架已准备"],
            ),
            Task(
                id="TASK-004",
                project_id=platform_project.id,
                title="执行节点注册与心跳回传",
                description="让执行节点能注册、在线和回传心跳，供后续领取任务使用。",
                module="执行节点",
                priority="P0",
                status="testing",
                branch="ai/runner/TASK-004-runner-heartbeat",
                related_issue="TASK-004",
                assignee_agent_id=runner_agent.id,
                reviewers=["人类总工程师"],
                acceptance_criteria=["节点可以启动", "心跳可以上报", "领取任务入口已预留"],
            ),
            Task(
                id="TASK-012",
                project_id=platform_project.id,
                title="重做基地首页主面板",
                description="把首页做成中文基地经营风格，并保留庄园语义。",
                module="前端基地",
                priority="P1",
                status="ready",
                branch="ai/fe-game/TASK-012-base-panels",
                related_issue="TASK-012",
                assignee_agent_id=fe_agent.id,
                reviewers=["人类总工程师"],
                acceptance_criteria=["顶部总览已成形", "工位区已出现", "移动端布局稳定"],
            ),
        ]
        db.add_all(tasks)
        db.flush()
        db.add_all(
            [
                TaskEvent(
                    task_id=tasks[0].id,
                    event_type="created",
                    message="已写入样板任务",
                    actor_type="system",
                ),
                TaskEvent(
                    task_id=tasks[1].id,
                    event_type="created",
                    message="已写入样板任务",
                    actor_type="system",
                ),
                TaskEvent(
                    task_id=tasks[2].id,
                    event_type="created",
                    message="已写入样板任务",
                    actor_type="system",
                ),
            ]
        )
        seeded = True

    if not _has_rows(db, UsageLog):
        usage = [
            UsageLog(
                project_id=platform_project.id,
                task_id=None,
                agent_id=boss_agent.id,
                provider="manual_codex_thread",
                model="线程驾驶舱",
                input_tokens=18000,
                output_tokens=5200,
                cached_tokens=1000,
                cost_cents=1820,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status="completed",
            ),
            UsageLog(
                project_id=platform_project.id,
                task_id=None,
                agent_id=fe_agent.id,
                provider="manual_codex_thread",
                model="线程驾驶舱",
                input_tokens=14000,
                output_tokens=4200,
                cached_tokens=800,
                cost_cents=1260,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status="completed",
            ),
            UsageLog(
                project_id=platform_project.id,
                task_id=None,
                agent_id=runner_agent.id,
                provider="local_runner",
                model="本地执行节点",
                input_tokens=2000,
                output_tokens=600,
                cached_tokens=0,
                cost_cents=180,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status="completed",
            ),
        ]
        db.add_all(usage)
        seeded = True

    if not _has_rows(db, Requirement):
        requirements = [
            Requirement(
                id="REQ-001",
                project_id=platform_project.id,
                task_id="TASK-012",
                title="庄园公告板：补齐需求管理库的列表与回复流转",
                requirement_type="thread_request",
                module="需求管理库",
                priority="P1",
                status="waiting_response",
                from_agent=boss_agent.id,
                to_agent=fe_agent.id,
                context_summary="目前庄园里只有任务看板，没有一块专门承接 AI 之间结构化提需求的公告板。需要先把需求列表、详情、更新和回复跑通。",
                expected_output="请先把需求库做成最小可用版本：能看到需求案、能更新状态、能回复消息，并把所有回复沉淀成记录。",
                related_files=["apps/api/app/modules/requirements", "apps/web/app/requirements"],
                max_response_tokens=3000,
                response_count=2,
                last_response_at=datetime.now(timezone.utc),
            ),
            Requirement(
                id="REQ-002",
                project_id=platform_project.id,
                task_id="TASK-004",
                title="庄园工位升级：让执行节点和需求案能互相接手",
                requirement_type="thread_request",
                module="执行与接手",
                priority="P2",
                status="in_progress",
                from_agent=runner_agent.id,
                to_agent=boss_agent.id,
                context_summary="需求案需要能明确谁发起、谁接手、谁回复，以及后续怎么把接手信息传给新的 AI 工位。",
                expected_output="增加回复记录、接手标记和最后回复时间，便于后续做上下文健康与换岗。",
                related_files=["apps/api/app/modules/requirements", "apps/api/app/modules/context"],
                max_response_tokens=2500,
                response_count=2,
                last_response_at=datetime.now(timezone.utc),
            ),
            Requirement(
                id="REQ-003",
                project_id=platform_project.id,
                task_id="TASK-012",
                title="沉淀基地经典：把需求直接转成知识条目",
                requirement_type="knowledge_note",
                module="知识库",
                priority="P1",
                status="accepted",
                from_agent=fe_agent.id,
                to_agent=boss_agent.id,
                context_summary="这是一条可以直接在知识页演示的样板需求，它已经被采纳，适合展示 requirements -> knowledge 的闭环。",
                expected_output="让知识页能直接看到一条来源于需求的沉淀记录，并保留来源、任务和摘要。",
                related_files=["apps/api/app/modules/requirements", "apps/web/app/requirements", "apps/web/app/knowledge"],
                max_response_tokens=2000,
                response_count=1,
                last_response_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(requirements)
        db.flush()
        db.add_all(
            [
                RequirementMessage(
                    requirement_id="REQ-001",
                    sender_type="human",
                    sender_id="human_lead",
                    message="请先补齐需求管理库的最小闭环，庄园里先要有可以公告、接单、回话的地方。",
                ),
                RequirementMessage(
                    requirement_id="REQ-001",
                    sender_type="agent",
                    sender_id=fe_agent.id,
                    message="收到，先实现需求列表、详情、更新和回复接口，前端再接一层最小页面。",
                    status_after_reply="in_progress",
                ),
                RequirementMessage(
                    requirement_id="REQ-002",
                    sender_type="human",
                    sender_id="human_lead",
                    message="把接手信息和最后回复时间记录下来，后面给上下文健康和换岗用。",
                ),
                RequirementMessage(
                    requirement_id="REQ-002",
                    sender_type="agent",
                    sender_id=runner_agent.id,
                    message="会把需求案的回复次数、最后回复时间和当前状态一起维护，方便后续接手。",
                    status_after_reply="in_progress",
                ),
                RequirementMessage(
                    requirement_id="REQ-003",
                    sender_type="human",
                    sender_id="human_lead",
                    message="这条需求就是现场演示样板，先把它沉淀到知识页里。",
                ),
                RequirementMessage(
                    requirement_id="REQ-003",
                    sender_type="agent",
                    sender_id=fe_agent.id,
                    message="收到，已按知识库语义采纳，知识页会直接展示这条来源于需求的记录。",
                    status_after_reply="accepted",
                ),
            ]
        )
        seeded = True

    if not _has_rows(db, CollaborationMessage):
        messages = [
            CollaborationMessage(
                id="msg-project-001",
                project_id=platform_project.id,
                message_type="comment_message",
                title="庄园早会",
                body="今天先把线程工位、审批门岗和交接邮局串成闭环，明早验收时从庄园首页一条线走到底。",
                sender_type="human",
                sender_id=chief_user.id,
                recipient_type="project",
                recipient_id=platform_project.id,
                status="open",
            ),
            CollaborationMessage(
                id="msg-task-001",
                project_id=platform_project.id,
                task_id="TASK-012",
                agent_id=fe_agent.id,
                message_type="task_message",
                title="首页收口",
                body="把基地页做成真正的庄园地图，所有入口要能点，文案只保留中文。",
                sender_type="human",
                sender_id=chief_user.id,
                recipient_type="agent",
                recipient_id=fe_agent.id,
                status="open",
            ),
            CollaborationMessage(
                id="msg-approval-001",
                project_id=primary_project.id,
                task_id="TASK-004",
                approval_id="APR-001",
                message_type="approval_message",
                title="实验楼提示",
                body="真机动作仍需人类确认，审批单里要写清楚风险、现场条件和回退手段。",
                sender_type="human",
                sender_id=hardware_user.id,
                recipient_type="approval",
                recipient_id="APR-001",
                status="open",
            ),
        ]
        db.add_all(messages)
        seeded = True

    if not _has_rows(db, Message):
        thread_messages = [
            Message(
                id="thread-msg-project-001",
                project_id=platform_project.id,
                entity_type="project",
                entity_id=platform_project.id,
                message_type="comment_message",
                sender_type="human",
                sender_id=chief_user.id,
                body="今晚先把项目消息入口、成员列表和邀请状态串起来。",
                data={"kind": "project_notice"},
            ),
            Message(
                id="thread-msg-task-001",
                project_id=platform_project.id,
                entity_type="task",
                entity_id="TASK-012",
                message_type="task_message",
                sender_type="human",
                sender_id=chief_user.id,
                body="TASK-012 先把基地首页入口稳定住，再补任务消息流。",
                data={"kind": "task_brief"},
            ),
            Message(
                id="thread-msg-requirement-001",
                project_id=platform_project.id,
                entity_type="requirement",
                entity_id="REQ-003",
                message_type="requirement_message",
                sender_type="agent",
                sender_id=fe_agent.id,
                body="需求已沉淀到知识库，后续按 requirement_message 继续追踪即可。",
                data={"kind": "requirement_reply"},
            ),
            Message(
                id="thread-msg-approval-001",
                project_id=platform_project.id,
                entity_type="approval",
                entity_id="APR-001",
                message_type="approval_message",
                sender_type="human",
                sender_id=hardware_user.id,
                body="这条审批要保留现场确认和回退说明，别只写一个通过。",
                data={"kind": "approval_notice"},
            ),
            Message(
                id="thread-msg-handoff-001",
                project_id=platform_project.id,
                entity_type="handoff",
                entity_id="TASK-012",
                message_type="handoff_message",
                sender_type="system",
                sender_id=None,
                body="当前交接包已入库，接手前先看上下文健康和最新 diff。",
                data={"kind": "handoff_hint"},
            ),
            Message(
                id="thread-msg-system-001",
                project_id=platform_project.id,
                entity_type="project",
                entity_id=platform_project.id,
                message_type="system_message",
                sender_type="system",
                sender_id=None,
                body="系统消息：项目、任务、审批、交接消息已接通。",
                data={"kind": "system_bootstrap"},
            ),
        ]
        db.add_all(thread_messages)
        seeded = True

    if not _has_rows(db, Approval):
        approvals = [
            Approval(
                project_id=platform_project.id,
                task_id="TASK-012",
                level="H3",
                action="烧录固件",
                status="pending",
                notes="需要人类确认后再进入下一步。",
            ),
            Approval(
                project_id=platform_project.id,
                task_id="TASK-004",
                level="H4",
                action="真机动作测试",
                status="rejected",
                approver_user_id="human_lead",
                notes="真机动作暂不允许自动执行。",
            ),
        ]
        db.add_all(approvals)
        seeded = True

    if not _has_rows(db, ContextHealthRecord):
        context_records = [
            ContextHealthRecord(
                project_id=platform_project.id,
                task_id="TASK-012",
                agent_id=fe_agent.id,
                usage_ratio=0.68,
                health="yellow",
                conversation_turns=14,
                files_loaded_count=9,
                failed_retry_count=1,
                summary="前端工位区上下文已进入中等负载，适合生成交接包后切换到新线程。",
                recommended_action="先压缩任务信息，再继续拆分视觉和交互页。",
            ),
            ContextHealthRecord(
                project_id=platform_project.id,
                task_id="TASK-004",
                agent_id=runner_agent.id,
                usage_ratio=0.42,
                health="green",
                conversation_turns=6,
                files_loaded_count=4,
                failed_retry_count=0,
                summary="Runner 闭环还在轻载阶段，可以继续补任务领取和日志回传接口。",
                recommended_action="优先补 next-task 和 result 回传，再扩展状态机。",
            ),
        ]
        db.add_all(context_records)
        seeded = True

    if not _has_rows(db, Handoff):
        handoffs = [
            Handoff(
                project_id=platform_project.id,
                task_id="TASK-012",
                handoff_from=fe_agent.id,
                handoff_to=boss_agent.id,
                payload={
                    "summary": "前端工位区已完成基础拆分，建议交给总控线程做下一轮范围确认。",
                    "reason": "页面视觉需要统一，继续分支前先收敛结构。",
                    "current_status": "needs_review",
                    "latest_files": ["apps/web/app/agents/page.tsx", "apps/web/app/base/page.tsx"],
                    "next_steps": ["确认统一视觉规范", "继续接入真实 API"],
                    "blocked_by": ["前端视觉统一策略"],
                    "context_health": {
                        "usage_ratio": 0.68,
                        "health": "yellow",
                        "conversation_turns": 14,
                    },
                },
            ),
        ]
        db.add_all(handoffs)
        seeded = True

    if not _has_rows(db, AuditLog):
        audit_logs = [
            AuditLog(
                project_id=platform_project.id,
                task_id="TASK-012",
                actor_type="system",
                actor_id="bootstrap",
                action="seed.initialized",
                resource_type="project",
                resource_id=platform_project.id,
                before={},
                after={"note": "bootstrap audit log"},
                success=True,
            ),
            AuditLog(
                project_id=platform_project.id,
                task_id="TASK-004",
                actor_type="system",
                actor_id="bootstrap",
                action="seed.initialized",
                resource_type="task",
                resource_id="TASK-004",
                before={},
                after={"note": "bootstrap audit log"},
                success=True,
            ),
        ]
        db.add_all(audit_logs)
        seeded = True

    if not _has_rows(db, User):
        users = [
            User(email="lead@example.com", name="项目负责人", display_name="项目负责人", bio="owner", is_active=True),
            User(email="frontend@example.com", name="frontend", display_name="Frontend Lead", bio="member", is_active=True),
            User(email="runner@example.com", name="runner", display_name="Runner Lead", bio="member", is_active=True),
            User(email="collab@example.com", name="collab", display_name="Collaboration Member", bio="member", is_active=True),
        ]
        db.add_all(users)
        db.flush()
        seeded = True

    users = list(db.scalars(select(User).order_by(User.created_at.asc())))
    lead_user = next((item for item in users if item.email == "lead@example.com"), users[0])
    frontend_user = next((item for item in users if item.email == "frontend@example.com"), users[0])
    runner_user = next((item for item in users if item.email == "runner@example.com"), users[-1])
    collab_user = next((item for item in users if item.email == "collab@example.com"), users[-1])

    if not _has_rows(db, ProjectMember):
        project_members = [
            ProjectMember(project_id=platform_project.id, user_id=lead_user.id, role="owner", status="active", is_owner=True),
            ProjectMember(project_id=platform_project.id, user_id=frontend_user.id, role="member", status="active", is_owner=False),
            ProjectMember(project_id=primary_project.id, user_id=runner_user.id, role="member", status="active", is_owner=False),
            ProjectMember(project_id=platform_project.id, user_id=collab_user.id, role="member", status="active", is_owner=False),
        ]
        db.add_all(project_members)
        seeded = True

    if not _has_rows(db, Invitation):
        invitations = [
            Invitation(
                email="joiner1@example.com",
                project_id=platform_project.id,
                role="member",
                invited_by_user_id=lead_user.id,
                token="invite-token-platform-1",
                status="pending",
                note="platform invite sample",
            ),
            Invitation(
                email="joiner2@example.com",
                project_id=primary_project.id,
                role="collaborator",
                invited_by_user_id=lead_user.id,
                token="invite-token-project-1",
                status="pending",
                note="project invite sample",
            ),
            Invitation(
                email=collab_user.email,
                project_id=platform_project.id,
                role="member",
                invited_by_user_id=lead_user.id,
                token="invite-token-platform-accepted",
                status="accepted",
                note="accepted invite sample",
                accepted_by_user_id=collab_user.id,
                accepted_at=datetime.now(timezone.utc),
            ),
        ]
        db.add_all(invitations)
        seeded = True

    if not _has_rows(db, ProjectInvite):
        project_invites = [
            ProjectInvite(
                project_id=platform_project.id,
                email="joiner3@example.com",
                role="member",
                token="project-invite-token-platform-1",
                status="pending",
                invited_by_user_id=lead_user.id,
                message="collaboration sample invite",
            ),
            ProjectInvite(
                project_id=primary_project.id,
                email="joiner4@example.com",
                role="collaborator",
                token="project-invite-token-project-1",
                status="pending",
                invited_by_user_id=lead_user.id,
                message="collaboration sample invite",
            ),
        ]
        db.add_all(project_invites)
        seeded = True

    if seeded:
        db.commit()


def normalize_sample_ids(db: Session) -> None:
    task_id_map = {
        "搭起后端骨架与健康检查": "TASK-001",
        "执行节点注册与心跳回传": "TASK-004",
        "重做基地首页主面板": "TASK-012",
    }

    for title, target_id in task_id_map.items():
        current_id = db.scalar(select(Task.id).where(Task.title == title))
        if current_id and current_id != target_id:
            db.execute(update(Task).where(Task.id == current_id).values(id=target_id))

    db.commit()


def normalize_sample_workflow_state(db: Session) -> None:
    target_statuses = {
        "TASK-001": "running",
        "TASK-004": "testing",
        "TASK-012": "ready",
    }

    changed = False
    for task_id, target_status in target_statuses.items():
        task = db.get(Task, task_id)
        if task is None or task.status == target_status:
            continue
        previous_status = task.status
        task.status = target_status
        db.add(task)
        db.add(
            TaskEvent(
                task_id=task.id,
                event_type="status_changed",
                message=f"系统已将任务状态调整为 {target_status}",
                data={"from_status": previous_status, "to_status": target_status},
                actor_type="system",
            )
        )
        changed = True

    if changed:
        db.commit()


def normalize_sample_requirement_policy(db: Session) -> None:
    projects = list(db.scalars(select(Project).order_by(Project.created_at.asc())))
    primary_project = projects[0] if projects else None
    platform_project = projects[1] if len(projects) > 1 else (projects[0] if projects else None)

    changed = False
    for project in projects:
        if project.requirement_policy is not None:
            continue
        if "康复" in (project.name or "") or "机器人" in (project.project_type or ""):
            project.requirement_policy = {
                "default_type": "hardware_request",
                "default_priority": "P1",
                "default_status": "waiting_response",
                "default_to_agent": "agent_runner_git",
                "promote_to_knowledge": True,
                "knowledge_module": "硬件知识",
                "allow_human_to_thread": True,
                "allow_thread_to_thread": True,
            }
        else:
            project.requirement_policy = {
                "default_type": "thread_request",
                "default_priority": "P1",
                "default_status": "waiting_response",
                "default_to_agent": "agent_boss",
                "promote_to_knowledge": True,
                "knowledge_module": "需求管理库",
                "allow_human_to_thread": True,
                "allow_thread_to_thread": True,
            }
        db.add(project)
        changed = True

    for project in projects:
        if project.collaboration_config is not None:
            continue
        project.collaboration_config = {
            "thread_workstations": [
                {"name": "前端工位", "agent_id": "agent_fe_game", "computer_node": "runner_pc1", "ai_provider": "manual_codex_thread"},
                {"name": "执行工位", "agent_id": "agent_runner_git", "computer_node": "runner_nanopi", "ai_provider": "local_runner"},
            ],
            "ai_providers": [
                {"id": "manual_codex_thread", "label": "人工线程"},
                {"id": "local_runner", "label": "本地执行"},
            ],
            "computer_nodes": [
                {"id": "runner_pc1", "label": "主控执行节点", "status": "online"},
                {"id": "runner_nanopi", "label": "边缘执行节点", "status": "offline"},
            ],
        }
        db.add(project)
        changed = True

    for requirement in db.scalars(select(Requirement).where(Requirement.requirement_type.is_(None))):
        requirement.requirement_type = "thread_request"
        db.add(requirement)
        changed = True

    if platform_project is not None and db.get(Requirement, "REQ-003") is None:
        requirement = Requirement(
            id="REQ-003",
            project_id=platform_project.id,
            task_id="TASK-012",
            title="沉淀基地经典：把需求直接转成知识条目",
            requirement_type="knowledge_note",
            module="知识库",
            priority="P1",
            status="accepted",
            from_agent="agent_fe_game",
            to_agent="agent_boss",
            context_summary="这是一条可以直接在知识页演示的样板需求，它已经被采纳，适合展示 requirements -> knowledge 的闭环。",
            expected_output="让知识页能直接看到一条来源于需求的沉淀记录，并保留来源、任务和摘要。",
            related_files=["apps/api/app/modules/requirements", "apps/web/app/requirements", "apps/web/app/knowledge"],
            max_response_tokens=2000,
            response_count=1,
            last_response_at=datetime.now(timezone.utc),
        )
        db.add(requirement)
        db.flush()
        db.add_all(
            [
                RequirementMessage(
                    requirement_id=requirement.id,
                    sender_type="human",
                    sender_id="human_lead",
                    message="这条需求就是现场演示样板，先把它沉淀到知识页里。",
                ),
                RequirementMessage(
                    requirement_id=requirement.id,
                    sender_type="agent",
                    sender_id="agent_fe_game",
                    message="收到，已按知识库语义采纳，知识页会直接展示这条来源于需求的记录。",
                    status_after_reply="accepted",
                ),
            ]
        )
        changed = True

    if changed:
        db.commit()


def normalize_sample_collaboration_config(db: Session) -> None:
    projects = list(db.scalars(select(Project).order_by(Project.created_at.asc())))
    changed = False

    for project in projects:
        if project.collaboration_config is not None:
            continue
        if "Rehabilitation" in (project.github_url or "") or "rehab" in (project.local_git_url or ""):
            project.collaboration_config = {
                "thread_workstations": [
                    {"name": "hardware_workstation", "agent_id": "agent_runner_git", "computer_node": "runner_nanopi", "ai_provider": "local_runner"},
                ],
                "ai_providers": [
                    {"id": "manual_codex_thread", "label": "manual thread"},
                    {"id": "local_runner", "label": "local runner"},
                ],
                "computer_nodes": [
                    {"id": "runner_nanopi", "label": "edge node", "status": "offline"},
                ],
            }
        else:
            project.collaboration_config = {
                "thread_workstations": [
                    {"name": "frontend_workstation", "agent_id": "agent_fe_game", "computer_node": "runner_pc1", "ai_provider": "manual_codex_thread"},
                    {"name": "execution_workstation", "agent_id": "agent_runner_git", "computer_node": "runner_nanopi", "ai_provider": "local_runner"},
                ],
                "ai_providers": [
                    {"id": "manual_codex_thread", "label": "manual thread"},
                    {"id": "local_runner", "label": "local runner"},
                ],
                "computer_nodes": [
                    {"id": "runner_pc1", "label": "main node", "status": "online"},
                    {"id": "runner_nanopi", "label": "edge node", "status": "offline"},
                ],
            }
        db.add(project)
        changed = True

    for project in projects:
        sync_project_collaboration_inventory(db, project, project.collaboration_config)
        changed = True

    if changed:
        db.commit()


def ensure_sample_task_events(db: Session) -> None:
    sample_events = {
        "TASK-001": "后端骨架已经搭好，准备接样板数据。",
        "TASK-004": "执行节点心跳链路已经接上，等待下一步回传。",
        "TASK-012": "基地首页已经切到庄园路线，继续补建筑感。",
    }

    for task_id, message in sample_events.items():
        has_event = db.scalar(select(TaskEvent.id).where(TaskEvent.task_id == task_id).limit(1))
        if not has_event:
            db.add(
                TaskEvent(
                    task_id=task_id,
                    event_type="created",
                    message=message,
                    actor_type="system",
                )
            )

    db.commit()
