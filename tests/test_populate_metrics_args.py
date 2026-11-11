"""CLI metric selection helpers for the core transform package."""

from sigmarail.populate import _split_metrics_args


def test_split_metrics_args_comma_separated():
    assert _split_metrics_args(["daily-metrics,weekly-metrics,arq"]) == [
        "daily-metrics", "weekly-metrics", "arq"
    ]


def test_split_metrics_args_space_separated():
    assert _split_metrics_args(["daily-metrics", "weekly-metrics"]) == [
        "daily-metrics", "weekly-metrics"
    ]


def test_split_metrics_args_empty_tokens_are_ignored():
    assert _split_metrics_args(["daily-metrics,, arq "]) == ["daily-metrics", "arq"]
