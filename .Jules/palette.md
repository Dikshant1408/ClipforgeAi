## 2024-05-24 - HTML Forms and Screen Reader Associations in Pure HTML
**Learning:** Native `<label>` elements missing the `for` attribute in raw HTML/Flask templates prevent screen readers from associating the label with input fields, unlike React where `htmlFor` is typically linted. Toggles modeled as styled spans also lacked label associations, making them unclickable by text.
**Action:** When working on raw HTML dashboards without a frontend framework, verify native `for` associations between labels and inputs are explicitly defined to enable screen-reader focus and text clickability.
