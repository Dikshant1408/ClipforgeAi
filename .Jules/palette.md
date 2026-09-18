## 2024-05-18 - Playwright Testing Static Flask HTML
**Learning:** For local frontend UI verification, although there is no Node.js frontend dev server, use the Flask development server (e.g., `http://127.0.0.1:5050`) rather than `file:///` URLs with Playwright, as dynamic fetching may block proper page loading when opening files directly.
**Action:** Always start the Flask dev server (`python3 dashboard/app.py &`) and point Playwright to localhost for frontend verification of static HTML components in this project.
