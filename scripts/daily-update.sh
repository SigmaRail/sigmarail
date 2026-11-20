#!/usr/bin/env bash
set -u

# Run the SigmaRail Sharadar load and derived-table population in order.
# This runner deliberately does not start, stop, optimize, or migrate ClickHouse.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${SIGMARAIL_LOG_DIR:-$PROJECT_ROOT/logs}"
VENV_PATH="${SIGMARAIL_VENV:-$PROJECT_ROOT/.venv}"
RUN_LOG="$LOG_DIR/sigmarail-daily-update.log"
ERROR_LOG="$LOG_DIR/sigmarail-daily-update-error.log"
LOCK_DIR="${SIGMARAIL_UPDATE_LOCK_DIR:-$LOG_DIR/.sigmarail-daily-update.lockdir}"

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

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "Another SigmaRail daily update is already running (lock: $LOCK_DIR); exiting."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM HUP

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  log_error "Python environment not found at $VENV_PATH/bin/python; install SigmaRail into .venv or set SIGMARAIL_VENV."
  notify "SigmaRail update failed" "Python environment not found"
  exit 1
fi

export VIRTUAL_ENV="$VENV_PATH"
export PATH="$VENV_PATH/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

for cli in sigmarail-load sigmarail-populate; do
  if [[ ! -x "$VENV_PATH/bin/$cli" ]]; then
    log_error "Missing $VENV_PATH/bin/$cli; from the SigmaRail repo run: $VENV_PATH/bin/python -m pip install -e ."
    notify "SigmaRail update failed" "SigmaRail CLI missing"
    exit 1
  fi
done

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
  "$@" >>"$RUN_LOG" 2>&1
  local status=$?
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
if ! run_step "Sharadar download and load" "$VENV_PATH/bin/sigmarail-load" --download --backup --mode prod; then
  notify "SigmaRail update failed" "Sharadar load failed; populate was not started"
  exit 1
fi

if ! run_step "Derived metrics population" "$VENV_PATH/bin/sigmarail-populate" --metrics all --mode prod; then
  notify "SigmaRail update failed" "Derived metrics population failed"
  exit 1
fi

log "=== SigmaRail daily update completed successfully ==="
notify "SigmaRail update complete" "Sharadar data and metrics updated"
exit 0
