#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="com.sigmarail.daily-update"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="${SIGMARAIL_LOG_DIR:-$PROJECT_ROOT/logs}"
RUNNER="$SCRIPT_DIR/daily-update.sh"
VENV_PATH="${SIGMARAIL_VENV:-$PROJECT_ROOT/.venv}"

usage() {
  cat <<EOF
SigmaRail nightly data job (macOS LaunchAgent)

Usage: $0 {install|uninstall|status|run|start|logs}

install   Install a weekday 20:00 local LaunchAgent for this checkout.
uninstall Remove only $LABEL.
status    Show whether the LaunchAgent is loaded.
run       Run the production update in the foreground (requires acknowledgement).
start     Trigger a one-off production LaunchAgent run (requires acknowledgement).
logs      Tail the SigmaRail update logs.

The installer does not remove or disable VeraBase's existing LaunchAgent.
Do not install both schedules against the same production database.
EOF
}

launchctl_domain="gui/$(id -u)"

write_plist() {
  mkdir -p "$(dirname "$PLIST_PATH")" "$LOG_DIR" || return 1
  cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$RUNNER</string></array>
  <key>WorkingDirectory</key><string>$PROJECT_ROOT</string>
  <key>RunAtLoad</key><false/>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$LOG_DIR/sigmarail-daily-update.launchd.stdout.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/sigmarail-daily-update.launchd.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$VENV_PATH/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
</dict>
</plist>
EOF
}

case "${1:-}" in
  install)
    if [[ "${SIGMARAIL_INSTALL_ACK:-}" != "I understand this installs a production schedule" ]]; then
      echo "Install is a production scheduling action. Review first, then rerun with SIGMARAIL_INSTALL_ACK='I understand this installs a production schedule'." >&2
      exit 2
    fi
    if [[ ! -x "$RUNNER" ]]; then
      echo "Runner is missing or not executable: $RUNNER" >&2
      exit 1
    fi
    write_plist || exit 1
    plutil -lint "$PLIST_PATH" || exit 1
    launchctl bootout "$launchctl_domain/$LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "$launchctl_domain" "$PLIST_PATH"
    ;;
  uninstall)
    launchctl bootout "$launchctl_domain/$LABEL" >/dev/null 2>&1 || true
    rm -f "$PLIST_PATH"
    echo "Removed $LABEL."
    ;;
  status)
    if launchctl print "$launchctl_domain/$LABEL" 2>/dev/null; then exit 0; fi
    echo "$LABEL is not loaded."
    exit 1
    ;;
  run)
    if [[ "${SIGMARAIL_RUN_ACK:-}" != "I understand this runs a production update" ]]; then
      echo "This runs a production load and populate. Set SIGMARAIL_RUN_ACK='I understand this runs a production update' to proceed." >&2
      exit 2
    fi
    exec "$RUNNER"
    ;;
  start)
    if [[ "${SIGMARAIL_RUN_ACK:-}" != "I understand this runs a production update" ]]; then
      echo "This triggers a production load and populate. Set SIGMARAIL_RUN_ACK='I understand this runs a production update' to proceed." >&2
      exit 2
    fi
    launchctl kickstart -k "$launchctl_domain/$LABEL"
    ;;
  logs)
    tail -n 100 -F "$LOG_DIR/sigmarail-daily-update.log" "$LOG_DIR/sigmarail-daily-update-error.log"
    ;;
  *) usage; exit 2 ;;
esac
