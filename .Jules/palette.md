## 2024-05-24 - Add Accessibility Labels to Forms
**Learning:** The dashboard has many forms and input fields, but most of the `<label>` tags lacked a `for` attribute corresponding to their input's `id`. Additionally, the search input field in the videos queue had no associated label.
**Action:** Consistently added `for="id"` to all `<label>` tags linked to inputs/selects/textareas. Also added `aria-label` attribute to the icon-only search input to ensure it is accessible via screen readers.
