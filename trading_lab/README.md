# SigmaRail Trading Lab runtime template

`trading_lab/` contains the LEAN project entry point, vendored SigmaRail Spec runtime, project configuration template, and runner scripts. The maintained five-slot `QCAlgorithm` implementation is packaged under `src/sigmarail_lab/lean/algorithm.py`.

SigmaRail Studio stages a per-run LEAN project from these sources, adds the installed SigmaRail Lab package, and injects the selected strategy ID and run settings. Generated folders are run snapshots, not source repositories. The C# LEAN engine and its Docker image remain separate.
