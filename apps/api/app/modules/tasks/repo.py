from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.task import Task
from app.db.models.task_event import TaskEvent

from .schemas import TaskCreate, TaskUpdate


def list_tasks(db: Session, project_ids: list[str] | None = None) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
    if project_ids:
        stmt = stmt.where(Task.project_id.in_(project_ids))
    return list(db.scalars(stmt))


def get_task(db: Session, task_id: str) -> Task | None:
    return db.get(Task, task_id)


def create_task(db: Session, payload: TaskCreate) -> Task:
    task = Task(**payload.model_dump())
    db.add(task)
    db.flush()
    db.add(TaskEvent(task_id=task.id, event_type="created", message="已创建任务", actor_type="human"))
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: Task, payload: TaskUpdate) -> Task:
    before_status = task.status
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(task, key, value)
    db.add(task)

    if "status" in updates and updates["status"] != before_status:
        db.add(
            TaskEvent(
                task_id=task.id,
                event_type="status_changed",
                message=f"任务状态已从 {before_status} 更新为 {updates['status']}",
                actor_type="system",
            )
        )

    db.commit()
    db.refresh(task)
    return task


def list_task_events(db: Session, task_id: str) -> list[TaskEvent]:
    return list(db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.asc())))


def create_task_event(
    db: Session,
    task_id: str,
    event_type: str,
    message: str,
    data: dict | None = None,
    *,
    actor_type: str = "system",
    actor_id: str | None = None,
    commit: bool = True,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task_id,
        event_type=event_type,
        message=message,
        data=data or {},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()
    return event
