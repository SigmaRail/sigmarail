"""Schema checks and validation of provider-free synthetic source inputs."""

import csv
from collections import Counter
import json
import re
import tempfile
from pathlib import Path

from sigmarail.config import get_schema_files

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "src/sigmarail/sql/schema"
LINEAGE = json.loads((ROOT / "spec/lineage-manifest.json").read_text(encoding="utf-8"))


def test_schema_views_are_dropped_before_recreation():
    """Every regular schema view is refreshed by its SQL file."""
    missing_drops = []
    for schema_file in get_schema_files():
        sql = schema_file.read_text(encoding="utf-8")
        for match in re.finditer(r"(?im)^\s*CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS\s+([A-Za-z_]\w*)", sql):
            view_name = match.group(1)
            immediately_dropped = re.search(
                rf"(?is)\bDROP\s+VIEW\s+IF\s+EXISTS\s+{re.escape(view_name)}\s*;\s*$",
                sql[:match.start()],
            )
            if not immediately_dropped:
                missing_drops.append(f"{schema_file.name}: {view_name}")
    assert not missing_drops, "Views missing preceding DROP VIEW IF EXISTS:\n" + "\n".join(missing_drops)


def test_no_vera_database_prefixes_in_schema_sql():
    violations = []
    for schema_file in get_schema_files():
        for line_no, line in enumerate(schema_file.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bvera\.[A-Za-z_]", line, flags=re.IGNORECASE):
                violations.append(f"{schema_file.name}:{line_no}: {line.strip()}")
    assert not violations, "Hard-coded Vera database prefixes:\n" + "\n".join(violations)


def test_synthetic_inputs_match_source_schemas_and_manifest():
    """Generated inputs conform to the source schema without using provider rows."""
    from tests.support.synthetic_sharadar import TABLES, generate_synthetic_dataset

    raw_tables = {
        table["name"]: {column["name"] for column in table["columns"]}
        for table in LINEAGE["tables"]
        if table["kind"] == "sharadar_source"
    }
    with tempfile.TemporaryDirectory(prefix="sigmarail-synthetic-schema-") as temp:
        fixture_dir = Path(temp)
        manifest = generate_synthetic_dataset(fixture_dir)
        fixtures = sorted(fixture_dir.glob("SHARADAR_*.csv"))
        assert len(fixtures) == len(raw_tables) - 2  # metrics and sf2 are empty in the source sample
        assert manifest["provider_data"] is False
        assert manifest["stock_count"] == 35
        assert manifest["fund_count"] == 16
        assert manifest["symbol_count"] == 51
        assert manifest["price_session_count"] == 1005
        assert manifest["first_price_date"] == "2021-01-04"
        assert manifest["end_date"] == "2024-12-31"
        assert manifest["tables"]["sep"] == 35 * 1005
        assert manifest["tables"]["daily"] == 35 * 1005
        assert manifest["tables"]["sfp"] == 16 * 1005
        assert manifest["tables"]["sf1"] == 35 * 72
        assert manifest["tables"].keys() == raw_tables.keys()
        assert manifest["tables"]["metrics"] == 0
        assert manifest["tables"]["sf2"] == 0
        for path in fixtures:
            table = path.name.split("_")[1].lower()
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.reader(stream)
                header = next(reader)
                rows = sum(1 for _ in reader)
            assert len(header) == len(set(header)), f"Duplicate CSV columns in {path.name}"
            assert set(header) <= raw_tables[table], f"Unknown columns for {table}: {set(header) - raw_tables[table]}"
            assert rows == manifest["tables"][table], f"Manifest mismatch for {table}"
            if table not in {"actions", "sp500"}:
                assert set(header) == set(TABLES[table])
        assert not (fixture_dir / "SHARAD_METRICS_SYNTHETIC.csv").exists()
        assert not (fixture_dir / "SHARAD_SF2_SYNTHETIC.csv").exists()

        with (fixture_dir / "SHARADAR_TICKERS_SYNTHETIC.csv").open(encoding="utf-8", newline="") as stream:
            ticker_rows = list(csv.DictReader(stream))
        assert Counter(row["table"] for row in ticker_rows) == {"stocks": 35, "funds": 16}
        assert Counter(row["category"] for row in ticker_rows) == {
            "Domestic Common Stock": 27,
            "Domestic Common Stock Primary Class": 8,
            "ETF": 14,
            "IDX": 2,
        }

        with (fixture_dir / "SHARADAR_SF1_SYNTHETIC.csv").open(encoding="utf-8", newline="") as stream:
            sf1_dimensions = Counter(row["dimension"] for row in csv.DictReader(stream))
        assert sf1_dimensions == {
            "ARQ": 560, "MRQ": 560, "MRT": 560, "ART": 560, "ARY": 140, "MRY": 140,
        }

        with (fixture_dir / "SHARADAR_SF3A_SYNTHETIC.csv").open(encoding="utf-8", newline="") as stream:
            ownership_rows = list(csv.DictReader(stream))
        assert len(ownership_rows) == manifest["tables"]["sf3a"]
        assert len({row["date"] for row in ownership_rows}) == 16
