import pytest
from django.test import Client


@pytest.mark.django_db
def test_framework_templates_api() -> None:
    client = Client()

    # 1. List initial templates — no legacy system framework JSON templates
    res = client.get("/api/backtests/framework-templates")
    assert res.status_code == 200
    data = res.json()
    system_ids = [t["id"] for t in data["templates"] if t.get("is_system")]
    assert system_ids == []

    # 2. Missing system template id → 404
    res_sys = client.get("/api/backtests/framework-templates/multi_alpha_ensemble")
    assert res_sys.status_code == 404

    # 3. Create a custom framework template
    custom_payload = {
        "name": "Custom Quad-Alpha Defensive",
        "description": "4 Alpha layers with 5% trailing stop and 20% sector cap",
        "category": "Multi-Strategy",
        "framework": {
            "alpha": {
                "use_screener": True,
                "screener_max_positions": 15,
                "screener_stop_loss_pct": 0.06,
                "use_rsi": True,
                "rsi_period": 10,
                "rsi_resolution": "Daily",
                "use_macd": True,
                "use_ema": True,
            },
            "pcm": {
                "engine": "ConfidenceWeightedPortfolioConstructionModel",
                "max_weight": 0.1,
                "rebalance": "Daily",
            },
            "risk": {
                "use_trailing_stop": True,
                "trailing_stop_pct": 0.05,
                "use_sector_cap": True,
                "max_sector_exposure": 0.20,
                "use_hard_stop": False,
                "stop_loss_pct": 0.08,
                "use_take_profit": True,
                "take_profit_pct": 0.25,
            },
            "execution": {
                "engine": "VolumeWeightedAveragePriceExecutionModel",
            },
        },
    }

    res_create = client.post(
        "/api/backtests/framework-templates",
        data=custom_payload,
        content_type="application/json",
    )
    assert res_create.status_code == 201
    created_id = res_create.json()["id"]
    assert res_create.json()["name"] == "Custom Quad-Alpha Defensive"
    assert res_create.json()["is_system"] is False

    # 4. Conflict check on duplicate name
    res_dup = client.post(
        "/api/backtests/framework-templates",
        data=custom_payload,
        content_type="application/json",
    )
    assert res_dup.status_code == 409

    # 5. List templates and verify custom template is present
    res_list = client.get("/api/backtests/framework-templates")
    assert res_list.status_code == 200
    custom_names = [t["name"] for t in res_list.json()["templates"]]
    assert "Custom Quad-Alpha Defensive" in custom_names

    # 6. Update the custom template
    res_update = client.put(
        f"/api/backtests/framework-templates/{created_id}",
        data={"description": "Updated description with tighter stops"},
        content_type="application/json",
    )
    assert res_update.status_code == 200
    assert res_update.json()["description"] == "Updated description with tighter stops"

    # 7. Delete the custom template
    res_del = client.delete(f"/api/backtests/framework-templates/{created_id}")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # 8. Verify deletion
    res_after = client.get(f"/api/backtests/framework-templates/{created_id}")
    assert res_after.status_code == 404
