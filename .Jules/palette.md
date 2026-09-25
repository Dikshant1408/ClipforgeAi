## 2024-05-18 - Accessibility: Inputs missing visual label mappings
**Learning:** Found multiple instances where the dashboard HTML form `<label>` tags lacked a `for` attribute tying them to their corresponding `<input>` or `<select>` elements.
**Action:** Always ensure that `<label>` explicitly uses the `for` attribute and that it corresponds to the `id` of the linked form control. Also, adding `aria-label` to buttons and ensuring SVGs inside buttons with text have `aria-hidden="true"`.
