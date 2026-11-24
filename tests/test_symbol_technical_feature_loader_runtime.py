from datetime import date

from sigmarail_lab.runtime.sigmarail_symbol_technical_features import (
    VeraSymbolTechnicalFeaturesDaily,
)


class _FakeClickHouse:
    def __init__(self):
        self.queries = []

    def query_json_each_row(self, sql, max_rows):
        self.queries.append((sql, max_rows))
        return []


def test_technical_feature_range_is_loaded_in_bounded_date_chunks():
    loader = VeraSymbolTechnicalFeaturesDaily()
    client = _FakeClickHouse()
    loader.set_http_client(client)
    loader.set_tickers(["AAA", "BBB"])

    loader.load_range(date(2025, 1, 1), date(2025, 3, 5))

    assert len(client.queries) == 3
    assert [query[1] for query in client.queries] == [100_000] * 3
    assert "toDate('2025-01-01')" in client.queries[0][0]
    assert "toDate('2025-01-30')" in client.queries[0][0]
    assert "toDate('2025-01-31')" in client.queries[1][0]
    assert "toDate('2025-03-02')" in client.queries[2][0]
    assert "toDate('2025-03-05')" in client.queries[2][0]


def test_technical_feature_chunk_results_are_combined_for_lookup():
    class _Rows(_FakeClickHouse):
        def query_json_each_row(self, sql, max_rows):
            super().query_json_each_row(sql, max_rows)
            if "2025-01-01" in sql:
                return [{"ticker": "AAA", "trade_date": "2025-01-02", "value": 1}]
            return [{"ticker": "AAA", "trade_date": "2025-02-01", "value": 2}]

    loader = VeraSymbolTechnicalFeaturesDaily()
    loader.set_http_client(_Rows())
    loader.set_tickers(["AAA"])
    loader.load_range(date(2025, 1, 1), date(2025, 2, 5))

    assert loader.get_features("AAA", "2025-01-02")["value"] == 1
    assert loader.get_features("AAA", "2025-02-01")["value"] == 2
