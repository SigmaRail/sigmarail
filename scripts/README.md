# SigmaRail Docker data updater

The data refresh runs in one `data-updater` Compose service. The container owns its
weekday 20:00 `America/New_York` schedule and sequentially runs the SigmaRail Sharadar
load followed by derived-metrics population. A failed load prevents populate. The job
connects to the already-running ClickHouse service; it does not start, stop, migrate,
or optimize ClickHouse. It is separate from the LEAN backtest worker, which requires
Docker socket access.

## Credentials

The Mac-side control script reads the existing ClickHouse credential entry and the
Sharadar API key from the local macOS Keychain. Compose grants those values only to the
updater service as files at `/run/secrets/clickhouse_password` and
`/run/secrets/sharadar_api_key`; they are not ordinary container environment variables
or image contents. For local Compose these are host-sourced secret mounts, not Docker
Swarm's encrypted-at-rest secret store. Keep Docker Desktop access restricted to the
trusted local user.

Store the Sharadar key in Keychain once:

```bash
.venv/bin/python -m sigmarail.credentials set-sharadar
```

ClickHouse credentials can be stored or replaced interactively with:

```bash
.venv/bin/python -m sigmarail.credentials set-clickhouse
```

No secret is entered on a command line or written to a SigmaRail YAML file by these
commands. The SigmaRail loader also accepts mounted secret-file paths through
`SIGMARAIL_SHARADAR_API_KEY_FILE` and `SIGMARAIL_DATABASE_PASSWORD_FILE`.

## Control commands

```bash
./scripts/data-updater.sh status
./scripts/data-updater.sh build
SIGMARAIL_INSTALL_ACK='I understand this starts the scheduled data updater' ./scripts/data-updater.sh up
./scripts/data-updater.sh logs
SIGMARAIL_RUN_ACK='I understand this runs a production data update' ./scripts/data-updater.sh run
./scripts/data-updater.sh stop
```

`up` builds and starts only the `data-updater` service. It waits for the next scheduled
weekday time; it does not launch a production update immediately. `run` is the explicit
one-off production update. Both require acknowledgement. The updater's input CSVs and
logs persist in the `sigmarail_data_updater` Docker volume.

Start the container schedule only after confirming its ClickHouse database target and
retiring any old schedule that writes to the same datasets. Do not run the old VeraBase
schedule and this updater against the same production tables after cutover.
