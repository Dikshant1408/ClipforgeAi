import json
from pathlib import Path
from unittest.mock import patch
import pytest
from dashboard.app import app
from clipforge.config import Config
from clipforge.db import Database


@pytest.fixture
def mock_config(tmp_path):
    return Config(
        source_channels=[],
        publish_time="18:00",
        timezone="Asia/Kolkata",
        monitor_interval_minutes=10,
        clip_min_seconds=20,
        clip_max_seconds=60,
        crop="center",
        hook_lead_seconds=1.5,
        whisper_model="small",
        whisper_device="cpu",
        whisper_language="",
        llm_provider="gemini",
        llm_model="gemini-2.0-flash",
        youtube_privacy_status="public",
        youtube_category_id="20",
        storage_root=str(tmp_path),
        max_disk_gb=50.0,
        _path=str(tmp_path / "config.json")
    )


@pytest.fixture
def mock_db(tmp_path):
    db_path = tmp_path / "test.db"
    return Database(str(db_path))


@pytest.fixture
def client(mock_config, mock_db):
    app.config["TESTING"] = True
    with patch("dashboard.app._get_config", return_value=mock_config), \
         patch("dashboard.app._get_db", return_value=mock_db), \
         patch("dashboard.app.CONFIG_PATH", "./config.json"):
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
