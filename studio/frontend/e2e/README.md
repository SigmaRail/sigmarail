# Opt-in browser UI smoke tests

Run `npm run test:e2e:ui` from `frontend/` to exercise the paper deployment UI in
Chromium. This command is intentionally separate from `npm test` (Vitest) and is
not wired into CI.

The UI smoke uses mocked `/api/**` responses and fake credentials. It launches
only the Vite frontend on port 5174; it does not start Django, ClickHouse, Docker,
LEAN, or contact a broker. Playwright keeps failure traces and screenshots under
`test-results-ui/` and the HTML report under `playwright-ui-report/`.
