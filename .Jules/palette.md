## 2024-05-19 - Missing 'for' attributes in form labels
**Learning:** The `dashboard/index.html` uses labels for numerous configuration and editing forms, but explicitly lacks the `for` attribute linking labels to their respective inputs/selects/textareas. This significantly hurts screen reader usability and prevents clicking the label to focus the input.
**Action:** When working on form accessibility, ensure all labels have a `for` attribute that strictly matches the `id` of the related input field.
