## 2026-08-07 - [Nav Item Keyboard Nav]
**Learning:** The .nav-item tabs in the sidebar use onClick for navigation but do not support keyboard navigation (tabbing and Enter key). They are a missing accessibility feature for users relying on keyboard interaction.
**Action:** Add tabindex='0' to focus elements, support aria-selected, or ensure role=button or tab, and listen to keypress/keydown to simulate a click.
