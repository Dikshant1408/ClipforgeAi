import json
from pathlib import Path
from clipforge.scheduler import DryRunUploader
from clipforge.models import ClipMetadata

def test_dryrun_uploader_writes_json(tmp_path):
    up = DryRunUploader(str(tmp_path))
    meta = ClipMetadata(title="T", description="D", tags=["a", "b"])
    vid = up.upload(str(tmp_path / "clip.mp4"), meta)
    assert vid == "DRYRUN"
    files = list((tmp_path / "dryrun").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["title"] == "T" and data["tags"] == ["a", "b"]
