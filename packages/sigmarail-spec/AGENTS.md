# Embedded SigmaRail Spec distribution

This directory contains the currently installable Spec package distribution within the SigmaRail
implementation repository. The product architecture and normative contract documentation live in
the separate [SigmaRail Spec project](https://github.com/SigmaRail/sigmarail-spec). Read its
[architecture guide](https://github.com/SigmaRail/sigmarail-spec/blob/main/docs/ARCHITECTURE.md)
before changing contract meaning.

Until packaging is consolidated, treat this tree as an implementation distribution that must remain
consistent with SigmaRail Spec, not as a second architecture authority. If the two contract sources
differ, report and resolve the divergence explicitly. Do not silently choose one copy or hand-edit
generated artifacts.

## Source ownership and generation

- SigmaRail SQL owns the executable data schema, transforms, and lineage facts.
- SigmaRail Lean owns executable model and runtime behavior.
- Spec documents define the shared ASTs, strategy and slot contracts, and supported capability shape.
- Use `spec/sources.lock.json` and the build tool to inspect source inputs and generated output. Review
  every input change and generated diff before refreshing the lock.
- Keep the expression runtime Pydantic plus standard-library-only where it is vendored into LEAN.
- Generate LEAN vendor copies with `tools/sync_lean_vendor.py`; never edit generated copies by hand.

## Build and validation

From the SigmaRail implementation repository root:

```bash
python3 packages/sigmarail-spec/tools/build.py --lean-source ../Lean
python3 packages/sigmarail-spec/tools/build.py --lean-source ../Lean --check
python3 -m pytest packages/sigmarail-spec/tests/ -q
python3 packages/sigmarail-spec/tools/sync_lean_vendor.py --destination trading_lab/sigmarail_spec
```

`--check` is read-only. The build must not connect to ClickHouse, load provider data, or populate a
database.
