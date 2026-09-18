## 2024-03-24 - Efficient overlapping audio queries via Cumulative Sums (Prefix Sums)
**Learning:** Audio energy calculations (RMS) for short, heavily overlapping highlighting windows severely bottleneck the clip extraction process if they rely on native Python loop processing and repetitively seeking/reading file chunks.
**Action:** Use an LRU cache combined with `np.cumsum` float64 arrays to transform O(N) loop queries into O(1) prefix sum queries. This avoids repeated disk IO without loading massive uncompressed audio streams into memory.
