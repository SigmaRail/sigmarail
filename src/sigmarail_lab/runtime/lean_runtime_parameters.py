"""
Parameter reading for QuantConnect LEAN algorithms (GetParameter + lean.json Config).

LEAN runtime only — imports QuantConnect.Configuration.
"""

from QuantConnect.Configuration import Config


def _raw_param(algorithm, key):
    """Get raw parameter value from algorithm or config."""
    value = algorithm.GetParameter(key)
    if value is None or value == "":
        getter = getattr(Config, "Get", None)
        value = getter(key) if getter is not None else None
    return value


def get_param(*keys, algorithm, default=None):
    """
    Get parameter value trying multiple keys in order.

    Tries algorithm parameters first, then lean.json config.
    """
    for key in keys:
        value = _raw_param(algorithm, key)
        if value is not None and value != "":
            return value
    return default


def get_str(algorithm, key, default):
    """Get string parameter (single key)."""
    value = _raw_param(algorithm, key)
    return default if value is None or value == "" else str(value)


def get_int(algorithm, key, default):
    """Get integer parameter (single key)."""
    try:
        value = _raw_param(algorithm, key)
        return default if value is None or value == "" else int(value)
    except Exception:
        return default


def get_float(algorithm, key, default):
    """Get float parameter (single key)."""
    try:
        value = _raw_param(algorithm, key)
        return default if value is None or value == "" else float(value)
    except Exception:
        return default


def get_bool(algorithm, key, default):
    """Get boolean parameter (single key)."""
    value = _raw_param(algorithm, key)
    if value is None or value == "":
        return default
    return str(value).lower() in ("true", "1", "yes")
