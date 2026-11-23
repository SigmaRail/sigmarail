#!/bin/sh
# Entrypoint script for Apollo MCP Server
# Generates config from environment variables at runtime

set -e

# Default values
GRAPHQL_ENDPOINT="${GRAPHQL_ENDPOINT:-http://backend:5001/api/graphql/}"
# Mutation mode: none (default), explicit (pre-defined mutations only), all (any mutations)
MUTATION_MODE="${MUTATION_MODE:-none}"

# Generate config file from template
cat > /app/runtime-config.yaml << EOF
# Apollo MCP Server - Runtime Configuration
# Auto-generated from environment variables

# GraphQL endpoint to execute queries against
endpoint: ${GRAPHQL_ENDPOINT}

# Forward authentication headers from MCP client to GraphQL endpoint
forward_headers:
  - Authorization
  - X-Tenant-ID

# Transport configuration for HTTP server
transport:
  type: streamable_http
  address: 0.0.0.0
  port: 4000
  host_validation:
    enabled: true
    allowed_hosts:
      - mcp-server:4000

health_check:
  enabled: true
  path: /health

# Schema configuration - use local file
schema:
  source: local
  path: /app/schema/api.graphql

# JSON Schema is used to describe custom scalar arguments in MCP tool schemas.
# GenericScalar is the input carrier for canonical SigmaRail AST documents;
# their operation descriptions and schema tools provide the versioned shape.
custom_scalars: /app/custom-scalars.json

# Self-documenting workflow guidance is included in MCP initialize results.
# Keep this focused on tool discovery, query composition, and safety boundaries.
instructions: |
  SigmaRail MCP is a tenant-scoped, read-only interface to the SigmaRail data and strategy APIs.
  Start by calling GetUserTenants when the account's tenant is not already known. For tenant-scoped tools, pass tenantContext only when the user has multiple tenants; use an ID returned by GetUserTenants, never ask the user to find an ID. The authenticated proxy validates membership on every call and selects the sole tenant automatically. Call GetSigmaRailReadiness before research to check the selected tenant's effective permission codes and the latest price and market-context coverage.

  Use the named SigmaRail operations as the supported interface. Apollo's generic execute tool is disabled; do not construct arbitrary GraphQL requests. For flexible data retrieval, use the bounded DataQueryV1 path: GetSigmaRailCoreDatasets -> GetSigmaRailCoreDataset -> GetSigmaRailCoreQuerySchema -> RunSigmaRailCoreQuery. Select the exact stable field IDs needed in query.select; the returned columns follow that selection. The canonical schema returned by GetSigmaRailCoreQuerySchema is authoritative for filters, joins, date bounds, expressions, and limits.

  For point-in-time screens, use GetSigmaRailScreenSchema before authoring a UniverseQueryV1 AST; use CompileSigmaRailScreen to validate/compile without running it, then PreviewSigmaRailScreen for a bounded result. Use GetSigmaRailScreenSectorRange or ProbeSigmaRailScreen for historical membership analysis.

  For strategy authoring, discover factors, presets, setup recipes, and position fields, then retrieve the pipeline or portfolio schema before constructing an AST. Validate or lint before compiling. Compile/decompile/diff operations are previews; they do not save, launch, or trade.

  For backtests, list tenant-owned runs or jobs before requesting a report. Reports are read only after ownership is checked. Use the regime tools for date-scoped market context and candidate analysis.

  For deeper implementation and AST semantics, consult the public contracts: https://github.com/SigmaRail/sigmarail/blob/main/docs/QUERY_API.md, https://github.com/SigmaRail/sigmarail/blob/main/packages/sigmarail-spec/README.md, https://github.com/SigmaRail/sigmarail/blob/main/packages/sigmarail-spec/docs/EXPRESSIONS.md, and https://github.com/SigmaRail/sigmarail/blob/main/docs/DECISION_EVIDENCE.md. These links explain the design; the schemas and tool results returned by this running MCP are authoritative. The public main branch can be newer than the deployed revision.

  All exposed operations are read-only. Strategy saves, backtest submissions/cancellations, broker actions, and live deployment actions are not available through this MCP. For missing or failed data, preserve the returned code and action, retry only when instructed, and never convert unavailable data into a zero or a positive/negative market conclusion.

# Operations to expose as MCP tools
operations:
  source: local
  paths:
    - /app/operations

# Introspection capabilities for AI. Agent-authored query ASTs are accepted
# only by the bounded SigmaRail GraphQL fields; do not expose Apollo's generic
# ad hoc GraphQL executor over the entire AppTension schema.
introspection:
  execute:
    enabled: false
  introspect:
    enabled: true
    hint: >-
      Use only when a named operation's GraphQL field/argument shape is unclear.
      Prefer predefined SigmaRail operations and their per-tool descriptions. Do not
      use this to construct arbitrary GraphQL execution; generic execute is disabled.
  search:
    enabled: true
    hint: >-
      Search for a specific schema type only when an operation description or the
      canonical SigmaRail AST schema does not answer the question. Prefer named
      operations; this MCP does not expose arbitrary GraphQL execution.

# Enable mutations (create/update/delete operations)
# Options: none (default), explicit (pre-defined mutations only), all (any mutations)
overrides:
  mutation_mode: ${MUTATION_MODE}
EOF

echo "Generated config with endpoint: ${GRAPHQL_ENDPOINT}, mutation_mode: ${MUTATION_MODE}"

if [ -n "${CHAMBER_SERVICE_NAME}" ]; then
  exec /bin/chamber exec "${CHAMBER_SERVICE_NAME}" -- apollo-mcp-server /app/runtime-config.yaml
else
  # The image's previous Compose definition passed /app/config.yaml as a
  # command argument. The Apollo binary accepts exactly one config path, so
  # use the config generated above and ignore any stale command override.
  exec apollo-mcp-server /app/runtime-config.yaml
fi
