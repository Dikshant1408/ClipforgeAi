## 2026-08-04 - Tab-based Navigation Playwright Verification
**Learning:** The dashboard UI uses hidden tabs for different views, so elements on non-active pages cannot be interacted with via Playwright out-of-the-box. Screen readers may face similar challenges if pages aren't cleanly managed with standard aria roles.
**Action:** Next time I need to test or interact with components in a multi-page/tabbed dashboard, ensure scripts navigate and wait for tab transitions before acting on elements.
