from __future__ import annotations
import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from clipforge.config import Config, load_config
from clipforge.db import Database
from clipforge.models import Status, VideoRecord, ClipMetadata
from clipforge.downloader import Downloader
from clipforge.transcribe import Transcriber
from clipforge.clipper import Clipper
from clipforge.cleanup import Cleanup
from clipforge.youtube import YouTubeUploader
from clipforge.pipeline import Pipeline
from clipforge.monitor import Monitor
from clipforge.llm import get_provider

log = logging.getLogger("clipforge")


class DryRunUploader:
    def __init__(self, storage_root: str):
        self._dir = Path(storage_root) / "dryrun"

    def upload(self, clip_path: str, meta: ClipMetadata) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        name = Path(clip_path).stem or "clip"
        out = self._dir / f"{name}.json"
        out.write_text(json.dumps({
            "clip_path": clip_path,
            "title": meta.title,
            "description": meta.description,
            "tags": meta.tags,
        }, indent=2), encoding="utf-8")
        return "DRYRUN"


def _make_llm(config: Config):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        log.warning("GEMINI_API_KEY not set; running degraded (no LLM)")
        return None
    try:
        return get_provider(config.llm_provider, config.llm_model, key)
    except Exception as e:
        log.warning("LLM init failed: %s", e)
        return None


def build_pipeline(config: Config, dry_run: bool) -> tuple[Database, Pipeline, Monitor]:
    db = Database(str(Path(config.storage_root) / "clipforge.db"))
    downloader = Downloader(config.storage_root)
    transcriber = Transcriber(config.whisper_model, config.whisper_device)
    clipper = Clipper(config.storage_root)
    cleanup = Cleanup(db, config.storage_root, config.max_disk_gb)
    uploader = (DryRunUploader(config.storage_root) if dry_run
                else YouTubeUploader(config.youtube_privacy_status,
                                     config.youtube_category_id))
    llm = _make_llm(config)
    pipe = Pipeline(db, downloader, transcriber, clipper, uploader,
                    cleanup, config, llm=llm)
    monitor = Monitor(db)
    return db, pipe, monitor


def _drain(pipe: Pipeline) -> None:
    while pipe.advance_one() is not None:
        pass


def run_once(config: Config, url: str) -> None:
    db, pipe, _ = build_pipeline(config, dry_run=True)
    vid = url.split("v=")[-1][:11] or "once"
    db.insert_discovered(VideoRecord(vid, "manual", "manual", "manual clip",
                                     url, Status.DISCOVERED,
                                     discovered_at=datetime.utcnow().isoformat()))
    _drain(pipe)
    pipe.publish_daily()
    log.info("run_once complete for %s", vid)


def run_forever(config: Config, dry_run: bool = False) -> None:
    db, pipe, monitor = build_pipeline(config, dry_run=dry_run)
    if not dry_run:
        log.info("Checking YouTube API credentials...")
        try:
            from clipforge.youtube import _default_service_factory
            _default_service_factory()
            log.info("YouTube credentials verified successfully.")
        except Exception as e:
            log.error("Failed to authenticate YouTube API on startup: %s", e)
            raise e
    db.reset_stuck()
    sched = BackgroundScheduler(timezone=config.timezone)
    sched.add_job(lambda: monitor.poll(config.reload().enabled_channels()),
                  "interval", minutes=config.monitor_interval_minutes,
                  id="monitor")
    sched.add_job(lambda: _drain(pipe), "interval", seconds=30, id="worker")
    hh, mm = config.publish_time.split(":")
    sched.add_job(pipe.publish_daily, "cron", hour=int(hh), minute=int(mm),
                  id="publish")
    sched.start()
    log.info("clipforge running; publish at %s %s (dry_run=%s)",
             config.publish_time, config.timezone, dry_run)
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
