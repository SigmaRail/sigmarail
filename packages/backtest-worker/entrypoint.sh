#!/bin/sh
set -eu

: "${SIGMARAIL_CLICKHOUSE_USER:?SIGMARAIL_CLICKHOUSE_USER is required}"
: "${SIGMARAIL_CLICKHOUSE_PASSWORD:?SIGMARAIL_CLICKHOUSE_PASSWORD is required}"

# The LEAN execution container connects to native ClickHouse through Docker
# Desktop's host gateway. The worker itself shares the same native endpoint.
export CLICKHOUSE_HOST="${SIGMARAIL_CLICKHOUSE_HOST:-host.docker.internal}"
export CLICKHOUSE_HTTP_PORT="${SIGMARAIL_CLICKHOUSE_HTTP_PORT:-8123}"
export CLICKHOUSE_USER="$SIGMARAIL_CLICKHOUSE_USER"
export CLICKHOUSE_PASSWORD="$SIGMARAIL_CLICKHOUSE_PASSWORD"
export CLICKHOUSE_DATABASE="${SIGMARAIL_CLICKHOUSE_DATABASE:-sigmarail}"
export SIGMARAIL_API_URL="${SIGMARAIL_API_URL:-http://host.docker.internal:5001}"
export SIGMARAIL_BACKTEST_WORKER_HEARTBEAT="${SIGMARAIL_BACKTEST_WORKER_HEARTBEAT:-/tmp/sigmarail-backtest-worker.heartbeat}"
export RUNNER_ID="${RUNNER_ID:-sigmarail-compose-backtest-worker}"
mkdir -p "${TMPDIR:-/tmp}"

lean_root="${SIGMARAIL_LEAN_WORKSPACE_ROOT:?SIGMARAIL_LEAN_WORKSPACE_ROOT is required}"
mkdir -p "$lean_root"
if [ ! -f "$lean_root/lean.json" ]; then
  cp /app/lean-workspace/lean.json "$lean_root/lean.json"
fi
if [ ! -f "$lean_root/lean.json" ]; then
  echo "SigmaRail LEAN workspace could not be initialized at $lean_root" >&2
  exit 2
fi

exec python -m sigmarail_studio_mcp.backtest_runner.worker "$@"
