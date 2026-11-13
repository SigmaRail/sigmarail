# SigmaRail capability migration to-do

This is the execution checklist for preserving the Vera-era capability surface while
moving runtime ownership to SigmaRail projects. A capability is complete only when its
MCP/API behavior is retained, its dependencies are SigmaRail-owned or explicitly
module-owned, and its tests pass without Vera packages installed.

## Phase 1 — Finish the shared strategy contract

- [x] Move the semantic strategy linter into `sigmarail-spec`; preserve E000/E100/E101,
  E110, E200/E201 and E210–E212 behavior, plus warning/error paths and runtime action
  vocabulary.
- [ ] Generate/verify runtime model parameter and action catalogs from SigmaRail Lean;
  keep unknown runtime types explicit rather than silently accepting them.
- [x] Switch Studio save and backtest gates to the Spec linter; keep the current
  `off|warn|enforce` behavior and wire formats.
- [ ] Remove the remaining strategy-authoring and lint imports from `sigmarail.features`.
- [ ] Verify the standalone LEAN vendor artifact includes only Spec runtime code and
  remains importable without Django, ClickHouse, or Studio dependencies.

## Phase 2 — Finish SigmaRail Core-backed analytics

- [ ] Port factor/alpha performance evaluation from `sigmarail.features.alpha_evaluation`
  into Core using generated field/relationship metadata and the registered query API.
- [ ] Preserve factor validation, quantile forward returns, Spearman IC/ICIR, regime
  slices, verdicts, and the existing REST/MCP response contract.
- [ ] Migrate remaining chart and regime reads to registered SigmaRail datasets or a
  documented chart adapter; preserve MCP names and response shapes.
- [ ] Audit Core SQL comments/docs for stale package references; keep wire-format IDs
  unchanged unless versioned separately.

## Phase 3 — Route execution capabilities through SigmaRail Lean

- [ ] Define and version the Studio-to-Lean service contract for run submission, status,
  waiting, reports, artifacts, cancellation, and progress.
- [ ] Move backtest MCP/report screens from `sigmarail.features.backtest_report` to that
  service while retaining tool inputs, outputs, and saved run records.
- [ ] Move framework discovery and runtime parameter/action capability export to Lean;
  make Spec generation consume pinned Lean artifacts.
- [ ] Move deployment status/performance/promotion and optimizer run/scorecard calls
  behind Lean service endpoints.
- [ ] Validate using the shipped private Lean image, synthetic ClickHouse data, and a
  full-stack smoke test; retain the current 714-row/43-order baseline where applicable.

## Phase 4 — Keep optional external modules independent

- [ ] Define an explicit KnowledgeBase service contract for episode reads, extraction,
  chunk submission, search, sentiment, and research context.
- [ ] Define a Portfolio module contract for broker accounts, positions, trades,
  allocation drift, performance, household status, and sizing.
- [ ] Preserve all registered MCP tools, but report unavailable optional services
  accurately; do not require KB/broker dependencies for Core or Studio installation.
- [ ] Add module-level tests and configuration/credential boundaries without importing
  `sigmarail.features` into Studio startup.

## Phase 5 — Release and close-out

- [ ] Remove or migrate every runtime import of `sigmarail.features`, `vera_spec`, and
  `vera_lab`; classify remaining occurrences as documented compatibility strings,
  provenance, or versioned serialized identifiers.
- [ ] Run Core, Spec, Studio, Lean, and optional-module suites in clean environments;
  run the synthetic full-stack Lean smoke and deterministic Spec build check.
- [ ] Verify no tools/domains were dropped, generated artifacts are current, packaging
  works without Vera checkouts on `PYTHONPATH`, and install docs match the module model.
- [ ] Update the capability audit, source locks, release notes, and CI cross-repository
  pins; obtain independent exact-SHA review before merging.

## Current checkpoint

- Completed: strategy authoring models/compiler/presets and PCM/risk builders moved to
  Spec; Core-backed universe querying/catalog/named screeners are migrated. Focused
  validation at this checkpoint: 729 Spec tests and 100 Core/Studio tests passed, with
  one integration test skipped.
- Active next slice: connect the generated runtime model/action catalog to SigmaRail
  Lean and remove remaining Vera strings/imports from the linter gates. The linter parity
  suite passes; factor performance follows as the first Core analytics port.
- Still outstanding: all unchecked items above. Legacy MCP modules remain registered;
  pending imports are migration work, not completed SigmaRail implementations.
