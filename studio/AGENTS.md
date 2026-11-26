# SigmaRail research and authoring interface contributor notes

## Project boundary

This directory contains the research and strategy-authoring interface within the SigmaRail implementation. Read the [three-project architecture](https://github.com/SigmaRail/sigmarail-spec/blob/main/docs/ARCHITECTURE.md) before changing behavior.

- SigmaRail Spec defines the product model and versioned contracts.
- The SigmaRail implementation owns this UI, API/MCP services, ClickHouse schema, transforms, loading, and query execution.
- SigmaRail Lean owns the customized LEAN runtime and strategy execution.

## Migration rules

- Keep work specific to capabilities implemented in the SigmaRail project family. Do not advertise unported features as working SigmaRail capabilities.
- Keep SQL as SigmaRail core's executable truth. Studio may consume generated schema/lineage contracts and issue validated read-only queries through its data adapter.
- Preserve versioned saved-screen and strategy payload compatibility. Do not rename wire keys or reinterpret stored documents without a contract version and migration plan.
- Keep knowledge-base and non-core provider integrations optional and separate from core SigmaRail data.
- Do not carry source-specific destructive database maintenance into this application.
- Treat hosted-service and routing changes as a separate deployment task with a completed endpoint and explicit cutover plan.
- Never commit credentials, production data, or generated local user data.

## Validation

Follow `pyproject.toml` and `frontend/package.json` for checks. Prefer synthetic fixtures. Integration checks must use a dedicated test database; production ClickHouse remains read-only.
