# Apollo MCP Server Configuration

This directory contains the configuration for the Apollo MCP Server, which exposes GraphQL operations as MCP (Model Context Protocol) tools for AI assistants.

## Overview

The MCP Server acts as a bridge between AI models (OpenAI, Claude, etc.) and your GraphQL API, allowing AI assistants to query your business data in a secure, tenant-scoped manner.

## Directory Structure

```
mcp-server/
├── config.yaml           # Main server configuration
├── Dockerfile            # Production Dockerfile for cloud deployments
├── operations/           # GraphQL operations exposed as MCP tools
│   ├── projects.graphql  # Project queries
│   ├── clients.graphql   # Client queries
│   ├── people.graphql    # Team member queries
│   ├── financials.graphql # Revenue, costs, profitability
│   ├── forecasting.graphql # Forecasting and insights
│   ├── invoices.graphql  # Invoice queries
│   └── deals.graphql     # Sales pipeline queries
└── README.md
```

## Configuration

### Environment Variables

| Variable                | Description                                                 | Default                            |
| ----------------------- | ----------------------------------------------------------- | ---------------------------------- |
| `GRAPHQL_ENDPOINT`      | Backend GraphQL endpoint                                    | `http://backend:5001/api/graphql/` |
| `MCP_LLM_PROVIDER`      | LLM provider (openai/anthropic)                             | `openai`                           |
| `MCP_LLM_MODEL`         | Model to use                                                | `gpt-4o`                           |
| `OPENAI_API_KEY`        | OpenAI API key                                              | Required                           |
| `MCP_TELEMETRY_ENABLED` | Enable OpenTelemetry                                        | `false`                            |
| `MCP_LOG_LEVEL`         | Log level                                                   | `info`                             |
| `MUTATION_MODE`         | Mutation mode: `none` or `explicit` (allowlisted only)      | `explicit` in primary Compose     |

### SigmaRail AST tools

The MCP is designed to teach its workflow through the `initialize` instructions, each
tool's description, and canonical schema-discovery operations. When the server is behind
AppTension, the authenticated proxy must preserve Apollo's `initialize` instructions while
adding its tenant-selection guidance. This mirrors the useful Vera MCP pattern: discover
the supported interface, fetch the authoritative schema, compose a bounded request, inspect
validation output, then execute or preview.

#### Data-query workflow

1. Call `GetUserTenants` when the active tenant is not known, then call
   `GetSigmaRailReadiness` before research. It reports effective permission codes and latest
   observed dates and row coverage for price and market-context data.
2. Call `GetSigmaRailCoreDatasets` to discover registered datasets and their time semantics.
3. Call `GetSigmaRailCoreDataset` for the chosen dataset to inspect stable field IDs and
   declared relationships.
4. Call `GetSigmaRailCoreQuerySchema` before constructing a `DataQueryV1` AST. Treat its
   result as the authority for supported AST fields and constraints.
5. Call `RunSigmaRailCoreQuery` with only the required fields in `query.select`, explicit
   date bounds for historical work, and a bounded row limit. The selected IDs determine
   the returned columns; there is no fixed result-column allowlist.
6. Read coverage and result metadata before interpreting empty or sparse output as a real
   zero. Schema validity does not establish source-data completeness.

`GetSigmaRailReadiness` returns stable codes such as `DATA_BACKEND_DISABLED`,
`DATA_NOT_AVAILABLE`, `DATA_SOURCE_UNAVAILABLE`, and `PERMISSIONS_UNAVAILABLE`, with a
recovery action. Keep the actual available date and counts attached to any analysis; never
interpret unavailable or empty data as a zero-valued market observation.

#### Screener workflow

Fetch `GetSigmaRailScreenSchema` before authoring a `UniverseQueryV1` AST. Use catalog field
IDs, call `CompileSigmaRailScreen` to validate/compile without execution, then call
`PreviewSigmaRailScreen` with an explicit `asOf` date and bounded `spec.select`/limit.
Use `GetSigmaRailScreenSectorRange` or `ProbeSigmaRailScreen` for historical membership
and stage-prefix analysis. Named preset discovery/preview is preferable when a suitable
canonical preset already exists.

#### Strategy and backtest-review workflow

Discover factors, setup recipes, position fields, presets, or saved documents as needed.
Fetch the canonical `PipelineDocument` or `PortfolioDocument` schema before authoring;
validate or lint before compile/decompile/diff. To persist a screen or strategy, call
`SaveSigmaRailScreen` or `SaveSigmaRailStrategy` only after the user asks to save it. These
write only tenant-owned AppTension PostgreSQL records. For backtests, use
`SubmitSigmaRailBacktest` with an explicit date range and stable idempotency key; the strategy
content hash is pinned at queue time, and retries with the same key/request return the same job.
Poll jobs and inspect tenant-owned reports before reaching a conclusion. `costAssumptions` and
`outOfSamplePeriod` are recorded as request metadata only: the current runner does not apply a
custom fee/slippage model or automatically run a second OOS period. Regime tools provide
date-scoped context. After a completed run has been reviewed, `RecordSigmaRailExperimentDecision`
can append a tenant-owned retain/revise/discard/defer verdict with rationale and evidence.

GraphQL's `GenericScalar` is used to transport versioned AST documents. Apollo maps that
scalar to an object-shaped JSON Schema so agents know to submit structured input; this is
tool-call guidance, not semantic validation. SigmaRail Spec remains authoritative for AST
shape and meaning. Apollo's generic ad hoc GraphQL `execute` tool is disabled. Only the four
reviewed mutation operations in `mutation-allowlist.txt` are configured. CRUD demo mutations,
cancellation, broker actions, and live deployment actions are not exposed.

Read-only market context also exposes the date-scoped regime, per-ticker allocation
explanations, entry-gate evaluation, transition weighting, candidate ranking, and comparisons
between two bounded periods. These resolve through the existing SigmaRail feature functions;
they do not write strategy state or orders.

Apollo's generic ad hoc GraphQL `execute` tool is disabled. Agents can shape query results
through the AST's `select` list without receiving arbitrary execution over the full
AppTension GraphQL schema.

### Adding New Operations

To expose new GraphQL queries as MCP tools:

1. Create a new `.graphql` file in the `operations/` directory.
2. Give the GraphQL operation its stable public MCP tool name in `PascalCase`. Apollo uses the
   GraphQL operation name as the exposed tool name and the leading comment as its description:

```graphql
# Describe when an agent should use this tool, its required workflow, and important safety or coverage limits.
query MyToolName($tenantId: ID!, $otherParam: String) {
  myQuery(tenantId: $tenantId, otherParam: $otherParam) {
    field1
    field2
  }
}
```

3. Validate the tool name and description with MCP `tools/list`, then restart the MCP server
   to pick up the new operation.

### Security

- All requests go through the Django proxy which validates tenant access
- Every SigmaRail operation requires a tenant ID and checks the authenticated user's
  accepted membership on the backend. A supplied tenant ID is never trusted without that
  membership check.
- Rate limiting is configured at both proxy and MCP server levels
- Mutation mode defaults to `none`; primary Compose opts into the explicit allowlist
- To change mutation behavior, set `MUTATION_MODE` environment variable or update `config.yaml`

### Mutation Modes

| Mode       | Description                             | Recommended For            |
| ---------- | --------------------------------------- | -------------------------- |
| `none`     | Mutations disabled                      | High security environments |
| `explicit` | Only allowlisted operation files loaded | Primary Compose; exposes four named SigmaRail writes |
| `all`      | Not supported for SigmaRail deployment  | Do not use |

## Deployment

### Local Development

The MCP server is automatically started with `pnpm saas up`:

```bash
# Start all services including MCP server
pnpm saas up

# Or start MCP server individually
docker compose up mcp-server
```

### VPS / Self-Hosted (docker-compose.prod.yml)

The MCP server is included in the production docker-compose configuration:

```bash
# Deploy with all services
docker compose -f docker-compose.prod.yml up -d
```

Required environment variables in `.env.prod`:

- `OPENAI_API_KEY` - Your OpenAI API key
- `MCP_LLM_MODEL` - Model to use (default: gpt-4o)

### Render.com

The MCP server is defined in `render.yaml` but commented out by default to save costs.
To enable it:

1. Uncomment the `mcp-server` service in `render.yaml`
2. Deploy to Render
3. Set environment variables in Render Dashboard:
   - `GRAPHQL_ENDPOINT`: Your backend API URL (e.g., `https://backend-api-xxxx.onrender.com/api/graphql/`)
   - `OPENAI_API_KEY`: Your OpenAI API key
4. Update `MCP_SERVER_URL` in backend-api to point to the MCP server URL

### AWS (ECS Fargate)

For AWS deployments, you'll need to:

1. Create an ECS task definition for the MCP server
2. Add the service to your ECS cluster
3. Configure the security group to allow traffic from the backend service
4. Set the `MCP_SERVER_URL` environment variable in the backend task

## Backend Integration

The Django backend includes a proxy endpoint at `/api/ai-assistant/` that:

- Validates user authentication and tenant access
- Injects `tenantId` into all GraphQL operations
- Forwards requests to the MCP server
- Handles errors gracefully when MCP is unavailable

Required backend environment variable:

- `MCP_SERVER_URL` - URL of the MCP server (e.g., `http://mcp-server:4000`)

If `MCP_SERVER_URL` is not set, the AI Assistant will be disabled with a helpful message.

## Testing

You can test the MCP server using the MCP Inspector:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Connect to the server
mcp-inspector http://localhost:4000
```

Or test the AI Assistant directly via the API:

```bash
curl -X POST http://localhost:5001/api/ai-assistant/tenants/{tenant_id}/chat/ \
  -H "Authorization: Bearer {your_token}" \
  -H "Content-Type: application/json" \
  -d '{"message": "How many active projects do we have?"}'
```

## Identity, tenant access, and permissions

Start with `GetUserTenants` when the user's tenant is not already known. The authenticated
proxy discovers accepted memberships and enforces tenant access on every call; for a single
tenant it selects that tenant automatically. For multiple tenants, ask which tenant by name
and pass only an ID returned by `GetUserTenants` as `tenantContext`. Never ask the user to
look up an ID. `GetUserPermissions` is supplementary when the authorization requirements
of a particular operation are unclear; it is not a prerequisite for every tool call.

### Permission System

Users are assigned organization roles that grant specific permissions. The system supports:

- **OWNER**: Full access to all data and operations
- **ADMIN**: Administrative access to most data (excluding delete operations)
- **MEMBER**: Limited access based on assigned permissions

### Deeper reference

The live MCP schemas and results are authoritative for the running deployment. For explanatory
detail, use the public [SigmaRail repository](https://github.com/SigmaRail/sigmarail), especially
the [query contract](https://github.com/SigmaRail/sigmarail/blob/main/docs/QUERY_API.md),
[SigmaRail Spec and AST](https://github.com/SigmaRail/sigmarail/blob/main/packages/sigmarail-spec/README.md),
[expression semantics](https://github.com/SigmaRail/sigmarail/blob/main/packages/sigmarail-spec/docs/EXPRESSIONS.md),
and [decision evidence](https://github.com/SigmaRail/sigmarail/blob/main/docs/DECISION_EVIDENCE.md).
The public `main` branch may be newer than a running deployment; use schemas returned by the
authenticated MCP for exact field names and supported constraints.

Example response when user lacks access:

> "You don't have access to financial data (requires `management.financial.view` permission). Please contact your organization admin to request access."

## Available Tools

### Tenant and permission tools

| Tool | Use |
| --- | --- |
| `GetUserTenants` | Discover accepted tenants when the user's tenant is not already known; choose by name if multiple are available. |
| `GetUserPermissions` | Inspect a tenant's permission codes when a specific tool's authorization needs clarification. It is supplementary, not a required first call. |

## Troubleshooting

### MCP server not starting

1. Check if the backend is running: `docker compose ps backend`
2. Check MCP server logs: `docker compose logs mcp-server`
3. Verify `OPENAI_API_KEY` is set in your environment

### AI Assistant returns "unavailable" error

1. Check if `MCP_SERVER_URL` is set in backend environment
2. Verify MCP server is reachable: `curl http://localhost:4000/health`
3. Check backend logs for connection errors

### GraphQL operations not being recognized

1. Verify the `.graphql` files are in the `operations/` directory
2. Check that each query has a descriptive leading comment and the intended stable GraphQL operation name
3. Restart the MCP server after adding new operations
4. Send `initialize` and `tools/list` through the configured gateway. Confirm named tools such
   as `GetSigmaRailCoreDatasets`, `GetSigmaRailCoreQuerySchema`, `GetSigmaRailScreenSchema`, and
   `GetSigmaRailStrategyPipelineSchema` are present. If the client only shows a generic GraphQL
   executor or an older AppTension tool set, check the configured server URL and refresh/recreate
   the client's cached tool catalog; do not assume a successful OAuth login means tool discovery
   succeeded.
