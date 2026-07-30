import time
from clipforge.db import Database
from clipforge.models import VideoRecord, Status

db = Database("perf_test.db")
db._conn.execute("DELETE FROM videos")
db._conn.commit()

# Insert 10k records
recs = []
for i in range(10000):
    recs.append((
        f"vid{i}", f"ch{i%50}", f"Channel {i%50}", f"Title {i}", f"http://vid{i}",
        Status.DISCOVERED.value if i % 2 == 0 else Status.PUBLISHED.value,
        0, "", "", "", 0.0, f"2023-01-{i%28+1:02d}T10:00:00Z"
    ))
db._conn.executemany(
    "INSERT INTO videos (video_id, channel_id, channel_name, title, url, status, retry_count, last_error, source_path, clip_path, rank_score, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    recs
)
db._conn.commit()

# 1. Test has_channel_videos
start = time.time()
for i in range(500):
    db.has_channel_videos(f"ch{i%50}")
t1 = time.time() - start

# 2. Test status_filter query (like dashboard)
start = time.time()
for _ in range(500):
    db._conn.execute("SELECT * FROM videos WHERE status=? ORDER BY discovered_at DESC LIMIT 300", ("DISCOVERED",)).fetchall()
t2 = time.time() - start

# 3. Test next_in_status (like advance_one)
start = time.time()
for _ in range(500):
    db.next_in_status(Status.DISCOVERED)
t3 = time.time() - start

print(f"Before Indexes: has_channel_videos={t1:.4f}s, dashboard={t2:.4f}s, next_in_status={t3:.4f}s")

# Create Indexes
db._conn.execute("CREATE INDEX IF NOT EXISTS idx_channel_id ON videos(channel_id)")
db._conn.execute("CREATE INDEX IF NOT EXISTS idx_status_discovered_at ON videos(status, discovered_at)")
db._conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_at ON videos(discovered_at)")
db._conn.commit()

# 1. Test has_channel_videos again
start = time.time()
for i in range(500):
    db.has_channel_videos(f"ch{i%50}")
t1 = time.time() - start

# 2. Test status_filter query again
start = time.time()
for _ in range(500):
    db._conn.execute("SELECT * FROM videos WHERE status=? ORDER BY discovered_at DESC LIMIT 300", ("DISCOVERED",)).fetchall()
t2 = time.time() - start

# 3. Test next_in_status again
start = time.time()
for _ in range(500):
    db.next_in_status(Status.DISCOVERED)
t3 = time.time() - start

print(f"After Indexes: has_channel_videos={t1:.4f}s, dashboard={t2:.4f}s, next_in_status={t3:.4f}s")
