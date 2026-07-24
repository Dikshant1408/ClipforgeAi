from __future__ import annotations
import json
import os
import sys
import logging
from pathlib import Path

# Ensure the project root is on the path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from clipforge.config import load_config, Config, setup_file_logging
from clipforge.db import Database
from clipforge.models import Status

CONFIG_PATH = str(ROOT / "config.json")
try:
    _startup_cfg = load_config(CONFIG_PATH)
    setup_file_logging(_startup_cfg.storage_root)
except Exception:
    pass


app = Flask(__name__, static_folder=str(Path(__file__).parent), static_url_path="")
CORS(app)

log = logging.getLogger("clipforge.dashboard")

# Force no-cache on every API response so the dashboard always sees fresh data.
@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config() -> Config:
    return load_config(CONFIG_PATH)


def _get_db() -> Database:
    cfg = _get_config()
    db_path = str(Path(cfg.storage_root) / "clipforge.db")
    return Database(db_path)


def _config_to_dict(cfg: Config) -> dict:
    return {
        "source_channels": [
            {
                "name": c.name,
                "channel_id": c.channel_id,
                "enabled": c.enabled,
                "priority": c.priority,
            }
            for c in cfg.source_channels
        ],
        "publish_time": cfg.publish_time,
        "timezone": cfg.timezone,
        "monitor_interval_minutes": cfg.monitor_interval_minutes,
        "clip": {
            "min_seconds": cfg.clip_min_seconds,
            "max_seconds": cfg.clip_max_seconds,
            "crop": cfg.crop,
            "hook_lead_seconds": cfg.hook_lead_seconds,
        },
        "whisper": {
            "model": cfg.whisper_model,
            "device": cfg.whisper_device,
        },
        "llm": {
            "provider": cfg.llm_provider,
            "model": cfg.llm_model,
        },
        "youtube": {
            "privacy_status": cfg.youtube_privacy_status,
            "category_id": cfg.youtube_category_id,
        },
        "storage": {"root": cfg.storage_root},
        "max_disk_gb": cfg.max_disk_gb,
    }


def _save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Static SPA
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(Path(__file__).parent, "index.html")


# ---------------------------------------------------------------------------
# API – Config
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def get_config():
    try:
        cfg = _get_config()
        return jsonify(_config_to_dict(cfg))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["POST"])
def save_config():
    try:
        data = request.get_json(force=True)
        _save_config(data)
        load_config(CONFIG_PATH)  # validate
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# API – Channels
# ---------------------------------------------------------------------------

@app.route("/api/channels", methods=["GET"])
def get_channels():
    cfg = _get_config()
    return jsonify([
        {"name": c.name, "channel_id": c.channel_id,
         "enabled": c.enabled, "priority": c.priority}
        for c in cfg.source_channels
    ])


@app.route("/api/channels", methods=["POST"])
def add_channel():
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    channel_id = body.get("channel_id", "").strip()
    if not name or not channel_id:
        return jsonify({"error": "name and channel_id required"}), 400

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg_data = json.load(f)

    for ch in cfg_data.get("source_channels", []):
        if ch["channel_id"] == channel_id:
            return jsonify({"error": "Channel already exists"}), 409

    cfg_data.setdefault("source_channels", []).append({
        "name": name,
        "channel_id": channel_id,
        "enabled": body.get("enabled", True),
        "priority": int(body.get("priority", 100)),
    })
    _save_config(cfg_data)
    return jsonify({"ok": True})


@app.route("/api/channels/<channel_id>", methods=["PUT"])
def update_channel(channel_id: str):
    body = request.get_json(force=True)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg_data = json.load(f)

    found = False
    for ch in cfg_data.get("source_channels", []):
        if ch["channel_id"] == channel_id:
            ch["name"] = body.get("name", ch["name"])
            ch["enabled"] = bool(body.get("enabled", ch["enabled"]))
            ch["priority"] = int(body.get("priority", ch["priority"]))
            found = True
            break

    if not found:
        return jsonify({"error": "Channel not found"}), 404
    _save_config(cfg_data)
    return jsonify({"ok": True})


@app.route("/api/channels/<channel_id>", methods=["DELETE"])
def delete_channel(channel_id: str):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg_data = json.load(f)

    before = len(cfg_data.get("source_channels", []))
    cfg_data["source_channels"] = [
        c for c in cfg_data.get("source_channels", [])
        if c["channel_id"] != channel_id
    ]
    if len(cfg_data["source_channels"]) == before:
        return jsonify({"error": "Channel not found"}), 404
    _save_config(cfg_data)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API – Videos / Pipeline
# ---------------------------------------------------------------------------

@app.route("/api/videos", methods=["GET"])
def get_videos():
    try:
        db = _get_db()
        status_filter = request.args.get("status")
        conn = db._conn
        if status_filter and status_filter != "ALL":
            rows = conn.execute(
                "SELECT * FROM videos WHERE status=? ORDER BY discovered_at DESC LIMIT 300",
                (status_filter.upper(),)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM videos ORDER BY discovered_at DESC LIMIT 300"
            ).fetchall()

        keys = [d[0] for d in conn.execute("SELECT * FROM videos LIMIT 0").description or []]

        def safe(r, k):
            try:
                return r[k]
            except (IndexError, KeyError):
                return ""

        videos = []
        for r in rows:
            videos.append({
                "video_id": r["video_id"],
                "channel_id": r["channel_id"],
                "channel_name": r["channel_name"],
                "title": r["title"],
                "url": r["url"],
                "status": r["status"],
                "retry_count": r["retry_count"],
                "last_error": r["last_error"],
                "rank_score": r["rank_score"],
                "discovered_at": r["discovered_at"],
                "meta_title": safe(r, "meta_title"),
                "meta_description": safe(r, "meta_description"),
                "meta_tags": safe(r, "meta_tags"),
            })
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<video_id>", methods=["PUT"])
def update_video_meta(video_id: str):
    body = request.get_json(force=True)
    try:
        db = _get_db()
        rec = db.get(video_id)
        if not rec:
            return jsonify({"error": "Video not found"}), 404

        tags = body.get("meta_tags", rec.meta_tags)
        if isinstance(tags, list):
            tags = ",".join(tags)

        db.set_metadata(
            video_id,
            body.get("meta_title", rec.meta_title),
            body.get("meta_description", rec.meta_description),
            tags.split(",") if isinstance(tags, str) and tags else [],
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<video_id>/reset", methods=["POST"])
def reset_video(video_id: str):
    try:
        db = _get_db()
        rec = db.get(video_id)
        if not rec:
            return jsonify({"error": "Video not found"}), 404
        db.set_status(video_id, Status.DISCOVERED)
        db._conn.execute(
            "UPDATE videos SET retry_count=0, last_error='' WHERE video_id=?",
            (video_id,)
        )
        db._conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<video_id>", methods=["DELETE"])
def delete_video(video_id: str):
    try:
        db = _get_db()
        db._conn.execute("DELETE FROM videos WHERE video_id=?", (video_id,))
        db._conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API – Actions
# ---------------------------------------------------------------------------

@app.route("/api/publish-now", methods=["POST"])
def publish_now():
    try:
        from clipforge.scheduler import build_pipeline
        cfg = _get_config()
        _, pipe, _ = build_pipeline(cfg, dry_run=False)
        result = pipe.publish_daily()
        if result:
            return jsonify({"ok": True, "video_id": result})
        return jsonify({"ok": False, "message": "No READY clips available to publish"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/poll-now", methods=["POST"])
def poll_now():
    try:
        from clipforge.monitor import Monitor
        cfg = _get_config()
        db = _get_db()
        monitor = Monitor(db)
        new_ids = monitor.poll(cfg.enabled_channels())
        return jsonify({"ok": True, "new_videos": len(new_ids), "ids": new_ids})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API – Stats
# ---------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        db = _get_db()
        conn = db._conn
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM videos GROUP BY status"
        ).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}
        total = sum(counts.values())

        cfg = _get_config()
        storage = Path(cfg.storage_root)
        disk_used_gb = 0.0
        if storage.exists():
            disk_used_gb = sum(
                f.stat().st_size for f in storage.rglob("*") if f.is_file()
            ) / (1024 ** 3)

        recent = conn.execute(
            "SELECT video_id, channel_name, title, discovered_at FROM videos "
            "WHERE status='PUBLISHED' AND (last_error = '' OR last_error IS NULL) "
            "ORDER BY discovered_at DESC LIMIT 10"
        ).fetchall()

        return jsonify({
            "total": total,
            "by_status": counts,
            "disk_used_gb": round(disk_used_gb, 2),
            "max_disk_gb": cfg.max_disk_gb,
            "recent_published": [
                {
                    "video_id": r["video_id"],
                    "channel_name": r["channel_name"],
                    "title": r["title"],
                    "discovered_at": r["discovered_at"],
                }
                for r in recent
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API – Advanced Dashboard Operations
# ---------------------------------------------------------------------------

@app.route("/storage/<path:filename>", methods=["GET"])
def get_storage_file(filename):
    try:
        cfg = _get_config()
        storage_dir = Path(cfg.storage_root).resolve()
        target_path = (storage_dir / filename).resolve()
        if not str(target_path).startswith(str(storage_dir)):
            return jsonify({"error": "Access denied"}), 403
        if target_path.suffix.lower() not in [".mp4", ".wav", ".ass", ".json"]:
            return jsonify({"error": "Unsupported file type"}), 400
        if not target_path.exists():
            return jsonify({"error": "File not found"}), 404
        return send_from_directory(str(storage_dir), filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs", methods=["GET"])
def get_logs():
    try:
        cfg = _get_config()
        log_file = Path(cfg.storage_root) / "clipforge.log"
        if not log_file.exists():
            return jsonify([])
        
        limit = request.args.get("limit", 150, type=int)
        from collections import deque
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = list(deque(f, limit))
        return jsonify([line.rstrip("\n") for line in lines])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<video_id>/advance", methods=["POST"])
def advance_video(video_id: str):
    try:
        from clipforge.scheduler import build_pipeline
        cfg = _get_config()
        db, pipe, _ = build_pipeline(cfg, dry_run=False)
        rec = db.get(video_id)
        if not rec:
            return jsonify({"error": "Video not found"}), 404
        
        if rec.status == Status.READY:
            return jsonify({"ok": False, "message": "Video is already READY and waiting to be published."})
        if rec.status == Status.PUBLISHED:
            return jsonify({"ok": False, "message": "Video is already PUBLISHED."})
        if rec.status == Status.PUBLISHING:
            return jsonify({"ok": False, "message": "Video is currently publishing."})
        
        # If the video is FAILED, reset it first
        if rec.status == Status.FAILED:
            db.set_status(video_id, Status.DISCOVERED)
            db._conn.execute(
                "UPDATE videos SET retry_count=0, last_error='' WHERE video_id=?",
                (video_id,)
            )
            db._conn.commit()
            rec = db.get(video_id)
        
        # Stuck/In-progress mapping
        stuck_map = {
            Status.DOWNLOADING: Status.DISCOVERED,
            Status.TRANSCRIBING: Status.DOWNLOADED,
            Status.HIGHLIGHTING: Status.TRANSCRIBED,
            Status.CLIPPING: Status.HIGHLIGHTED,
            Status.METADATA: Status.CLIPPED,
        }
        if rec.status in stuck_map:
            stable_status = stuck_map[rec.status]
            db.set_status(video_id, stable_status)
            rec = db.get(video_id)

        old_status = rec.status
        try:
            pipe._handle(rec)
            updated_rec = db.get(video_id)
            return jsonify({
                "ok": True,
                "video_id": video_id,
                "old_status": old_status.value,
                "new_status": updated_rec.status.value
            })
        except Exception as e:
            count = db.bump_retry(video_id, str(e))
            db.reset_stuck()
            if count > 3:
                db.set_status(video_id, Status.FAILED, str(e))
            updated_rec = db.get(video_id)
            return jsonify({
                "ok": False,
                "error": str(e),
                "video_id": video_id,
                "old_status": old_status.value,
                "new_status": updated_rec.status.value
            }), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app.run(host="0.0.0.0", port=5050, debug=True)

