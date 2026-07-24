from __future__ import annotations
from pathlib import Path
from clipforge.db import Database
from clipforge.models import Status, ClipMetadata
from clipforge import highlights, metadata

_MAX_RETRIES = 3

# stage order: (current_status, in_progress_status, handler_name)
_STAGES = [
    Status.DISCOVERED, Status.DOWNLOADED, Status.TRANSCRIBED,
    Status.HIGHLIGHTED, Status.CLIPPED,
]


class Pipeline:
    def __init__(self, db: Database, downloader, transcriber, clipper,
                 uploader, cleanup, config, llm=None):
        self._db = db
        self._dl = downloader
        self._tr = transcriber
        self._clip = clipper
        self._up = uploader
        self._cleanup = cleanup
        self._cfg = config
        self._llm = llm
        self._segments: dict[str, list] = {}
        self._best: dict[str, object] = {}

    def _handle(self, rec) -> None:
        vid = rec.video_id
        root = Path(self._cfg.storage_root)
        if rec.status == Status.DISCOVERED:
            if self._dl.is_live(rec.url):
                raise RuntimeError("still live")
            try:
                duration = self._dl.duration(rec.url)
                if duration > 0 and duration <= 60:
                    self._db.set_status(vid, Status.PUBLISHED, "skipped: already a short")
                    return
                if self._dl.was_live(rec.url):
                    self._db.set_status(vid, Status.PUBLISHED, "skipped: was a livestream")
                    return
            except Exception:
                pass
            self._db.set_status(vid, Status.DOWNLOADING)
            path = self._dl.download(vid, rec.url)
            self._db.set_paths(vid, source_path=path)
            self._db.set_status(vid, Status.DOWNLOADED)
        elif rec.status == Status.DOWNLOADED:
            self._db.set_status(vid, Status.TRANSCRIBING)
            audio = str(root / "audio" / f"{vid}.wav")
            (root / "audio").mkdir(parents=True, exist_ok=True)
            segs = self._tr.transcribe(rec.source_path, audio)
            self._segments[vid] = segs
            self._db.set_status(vid, Status.TRANSCRIBED)
        elif rec.status == Status.TRANSCRIBED:
            self._db.set_status(vid, Status.HIGHLIGHTING)
            segs = self._segments.get(vid, [])
            audio_path = str(root / "audio" / f"{vid}.wav")
            
            # No-speech handling: generate dummy segments every 10s if transcript is empty
            if not segs:
                from clipforge.transcribe import TranscriptSeg
                duration = self._dl.duration(rec.url)
                if duration <= 0:
                    duration = 100.0  # fallback
                step = 10.0
                segs = []
                for t in range(0, int(duration), int(step)):
                    segs.append(TranscriptSeg(
                        start=float(t),
                        end=float(min(t + step, duration)),
                        text="",
                        words=[]
                    ))
                self._segments[vid] = segs
                
            energy_fn = highlights.make_wav_energy_func(audio_path) if Path(audio_path).exists() else None
            best = highlights.pick_best(
                segs, self._cfg.clip_min_seconds, self._cfg.clip_max_seconds,
                llm=self._llm, energy=energy_fn,
                hook_lead=self._cfg.hook_lead_seconds)
            if best is None:
                raise RuntimeError("no highlight found")
            self._best[vid] = best
            self._db.set_rank(vid, best.score)
            self._db.set_status(vid, Status.HIGHLIGHTED)
        elif rec.status == Status.HIGHLIGHTED:
            self._db.set_status(vid, Status.CLIPPING)
            segs = self._segments.get(vid, [])
            best = self._best.get(vid)
            if best is None:
                raise RuntimeError("missing segment; will reprocess")
            hook_text = self._make_hook(rec, segs)
            clip_path = self._clip.make_short(
                vid, rec.source_path, best, segs, hook_text=hook_text)
            self._db.set_paths(vid, clip_path=clip_path)
            self._db.set_status(vid, Status.CLIPPED)
        elif rec.status == Status.CLIPPED:
            self._db.set_status(vid, Status.METADATA)
            segs = self._segments.get(vid, [])
            text = " ".join(s.text for s in segs)
            meta = metadata.generate_metadata(rec.title, text, llm=self._llm)
            self._db.set_metadata(vid, meta.title, meta.description, meta.tags)
            self._db.set_status(vid, Status.READY)
            self._meta_cache = getattr(self, "_meta_cache", {})
            self._meta_cache[vid] = meta

    def _make_hook(self, rec, segs) -> str:
        """Short bold 'story' hook for the first frames. Prioritises the LLM
        so it sets up a narrative; falls back to a trimmed title. Capped at
        ~60 chars so it fits one line on the hook overlay."""
        if self._llm is not None:
            text = " ".join(s.text for s in segs)
            prompt = (
                "Write ONE short, bold hook line (max 8 words, no emoji, no "
                "quote marks) that sets up a story and makes someone want to "
                "keep watching this gaming clip. Examples: 'He threw the whole "
                "game', 'This clutch was NOT scripted'.\n"
                f"Clip context: {rec.title}\nTranscript: {text[:800]}\n\n"
                'Return ONLY JSON: {"hook": "..."}'
            )
            try:
                data = self._llm.generate_json(prompt)
                hook = str(data.get("hook", "")).strip().strip('"').strip("'")
                if hook:
                    return hook[:60]
            except Exception:
                pass
        title = rec.title or "Insane moment"
        return title[:60].replace(" | VALORANT #shorts", "")

    def advance_one(self) -> str | None:
        for status in _STAGES:
            rec = self._db.next_in_status(status)
            if rec is None:
                continue
            try:
                self._handle(rec)
                return rec.video_id
            except Exception as e:
                count = self._db.bump_retry(rec.video_id, str(e))
                # roll back to clean state so the stage retries
                self._db.reset_stuck()
                if count > _MAX_RETRIES:
                    self._db.set_status(rec.video_id, Status.FAILED, str(e))
                    self._cleanup.delete_video_files(rec.video_id, rec.source_path, rec.clip_path)
                return rec.video_id
        return None

    def _priority_index(self, channel_id: str) -> int:
        for i, ch in enumerate(self._cfg.enabled_channels()):
            if ch.channel_id == channel_id:
                return i
        return 10_000

    def publish_daily(self) -> str | None:
        ready = self._db.list_ready()
        if not ready:
            return None
        ready.sort(key=lambda r: (-r.rank_score,
                                  self._priority_index(r.channel_id),
                                  r.discovered_at))
        rec = ready[0]
        self._db.set_status(rec.video_id, Status.PUBLISHING)
        cache = getattr(self, "_meta_cache", {})
        meta = cache.get(rec.video_id)
        if meta is None:
            if rec.meta_title:
                meta = ClipMetadata(
                    title=rec.meta_title,
                    description=rec.meta_description,
                    tags=rec.meta_tags.split(",") if rec.meta_tags else []
                )
            else:
                meta = ClipMetadata(
                    title=rec.title[:100], description="#Shorts", tags=["shorts"])
        try:
            self._up.upload(rec.clip_path, meta)
        except Exception as e:
            self._db.set_status(rec.video_id, Status.READY, str(e))
            return None
        self._db.set_status(rec.video_id, Status.PUBLISHED)
        self._cleanup.delete_source(rec.video_id, rec.source_path)
        self._cleanup.enforce_quota()
        return rec.video_id

    def cleanup_expired_files(self) -> None:
        self._cleanup.cleanup_expired_files()
