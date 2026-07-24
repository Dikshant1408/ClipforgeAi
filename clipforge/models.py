from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    HIGHLIGHTING = "HIGHLIGHTING"
    HIGHLIGHTED = "HIGHLIGHTED"
    CLIPPING = "CLIPPING"
    CLIPPED = "CLIPPED"
    METADATA = "METADATA"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass
class Segment:
    start: float
    end: float
    score: float
    reason: str = ""


@dataclass
class ClipMetadata:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass
class SourceChannel:
    name: str
    channel_id: str
    enabled: bool = True
    priority: int = 100


@dataclass
class VideoRecord:
    video_id: str
    channel_id: str
    channel_name: str
    title: str
    url: str
    status: Status
    retry_count: int = 0
    last_error: str = ""
    source_path: str = ""
    clip_path: str = ""
    rank_score: float = 0.0
    discovered_at: str = ""
    meta_title: str = ""
    meta_description: str = ""
    meta_tags: str = ""
