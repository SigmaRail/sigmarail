# Primary Docker runtime

`deploy/compose.primary.yml` is the laptop runtime definition for the primary
SigmaRail checkout on `main`. It keeps the UI, Django API, Apollo MCP, Postgres,
and Redis as separate containers. The frontend is built from this checkout and
uses a same-origin `/api` proxy to the API container. ClickHouse remains native
on macOS and is reached from Docker through `host.docker.internal`.

This is the current development-machine setup, not a portable public installer.
It assumes machine-local environment files, existing Postgres and Redis Docker
volumes, a native ClickHouse server, and the LEAN workspace path configured in
the Compose file. A clean-machine setup still needs to be made portable before
advertising this as a one-command install.

## Data ownership

- Postgres uses the existing external Docker volume
  `sigmarail-web-backend-db-data`.
- Redis uses the existing external Docker volume
  `sigmarail-studio-apptension_redis_cache`.
- Do not remove either external volume when updating or rebuilding services.
- ClickHouse data remains in the native ClickHouse instance; Docker services
  connect to it but do not own its storage.

The private backend environment is stored outside the repository at
`../.sigmarail/backend.env` (relative to this repository). It is machine-local
and must not be committed. Storage is configured for local filesystem use and
email uses Django's console backend. Stripe and S3 are not enabled in this
runtime. AWS metadata credential discovery is disabled, and the old LocalStack,
Stripe mock, and Mailcatcher containers are not part of the active stack.

Before starting the full application, confirm that the backend and gateway env
files exist, `SIGMARAIL_BACKTEST_DB_PASSWORD` is set in the local shell, the
external Postgres and Redis volumes already exist, ClickHouse is running on the
host, and the LEAN workspace path in `deploy/compose.primary.yml` matches this
machine. Do not commit the env files or credentials.

## Build and update

From the SigmaRail repository root, use the current `main` revision when
building the backend identity into the image:

```sh
SIGMARAIL_BUILD_REVISION="$(git rev-parse HEAD)" \
  docker compose -f deploy/compose.primary.yml build backend backtest-worker frontend mcp-server mcp-gateway
```

Then update only the app services:

```sh
SIGMARAIL_BUILD_REVISION="$(git rev-parse HEAD)" \
  docker compose -f deploy/compose.primary.yml up -d backend backtest-worker frontend mcp-server mcp-gateway
```

The Compose project is named `sigmarail`. Its Postgres and Redis services mount
the existing data volumes. Do not run a second Postgres container against the
same data directory at the same time.

The optional `data-updater` profile is intentionally excluded from these
commands. Its `up` and one-off production run procedures are documented in
[`scripts/README.md`](../scripts/README.md).

Check service status or stop the stack without deleting its data volumes with:

```sh
docker compose -f deploy/compose.primary.yml ps
docker compose -f deploy/compose.primary.yml down
```

## Ports

- Frontend: `127.0.0.1:4300` (the existing Tailscale UI route targets this).
- Backend: container port 80, published at `127.0.0.1:5001` for local API
  access; browser API traffic goes through frontend `/api`.
- Postgres and Redis remain loopback-only on ports 5432 and 6379.
- Apollo MCP listens on container port 4000 and is reachable only inside the
  Compose network. The Tailscale gateway targets the authenticated backend MCP
  adapter on loopback port 5001.

The UI publishes `/runtime/identity` with its built commit, branch, source tree,
container and host ports, and Tailscale route. The API publishes the same build
identity plus its actual container/image details at `/api/runtime/identity`;
the API route requires normal application authentication.
