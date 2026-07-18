from __future__ import annotations
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable
from clipforge.db import Database
from clipforge.models import SourceChannel, VideoRecord, Status

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def parse_feed(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    items: list[dict] = []
    for entry in root.findall("atom:entry", _NS):
        vid_el = entry.find("yt:videoId", _NS)
        title_el = entry.find("atom:title", _NS)
        link_el = entry.find("atom:link", _NS)
        pub_el = entry.find("atom:published", _NS)
        if vid_el is None or vid_el.text is None:
            continue
        items.append({
            "video_id": vid_el.text,
            "title": title_el.text if title_el is not None else "",
            "url": link_el.get("href") if link_el is not None else
                   f"https://www.youtube.com/watch?v={vid_el.text}",
            "published": pub_el.text if pub_el is not None else "",
        })
    return items


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


class Monitor:
    def __init__(self, db: Database, fetch: Callable[[str], str] = _default_fetch):
        self._db = db
        self._fetch = fetch

    def poll(self, channels: list[SourceChannel]) -> list[str]:
        new_ids: list[str] = []
        for ch in channels:
            try:
                xml = self._fetch(feed_url(ch.channel_id))
                items = parse_feed(xml)
            except Exception:
                continue
            for it in items:
                rec = VideoRecord(
                    video_id=it["video_id"],
                    channel_id=ch.channel_id,
                    channel_name=ch.name,
                    title=it["title"],
                    url=it["url"],
                    status=Status.DISCOVERED,
                    discovered_at=it["published"],
                )
                if self._db.insert_discovered(rec):
                    new_ids.append(it["video_id"])
        return new_ids
