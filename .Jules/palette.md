## 2024-05-14 - Missing Form Elements Associations
**Learning:** Found multiple `<label>` elements missing their `for` attribute and corresponding `id` bindings on inputs in `dashboard/index.html`. This creates significant accessibility barriers as screen readers won't announce the label when inputs gain focus. This seems to be a common pattern in the current forms structure.
**Action:** Associate `<label>` elements with their respective form inputs using the `for` attribute pointing to the input's `id`. This is a low-effort, high-impact a11y improvement.
