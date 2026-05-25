from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings


client = TestClient(app)


def test_rehab_arm_sync_endpoints_store_non_realtime_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REHAB_ARM_SYNC_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    register = client.post(
        "/api/rehab-arm/v1/devices/register",
        json={
            "device_id": "nanopi-m5",
            "robot_id": "rehab-arm-alpha",
            "device_type": "nanopi",
            "software_version": "dev",
            "capabilities": ["ros2_bridge", "jsonl_recorder"],
        },
    )
    assert register.status_code == 200
    assert register.json()["data"]["sync_role"] == "non_realtime_data_only"

    manifest = client.post(
        "/api/rehab-arm/v1/sessions/manifest",
        json={
            "manifest": {
                "schema_version": "rehab_arm_manifest_v1",
                "sessions": [
                    {
                        "ok": True,
                        "session_id": "s1",
                        "device_id": "nanopi-m5",
                        "robot_id": "rehab-arm-alpha",
                    }
                ],
            }
        },
    )
    assert manifest.status_code == 200
    assert manifest.json()["data"]["accepted_sessions"] == ["s1"]

    file_upload = client.post(
        "/api/rehab-arm/v1/sessions/s1/files",
        content=b"--boundary\r\nsession payload\r\n--boundary--\r\n",
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )
    assert file_upload.status_code == 200
    file_data = file_upload.json()["data"]
    assert file_data["sync_status"] == "uploaded"
    assert Path(file_data["stored_body_path"]).exists()

    status = client.post(
        "/api/rehab-arm/v1/sessions/s1/sync-status",
        json={
            "device_id": "nanopi-m5",
            "sync_status": "uploaded",
            "file_name": "s1.jsonl",
            "record_count": 1,
        },
    )
    assert status.status_code == 200
    assert status.json()["data"]["sync_status"] == "uploaded"

    event_lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(event_lines) == 4
    get_settings.cache_clear()
