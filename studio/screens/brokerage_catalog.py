"""Brokerage options supported by the installed LEAN CLI.

Only brokerages with a well-defined credential contract are exposed in Studio.
The CLI remains the execution authority; this catalog describes the fields Studio
stores securely and the non-secret options required to select each adapter.
"""

from __future__ import annotations

from typing import Any


def _field(
    key: str, label: str, *, secret: bool = True, required: bool = True, choices: list[str] | None = None
) -> dict[str, Any]:
    result = {"key": key, "label": label, "secret": secret, "required": required}
    if choices:
        result["choices"] = choices
    return result


BROKERAGES: dict[str, dict[str, Any]] = {
    "alpaca": {
        "label": "Alpaca", "cli_name": "Alpaca", "default_data_provider": "alpaca",
        "environments": {"paper": "paper", "live": "live"},
        "environment_option": "--alpaca-environment", "environment_config": "alpaca-environment",
        "credentials": [_field("alpaca-api-key", "API key"), _field("alpaca-api-secret", "API secret")],
    },
    "interactive_brokers": {
        "label": "Interactive Brokers", "cli_name": "Interactive Brokers", "default_data_provider": "interactive_brokers",
        "environments": {"paper": "paper", "live": "live"}, "environment_config": "ib-trading-mode",
        "credentials": [_field("ib-user-name", "Username"), _field("ib-password", "Password"), _field("ib-account", "Account ID")],
    },
    "tradier": {
        "label": "Tradier", "cli_name": "Tradier", "default_data_provider": "tradier",
        "environments": {"paper": "paper", "live": "live"},
        "environment_option": "--tradier-environment", "environment_config": "tradier-environment",
        "credentials": [_field("tradier-account-id", "Account ID"), _field("tradier-access-token", "Access token")],
    },
    "oanda": {
        "label": "OANDA", "cli_name": "Oanda", "default_data_provider": "oanda",
        "environments": {"paper": "Practice", "live": "Trade"},
        "environment_option": "--oanda-environment", "environment_config": "oanda-environment",
        "credentials": [_field("oanda-account-id", "Account ID"), _field("oanda-access-token", "API token")],
    },
    "tradestation": {
        "label": "TradeStation", "cli_name": "TradeStation", "default_data_provider": "tradestation",
        "environments": {"paper": "paper", "live": "live"},
        "environment_option": "--trade-station-environment", "environment_config": "trade-station-environment",
        "credentials": [_field("trade-station-account-id", "Account ID"), _field("trade-station-client-id", "Client ID"), _field("trade-station-client-secret", "Client secret"), _field("trade-station-refresh-token", "Refresh token")],
    },
    "binance": {
        "label": "Binance", "cli_name": "Binance", "default_data_provider": "binance",
        "environments": {"paper": "paper", "live": "live"},
        "environment_option": "--binance-use-testnet", "environment_config": "binance-use-testnet",
        "credentials": [_field("binance-exchange-name", "Exchange", secret=False, choices=["Binance", "BinanceUS", "Binance-USDM-Futures", "Binance-COIN-Futures"]), _field("binance-api-key", "API key"), _field("binance-api-secret", "API secret")],
    },
    "bybit": {
        "label": "Bybit", "cli_name": "Bybit", "default_data_provider": "bybit",
        "environments": {"paper": "paper", "live": "live"},
        "environment_option": "--bybit-use-testnet", "environment_config": "bybit-use-testnet",
        "credentials": [_field("bybit-api-key", "API key"), _field("bybit-api-secret", "API secret"), _field("bybit-vip-level", "VIP level", secret=False, choices=["VIP0", "VIP1", "VIP2", "VIP3", "VIP4", "VIP5", "SupremeVIP", "Pro1", "Pro2", "Pro3", "Pro4", "Pro5"])],
    },
    "kraken": {
        "label": "Kraken", "cli_name": "Kraken", "default_data_provider": "kraken",
        "environments": {"live": "live"},
        "credentials": [_field("kraken-api-key", "API key"), _field("kraken-api-secret", "API secret"), _field("kraken-verification-tier", "Verification tier", secret=False, choices=["Starter", "Intermediate", "Pro"])],
    },
    "bitfinex": {
        "label": "Bitfinex", "cli_name": "Bitfinex", "default_data_provider": "bitfinex",
        "environments": {"live": "live"},
        "credentials": [_field("bitfinex-api-key", "API key"), _field("bitfinex-api-secret", "API secret")],
    },
    "coinbase": {
        "label": "Coinbase Advanced Trade", "cli_name": "Coinbase Advanced Trade", "default_data_provider": "coinbase",
        "environments": {"live": "live"},
        "credentials": [_field("coinbase-api-name", "API name"), _field("coinbase-api-private-key", "Private key")],
    },
    "charles_schwab": {
        "label": "Charles Schwab", "cli_name": "CharlesSchwab", "default_data_provider": "charles_schwab",
        "environments": {"live": "live"},
        "credentials": [_field("charles-schwab-user-name", "Login ID"), _field("charles-schwab-account-number", "Account number"), _field("charles-schwab-app-key", "App key"), _field("charles-schwab-secret", "App secret"), _field("charles-schwab-authorization-code-from-url", "Authorization code"), _field("charles-schwab-refresh-token", "Refresh token")],
    },
    "zerodha": {
        "label": "Zerodha", "cli_name": "Zerodha", "default_data_provider": "zerodha",
        "environments": {"live": "live"},
        "credentials": [_field("zerodha-api-key", "API key"), _field("zerodha-access-token", "Access token"), _field("zerodha-history-subscription", "History subscription", secret=False, choices=["true", "false"])],
    },
    "samco": {
        "label": "Samco", "cli_name": "Samco", "default_data_provider": "samco",
        "environments": {"live": "live"},
        "credentials": [_field("samco-client-id", "Client ID"), _field("samco-client-password", "Client password"), _field("samco-year-of-birth", "Year of birth")],
    },
    "dydx": {
        "label": "dYdX", "cli_name": "dYdX", "default_data_provider": "dydx",
        "environments": {"paper": "paper", "live": "live"}, "environment_option": "--dydx-environment", "environment_config": "dydx-environment",
        "credentials": [_field("dydx-private-key-hex", "Private key"), _field("dydx-address", "Wallet address"), _field("dydx-subaccount-number", "Subaccount number", secret=False)],
    },
    "eze": {
        "label": "Eze", "cli_name": "Eze", "default_data_provider": "eze",
        "environments": {"live": "live"},
        "credentials": [_field("eze-user-name", "Username"), _field("eze-password", "Password"), _field("eze-trading-account", "Trading account"), _field("eze-domain", "Domain"), _field("eze-locale", "Locale")],
    },
}


# LEAN's local CLI requires a live data provider separately from the brokerage.
# Matching-provider credentials are shared in the account's single vault entry.
DATA_PROVIDERS: dict[str, dict[str, Any]] = {
    key: {
        "label": value["label"],
        "cli_name": value["cli_name"],
        "credentials": value["credentials"],
        **({"environments": value["environments"]} if value.get("environments") else {}),
        **({"environment_option": value["environment_option"]} if value.get("environment_option") else {}),
        **({"environment_config": value["environment_config"]} if value.get("environment_config") else {}),
    }
    for key, value in BROKERAGES.items()
}
DATA_PROVIDERS.update({
    "polygon": {"label": "Polygon", "cli_name": "Polygon", "credentials": [_field("polygon-api-key", "Polygon API key")]},
    "iqfeed": {"label": "IQFeed", "cli_name": "IQFeed", "credentials": [_field("iqfeed-iqconnect", "IQConnect executable path", secret=False), _field("iqfeed-username", "IQFeed username"), _field("iqfeed-password", "IQFeed password"), _field("iqfeed-version", "IQFeed product version")]},
    "coinapi": {"label": "CoinAPI", "cli_name": "CoinApi", "credentials": [_field("coinapi-api-key", "CoinAPI key"), _field("coinapi-product", "CoinAPI plan", secret=False, choices=["Free", "Startup", "Streamer", "Professional", "Enterprise"])]},
    "databento": {"label": "Databento", "cli_name": "Databento", "credentials": [_field("databento-api-key", "Databento API key")]},
    "eze": {"label": "Eze", "cli_name": "Eze", "credentials": BROKERAGES["eze"]["credentials"]},
    "dydx": {"label": "dYdX", "cli_name": "dYdX", "credentials": BROKERAGES["dydx"]["credentials"]},
    "thetadata": {"label": "ThetaData", "cli_name": "ThetaData", "credentials": [_field("thetadata-subscription-plan", "ThetaData subscription plan", secret=False, choices=["Free", "Value", "Standard", "Pro"])]},
    "custom_data_only": {"label": "Custom data only", "cli_name": "Custom data only", "credentials": []},
})


def public_catalog() -> list[dict[str, Any]]:
    """Return UI-safe adapter metadata; never includes actual credential values."""
    return [{"id": key, **value} for key, value in BROKERAGES.items()]


def public_data_provider_catalog() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in DATA_PROVIDERS.items()]


def get_brokerage(provider: str) -> dict[str, Any]:
    try:
        return BROKERAGES[provider]
    except KeyError as exc:
        raise ValueError("Unsupported LEAN brokerage selected") from exc


def get_data_provider(provider: str) -> dict[str, Any]:
    try:
        return DATA_PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError("Unsupported LEAN live data provider selected") from exc


def validate_credentials(provider: str, credentials: dict[str, Any], data_provider: str | None = None) -> dict[str, str]:
    fields = list(get_brokerage(provider)["credentials"])
    if data_provider:
        fields.extend(get_data_provider(data_provider)["credentials"])
    allowed = {field["key"]: field for field in fields}
    if set(credentials) - set(allowed):
        raise ValueError("Credential payload contains fields unsupported by the selected brokerage")
    cleaned: dict[str, str] = {}
    for key, field in allowed.items():
        value = credentials.get(key)
        if value is None or value == "":
            if field["required"]:
                raise ValueError(f"{field['label']} is required for this brokerage")
            continue
        if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
            raise ValueError(f"{field['label']} must be a text value no longer than 4096 characters")
        if field.get("choices") and value not in field["choices"]:
            raise ValueError(f"{field['label']} must be one of the listed options")
        cleaned[key] = value
    return cleaned
