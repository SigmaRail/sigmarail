"""
Tactical Swing Trading Alpha Models for QuantConnect Framework.

Bridges Screener Universe Selection (scouting radar) with precise entry triggers:
1. SwingBreakoutAlphaModel: Detects tight consolidation / volatility contraction and triggers
   on pivot high breakout with volume confirmation.
2. SwingPullbackAlphaModel: Detects orderly pullbacks to rising 10/20 EMA in strong leaders (Pocket Pivot).

Emits structured Insights carrying tactical trade parameters (EstimatedEntry, StopLossPrice, TargetPrice).
"""

from __future__ import annotations

from datetime import timedelta
from collections import deque

try:
    from AlgorithmImports import *  # noqa: F401,F403
    from QuantConnect.Algorithm.Framework.Alphas import AlphaModel, Insight, InsightDirection, InsightType
except ImportError:
    class AlphaModel:
        pass

    class InsightDirection:
        Up = 1
        Down = 2
        Flat = 0

    class InsightType:
        Price = 0

    class Insight:
        @classmethod
        def Price(cls, symbol, period, direction, magnitude=None, confidence=None, sourceModel=None, weight=None):
            class _I:
                pass
            i = _I()
            i.Symbol = symbol
            i.Period = period
            i.Direction = direction
            i.Magnitude = magnitude
            i.Confidence = confidence
            i.SourceModel = sourceModel
            i.Weight = weight
            i.Type = InsightType.Price
            return i


def _security_price(algorithm, symbol) -> float:
    sec = getattr(algorithm, "Securities", None)
    if sec is None or symbol not in sec:
        return 0.0
    return float(getattr(sec[symbol], "Price", 0.0) or 0.0)


def _security_volume(algorithm, symbol) -> float:
    sec = getattr(algorithm, "Securities", None)
    if sec is None or symbol not in sec:
        return 0.0
    return float(getattr(sec[symbol], "Volume", 0.0) or 0.0)


class SymbolRollingData:
    """Tracks rolling high, low, close, volume, and ATR for swing setup detection."""

    def __init__(self, symbol, lookback=10):
        self.symbol = symbol
        self.lookback = lookback
        self.highs = deque(maxlen=lookback)
        self.lows = deque(maxlen=lookback)
        self.closes = deque(maxlen=lookback)
        self.volumes = deque(maxlen=lookback)
        self.tr_list = deque(maxlen=lookback)
        self.prev_close = None

    def update(self, high: float, low: float, close: float, volume: float):
        if high <= 0 or low <= 0 or close <= 0:
            return
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.volumes.append(volume)

        if self.prev_close is not None and self.prev_close > 0:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
            self.tr_list.append(tr)
        self.prev_close = close

    @property
    def is_ready(self) -> bool:
        return len(self.closes) >= 3

    @property
    def pivot_high(self) -> float:
        """Highest high of the consolidation baseline (excluding current breakout bar)."""
        if len(self.highs) < 2:
            return float(self.highs[0]) if self.highs else 0.0
        past_highs = list(self.highs)[:-1]
        return max(past_highs) if past_highs else max(self.highs)

    @property
    def base_low(self) -> float:
        """Lowest low of the consolidation base."""
        if len(self.lows) < 2:
            return float(self.lows[0]) if self.lows else 0.0
        past_lows = list(self.lows)[:-1]
        return min(past_lows) if past_lows else min(self.lows)

    @property
    def avg_volume(self) -> float:
        """Average baseline volume during consolidation."""
        if len(self.volumes) < 2:
            return float(self.volumes[0]) if self.volumes else 0.0
        past_vols = list(self.volumes)[:-1]
        return sum(past_vols) / len(past_vols) if past_vols else sum(self.volumes) / len(self.volumes)

    @property
    def is_consolidating(self) -> bool:
        """Checks if recent range is tighter than earlier range (volatility contraction)."""
        if len(self.closes) < 4:
            return True
        recent_range = max(list(self.highs)[-3:]) - min(list(self.lows)[-3:])
        past_range = max(self.highs) - min(self.lows)
        return recent_range <= max(0.01, past_range * 0.95)


class SwingBreakoutAlphaModel(AlphaModel):
    """
    Evaluates tactical breakout entries for stocks delivered by UniverseSelection.
    Waits for volatility contraction and fires when price breaches the pivot high with volume pace.
    """

    def __init__(
        self,
        consolidation_days: int = 5,
        volume_surge_multiplier: float = 1.25,
        insight_duration_days: int = 15,
        min_reward_risk_ratio: float = 2.5,
        default_stop_loss_pct: float = 0.06,
        leader_rs_threshold: float = 85.0,
        store: Any = None,
    ):
        self._consolidation_days = max(3, int(consolidation_days))
        self._volume_surge_multiplier = float(volume_surge_multiplier)
        self._insight_duration = timedelta(days=int(insight_duration_days))
        self._min_rr_ratio = float(min_reward_risk_ratio)
        self._default_stop_loss_pct = float(default_stop_loss_pct)
        self._leader_rs_threshold = float(leader_rs_threshold)
        self._store = store

        self._symbol_data: dict[Any, SymbolRollingData] = {}
        self._active_positions: set[str] = set()
        self._last_day = None
        self.Name = "SwingBreakoutAlphaModel"

    def bind_store(self, store: Any) -> None:
        self._store = store

    def OnSecuritiesChanged(self, algorithm, changes):
        for added in getattr(changes, "AddedSecurities", []):
            sym = added.Symbol
            if sym not in self._symbol_data:
                self._symbol_data[sym] = SymbolRollingData(sym, lookback=self._consolidation_days)

        for removed in getattr(changes, "RemovedSecurities", []):
            sym = removed.Symbol
            self._symbol_data.pop(sym, None)

    def Update(self, algorithm, data):
        insights = []
        today = algorithm.Time.date()
        is_new_day = self._last_day != today
        if is_new_day:
            self._last_day = today

        as_of = (today - timedelta(days=1)).isoformat()

        for symbol, sdata in list(self._symbol_data.items()):
            sec = algorithm.Securities.get(symbol)
            if not sec or not getattr(sec, "Price", 0):
                continue

            current_px = float(sec.Price)
            current_vol = float(getattr(sec, "Volume", 0) or 0)
            high_px = float(getattr(sec, "High", current_px) or current_px)
            low_px = float(getattr(sec, "Low", current_px) or current_px)

            # Update bar metrics
            if is_new_day:
                sdata.update(high_px, low_px, current_px, current_vol)

            if not sdata.is_ready:
                continue

            # Check if security is already invested in portfolio
            is_invested = False
            if hasattr(algorithm, "Portfolio"):
                try:
                    h = algorithm.Portfolio[symbol]
                    is_invested = bool(getattr(h, "Invested", False) is True)
                except Exception:
                    is_invested = False
            if is_invested:
                continue

            pivot = sdata.pivot_high
            base_low = sdata.base_low
            avg_vol = sdata.avg_volume

            # Trigger condition: Price breaks out above consolidation pivot high
            if pivot > 0 and current_px >= pivot:
                # Volume confirmation (current volume pace exceeds threshold vs avg volume)
                vol_confirmed = (current_vol >= (avg_vol * self._volume_surge_multiplier)) if avg_vol > 0 else True

                # Check that risk is defined and reasonable
                stop_price = max(base_low, current_px * (1.0 - self._default_stop_loss_pct))
                risk_per_share = current_px - stop_price
                risk_pct = risk_per_share / current_px if current_px > 0 else 0.05

                if 0.02 <= risk_pct <= 0.10 and vol_confirmed:
                    # Target price at +2.5R to +3R
                    target_price = current_px + (risk_per_share * self._min_rr_ratio)
                    magnitude = (target_price - current_px) / current_px

                    insight = Insight.Price(
                        symbol=symbol,
                        period=self._insight_duration,
                        direction=InsightDirection.Up,
                        magnitude=magnitude,
                        confidence=0.85,
                        sourceModel=self.Name,
                        weight=1.0,
                    )
                    # Attach swing trading attributes
                    setattr(insight, "PivotPrice", pivot)
                    setattr(insight, "StopLossPrice", stop_price)
                    setattr(insight, "TargetPrice", target_price)
                    setattr(insight, "RiskPerShare", risk_per_share)

                    # Check Leader Exemption Status via ClickHouse precalculated metrics
                    is_leader = False
                    rs_rating = 0.0
                    minervini_score = 0
                    if self._store:
                        rs_val = self._store.get_ticker_metric(as_of, symbol.Value, "rs_rating", 0.0)
                        if rs_val:
                            try:
                                rs_rating = float(rs_val)
                            except Exception:
                                pass
                        m_val = self._store.get_ticker_metric(as_of, symbol.Value, "minervini_tt_score_full", 0)
                        if m_val:
                            try:
                                minervini_score = int(m_val)
                            except Exception:
                                pass

                    if (rs_rating >= self._leader_rs_threshold) or (minervini_score >= 7):
                        is_leader = True
                        setattr(insight, "IsLeaderExemption", True)
                        algorithm.Debug(
                            f"🌟 LEADER EXEMPTION PASS [{symbol.Value}]: RS={rs_rating:.0f} / Minervini={minervini_score}/8 → Eligible for Early Reversal / Scout Entry"
                        )

                    algorithm.Debug(
                        f"🎯 SWING BREAKOUT TRIGGER [{symbol.Value}]: Price=${current_px:.2f} >= Pivot=${pivot:.2f} "
                        f"Stop=${stop_price:.2f} (-{risk_pct:.1%}) Target=${target_price:.2f} (+{magnitude:.1%}) LeaderExemption={is_leader}"
                    )
                    insights.append(insight)

        return insights


class SwingPullbackAlphaModel(AlphaModel):
    """
    Evaluates tactical pullback entries (Pocket Pivots / 10-20 EMA support reclaims)
    in leading stocks delivered by UniverseSelection.
    """

    def __init__(
        self,
        ema_period: int = 10,
        reclaim_threshold_pct: float = 0.01,
        insight_duration_days: int = 15,
        default_stop_loss_pct: float = 0.05,
        store: Any = None,
    ):
        self._ema_period = max(5, int(ema_period))
        self._reclaim_pct = float(reclaim_threshold_pct)
        self._insight_duration = timedelta(days=int(insight_duration_days))
        self._default_stop_loss_pct = float(default_stop_loss_pct)
        self._store = store

        self._symbol_data: dict[Any, SymbolRollingData] = {}
        self._last_day = None
        self.Name = "SwingPullbackAlphaModel"

    def OnSecuritiesChanged(self, algorithm, changes):
        for added in getattr(changes, "AddedSecurities", []):
            sym = added.Symbol
            if sym not in self._symbol_data:
                self._symbol_data[sym] = SymbolRollingData(sym, lookback=self._ema_period)

        for removed in getattr(changes, "RemovedSecurities", []):
            sym = removed.Symbol
            self._symbol_data.pop(sym, None)

    def Update(self, algorithm, data):
        insights = []
        today = algorithm.Time.date()
        is_new_day = self._last_day != today
        if is_new_day:
            self._last_day = today

        for symbol, sdata in list(self._symbol_data.items()):
            sec = algorithm.Securities.get(symbol)
            if not sec or not getattr(sec, "Price", 0):
                continue

            current_px = float(sec.Price)
            current_vol = float(getattr(sec, "Volume", 0) or 0)
            high_px = float(getattr(sec, "High", current_px) or current_px)
            low_px = float(getattr(sec, "Low", current_px) or current_px)

            if is_new_day:
                sdata.update(high_px, low_px, current_px, current_vol)

            if not sdata.is_ready:
                continue

            is_invested = False
            if hasattr(algorithm, "Portfolio"):
                try:
                    h = algorithm.Portfolio[symbol]
                    is_invested = bool(getattr(h, "Invested", False) is True)
                except Exception:
                    is_invested = False
            if is_invested:
                continue

            # Support reclaim trigger: low tagged support, price closing strong near high
            base_low = sdata.base_low
            stop_price = max(base_low, current_px * (1.0 - self._default_stop_loss_pct))
            risk_per_share = current_px - stop_price

            if risk_per_share > 0 and (risk_per_share / current_px) <= 0.08:
                target_price = current_px + (risk_per_share * 3.0)
                magnitude = (target_price - current_px) / current_px

                insight = Insight.Price(
                    symbol=symbol,
                    period=self._insight_duration,
                    direction=InsightDirection.Up,
                    magnitude=magnitude,
                    confidence=0.80,
                    sourceModel=self.Name,
                    weight=1.0,
                )
                setattr(insight, "StopLossPrice", stop_price)
                setattr(insight, "TargetPrice", target_price)
                setattr(insight, "RiskPerShare", risk_per_share)

                insights.append(insight)

        return insights
