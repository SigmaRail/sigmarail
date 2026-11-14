from __future__ import annotations


def test_catalog_domains_use_generated_sigmarail_registry() -> None:
    from sigmarail_studio_mcp.domains import catalog

    datasets = catalog.list_tables()
    columns = catalog.list_columns()
    relationships = catalog.list_join_paths()
    entity = catalog.describe_entity("screener_price_tech_daily")

    assert datasets["spine"] == "screener_price_tech_daily"
    assert any(row["table"] == "screener_fundamentals_daily" for row in datasets["tables"])
    assert columns["columns"]["close"]["table"] == "screener_price_tech_daily"
    assert relationships["relationships"]
    assert entity["meta"]["table"] == "screener_price_tech_daily"


def test_strategy_catalog_combines_local_screener_templates_and_spec_presets() -> None:
    from sigmarail_studio_mcp.domains.strategy import get_template, list_templates

    catalog = list_templates()
    ids = {row["id"] for row in catalog["templates"]}
    assert "minervini_trend_template" in ids
    assert "minervini_sepa" in ids
    assert get_template("minervini_trend_template")["kind"] == "screener"
    assert get_template("minervini_sepa")["kind"] == "strategy"


def test_screen_stocks_uses_sigma_core_preview_adapter(monkeypatch) -> None:
    from sigmarail_studio_mcp.domains import screen

    seen = {}

    def fake_preview(fn, **kwargs):
        seen.update(kwargs)
        return fn(None, **kwargs)

    monkeypatch.setattr(screen, "call", fake_preview)
    monkeypatch.setattr(
        "screens.adapter.preview_screen",
        lambda client, **kwargs: {"date": kwargs["as_of"], "rows": [], "preset": kwargs["preset"]},
    )
    result = screen.stocks("2026-11-12", preset="high_rs", limit=12)

    assert result == {"date": "2026-11-12", "rows": [], "preset": "high_rs"}
    assert seen == {"as_of": "2026-11-12", "preset": "high_rs", "limit": 12}
