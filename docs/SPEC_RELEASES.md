# SigmaRail Spec source and releases

`packages/sigmarail-spec/` is the only source of truth for the SigmaRail Spec package. Its
version is independent of the SigmaRail application release cadence, but its source is maintained
in this repository. Do not develop Spec in a second checkout or edit generated consumer copies.

## In-repository consumers

- SigmaRail Core, Studio, backend, and worker use the package source from this repository.
- `trading_lab/sigmarail_spec/` is a generated LEAN runtime subset. Regenerate it with
  `packages/sigmarail-spec/tools/sync_lean_vendor.py`; verify it with the same command without
  `--write`.
- CI checks generated Spec artifacts and the LEAN runtime subset against the canonical package.

The package build and runtime contract tests run from `packages/sigmarail-spec/`. A change to
Spec behavior must update its source, tests, and generated documents in the same change. A change
to LEAN's vendored runtime must be produced by the sync tool, never hand-edited.

## PyPI release

The repository's `publish-spec` workflow is triggered only by a tag named
`sigmarail-spec-vX.Y.Z`. Before creating the tag:

1. Set `project.version` in `packages/sigmarail-spec/pyproject.toml` to the intended version.
2. Merge the source, tests, generated documents, and synchronized LEAN vendor copy to `main`.
3. Confirm required CI and the LEAN smoke job passed for that commit.
4. Create the matching tag on that commit. The workflow validates the tag/version, builds the
   package, and publishes through PyPI trusted publishing.
5. Verify the published version and artifact metadata on PyPI before changing downstream pins.

Do not reuse a published version. Follow semantic versioning for compatibility: breaking changes
to the JSON contract or compiler input require a major version; compatible additions use a minor
version; fixes to existing behavior use a patch version.

## Downstream projects

Projects outside this repository should depend on an exact PyPI version, such as
`sigmarail-spec==X.Y.Z`, and update only after the release is visible on PyPI. Each consumer should
record the supported Spec version and validate its integration against that version. LEAN's
execution image may continue using the generated subset when package installation is unsuitable;
the subset's manifest hashes and CI sync check tie it to the canonical source.

The standalone `FinanceProjects/sigmarail-spec` checkout is not part of this release path. Changes
belong in this repository's `packages/sigmarail-spec/` directory.
