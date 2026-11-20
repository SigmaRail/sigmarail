"""Shared account-stat helpers for rule/book contexts (``acct.*`` fields).

Kept in one place so PCM book exprs and risk rule ``when`` clauses read the
same vocabulary — a field here must mean the same thing in both slots.
"""

from __future__ import annotations

from typing import Any


def trailing_loss_streak(algorithm: Any) -> int:
    """Consecutive losing closed trades, counting back from the most recent.

    Backed by LEAN ``algorithm.TradeBuilder.ClosedTrades`` — realized P&L per
    closed position in close order. A winning close resets the streak. Any
    accessor failure (no TradeBuilder, paper-vs-live shape drift) degrades to
    ``0`` — the breaker stays off rather than guessing at losses.
    """
    try:
        trades = getattr(getattr(algorithm, "TradeBuilder", None), "ClosedTrades", None)
        if not trades:
            return 0
        streak = 0
        for trade in reversed(list(trades)):
            if float(getattr(trade, "ProfitLoss", 0.0) or 0.0) < 0:
                streak += 1
            else:
                break
        return streak
    except Exception:
        return 0
