# Embedded Spec package distribution

This directory contains the installable contract/runtime package currently used by the SigmaRail
implementation. The normative product description and architecture live in the separate
[SigmaRail Spec project](https://github.com/SigmaRail/sigmarail-spec); read its
[architecture guide](https://github.com/SigmaRail/sigmarail-spec/blob/main/docs/ARCHITECTURE.md)
before changing contract meaning.

The package is versioned and built independently, but its source currently resides in the SigmaRail
implementation checkout. Keep it aligned with the separate Spec project and call out any mismatch as
a synchronization gap. Do not let this package become a second place to define product semantics.

## Build and check

From the SigmaRail implementation root, with Python 3.10+:

```bash
python3 -m pip install -e 'packages/sigmarail-spec[build,test]'
python3 packages/sigmarail-spec/tools/build.py --lean-source ../Lean
python3 packages/sigmarail-spec/tools/build.py --lean-source ../Lean --check
python3 -m pytest packages/sigmarail-spec/tests -q
```

The build verifies `spec/sources.lock.json`, exports normalized JSON to
`src/sigmarail_spec/data/`, and does not connect to ClickHouse or load data. Review source changes
and generated output before refreshing pins:

```bash
python3 packages/sigmarail-spec/tools/build.py --lean-source ../Lean --write-lock
python3 packages/sigmarail-spec/tools/build.py --lean-source ../Lean
```

## LEAN runtime copy

SigmaRail Lean may use a generated copy of the small runtime needed inside its execution container.
Check or refresh the copy only after reviewing the runtime change and destination:

```bash
python3 packages/sigmarail-spec/tools/sync_lean_vendor.py --destination trading_lab/sigmarail_spec
python3 packages/sigmarail-spec/tools/sync_lean_vendor.py --destination trading_lab/sigmarail_spec --write
```

The check command verifies hashes without writing. The write command generates the expression,
evaluator, strategy, and universe-query modules with a manifest. Do not edit generated vendor files
by hand.

## Runtime retrieval

The package exposes versioned JSON through `sigmarail_spec.list_documents()`, `get_document()`, and
`get_document_text()`. Studio and MCP are SigmaRail application components; they transport and
present these contracts but do not redefine them.

```python
from sigmarail_spec import get_document, get_document_text, list_documents

index = get_document("sigmarail-spec://v1/index")
alpha_slot = get_document("sigmarail-spec://v1/strategy/slots/alpha")
schema_text = get_document_text("sigmarail-spec://v1/data/schema")
```

The package includes expression, query, strategy-authoring, execution, and runtime-capability
artifacts. Consult the Spec project's contract index and architecture guide for meaning, authority,
and agent retrieval guidance.
