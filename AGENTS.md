# SigmaRail repository guidance

This repository contains the SigmaRail implementation. The canonical data and strategy contract
is the `sigmarail-spec` Python package at `packages/sigmarail-spec/`; do not use a separate checkout
as a second source of Spec behavior.

## Ownership

- `packages/sigmarail-spec/` owns versioned schemas, expression and strategy ASTs, compiler and
  decompiler contracts, generated capability documents, and package tests.
- `src/sigmarail/` owns ClickHouse schema, transforms, loading, population, and data/query services.
- `src/sigmarail_lab/` owns SigmaRail's LEAN integration and runtime adapters.
- `studio/` owns Studio UI, API, MCP adapter, and authoring experience. It consumes Spec and does
  not define independent strategy semantics.
- `trading_lab/` owns LEAN project templates and runners. Its `sigmarail_spec/` subset is generated
  from `packages/sigmarail-spec/` and must not be edited by hand.
- `packages/` contains deployable services and frontend packages. Services in this repository
  should consume the local Spec package; downstream projects use a published, pinned PyPI version.

## Contract-first changes

Strategies have exactly five fixed slots: universe selection, alpha, portfolio construction, risk
management, and execution. User-authored documents express SigmaRail semantics; the compiler maps
them to the supported runtime. Do not add arbitrary LEAN class selection, undocumented fields,
extra slots, or UI-only strategy behavior. If a capability cannot be expressed in the Spec contract,
update the Spec, examples, generated documents, and tests before wiring consumers.

The root `spec/` contains SigmaRail implementation manifests. The package's
`packages/sigmarail-spec/spec/` contains Spec package inputs and schemas; keep those roles distinct.

## Working and validation rules

- Work in the primary checkout on `main`. Do not create Git worktrees. Preserve existing changes
  and inspect status before editing or committing.
- Follow the nearest component guidance and existing focused validation commands. Use synthetic
  data for tests; do not write to production ClickHouse or perform live broker actions.
- Regenerate Spec artifacts with `packages/sigmarail-spec/tools/build.py` and the LEAN subset with
  `packages/sigmarail-spec/tools/sync_lean_vendor.py`; review generated diffs.
- Do not commit credentials, local runtime output, or user data.
