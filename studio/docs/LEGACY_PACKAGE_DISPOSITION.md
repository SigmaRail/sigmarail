# SigmaRail capability migration audit

This audit distinguishes serialized identifiers from Python package dependencies.
The migration target is the existing SigmaRail capability set with SigmaRail-owned
implementations. Optional features remain registered until their replacement is ready.

## Target ownership

| Capability | SigmaRail owner | Current migration state |
|---|---|---|
| Sharadar schema, transforms, field/join registry, bounded query execution | Core | Core SQL and query execution are SigmaRail-owned. Studio's basic catalog, preview, and query path use Core. |
| Universe query AST, strategy authoring models, compiler/decompiler, factor and preset definitions | Spec | Ported into `sigmarail-spec`; Studio authoring, MCP, probe, and PCM/risk materialization now import Spec directly. Spec suite passes. |
| Five-slot LEAN runtime, framework discovery, PCM/risk materialization, execution and backtest | SigmaRail Lean | Separate project boundary; Studio must call its API or consume Spec, not import its Python package. This boundary is not yet fully migrated. |
| Web application, REST API, consolidated MCP, catalog and saved screens | Studio | Studio stays in the SigmaRail Core repository. All existing MCP domains remain registered; core/studio remain the defaults. |
| Knowledge base and source research | KnowledgeBase module | Optional external module. Preserve tools while replacing the VeraBase adapter with an explicit KnowledgeBase service contract. No SigmaRail replacement endpoint is verified yet. |
| Broker-connected portfolios and sizing | Portfolio module | Optional external module. Preserve tools while moving broker state, sizing and performance APIs behind an explicit portfolio service contract. No SigmaRail replacement endpoint is verified yet. |

## Current Vera package references

| Reference area | Existing capability | Planned SigmaRail implementation | State |
|---|---|---|---|
| Strategy API, staged pipeline probes, presets and factors | Compile, decompile, edit, preview and catalog strategies | `sigmarail-spec.strategy`; SigmaRail Core resolves physical datasets/joins at query time | Strategy models/compilers/presets moved; Studio routes call Spec. Template catalog now combines Studio screener templates and Spec presets. |
| Universe SQL preview and date-range aggregates | Explain/query a universe and inspect daily membership metrics | Core's `universe` adapter and `compile_query`; keep SQL execution in Core | Query preview, membership and computed range measures route through Core. |
| Position/PCM/risk bindings and ladders | Materialize the same actions and risk rules accepted by LEAN | Declarative builders and registries in Spec; runtime execution stays in SigmaRail Lean | Bindings and ladders moved to Spec; focused materialization tests run without Vera imports. |
| Strategy lint and runtime parameter checks | Reject unsupported five-slot models/parameters and malformed expressions | Spec schema and Spec-owned semantic linter; generated runtime catalog will be sourced from SigmaRail Lean | Linter implementation and Studio save/backtest gate imports now use Spec. Runtime capability artifact provenance still points to the old Lean tree and must be reconnected to SigmaRail Lean. |
| Alpha/factor performance | Evaluate forward-return and factor performance from SigmaRail tables | Implement in Core using its registered fields and query API; keep the REST endpoint and tests | Still calls `sigmarail.features.alpha_evaluation`. |
| Backtest reports and jobs | Submit or inspect runs, wait, fetch results and artifacts | SigmaRail Studio API backed by SigmaRail Lean service | Still calls `sigmarail.features.backtest_report`; preserved. |
| Deployment and live reports | List deployments, status, performance, promotion gates | SigmaRail Lean deployment API | Still calls `sigmarail.features.live_report`; preserved. |
| Catalog and screening domain tools | Discover tables, fields, joins; run named screeners | SigmaRail Core module manifest and query API | MCP catalog wrappers now use the generated core registry and screen wrappers use the SigmaRail preview adapter. |
| Chart and regime tools | Embed charts, summarize regime and evaluate gates | SigmaRail Studio chart service and Core regime datasets/capabilities | Still calls old Vera query modules; preserved and optional. |
| Optimizer tools | List optimization runs and policy scorecards | SigmaRail Lean optimization API | Still calls old Vera platform tools; preserved and optional. |
| Knowledge/research tools | Read KB episodes, submit extractions, search source material and sentiment | KnowledgeBase service/API module; external data stays optional | Still calls Vera query wrappers; preserve until the target service contract is implemented. |
| Portfolio/broker tools | Read accounts, positions, trades, performance and risk sizing | Portfolio service/module with its own credentials and data boundary | Still calls Vera query wrappers; preserve until the target service contract is implemented. |
| LEAN discovery and execution | Enumerate wired types and run a backtest | SigmaRail Lean service, using `sigmarail-spec` for the shared contract | Still imports `vera_lab` in Studio; runtime stays separate but is not yet fully renamed/migrated. |

## Compatibility rule

Keep `VeraBase`, `VeraLabV1`, and `C-VERA-EXPR-V1` as serialized identifiers while
existing saved strategies and the Lean reader depend on them. These wire values are
not Python package dependencies. Any future rename requires a versioned schema and a
reader migration; this cleanup must not rewrite saved payloads in place.

## Release gate

This migration is incomplete. No feature has been removed from the MCP catalog. The
remaining imports above are explicit migration work, not approved permanent runtime
dependencies. Do not describe the optional modules as SigmaRail-native until their
target service/API is implemented and tested. Do not release the consolidated Studio
as Vera-independent until the required imports are gone and each retained capability
has SigmaRail or module-owned integration tests.
