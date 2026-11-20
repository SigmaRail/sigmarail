# SigmaRail modules: ownership and integration proposal

## Project boundaries

| Project or module | Owns | Must not own |
|---|---|---|
| **SigmaRail core** | Sharadar source tables, Sharadar-only transforms, derived technical/fundamental/institutional outputs, and a read-only query interface over those declared datasets | Analyst estimates, KB/sentiment, external-provider ingestion, brokerage state, portfolio policy, or trading execution |
| **SigmaRail Spec** | Versioned expression/query contracts, generated core schema and lineage, and the module/dataset/capability manifest format | Database connections, data loading, screener execution, or strategy runtime |
| **SigmaRail Studio** | Research and strategy-authoring UI, one MCP server, module discovery/activation, query composition, and adapters to data and execution services | Owning provider SQL or duplicating core schema/metric calculations |
| **SigmaRail Lean** | Backtest and live strategy execution, LEAN integration, execution lifecycle and runtime evidence | Owning core financial source data or Studio UX |
| **Provider/data add-ons** | Their own acquisition, licensing/provenance, schemas, transforms, and module-owned datasets | Altering SigmaRail core tables or being silently loaded by core commands |
| **Knowledge Base** | Source acquisition, document processing, KB-specific indexes and tools | SigmaRail core tables or mandatory Studio/core installation dependencies |

## One module mechanism

Treat SigmaRail core itself as the always-available `sigmarail.core` module. Core datasets and optional modules use the same descriptor and query/capability interfaces. Physical names such as `screener_*` are implementation details; Studio resolves logical dataset and field IDs from the registry.

An optional module declares:

- a stable module ID, version, package, and required dependencies;
- the datasets and fields it owns, including physical table, source lineage, and install target;
- entity keys, row grain, time interval, `as_of` meaning, completion/availability rules, and update cadence;
- explicit joins and their cardinality and temporal alignment rules;
- the capabilities it implements, with input/output contract references and MCP resource/tool IDs;
- configuration requirements and whether the module is discoverable, configured, and enabled.

The registry must not imply a join from matching column names. Each join declares entity keys and temporal behavior. Daily observations must not be mixed with weekly or monthly aggregates without an explicit as-of/alignment rule. Intraday, daily, weekly, monthly, and event datasets are distinct interval kinds.

## Dataset and table ownership

- A module exclusively owns its tables and transforms. Core schema reconciliation reads only the core SQL manifest and never scans or modifies add-on tables.
- Add-ons use namespaced tables such as `ext_estimates_analyst_daily`; they do not add columns to `screener_fundamentals_daily` or any other core table.
- A module may register its fields and dataset as screener-compatible. Studio's screener composes fields from registered datasets at compatible grains; it does not require every output table to be named `screener_*`.
- Start with a shared ClickHouse database and namespaced tables where cross-module joins are needed. The module descriptor should permit an explicitly configured database per module for security, licensing, retention, or operational isolation. Database separation is deployment policy; it does not change table ownership.
- Provider-specific estimates, AAII sentiment, ETF holdings/flows, index proxies, and macro series belong to optional provider modules. Their data rights, refresh jobs, and transformations stay with the owning module.

## Studio and MCP behavior

Studio remains the single user-facing MCP host. It always exposes the core schema, lineage, and query capability. It adds module resources/tools only for modules that are installed, explicitly enabled, configured, and healthy. Resource and tool names are namespaced (`core.*`, `estimates.*`, `kb.*`); an unavailable optional module reports its state without taking down core query tools.

Module discovery must be separate from module activation. A Python entry point or package manifest may identify installed code, but code is trusted and never activated merely because it is present. Users explicitly enable modules and supply provider credentials through Studio's settings/key store. The core package does not import or install optional provider packages.

The MCP Resource index should let an agent retrieve the compact module catalog first, then only the selected module's datasets, fields, joins, and capability slices. MCP Tools validate requests against those same contracts. The Spec describes supported behavior; the core or module package performs it.

## Migration from the source Studio

Move the Vera-derived pieces by ownership rather than copying the whole dependency graph into SigmaRail core:

1. Port the schema/field/lineage catalog and a bounded read-only query service for the core datasets into SigmaRail.
2. Move the universe-query AST and its validation contract into SigmaRail Spec; move SQL compilation and execution into SigmaRail's query implementation. Keep supported nodes limited to those implemented by the core query engine.
3. Migrate Studio's field/catalog/screening adapters to the core query API and Spec Resources.
4. Keep strategy authoring contracts in Spec and their UI in Studio. Keep backtesting/live execution in SigmaRail Lean, called through a Studio adapter.
5. Keep estimates, KB/sentiment, portfolios, brokerage, and other non-core source/runtime integrations outside the core package. Integrate them as optional modules only when their owner and contract are clear.

During migration, preserve existing saved-screen and strategy wire formats through compatibility adapters. A clean project rename does not itself authorize a breaking contract change.

## Status

This document defines the intended boundary. A draft JSON Schema is at `spec/modules/module-manifest-v1.schema.json`, with a synthetic example at `examples/modules/example-sentiment.json`. Neither is packaged or a published v1 contract yet. The current SigmaRail core still needs the query runtime, and the first SigmaRail Studio migration still contains legacy adapters. Module discovery/activation and temporal join validation also need implementation before claiming extension support.
