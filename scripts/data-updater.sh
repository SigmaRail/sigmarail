#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
case "$REPO_ROOT" in
  */.worktrees/*) WORKSPACE_ROOT="${REPO_ROOT%%/.worktrees/*}" ;;
  *) WORKSPACE_ROOT="$(cd "$REPO_ROOT/.." && pwd)" ;;
esac
COMPOSE_FILE="$REPO_ROOT/deploy/compose.primary.yml"
PYTHON_BIN="${SIGMARAIL_CREDENTIALS_PYTHON:-$REPO_ROOT/.venv/bin/python}"

usage() {
  cat <<EOF
SigmaRail Docker data updater

Usage: $0 {up|stop|status|logs|run|build}

up      Start the single scheduled Docker updater (weekday 20:00 America/New_York).
stop    Stop and remove only the updater container; preserve its data volume.
status  Show the updater container state.
logs    Follow the updater's Docker logs.
run     Run one immediate production update (requires acknowledgement).
build   Build the updater image without starting it.

The updater reads ClickHouse and Sharadar credentials from the macOS Keychain
when this helper invokes Docker Compose. Compose grants them to the updater
only as files under /run/secrets. It does not pass them as application env vars.
EOF
}

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "SigmaRail Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python environment not found at $PYTHON_BIN. Set SIGMARAIL_CREDENTIALS_PYTHON." >&2
  exit 1
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export SIGMARAIL_WORKSPACE_ROOT="$WORKSPACE_ROOT"

load_keychain_secrets() {
  local clickhouse_json
  clickhouse_json="$("$PYTHON_BIN" -c 'import json; from sigmarail.credentials import get_clickhouse_credentials; value=get_clickhouse_credentials(); print(json.dumps(value or {}))')"
  export SIGMARAIL_DATA_UPDATER_DATABASE_USER="$("$PYTHON_BIN" -c 'import json,sys; value=json.load(sys.stdin); print(value.get("user", ""))' <<<"$clickhouse_json")"
  export SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD="$("$PYTHON_BIN" -c 'import json,sys; value=json.load(sys.stdin); print(value.get("password", ""))' <<<"$clickhouse_json")"
  export SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY="$("$PYTHON_BIN" -c 'from sigmarail.credentials import get_sharadar_api_key; print(get_sharadar_api_key() or "")')"
  unset clickhouse_json

  if [[ -z "$SIGMARAIL_DATA_UPDATER_DATABASE_USER" || -z "$SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD" ]]; then
    echo "ClickHouse credentials are missing from the SigmaRail Keychain entry." >&2
    echo "Store them with: $PYTHON_BIN -m sigmarail.credentials set-clickhouse" >&2
    exit 2
  fi
  if [[ -z "$SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY" ]]; then
    echo "Sharadar API key is missing from the SigmaRail Keychain." >&2
    echo "Store it with: $PYTHON_BIN -m sigmarail.credentials set-sharadar" >&2
    exit 2
  fi
}

compose() {
  docker compose --project-directory "$REPO_ROOT/deploy" -f "$COMPOSE_FILE" --profile data-update "$@"
}

case "${1:-}" in
  up)
    if [[ "${SIGMARAIL_INSTALL_ACK:-}" != "I understand this starts the scheduled data updater" ]]; then
      echo "Starting this service schedules production data writes. Set SIGMARAIL_INSTALL_ACK='I understand this starts the scheduled data updater' after reviewing the target." >&2
      exit 2
    fi
    load_keychain_secrets
    compose up -d --build data-updater
    ;;
  stop)
    SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD=unused SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY=unused compose stop data-updater
    SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD=unused SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY=unused compose rm -f data-updater
    ;;
  status)
    SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD=unused SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY=unused compose ps data-updater
    ;;
  logs)
    SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD=unused SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY=unused compose logs -f --tail=100 data-updater
    ;;
  run)
    if [[ "${SIGMARAIL_RUN_ACK:-}" != "I understand this runs a production data update" ]]; then
      echo "This runs a production load and populate. Set SIGMARAIL_RUN_ACK='I understand this runs a production data update' to proceed." >&2
      exit 2
    fi
    load_keychain_secrets
    compose run --rm --no-deps data-updater /app/scripts/daily-update.sh
    ;;
  build)
    SIGMARAIL_DATA_UPDATER_CLICKHOUSE_PASSWORD=build-only SIGMARAIL_DATA_UPDATER_SHARADAR_API_KEY=build-only compose build data-updater
    ;;
  *) usage; exit 2 ;;
esac
