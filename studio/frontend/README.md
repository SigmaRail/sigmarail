# SigmaRail Studio frontend

React + Vite + TypeScript SPA for SigmaRail Studio Phase 1.

Proxies `/api` and `/health` to the Django API at `http://127.0.0.1:8001`.

## Run

```bash
# Terminal A — API (from SigmaRailStudio/)
python manage.py runserver 8001

# Terminal B — SPA
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Workbench navigation

A saved strategy opens at `/strategies/:irId`. Link to a slot with `?slot=universe`, `alpha`, `portfolio-construction`, `risk-management`, or `execution`. Existing strategy links open Universe. A bare `/strategies` opens a draft. Slot links identify editor views and do not serialize unsaved edits.

Backtests use `/backtests/:runId/:section`. Deploy accepts `?run=<runId>&deployment=<deploymentId>` to reopen a selection. For direct links and refreshes, configure the SPA host to serve `index.html` for frontend routes while forwarding `/api` and `/health` to Django. Vite development and preview servers provide the SPA fallback.

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite dev server (proxy → :8001) |
| `npm run build` | Typecheck + production build → `dist/` |
| `npm run preview` | Serve `dist/` locally |
| `npm run typecheck` | `tsc -b --noEmit` |

## Stack

- React 19 + TypeScript + Vite 6
- Tailwind CSS
- TanStack Query + TanStack Table

## Modes

- **Screen** — preset library, rankings table, inspector, as-of scrubber + turnover
- **Backtest** — Phase 2 placeholder
- **Library** — searchable preset list
