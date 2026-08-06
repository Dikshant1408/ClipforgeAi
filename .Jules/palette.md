## 2024-05-24 - Custom Toggle Label Accessibility Pattern
**Learning:** The custom toggle component implementation using `<span class="toggle-label">` alongside a checkbox input without an explicit connection (like a `for` attribute on a `<label>`) is a recurring accessibility issue in this app.
**Action:** Always convert generic text elements like `<span>` serving as labels to semantic `<label>` elements with the correct `for` attribute to associate them with the corresponding input element.
