#!/usr/bin/env bash
set -u
set -o pipefail

# Run the SigmaRail Sharadar load and derived-table population in order.
# This runner deliberately does not start, stop, optimize, or migrate ClickHouse.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${SIGMARAIL_LOG_DIR:-$PROJECT_ROOT/logs}"
VENV_PATH="${SIGMARAIL_VENV:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="${SIGMARAIL_PYTHON:-$VENV_PATH/bin/python}"
RUN_LOG="$LOG_DIR/sigmarail-daily-update.log"
ERROR_LOG="$LOG_DIR/sigmarail-daily-update-error.log"
LOCK_FILE="${SIGMARAIL_UPDATE_LOCK_FILE:-$LOG_DIR/.sigmarail-daily-update.lock}"

mkdir -p "$LOG_DIR" || exit 1

log() {
  local line="[$(date '+%Y-%m-%d %H:%M:%S %z')] $*"
  printf '%s\n' "$line" | tee -a "$RUN_LOG"
}

log_error() {
  local line="[$(date '+%Y-%m-%d %H:%M:%S %z')] ERROR: $*"
  printf '%s\n' "$line" | tee -a "$ERROR_LOG" "$RUN_LOG" >&2
}

notify() {
  local title="$1" message="$2"
  if [[ "$(uname -s)" == "Darwin" ]] && command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$message\" with title \"$title\"" >/dev/null 2>&1 || true
  fi
}

if ! command -v flock >/dev/null 2>&1; then
  log_error "flock is required to prevent overlapping SigmaRail data updates."
  exit 1
fi
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "Another SigmaRail daily update is already running (lock: $LOCK_FILE); exiting."
  exit 0
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python || command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  log_error "Python was not found; install SigmaRail in a virtual environment or container image."
  notify "SigmaRail update failed" "Python environment not found"
  exit 1
fi

if [[ -x "$VENV_PATH/bin/python" ]]; then
  export VIRTUAL_ENV="$VENV_PATH"
  export PATH="$VENV_PATH/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
fi
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

LOAD_COMMAND=("$(command -v sigmarail-load || true)")
if [[ -z "${LOAD_COMMAND[0]}" ]]; then
  LOAD_COMMAND=("$PYTHON_BIN" -m sigmarail.load)
fi
POPULATE_COMMAND=("$(command -v sigmarail-populate || true)")
if [[ -z "${POPULATE_COMMAND[0]}" ]]; then
  POPULATE_COMMAND=("$PYTHON_BIN" -m sigmarail.populate)
fi

if ! "$PYTHON_BIN" -c 'import sigmarail.load, sigmarail.populate' >/dev/null 2>&1; then
  log_error "SigmaRail modules unavailable; install dependencies in the selected Python environment."
  notify "SigmaRail update failed" "SigmaRail modules unavailable"
  exit 1
fi

cd "$PROJECT_ROOT" || {
  log_error "Cannot enter SigmaRail project directory: $PROJECT_ROOT"
  exit 1
}

run_step() {
  local label="$1"
  shift
  log "Starting: $label"
  # Log only the executable basename and arguments; configuration secrets are never printed.
  log "Command: $(basename "$1") ${*:2}"
  "$@" 2>&1 | tee -a "$RUN_LOG"
  local status=${PIPESTATUS[0]}
  if [[ $status -eq 0 ]]; then
    log "Completed: $label"
    return 0
  fi
  log_error "Failed: $label (exit $status)"
  return "$status"
}

log "=== Starting SigmaRail daily update ==="
log "Project root: $PROJECT_ROOT"
log "Configured environment: $VENV_PATH"
log "Production database target is resolved from SigmaRail configuration."

# Stop on partial load failure so populate never republishes stale inputs as success.
if ! run_step "Sharadar download and load" "${LOAD_COMMAND[@]}" --download --backup --mode prod; then
  notify "SigmaRail update failed" "Sharadar load failed; populate was not started"
  exit 1
fi

if ! run_step "Derived metrics population" "${POPULATE_COMMAND[@]}" --metrics all --mode prod; then
  notify "SigmaRail update failed" "Derived metrics population failed"
  exit 1
fi

log "=== SigmaRail daily update completed successfully ==="
notify "SigmaRail update complete" "Sharadar data and metrics updated"
exit 0
