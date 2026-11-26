# SigmaRail optional data modules

This document describes an extension proposal for optional datasets and providers within SigmaRail.
It does not create additional core projects or replace the [three-project architecture](https://github.com/SigmaRail/sigmarail-spec/blob/main/docs/ARCHITECTURE.md).

## Ownership

| Project or component | Owns | Must not own |
|---|---|---|
| **SigmaRail Spec** | Versioned module, dataset, field, join, query, and capability contracts | Database connections, data loading, query execution, UI, or strategy runtime |
| **SigmaRail** | Core ClickHouse schema, transforms, loaders, query execution, research interface, and MCP host; optional integrations that are explicitly enabled | A second definition of contract semantics or LEAN engine execution |
| **SigmaRail Lean** | Backtest and live strategy execution, LEAN integration, orders, and runtime evidence | Core market-data schema, data acquisition, or research interface |

An optional provider integration is a SigmaRail capability or external service integration, not a
fourth architecture project. It owns its acquisition, licensing, provenance, schema, and refresh
behavior. It must remain optional to the SigmaRail core data product.

## Module contract

Treat SigmaRail core datasets as the always-available `sigmarail.core` module. An optional module
declares:

- a stable module ID and contract version;
- the datasets, fields, physical tables, source lineage, and install target it owns;
- entity keys, row grain, interval, `as_of` meaning, availability rules, and refresh cadence;
- explicit joins with cardinality and temporal alignment rules;
- capabilities with input/output contract references and MCP resource or tool IDs;
- configuration requirements and whether it is discoverable, configured, enabled, and healthy.

Never infer a join from matching column names. Daily, weekly, monthly, event, and intraday datasets
require explicit temporal alignment rules. A registry must distinguish unavailable data from an empty
result.

## SigmaRail behavior

SigmaRail's research interface and MCP host consume the module catalog and query contracts. The UI
may compose supported fields and filters; it must not invent joins or query semantics. MCP tools
validate the same contracts and call SigmaRail-owned query services. A package's presence does not
activate its tools or provider integration: activation and credentials must be explicit.

The compact contract index should let an agent retrieve the global module catalog first, then only
the selected module's datasets, fields, joins, and capability slices. Tool descriptions and output
schemas must reflect the same contract.

## Current implementation status

The embedded package includes a draft module-manifest schema and generated core/module artifacts.
The generic third-party module manifest remains a proposal: package discovery, activation, and
execution are not implemented as a complete extension system. Do not claim general plug-in support
until the contract, activation flow, and runtime are implemented and validated together.
