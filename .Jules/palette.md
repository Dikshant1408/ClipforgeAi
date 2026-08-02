## 2024-05-19 - Form Label Accessibility in Static HTML Dashboard
**Learning:** Found a systemic pattern in `dashboard/index.html` where form `<label>` tags lacked `for` attributes connecting them to inputs, degrading screen reader accessibility and clickable target size in the settings and modal panels.
**Action:** When adding or auditing settings interfaces in this static dashboard layout, proactively ensure all `<label>` tags have `for` attributes matching the input ID.
