# SigmaRail implementation guidance

This repository implements SigmaRail. Before changing product behavior, read the
[SigmaRail architecture and contract guide](../sigmarail-spec/docs/ARCHITECTURE.md)
and this repository's [README](README.md). Use [SigmaRail Spec](https://github.com/SigmaRail/sigmarail-spec)
for the normative product model, contract definitions, and agent retrieval catalog.

## Ownership

- **SigmaRail Spec** defines what data, query, expression, authoring, strategy, and slot documents mean.
- **This SigmaRail repository** owns ClickHouse schema and transforms, data loading and population,
  query validation and execution, the research and strategy-authoring UI, and API/MCP adapters.
- **SigmaRail Lean** owns the customized LEAN engine integration and execution of supported strategy
  documents, including ClickHouse data access.
- The UI and MCP are components of this repository. They consume Spec contracts and do not define
  separate strategy semantics.

## Contract-first implementation

Before implementing behavior, record the applicable contract version, AST path or strategy slot,
owning module, and runtime consumer. If the behavior cannot be expressed in Spec, update the Spec
contract and examples first. Then update this implementation and SigmaRail Lean as required. Do not
add UI-only strategy state, undocumented JSON fields, extra slots, or consumer-specific meanings.

Keep the layers distinct: universe queries select dated data; expression trees classify or calculate
values at declared use sites; the strategy document configures exactly five LEAN slots. SQL and code
remain executable truth for data operations and runtime behavior. Published capability claims must
match the code that currently runs.

## Local safety and validation

- Follow the nearest component `AGENTS.md` and its documented checks.
- Use synthetic data for tests. ClickHouse-backed checks must use the dedicated test database.
- Keep production ClickHouse read-only unless the user explicitly authorizes a production operation.
- Review generated artifacts and source locks; do not hand-edit generated contracts to hide drift.
- Do not commit credentials, production data, or generated local user data.
