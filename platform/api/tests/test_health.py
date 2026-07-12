from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["status"] == "ok"
    assert isinstance(data["pid"], int)
    assert isinstance(data["local_services"], list)
    assert {item["port"] for item in data["local_services"]} >= {3000, 3001, 8010, 8011}
    assert data["deployment"]["build_sha"]
    assert data["deployment"]["build_ref"]
    assert data["deployment"]["build_time"]
    assert data["deployment"]["app_env"] == "test"
