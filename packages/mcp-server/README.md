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
| `MUTATION_MODE`         | Mutation mode: `none`, `explicit` (pre-defined only), `all` | `none`                             |

### SigmaRail AST tools

The MCP is designed to teach its workflow through the `initialize` instructions, each
tool's description, and canonical schema-discovery operations. When the server is behind
AppTension, the authenticated proxy must preserve Apollo's `initialize` instructions while
adding its tenant-selection guidance. This mirrors the useful Vera MCP pattern: discover
the supported interface, fetch the authoritative schema, compose a bounded request, inspect
validation output, then execute or preview.

#### Data-query workflow

1. Call `sigmarail_core_datasets` to discover registered datasets and their time semantics.
2. Call `sigmarail_core_dataset` for the chosen dataset to inspect stable field IDs and
   declared relationships.
3. Call `sigmarail_core_query_schema` before constructing a `DataQueryV1` AST. Treat its
   result as the authority for supported AST fields and constraints.
4. Call `sigmarail_core_query` with only the required fields in `query.select`, explicit
   date bounds for historical work, and a bounded row limit. The selected IDs determine
   the returned columns; there is no fixed result-column allowlist.
5. Read coverage and result metadata before interpreting empty or sparse output as a real
   zero. Schema validity does not establish source-data completeness.

#### Screener workflow

Fetch `sigmarail_screen_schema` before authoring a `UniverseQueryV1` AST. Use catalog field
IDs, call `sigmarail_screen_compile` to validate/compile without execution, then call
`sigmarail_screen_preview` with an explicit `asOf` date and bounded `spec.select`/limit.
Use `sigmarail_screen_sector_range` or `sigmarail_screen_probe` for historical membership
and stage-prefix analysis. Named preset discovery/preview is preferable when a suitable
canonical preset already exists.

#### Strategy and backtest-review workflow

Discover factors, setup recipes, position fields, presets, or saved documents as needed.
Fetch the canonical `PipelineDocument` or `PortfolioDocument` schema before authoring;
validate or lint before compile/decompile/diff. These operations are previews and do not
save or launch strategies. For backtests, list tenant-owned runs/jobs first and request a
report only for a run visible to that tenant; ownership is checked in PostgreSQL before
analytical artifacts are read from ClickHouse. Regime tools provide date-scoped context.

GraphQL's `GenericScalar` is used to transport versioned AST documents. Apollo maps that
scalar to an object-shaped JSON Schema so agents know to submit structured input; this is
tool-call guidance, not semantic validation. SigmaRail Spec remains authoritative for AST
shape and meaning. Apollo's generic ad hoc GraphQL `execute` tool is disabled. This MCP
slice is read-only: strategy saves, backtest submission/cancellation, broker actions, and
live deployment actions are not exposed.

Read-only market context also exposes the date-scoped regime, per-ticker allocation
explanations, entry-gate evaluation, transition weighting, candidate ranking, and comparisons
between two bounded periods. These resolve through the existing SigmaRail feature functions;
they do not write strategy state or orders.

Apollo's generic ad hoc GraphQL `execute` tool is disabled. Agents can shape query results
through the AST's `select` list without receiving arbitrary execution over the full
AppTension GraphQL schema.

### Adding New Operations

To expose new GraphQL queries as MCP tools:

1. Create a new `.graphql` file in the `operations/` directory
2. Add the `@tool` directive comment with name and description:

```graphql
# @tool(name: "my_tool_name", description: "Description for the AI to understand when to use this tool")
query MyQuery($tenantId: ID!, $otherParam: String) {
  myQuery(tenantId: $tenantId, otherParam: $otherParam) {
    field1
    field2
  }
}
```

3. Restart the MCP server to pick up the new operations

### Security

- All requests go through the Django proxy which validates tenant access
- Every SigmaRail operation requires a tenant ID and checks the authenticated user's
  accepted membership on the backend. A supplied tenant ID is never trusted without that
  membership check.
- Rate limiting is configured at both proxy and MCP server levels
- Mutation mode defaults to `none` (read-only)
- To change mutation behavior, set `MUTATION_MODE` environment variable or update `config.yaml`

### Mutation Modes

| Mode       | Description                             | Recommended For            |
| ---------- | --------------------------------------- | -------------------------- |
| `none`     | Mutations disabled, read-only           | High security environments |
| `explicit` | Only pre-defined mutation tools allowed | Enable only when reviewed operations need writes |
| `all`      | AI can build arbitrary mutations        | Development only           |

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

## Role-Based Access Control (RBAC)

The MCP server implements role-based access control through the GraphQL backend. **Always call `get_user_permissions` first** to discover what data the current user can access.

### Permission System

Users are assigned organization roles that grant specific permissions. The system supports:

- **OWNER**: Full access to all data and operations
- **ADMIN**: Administrative access to most data (excluding delete operations)
- **MEMBER**: Limited access based on assigned permissions

### Discovery Flow

1. **First call**: `get_user_permissions` to get current user's permissions
2. **Check permissions**: Before calling any tool, verify the user has required permissions
3. **Handle access denied**: If user lacks permission, explain what access they need instead of erroring

Example response when user lacks access:

> "You don't have access to financial data (requires `management.financial.view` permission). Please contact your organization admin to request access."

## Available Tools

### 🔐 Access Control (Always Call First)

| Tool                   | Description                                                        | Required Permission  |
| ---------------------- | ------------------------------------------------------------------ | -------------------- |
| `get_user_permissions` | **CRITICAL**: Get user's permissions and roles. Always call first! | None (authenticated) |

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
2. Check that each query has a `# @tool(...)` comment
3. Restart the MCP server after adding new operations
