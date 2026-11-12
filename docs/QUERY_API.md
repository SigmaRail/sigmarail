# Core query API

SigmaRail core exposes read-only queries over its SQL-declared datasets. The generated
`spec/module-manifest.json` registers the core tables, field schema reference, and the
reviewed same-session joins among the five daily screening outputs. The SQL-derived
`spec/lineage-manifest.json` remains authoritative for table and column definitions.

Callers use `sigmarail_spec.DataQueryV1` with a stable dataset ID, stable field IDs,
and join relationship IDs from the module catalog. `sigmarail.query` validates those
references against the packaged manifests, compiles parameterized SELECT statements,
and executes only through ClickHouse's query method. It does not accept arbitrary SQL,
DDL, or caller-supplied join keys. Reads are limited to 1,000 rows and must include a
reviewed as-of/date range or a predicate.

Query-local computed fields use the versioned `sigmarail-spec` AST and compile to
parameterized ClickHouse expressions. Supported forms are boolean predicates,
arithmetic expressions, prior computed aliases, sums of prior aliases, and
`mean_available` over registered fields. `post_where` filters projected and computed
results. Caller-provided SQL is never accepted. Field offsets remain in the Spec AST,
but this executor rejects non-zero offsets until their temporal join semantics are
implemented.

The initial queryable table relationships are daily exact-grain joins on `(ticker, date)`.
Other SQL tables are registered as single-dataset sources, but their frequency and
as-of meaning remain `unspecified` unless separately reviewed. The API rejects
`as_of_date` queries for those tables; callers can still specify explicit predicates
on declared columns. No cross-frequency or provider-module joins are inferred.

ClickHouse grants remain the read/write security boundary. Configure the Studio/core
query connection with a read-only ClickHouse account. `sigmarail-load`, `sigmarail-populate`,
and schema reconciliation remain separate core operations and are not invoked by this API.

## LEAN compatibility API

Studio exposes the LEAN service contract at `/v1/meta`, `/v1/schema/sources`,
`/v1/schema/sources/{prefix}/fields`, and `/v1/universe/run`. These routes use the same
SigmaRail field registry and ClickHouse query compiler. The old `universe_query_v1`
request envelope is translated into stable Spec field IDs before execution. The initial
universe scope is the daily price/technical spine plus its four declared daily joins:
fundamentals, ratings, stage, and ownership. Unknown fields, undeclared joins, raw
`where_sql`, unsupported modes, and non-core source requests receive explicit validation
errors.

Universe runs accept date windows, deterministic ordering, computed fields, post-filters,
up to 5,000 rows per date, and a 500,000-row total cap. Responses echo the registry digest,
selected fields, computed aliases, ordering, and required frame fields so LEAN can fail
closed if the returned frame does not match its request. The metadata route keeps the
current dialect ID for wire compatibility while SigmaRail Spec becomes the canonical
query contract. Set `SIGMARAIL_QUERY_API_KEY` to require `X-API-Key`; during migration,
`VERA_QUERY_API_KEY` remains an accepted fallback.
