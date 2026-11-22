# Primary Docker runtime

`deploy/compose.primary.yml` is the laptop runtime definition for the primary
SigmaRail checkout on `main`. It keeps the UI, Django API, Apollo MCP, Postgres,
and Redis as separate containers. The frontend is built from this checkout and
uses a same-origin `/api` proxy to the API container. ClickHouse remains native
on macOS and is reached from Docker through `host.docker.internal`.

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

## Build and update

From the SigmaRail repository root, use the current `main` revision when
building the backend identity into the image:

```sh
SIGMARAIL_BUILD_REVISION="$(git rev-parse HEAD)" \
  docker compose -f deploy/compose.primary.yml build backend frontend mcp-server
```

Then update only the app services:

```sh
SIGMARAIL_BUILD_REVISION="$(git rev-parse HEAD)" \
  docker compose -f deploy/compose.primary.yml up -d backend frontend mcp-server
```

The Compose project is named `sigmarail`. Its Postgres and Redis services mount
the existing data volumes. Do not run a second Postgres container against the
same data directory at the same time.

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
