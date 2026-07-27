## 2024-03-24 - Repeated I/O in Loop during Audio Analysis
**Learning:** `make_wav_energy_func` was repeatedly reopening and seeking the `.wav` file for every single candidate highlight window. This repeated I/O in a tight loop caused massive overhead, especially with overlapping windows.
**Action:** When calculating features (like RMS energy) over many overlapping windows of a file, load the file into memory once and pre-calculate intermediate values (like squared samples) to turn repeated disk reads and computations into fast memory slicing.
