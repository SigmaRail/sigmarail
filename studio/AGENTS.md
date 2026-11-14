# SigmaRail Studio contributor notes

## Project boundary

SigmaRail Studio owns the research and strategy-authoring application, its UI, consolidated MCP, and adapters to the SigmaRail data and strategy services. SigmaRail core owns database schema, transforms, load/populate, and data semantics. SigmaRail Spec owns versioned machine-readable contracts. SigmaRail Lean owns strategy execution when migrated.

## Migration rules

- Keep work specific to capabilities implemented in the SigmaRail project family. Do not advertise unported features as working SigmaRail capabilities.
- Keep SQL as SigmaRail core's executable truth. Studio may consume generated schema/lineage contracts and issue validated read-only queries through its data adapter.
- Preserve existing saved-screen and strategy payload compatibility while migration is in progress. In particular, do not mechanically rename versioned wire keys such as `VeraBase` or `VeraLabV1`.
- Keep knowledge-base and non-core provider integrations optional and separate from core SigmaRail data.
- Do not carry source-specific destructive database maintenance into this application.
- Keep the existing local Vera services untouched during migration. Hosting changes require a completed endpoint and explicit cutover plan.
- Never commit credentials, production data, or generated local user data.

## Validation

Follow `pyproject.toml` and `frontend/package.json` for checks. Prefer synthetic fixtures. Integration checks must use a dedicated test database; production ClickHouse remains read-only.
