# SigmaRail tenant ownership and legacy data

## Ownership boundary

- Market prices, fundamentals, estimates, and screener datasets in ClickHouse are shared SigmaRail data. They are not owned by an application tenant.
- Strategies, saved screens, backtest jobs, optimizer sessions, deployment records, and broker profile metadata are tenant-owned PostgreSQL records.
- Backtest results and runtime events may be retained in ClickHouse for analytics. Their PostgreSQL reference is the authorization link to a tenant. Do not expose a ClickHouse row to a user unless a matching reference belongs to the active tenant.
- Broker credentials are not stored in ClickHouse. PostgreSQL stores only non-secret broker profile metadata; secrets remain in the configured credential store.

## Legacy records

Tenantless PostgreSQL records and ClickHouse rows without a PostgreSQL ownership reference are unassigned. Runtime APIs omit them from catalogs and return not found for direct lookups. They are preserved in storage and remain available for a deliberate ownership decision; they are not automatically assigned to the active tenant or made globally shared.

Inspect tenantless PostgreSQL records from the backend directory:

```sh
uv run python manage.py reconcile_workspace_ownership
```

Include ClickHouse runtime identifiers and counts (read-only):

```sh
uv run python manage.py reconcile_workspace_ownership --include-clickhouse
```

To preview explicit assignments, supply a JSON file. IDs must identify existing tenantless rows; `tenant_slug` must identify the intended destination workspace:

```json
{
  "WorkspaceScreen": [
    {"id": "record-uuid", "tenant_slug": "my-workspace"}
  ],
  "WorkspaceBacktestReference": [
    {"id": "record-uuid", "tenant_slug": "my-workspace"}
  ],
  "ClickHouseBacktestRun": [
    {"run_id": "legacy-run-id", "tenant_slug": "my-workspace"}
  ],
  "ClickHouseOptimizerSession": [
    {"session_id": "legacy-session-id", "tenant_slug": "my-workspace"}
  ],
  "ClickHouseDeployment": [
    {"deployment_id": "legacy-deployment-id", "tenant_slug": "my-workspace"}
  ]
}
```

```sh
uv run python manage.py reconcile_workspace_ownership --mapping-file /secure/path/tenant-map.json
```

The command is preview-only by default. ClickHouse imports read the selected legacy metadata using a read-only client; they do not change ClickHouse. After reviewing the preview, apply the same mapping with `--apply`. A mapped backtest or deployment becomes visible only in its selected tenant. Deployment imports with an approval run require that run to be assigned to the same tenant in PostgreSQL.

## Adding runtime analytics

New runtime events should first have a durable tenant-scoped run/deployment identity in PostgreSQL. Project analytical events to ClickHouse with tenant ID, run/deployment ID, strategy content hash, event timestamp, and an idempotency key. Browser requests must not choose their own tenant filter; the API derives scope from authenticated membership and the active tenant.
