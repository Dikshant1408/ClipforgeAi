## 2024-05-18 - Missing label for attributes and aria labels
**Learning:** Found that most forms in `dashboard/index.html` were lacking `for` attributes on their `<label>` elements connecting them to the `<input>` `id`. Icon buttons and standard buttons lacked `aria-label`s.
**Action:** Always ensure `<label>` has a matching `for` attribute and that all interactive elements, especially icon-only ones, have `aria-label`s.
