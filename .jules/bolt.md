## 2024-05-24 - File IO inside hot loop
**Learning:** `make_wav_energy_func` opens the wave file, seeks, reads, and closes it *for every single candidate window*. In a typical video with hundreds of transcript segments, `candidate_windows` generates thousands of overlapping windows. Re-opening and parsing the `.wav` header thousands of times is extremely slow and blocks the CPU.
**Action:** Pre-load or memory-map the audio data once in `make_wav_energy_func` and return a closure that computes energy from the loaded array.
