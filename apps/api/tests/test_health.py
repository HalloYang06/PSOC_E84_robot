from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "ok"
    assert isinstance(payload["data"]["pid"], int)
    assert isinstance(payload["data"]["local_services"], list)
    assert {item["port"] for item in payload["data"]["local_services"]} >= {3000, 8010, 8011}
