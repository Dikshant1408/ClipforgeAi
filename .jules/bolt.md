## 2025-02-28 - Missing DB Indexes causing polling delays
**Learning:** Polling loops in `monitor.py` check `has_channel_videos` (`SELECT 1 FROM videos WHERE channel_id=?`) per channel on every interval. As the `videos` table grows, this missing index causes full table scans that degrade background job performance. Furthermore, the dashboard sorts queries on `discovered_at` which was unindexed, causing slow file sorts in SQLite.
**Action:** Always verify indexes exist for columns used in frequent polling queries (`WHERE`) and sorting (`ORDER BY`) in automated background tasks.
