## 2024-06-25 - Missing explicit for labels in form groups
**Learning:** Found that most forms in `dashboard/index.html` have `<label>` elements without the `for` attribute and matching `id`s on `<input>` elements. Form groups frequently rely on visual proximity rather than explicit matching for accessibility.
**Action:** Always link `<label>` directly to `<input>` or `<select>` or `<textarea>` using the `for` attribute referencing the `id` of the target element.
