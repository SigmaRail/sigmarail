"""Ported Vera populate schedule contracts for SigmaRail's schema-only pipeline."""

from unittest.mock import MagicMock, patch

from sigmarail.populate import DataPopulator, _metric_sql_sort_key
from sigmarail.transform_sql import discover_transform_specs


def test_numeric_transform_filenames_sort_by_number_not_lexically(tmp_path):
    early = tmp_path / "98-early.sql"
    late = tmp_path / "100-late.sql"
    assert _metric_sql_sort_key(early) < _metric_sql_sort_key(late)


def test_dependency_transforms_precede_their_consumers():
    specs = discover_transform_specs()
    by_target = {spec.target: spec for spec in specs if spec.target}
    for spec in specs:
        for source in spec.sources:
            if source in by_target:
                assert by_target[source].order < spec.order, (
                    source, by_target[source].order, spec.target, spec.order
                )


def test_all_schedule_excludes_explicitly_held_vcp_transform():
    pop = DataPopulator.__new__(DataPopulator)
    pop.client = MagicMock()
    with patch("sigmarail.populate.transform_catalog", return_value=[]):
        specs = pop._get_transform_specs(["all"])
    assert all(spec.target != "screener_vcp_pivot_daily" for spec in specs)


def test_explicit_vcp_request_remains_held():
    pop = DataPopulator.__new__(DataPopulator)
    pop.client = MagicMock()
    with patch("sigmarail.populate.transform_catalog", return_value=[]):
        specs = pop._get_transform_specs(["screener_vcp_pivot_daily"])
    assert not any(spec.target == "screener_vcp_pivot_daily" for spec in specs)
