## 2024-10-25 - Cache sliding window energy queries
**Learning:** In audio processing, continuously reading overlapping file segments from disk in Python can create significant bottlenecks. Furthermore, using `np.cumsum` on large audio arrays requires casting to `float64` to prevent severe precision loss.
**Action:** When querying overlapping chunks repeatedly, combine `lru_cache` and `np.cumsum` to pre-compute cumulative sums by chunk for $O(1)$ calculations, avoiding repeated disk access and slow loops. Always use `float64` for sum of squared audio samples.
