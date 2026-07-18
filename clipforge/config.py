from __future__ import annotations
import json
import re
from dataclasses import dataclass
from clipforge.models import SourceChannel

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class Config:
    source_channels: list[SourceChannel]
    publish_time: str
    timezone: str
    monitor_interval_minutes: int
    clip_min_seconds: int
    clip_max_seconds: int
    crop: str
    whisper_model: str
    whisper_device: str
    llm_provider: str
    llm_model: str
    youtube_privacy_status: str
    youtube_category_id: str
    storage_root: str
    max_disk_gb: int
    _path: str

    def enabled_channels(self) -> list[SourceChannel]:
        return sorted(
            [c for c in self.source_channels if c.enabled],
            key=lambda c: c.priority,
        )

    def reload(self) -> Config:
        return load_config(self._path)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)

    raw_channels = d.get("source_channels", [])
    _require(isinstance(raw_channels, list) and len(raw_channels) > 0,
             "source_channels must be a non-empty list")
    channels: list[SourceChannel] = []
    for c in raw_channels:
        _require("name" in c and "channel_id" in c,
                 "each channel needs name and channel_id")
        channels.append(SourceChannel(
            name=c["name"],
            channel_id=c["channel_id"],
            enabled=bool(c.get("enabled", True)),
            priority=int(c.get("priority", 100)),
        ))

    publish_time = d.get("publish_time", "")
    _require(bool(_TIME_RE.match(publish_time)),
             "publish_time must be HH:MM 24-hour")

    clip = d.get("clip", {})
    mn = int(clip.get("min_seconds", 20))
    mx = int(clip.get("max_seconds", 60))
    _require(0 < mn <= mx, "clip.min_seconds must be >0 and <= max_seconds")
    crop = clip.get("crop", "center")
    _require(crop == "center", "only crop=center supported in v1")

    return Config(
        source_channels=channels,
        publish_time=publish_time,
        timezone=d.get("timezone", "UTC"),
        monitor_interval_minutes=int(d.get("monitor_interval_minutes", 10)),
        clip_min_seconds=mn,
        clip_max_seconds=mx,
        crop=crop,
        whisper_model=d.get("whisper", {}).get("model", "small"),
        whisper_device=d.get("whisper", {}).get("device", "cpu"),
        llm_provider=d.get("llm", {}).get("provider", "gemini"),
        llm_model=d.get("llm", {}).get("model", "gemini-2.0-flash"),
        youtube_privacy_status=d.get("youtube", {}).get("privacy_status", "public"),
        youtube_category_id=d.get("youtube", {}).get("category_id", "20"),
        storage_root=d.get("storage", {}).get("root", "./storage"),
        max_disk_gb=int(d.get("max_disk_gb", 50)),
        _path=path,
    )
