# SigmaRail workbench frontend

React + Vite + TypeScript product module hosted by the AppTension web application.

The host application is in `packages/webapp`. Run the product module through that host for normal development. The standalone Vite entry remains available for focused UI work and browser checks; its API requests use the configured local Studio API proxy.

## Run

```bash
# Install every frontend package from the repository root
corepack pnpm install

# Run the AppTension host (from the repository root)
corepack pnpm --filter webapp dev
```

For isolated product UI work, run commands from this directory with `corepack pnpm dev`.
The mocked browser suite can be run from the repository root with `corepack pnpm --filter @sigmarail/workbench test:e2e:workbench`.

## Scripts

| Command | Purpose |
|---------|---------|
| `corepack pnpm dev` | Standalone Vite dev server |
| `corepack pnpm build` | Typecheck + production build → `dist/` |
| `corepack pnpm preview` | Serve `dist/` locally |
| `corepack pnpm typecheck` | `tsc -b --noEmit` |
| `corepack pnpm --filter @sigmarail/workbench test:e2e:workbench` | Mocked browser checks for the mounted workbench |

Install Playwright's Chromium runtime once per machine before the browser suite:

```bash
corepack pnpm --filter @sigmarail/workbench exec playwright install chromium
```

## Stack

- React 19 + TypeScript + Vite 6
- Tailwind CSS
- TanStack Query + TanStack Table
- Shared shell, account, organization, and UI foundation from the host application

## Product routes

The workbench provides screener, market, charts, watchlists, five-slot strategy authoring, backtests, optimization, paper deployment, and monitoring workflows within the host application's navigation.

Layout changes follow the shared [UI design guardrails](../docs/UI_DESIGN_GUARDRAILS.md): use AppTension primitives, standard breakpoints, persistent workflow navigation, and minimal section surfaces.

## Design guardrails

Use the shared AppTension components and responsive rules in [`docs/UI_DESIGN_GUARDRAILS.md`](../docs/UI_DESIGN_GUARDRAILS.md) when changing product layouts.
