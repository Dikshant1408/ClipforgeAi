## 2024-05-24 - Accessibility improvements
**Learning:** In the dashboard forms, input fields lacked explicit associations with their labels (missing `for` and `id` links). SVG icons inside buttons that contain text caused double-announcing for screen readers without `aria-hidden="true"`. Some input fields like the search box lacked visible labels and required an `aria-label`.
**Action:** Always link `<label>` with `<input>`/`<select>`/`<textarea>` via `for` and `id`. Add `aria-hidden="true"` to decorative SVGs in text buttons. Add `aria-label` to input fields without visible labels.
