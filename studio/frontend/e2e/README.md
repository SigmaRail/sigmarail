# Opt-in browser E2E checks

Run `npm run test:e2e:ui` from `frontend/` to exercise the paper deployment UI in
Chromium. This command is intentionally separate from `npm test` (Vitest) and is
not wired into CI.

The UI smoke uses mocked `/api/**` responses and fake credentials. It launches
only the Vite frontend on port 5174; it does not start Django, ClickHouse, Docker,
LEAN, or contact a broker. Playwright keeps failure traces and screenshots under
`test-results-ui/` and the HTML report under `playwright-ui-report/`.

## AppTension workbench regression suite

From `frontend/`, run:

```bash
corepack pnpm exec playwright test --config=playwright.workbench.config.ts
```

This builds the AppTension webapp, starts its isolated Vite preview on port 4302,
and exercises page behavior at phone, tablet, and desktop widths. Coverage
includes chart deep links, the saved-screen picker (including catalog errors and
loading a personal screen), and the five-slot editor. It uses fake account data
and mocked APIs, so it cannot validate ClickHouse SQL or production data.

The chart API's database qualification also has a backend regression check in
`tests/test_stock_introspection.py`: it captures the query before execution and
fails if the chart joins a hard-coded legacy database. Run it from the repository
root in the backend pytest environment with `VERA_MODE=test`. Keep this check
separate from the browser suite; use only a dedicated ClickHouse test database
for any live API integration checks.
