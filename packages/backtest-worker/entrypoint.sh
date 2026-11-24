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

if [ ! -f "${LEAN_PROJECTS_ROOT:?LEAN_PROJECTS_ROOT is required}/lean.json" ]; then
  echo "LEAN_PROJECTS_ROOT must be mounted and contain lean.json" >&2
  exit 2
fi

exec python -m sigmarail_studio_mcp.backtest_runner.worker "$@"
