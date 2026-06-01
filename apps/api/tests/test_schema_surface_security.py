from __future__ import annotations

from app.modules.approvals.schemas import ApprovalActionRequest, ApprovalCreate, ApprovalUpdate
from app.modules.audit.schemas import AuditCreate
from app.modules.collaboration.schemas import RunnerRelayCommandCreate
from app.modules.lab.schemas import LabApprovalRequestCreate, LabCheckRecordCreate


def test_security_write_schemas_do_not_expose_actor_or_status_fields() -> None:
    assert set(ApprovalCreate.model_fields) == {"project_id", "task_id", "level", "action", "notes"}
    assert set(ApprovalUpdate.model_fields) == {"notes"}
    assert set(ApprovalActionRequest.model_fields) == {"notes"}

    assert set(LabCheckRecordCreate.model_fields) == {"task_id", "item", "passed", "notes"}
    assert set(LabApprovalRequestCreate.model_fields) == {"task_id", "action", "level", "notes"}

    assert set(AuditCreate.model_fields) == {
        "project_id",
        "task_id",
        "action",
        "resource_type",
        "resource_id",
        "before",
        "after",
        "success",
        "error_message",
    }
    assert set(RunnerRelayCommandCreate.model_fields) == {
        "task_id",
        "dispatch_id",
        "title",
        "body",
        "runner_id",
        "computer_node_id",
        "workstation_id",
        "metadata",
    }
