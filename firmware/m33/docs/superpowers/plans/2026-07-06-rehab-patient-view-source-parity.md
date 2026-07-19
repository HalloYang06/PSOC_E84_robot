# Rehab Patient View Source Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local backend source and tests preserve the deployed `data.patient_view` contract used by Stitch and browser QA.

**Architecture:** Keep `patient_view` inside the existing mobile bootstrap builder so `/api/rehab-arm/app/v1/me` remains the single frontend bootstrap endpoint. Add small serializer helpers in `cloud/rehab-platform/app/api/routes/rehab_app.py` that translate existing profile, readiness, device, and Agent metadata into patient-facing Chinese copy without raw hardware/debug terms.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, existing `tools/qa_rehab_mobile_acceptance.py` smoke script.

---

### Task 1: Add Source-Level Patient View Regression Test

**Files:**
- Modify: `cloud/rehab-platform/tests/test_app_compat.py`

- [ ] **Step 1: Write the failing test**

```python
def test_mobile_bootstrap_includes_patient_view_without_raw_debug_terms():
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    headers = _auth_headers(client)

    response = client.get("/api/rehab-arm/app/v1/me", headers=headers)

    assert response.status_code == 200
    patient_view = response.json()["data"]["patient_view"]
    assert sorted(patient_view.keys()) == ["agent", "device", "home", "profile"]
    raw_text = json.dumps(patient_view, ensure_ascii=False)
    for term in ("M33", "M55", "SPP", "CAN", "UUID", "preflight", "setup_required", "early_active"):
        assert term not in raw_text
    assert patient_view["home"]["primary_action"]["label"]
    assert patient_view["agent"]["entry_label"] == "问康复师"
    assert patient_view["device"]["binding_steps"][0] == "打开康复设备电源"
    assert patient_view["profile"]["medical_constraints"]["status"] in {"待完善", "已填写"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd cloud\rehab-platform
..\.venv\Scripts\python.exe -m pytest tests\test_app_compat.py::test_mobile_bootstrap_includes_patient_view_without_raw_debug_terms -q
```

Expected: FAIL with missing `patient_view`.

- [ ] **Step 3: Write minimal implementation**

Add `patient_view` to `build_mobile_bootstrap` and define small helpers:

```python
patient_view = _patient_view_for_mobile(profile, device_payloads, readiness_status, readiness_summary, next_action)
```

The helper returns four sections: `home`, `profile`, `device`, and `agent`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
cd cloud\rehab-platform
..\.venv\Scripts\python.exe -m pytest tests\test_app_compat.py::test_mobile_bootstrap_includes_patient_view_without_raw_debug_terms -q
```

Expected: PASS.

### Task 2: Run Backend Regression Suite And Smoke

**Files:**
- Verify: `cloud/rehab-platform/tests/*.py`
- Verify: `tools/qa_rehab_mobile_acceptance.py`

- [ ] **Step 1: Run local backend tests**

```powershell
cd cloud\rehab-platform
..\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run cloud acceptance smoke**

```powershell
$env:REHAB_QA_EMAIL='<staging email>'
$env:REHAB_QA_PASSWORD='<staging password>'
cloud\rehab-platform\.venv\Scripts\python.exe tools\qa_rehab_mobile_acceptance.py
```

Expected: `overall = PASS`, `p0_failed = 0`, `P0-PATIENT-VIEW-001 = PASS`.

### Task 3: Deploy And Record Evidence

**Files:**
- Modify: `docs/deployments/rehab-mobile-cloud-agent-20260705.md`
- Modify or create: `docs/qa/rehab-mobile-20260706/QA_REPORT.md`

- [ ] **Step 1: Deploy backend source parity to cloud**

Upload the changed `rehab_app.py`, restart the API service with the existing staging environment, and verify `/health`.

- [ ] **Step 2: Verify package delivery**

Run the acceptance smoke and confirm APK HEAD remains `200`, APK content type, and size over 1 MB.

- [ ] **Step 3: Update docs**

Record build SHA/PID, test commands, and the fact that frontend P0 remains blocked on Stitch.
