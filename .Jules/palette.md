## 2026-07-30 - Modal Keyboard Accessibility
**Learning:** Global keyboard shortcuts (like Escape to close) require careful iteration over open modal instances and handling of edge cases (like pausing a playing video) to be truly accessible and UX-friendly without trapping users.
**Action:** Always verify if a UI layer has a 'dismiss' interaction pattern that can benefit from global keydown listeners, and ensure we gracefully close related media components before unmounting/hiding the modal.
