## 2026-09-10 - Form Label Accessibility in Modals
**Learning:** The application's custom modal forms frequently omit the `for` attribute on `<label>` elements, which breaks the programmatic association with inputs for screen readers and reduces the clickable target area.
**Action:** When adding or modifying form fields in modals or settings panels within this app, always ensure labels have correct `for` attributes that map exactly to input `id`s.
