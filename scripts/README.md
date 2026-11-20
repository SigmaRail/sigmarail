# SigmaRail scheduled data update

`daily-update.sh` runs the SigmaRail-owned Sharadar loader followed by the SigmaRail
transform pipeline. It stops when loading fails, so a partial source load cannot be
reported as a successful populate. It assumes ClickHouse is already running and does
not start, stop, optimize, or migrate the database.

The macOS LaunchAgent installer is `setup-launchd.sh`. It installs a weekday 20:00
local schedule under `com.sigmarail.daily-update`. Installation requires an explicit
environment acknowledgement because it schedules writes to the configured production
database:

```bash
SIGMARAIL_INSTALL_ACK='I understand this installs a production schedule' \
  ./scripts/setup-launchd.sh install
```

Review the configured SigmaRail production database before installing. Do not install
this beside the VeraBase schedule if both jobs target the same data. The installer does
not remove or disable any VeraBase LaunchAgent; cutover must be performed separately
after verifying the SigmaRail job and its logs.

Useful commands:

```bash
./scripts/setup-launchd.sh status
SIGMARAIL_RUN_ACK='I understand this runs a production update' ./scripts/setup-launchd.sh run
SIGMARAIL_RUN_ACK='I understand this runs a production update' ./scripts/setup-launchd.sh start
./scripts/setup-launchd.sh logs
./scripts/setup-launchd.sh uninstall
```

`run` executes the actual load and populate commands; it writes to the database selected
by the SigmaRail configuration. Log files are `logs/sigmarail-daily-update.log` and
`logs/sigmarail-daily-update-error.log`.
