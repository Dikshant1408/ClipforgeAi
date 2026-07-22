import json
import pytest
from clipforge.config import load_config

def _write(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)

VALID = {
    "source_channels": [
        {"name": "B", "channel_id": "UCB", "enabled": True, "priority": 2},
        {"name": "A", "channel_id": "UCA", "enabled": True, "priority": 1},
        {"name": "C", "channel_id": "UCC", "enabled": False, "priority": 3},
    ],
    "publish_time": "18:00",
    "timezone": "Asia/Kolkata",
    "monitor_interval_minutes": 10,
    "clip": {"min_seconds": 20, "max_seconds": 60, "crop": "center"},
    "whisper": {"model": "small", "device": "cuda", "language": "ko"},
    "llm": {"provider": "gemini", "model": "gemini-2.0-flash"},
    "youtube": {"privacy_status": "public", "category_id": "20"},
    "storage": {"root": "./storage"},
    "max_disk_gb": 50,
}

def test_load_valid(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))
    assert cfg.publish_time == ["18:00"]
    assert cfg.clip_max_seconds == 60
    assert len(cfg.source_channels) == 3
    assert cfg.whisper_language == "ko"

def test_whisper_language_defaults_to_none(tmp_path):
    no_lang = json.loads(json.dumps(VALID))
    del no_lang["whisper"]["language"]
    cfg = load_config(_write(tmp_path, no_lang))
    assert cfg.whisper_language is None

def test_load_multiple_publish_times(tmp_path):
    multiple = dict(VALID)
    multiple["publish_time"] = ["12:00", "18:00"]
    cfg = load_config(_write(tmp_path, multiple))
    assert cfg.publish_time == ["12:00", "18:00"]

def test_enabled_channels_sorted_by_priority(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))
    en = cfg.enabled_channels()
    assert [c.name for c in en] == ["A", "B"]

def test_invalid_publish_time_rejected(tmp_path):
    bad = dict(VALID)
    bad["publish_time"] = "6pm"
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))

def test_invalid_publish_time_list_rejected(tmp_path):
    bad = dict(VALID)
    bad["publish_time"] = ["12:00", "6pm"]
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))

    bad = dict(VALID)
    bad["publish_time"] = []
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))

def test_min_greater_than_max_rejected(tmp_path):
    bad = json.loads(json.dumps(VALID))
    bad["clip"]["min_seconds"] = 90
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))

def test_empty_channels_rejected(tmp_path):
    bad = json.loads(json.dumps(VALID))
    bad["source_channels"] = []
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))
