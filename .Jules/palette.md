## 2024-05-18 - Improve accessibility mapping for labels and inputs
**Learning:** Found multiple instances where labels were not mapped to inputs using `for` attributes, and icon-only links lacked `aria-label`s.
**Action:** Always map labels properly with `for` attribute and ensure icon-only buttons/links have descriptive `aria-label` attributes.
