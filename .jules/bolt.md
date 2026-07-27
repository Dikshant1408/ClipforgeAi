## 2024-06-18 - SQLite Sorting Optimization
**Learning:** The `monitor.py` and `dashboard/app.py` frequently execute `SELECT` queries with `ORDER BY discovered_at` and `WHERE channel_id=?`. Without an index on these columns, SQLite performs a full table scan, which severely degrades performance as the `videos` table grows over time.
**Action:** Added database indexes for `channel_id` and `discovered_at` in `clipforge/db.py` to optimize these operations. Next time, always check `WHERE` and `ORDER BY` clauses on growing SQLite tables for missing indices.
