# SigmaRail expression contract

The canonical expression language and use-site rules are documented in
[SigmaRail Spec](https://github.com/SigmaRail/sigmarail-spec/blob/main/docs/EXPRESSIONS.md).
Read that guide before changing expression nodes, validation, or runtime behavior.

This directory contains the installable runtime distribution used by the SigmaRail implementation.
SigmaRail compiles supported query expressions for ClickHouse; SigmaRail Lean evaluates the supported
strategy expressions. A node in the shared schema is not automatically supported at every use site.
Keep the package runtime aligned with the Spec contract and update the affected consumers together.
