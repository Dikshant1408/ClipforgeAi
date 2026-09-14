## 2024-05-25 - Form Accessibility Improvement
**Learning:** Found that multiple forms and modals within the dashboard were missing `for` attributes on labels and `aria-label` on inputs without visible labels. This makes it difficult for screen readers to associate labels with inputs and degrades accessibility.
**Action:** When adding or modifying forms in this dashboard, explicitly link all `<label>`s to their corresponding inputs using the `for` attribute that matches the `id` of the input element. Use `aria-label` for inputs like search boxes that don't have visual labels attached.
