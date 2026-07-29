## 2024-05-15 - [Efficient File Tailing vs collections.deque]
**Learning:** Using `collections.deque(file, max_lines)` is highly inefficient for large log files (like `clipforge.log`) because it reads the entire file sequentially into memory just to return the last N lines, leading to O(N) time complexity where N is the file size.
**Action:** When tailing files or fetching recent logs from disk, implement a backward-seeking chunk reader (e.g. `_tail_file` with `os.SEEK_END`) to achieve O(L) time complexity, where L is the number of lines requested.
