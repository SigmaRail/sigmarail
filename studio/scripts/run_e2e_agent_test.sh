#!/usr/bin/env bash
# Component 4: run all four verification tiers locally.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Tier 1+3: backend unit + parity tests..."
(cd "$ROOT" && python -m pytest tests/test_strategy_lint_and_diff.py tests/test_optimizer_pareto.py tests/test_lineage_serialization.py tests/test_mcp_full_parity.py -v)

echo "==> Tier 2: frontend component + bridge tests..."
(cd "$ROOT/frontend" && npm run test -- --run)

echo "==> Tier 4: Playwright E2E (headed)..."
(cd "$ROOT/frontend" && npx playwright test --project=chromium --headed)

echo "==> [SUCCESS] Full 4-Tier Quant Flywheel Verified!"
