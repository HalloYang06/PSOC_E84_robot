from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _auth() -> tuple[str, str]:
    response = client.post(
        "/api/auth/session",
        json={"email": "lead@example.com", "password": "password"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["id"]


def _create_project(token: str) -> str:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"Qualification {suffix}",
            "project_type": "software",
            "github_url": "https://example.com/q.git",
            "local_git_url": "/workspace/q.git",
            "default_branch": "main",
            "develop_branch": "develop",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def _add_owner(project_id: str, token: str, user_id: str) -> None:
    response = client.post(
        f"/api/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "is_owner": True,
        },
    )
    assert response.status_code == 200, response.text


def _scorecard(project_id: str, token: str) -> dict:
    response = client.get(
        f"/api/qualification/projects/{project_id}/scorecard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_empty_project_returns_neutral_grades_not_d():
    """A brand-new project with no runners / NPCs / tasks must show neutral '-'
    rather than red D for every indicator. The user's complaint was that empty
    projects looked like failed projects."""
    token, user_id = _auth()
    pid = _create_project(token)
    _add_owner(pid, token, user_id)

    sc = _scorecard(pid, token)
    inds = sc["indicators"]

    # No runners → neutral, not D
    assert inds["thread_call_health"]["grade"] == "-"
    assert inds["thread_call_health"]["value"] is None
    assert "尚未绑定 runner" in inds["thread_call_health"]["detail"]

    # No NPCs → neutral, not D
    assert inds["npc_handover_health"]["grade"] == "-"
    assert inds["npc_handover_health"]["value"] is None

    # No approvals at all → neutral, not D (different from "0 minute response")
    assert inds["human_review_responsiveness"]["grade"] == "-"

    # No tasks + no messages → neutral
    assert inds["collaboration_density"]["grade"] == "-"

    # Hardware redline always has a grade (count starts at 0 → A)
    assert inds["hardware_redline_count"]["grade"] == "A"
    assert inds["hardware_redline_count"]["count_7d"] == 0

    # token_spend always has neutral grade (no SLO defined)
    assert inds["token_spend_7d_yuan"]["grade"] == "-"

    # Overall must be neutral too, with helpful onboarding hint
    assert sc["overall"]["grade"] == "-"
    assert sc["overall"]["score"] is None
    assert "先绑电脑" in sc["overall"]["summary"] or "先" in sc["overall"]["summary"]


def test_overall_score_uses_only_indicators_with_data():
    """If only some indicators have data, overall_score should weight only those,
    not include zero-fallback values from the empty ones."""
    token, user_id = _auth()
    pid = _create_project(token)
    _add_owner(pid, token, user_id)

    # Default empty project — only hardware_redline gets a grade ("A"), all
    # weighted indicators are None → overall must be neutral.
    sc = _scorecard(pid, token)
    assert sc["overall"]["grade"] == "-"
    assert sc["overall"]["score"] is None


def test_scorecard_response_shape_is_stable():
    """Front-end relies on every indicator having {label, detail, grade}.
    Lock the keys so we don't silently drop them."""
    token, user_id = _auth()
    pid = _create_project(token)
    _add_owner(pid, token, user_id)

    sc = _scorecard(pid, token)
    assert sc["project_id"] == pid
    assert sc["window_days"] == 7

    expected_keys = {
        "thread_call_health",
        "npc_handover_health",
        "human_review_responsiveness",
        "hardware_redline_count",
        "collaboration_density",
        "token_spend_7d_yuan",
    }
    assert set(sc["indicators"].keys()) == expected_keys

    for key, ind in sc["indicators"].items():
        assert "label" in ind, f"{key} missing label"
        assert "detail" in ind, f"{key} missing detail"
        assert "grade" in ind, f"{key} missing grade"
        assert ind["grade"] in {"A", "B", "C", "D", "-"}, f"{key} has invalid grade {ind['grade']!r}"

    overall = sc["overall"]
    assert "grade" in overall and overall["grade"] in {"A", "B", "C", "D", "-"}
    assert "summary" in overall
    assert "score" in overall  # may be None when neutral


def test_npc_with_no_recent_handoffs_is_b_not_d():
    """A stable project with NPCs but no handoffs in the last 7 days is the
    expected steady state, not a failure mode. Should show B, not D."""
    token, user_id = _auth()
    pid = _create_project(token)
    _add_owner(pid, token, user_id)

    # Create one NPC (workstation) so npc_count > 0
    response = client.post(
        f"/api/collaboration/projects/{pid}/thread-workstations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": f"NPC-{uuid4().hex[:6]}",
            "agent_id": "ai-fe-lead",
            "ai_provider_id": None,
            "computer_node_id": None,
            "status": "active",
            "description": "stable npc",
        },
    )
    assert response.status_code == 200, response.text

    sc = _scorecard(pid, token)
    npc_ind = sc["indicators"]["npc_handover_health"]
    assert npc_ind["grade"] == "B"
    assert npc_ind["value"] == 0.75
    assert "稳态运行" in npc_ind["detail"]
