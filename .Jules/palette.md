## 2024-06-25 - Unclickable toggle text in custom switch components
**Learning:** Custom toggle switch components often place descriptive text outside the `<label>` wrapping the checkbox (e.g., using `<span>`), which prevents users from clicking the text to toggle the switch. This breaks expected behavior and reduces hit area, harming accessibility.
**Action:** Always wrap toggle descriptive text in a `<label>` associated with the checkbox via the `for` attribute and apply `cursor: pointer` to make the interaction area larger and visually indicated.
