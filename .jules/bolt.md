## 2023-10-27 - LRU Caching for Overlapping Audio Windows
**Learning:** Sliding window calculations for highlight extraction caused O(N*M) disk I/O and redundant numpy casting when parsing the full `.wav` stream repeatedly per window.
**Action:** When implementing LRU chunk caching for audio processing sliding windows, pre-compute cumulative sums (`np.cumsum`) on fixed-size chunks (e.g. 30s) for O(1) interval queries, cast to `float64` to prevent precision loss, and keep the `lru_cache` `maxsize` small to avoid OOM exceptions.
