# Saved Strategy Identifier Migration

## Decision

SigmaRail will have one current strategy format. We will convert the existing private
strategy corpus and deploy the new compiler/runtime together. The new runtime will reject
Vera-branded identifiers; it will not carry a dual-format reader or legacy aliases.

## Canonical format

Use SigmaRail-owned contract identifiers throughout the serialized strategy:

| Existing value | Canonical value |
| --- | --- |
| `Kind: VeraLabV1` | `Kind: SigmaRailStrategyV1` |
| top-level `VeraBase` section | top-level `SigmaRail` section |
| `C-VERA-EXPR-V1/V2` | `C-SIGMARAIL-EXPR-V1/V2` |
| Vera-prefixed custom framework model IDs | same model IDs with the `SigmaRail` prefix |

Built-in LEAN model IDs such as `ConstantAlphaModel` stay unchanged because they are
owned by LEAN. SigmaRail custom model IDs resolve directly to SigmaRail runtime classes.

## Direct migration steps

1. Inventory every saved strategy, template, fixture, and backtest-linked strategy row.
   Record identifiers, row IDs, content hashes, and references before changing anything.
2. Implement the canonical SigmaRail format in SigmaRail Spec, Studio, and the LEAN
   runtime. Remove old identifiers, runtime aliases, and old package imports from active
   code. Update fixtures and tests to exercise only the canonical format.
3. Build a deterministic converter for the complete saved-strategy inventory. Convert
   both the editable pipeline and compiled runtime document, preserve strategy IDs and
   lineage, and reject any document that cannot be mapped exactly.
4. Run the converter in dry-run mode. Validate every output using the canonical schema,
   compile it, and compare the normalized strategy behavior and hashes. Resolve all
   rejected or ambiguous rows before writing.
5. Apply the converter to the saved strategy store in one auditable migration. Verify
   row counts, IDs, hashes, lineage, and canonical schema after read-back. Do not retain
   old-format copies in the active strategy store.
6. Build and deploy the SigmaRail worker, then run the SPY positive control and the
   migrated strategy corpus against it. Confirm dates, subscriptions, insights, targets,
   orders, fills, and accounting.

## Acceptance

- No active package, compiler, Studio screen, fixture, strategy row, or runtime accepts or
  emits a Vera-branded strategy identifier.
- Every saved strategy is represented in the migration report and has a canonical
  replacement with matching ID and lineage.
- The converter is deterministic and refuses lossy conversions.
- Canonical strategies compile and validate against the same contract used by LEAN.
- The SPY positive control places the expected trade and reconciles its accounting.

## Current migration access

The authenticated SigmaRail tenant currently lists 200 saved strategies: 17 with editable
pipeline documents and 183 compiled-only records. The local ClickHouse endpoint contains
252 strategy rows but does not contain the SPY control, so it is not the same strategy
store and must not be used to rewrite the tenant corpus.

The connected SigmaRail MCP exposes list, get, and pipeline-save operations, but no bulk
raw-spec update operation for the 183 compiled-only records. Add a tenant-owned migration
operation or run the converter in the deployment that owns that strategy store. Keep this
code change single-format; do not add a fallback reader while waiting for that migration
path. Scope the eventual write to strategy documents and preserve market-data tables.
