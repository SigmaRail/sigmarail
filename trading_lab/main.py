"""LEAN project entry point for SigmaRail's five-slot strategy algorithm."""

from pathlib import Path
import sys

# LEAN may launch Python with its engine directory as the current working
# directory. The generated project is mounted separately at /LeanCLI, so add
# the project root explicitly before importing its bundled SigmaRail library.
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sigmarail_lab.lean.algorithm import ClickHouseUniverseAlgorithm as _SigmaRailAlgorithm


class ClickHouseUniverseAlgorithm(_SigmaRailAlgorithm):
    """LEAN-discoverable entry point delegating behavior to SigmaRail's library."""

    pass

__all__ = ["ClickHouseUniverseAlgorithm"]
