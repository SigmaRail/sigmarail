"""Command-line interface for producing provider-free SigmaRail test data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthetic_sharadar import generate_synthetic_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = generate_synthetic_dataset(args.output_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
