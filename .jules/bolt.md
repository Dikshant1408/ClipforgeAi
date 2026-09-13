## 2024-09-13 - Audio cumulative sum optimization
**Learning:** For multi-channel audio data from wave files, samples are returned as a 1D interleaved buffer. When using float32 for cumulative sums on large audio files, precision loss is catastrophic. Additionally, time-based frame calculations must be multiplied by the number of channels (`nchannels`) to find correct array boundaries.
**Action:** When computing cumulative sums (`np.cumsum`) over large audio arrays, always cast to `float64`. Ensure time-to-frame conversions multiply by `nchannels` when indexing into flattened audio buffers.
