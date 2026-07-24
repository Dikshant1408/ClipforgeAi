import pytest
import json
from dashboard.app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_api_config_get(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "timezone" in data
    assert "publish_time" in data

def test_api_stats_get(client):
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "total" in data
    assert "disk_used_gb" in data

def test_api_logs_get(client):
    res = client.get("/api/logs")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert isinstance(data, list)

def test_storage_access_denied(client):
    # Try traversing out of the storage directory
    res = client.get("/storage/../../config.json")
    assert res.status_code == 403

def test_storage_invalid_extension(client):
    # Try requesting a file type that is not supported (e.g. .py)
    res = client.get("/storage/app.py")
    assert res.status_code == 400
