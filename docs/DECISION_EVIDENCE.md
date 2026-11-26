# Strategy decision evidence

SigmaRail's LEAN algorithm records bounded per-symbol evidence for each daily
store-backed decision pass. The event sequence is Universe membership, Alpha
prediction (including no prediction), Portfolio target (including no target),
Risk adjustment/check (including no adjustment), and Execution target. LEAN
order fills are recorded separately from targets passed to the Execution model.

Each event carries the strategy spec SHA-256, decision as-of date, observed
timestamp, concise outcome/reason, optional matched rule, and bounded JSON
inputs/outputs. The recorder observes existing model results; it does not alter
strategy outputs. Universe evidence means that the symbol was returned by the
compiled universe query; it does not claim to replay each predicate. Only the
first 100 returned candidates receive daily evidence, matching the existing
snapshot candidate limit.

## Storage and project lifecycle

The LEAN loop is maintained in `src/sigmarail_lab` in this SigmaRail
repository. The existing runner stages that source into a unique per-run LEAN
project under `SIGMARAIL_LEAN_WORKSPACE_ROOT`, then submits that isolated project to the
configured Docker-backed LEAN instance. Backtests include `decision_events` in
the existing `backtest_day_snapshots` artifact. Live runs include the most
recent bounded events and strategy hash in the existing `live_snapshot`
artifact. No new ClickHouse table or enum value is required.

The AppTension PostgreSQL run/deployment reference remains the tenant ownership
gate before the corresponding ClickHouse artifacts are read. Broker marks and
account positions continue to come from the LEAN/broker snapshot.

Older artifacts without these event fields remain legacy records. Snapshot
fallbacks synthesized from equity and order history never receive fabricated
decision events or explanations.
