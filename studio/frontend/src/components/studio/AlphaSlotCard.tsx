import { cn } from "../../lib/utils";

interface AlphaSlotCardProps {
  alphaScreener: boolean;
  onToggleAlphaScreener: (v: boolean) => void;
  screenerMaxPositions: number;
  onChangeScreenerMaxPositions: (v: number) => void;
  screenerStopLoss: number;
  onChangeScreenerStopLoss: (v: number) => void;

  alphaSwingBreakout: boolean;
  onToggleAlphaSwingBreakout: (v: boolean) => void;
  breakoutLookback: number;
  onChangeBreakoutLookback: (v: number) => void;
  breakoutVolSurge: number;
  onChangeBreakoutVolSurge: (v: number) => void;

  alphaSwingPullback: boolean;
  onToggleAlphaSwingPullback: (v: boolean) => void;
  pullbackEmaPeriod: number;
  onChangePullbackEmaPeriod: (v: number) => void;

  alphaRsi: boolean;
  onToggleAlphaRsi: (v: boolean) => void;
  rsiPeriod: number;
  onChangeRsiPeriod: (v: number) => void;
  rsiResolution: string;
  onChangeRsiResolution: (v: string) => void;

  alphaMacd: boolean;
  onToggleAlphaMacd: (v: boolean) => void;
  macdFast: number;
  onChangeMacdFast: (v: number) => void;
  macdSlow: number;
  onChangeMacdSlow: (v: number) => void;
  macdSignal: number;
  onChangeMacdSignal: (v: number) => void;

  alphaEmaCross: boolean;
  onToggleAlphaEmaCross: (v: boolean) => void;
  emaFast: number;
  onChangeEmaFast: (v: number) => void;
  emaSlow: number;
  onChangeEmaSlow: (v: number) => void;
}

export function AlphaSlotCard({
  alphaScreener,
  onToggleAlphaScreener,
  screenerMaxPositions,
  onChangeScreenerMaxPositions,
  screenerStopLoss,
  onChangeScreenerStopLoss,
  alphaSwingBreakout,
  onToggleAlphaSwingBreakout,
  breakoutLookback,
  onChangeBreakoutLookback,
  breakoutVolSurge,
  onChangeBreakoutVolSurge,
  alphaSwingPullback,
  onToggleAlphaSwingPullback,
  pullbackEmaPeriod,
  onChangePullbackEmaPeriod,
  alphaRsi,
  onToggleAlphaRsi,
  rsiPeriod,
  onChangeRsiPeriod,
  rsiResolution,
  onChangeRsiResolution,
  alphaMacd,
  onToggleAlphaMacd,
  macdFast,
  onChangeMacdFast,
  macdSlow,
  onChangeMacdSlow,
  macdSignal,
  onChangeMacdSignal,
  alphaEmaCross,
  onToggleAlphaEmaCross,
  emaFast,
  onChangeEmaFast,
  emaSlow,
  onChangeEmaSlow,
}: AlphaSlotCardProps) {
  const activeCount =
    (alphaSwingBreakout ? 1 : 0) +
    (alphaSwingPullback ? 1 : 0) +
    (alphaScreener ? 1 : 0) +
    (alphaRsi ? 1 : 0) +
    (alphaMacd ? 1 : 0) +
    (alphaEmaCross ? 1 : 0);

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-3.5 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-2">
        <div>
          <h4 className="text-[12.5px] font-bold text-ink">2. Alpha Model</h4>
        </div>
        <span className="font-mono text-[10px] text-ink-muted">
          {activeCount > 1 ? `CompositeAlphaModel (${activeCount} active)` : "Single Alpha"}
        </span>
      </div>

      {/* Model 1: Swing Breakout Alpha (Tactical Pivot Trigger) */}
      <div
        className={cn(
          "rounded border p-3 transition-all",
          alphaSwingBreakout ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60"
        )}
      >
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
            <input
              type="checkbox"
              checked={alphaSwingBreakout}
              onChange={(e) => onToggleAlphaSwingBreakout(e.target.checked)}
              className="rounded border-line"
            />
            <span>Swing Breakout & Pivot Trigger</span>
          </label>
          <span className="font-mono text-[9px] text-ink-faint">SwingBreakoutAlphaModel</span>
        </div>
        <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
          Waits for volatility contraction base and triggers when price breaks consolidation pivot with volume surge.
        </p>
        {alphaSwingBreakout && (
          <div className="mt-2.5 grid grid-cols-2 gap-2 border-t border-line/60 pt-2 text-[11px]">
            <div>
              <label className="text-[10px] text-ink-faint">
                Base Lookback: <span className="font-bold text-ink">{breakoutLookback} Days</span>
              </label>
              <input
                type="range"
                min={3}
                max={15}
                value={breakoutLookback}
                onChange={(e) => onChangeBreakoutLookback(Number(e.target.value))}
                className="mt-1 w-full"
              />
            </div>
            <div>
              <label className="text-[10px] text-ink-faint">
                Volume Pace Trigger: <span className="font-bold text-accent">{breakoutVolSurge}x Avg</span>
              </label>
              <input
                type="range"
                min={1.0}
                max={2.5}
                step={0.1}
                value={breakoutVolSurge}
                onChange={(e) => onChangeBreakoutVolSurge(Number(e.target.value))}
                className="mt-1 w-full"
              />
            </div>
          </div>
        )}
      </div>

      {/* Model 2: Swing Pullback / Pocket Pivot Alpha */}
      <div
        className={cn(
          "rounded border p-3 transition-all",
          alphaSwingPullback ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60"
        )}
      >
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
            <input
              type="checkbox"
              checked={alphaSwingPullback}
              onChange={(e) => onToggleAlphaSwingPullback(e.target.checked)}
              className="rounded border-line"
            />
            <span>Swing Pullback & Pocket Pivot</span>
          </label>
          <span className="font-mono text-[9px] text-ink-faint">SwingPullbackAlphaModel</span>
        </div>
        <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
          Detects orderly pullbacks finding support on rising 10/20 EMA in market leaders and triggers on reclaim.
        </p>
        {alphaSwingPullback && (
          <div className="mt-2.5 border-t border-line/60 pt-2 text-[11px]">
            <label className="text-[10px] text-ink-faint block">
              Moving Average Support Anchor: <span className="font-bold text-ink">{pullbackEmaPeriod}-Day EMA</span>
            </label>
            <div className="mt-1.5 flex gap-2">
              {[10, 20, 50].map((period) => (
                <button
                  key={period}
                  type="button"
                  onClick={() => onChangePullbackEmaPeriod(period)}
                  className={cn(
                    "flex-1 py-1 rounded text-[10.5px] font-medium border transition-colors",
                    pullbackEmaPeriod === period
                      ? "bg-accent text-white border-accent"
                      : "bg-surface text-ink-muted border-line hover:bg-surface-raised"
                  )}
                >
                  {period}-Day EMA
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Model 3: Vera Screener Score-Ranked Alpha */}
      <div
        className={cn(
          "rounded border p-3 transition-all",
          alphaScreener ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60"
        )}
      >
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
            <input
              type="checkbox"
              checked={alphaScreener}
              onChange={(e) => onToggleAlphaScreener(e.target.checked)}
              className="rounded border-line"
            />
            <span>Screener Score Direct Alpha</span>
          </label>
          <span className="font-mono text-[9px] text-ink-faint">VeraScreenerAlphaModel</span>
        </div>
        <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
          Emits immediate directional long insights for highest-scoring universe candidates.
        </p>
        {alphaScreener && (
          <div className="mt-2.5 grid grid-cols-2 gap-2 border-t border-line/60 pt-2 text-[11px]">
            <div>
              <label className="text-[10px] text-ink-faint">Max Open Positions</label>
              <input
                type="number"
                min={1}
                max={50}
                value={screenerMaxPositions}
                onChange={(e) => onChangeScreenerMaxPositions(Number(e.target.value))}
                className="mt-1 w-full rounded border border-line bg-surface px-2 py-1 text-ink font-mono text-[11px]"
              />
            </div>
            <div>
              <label className="text-[10px] text-ink-faint">
                Tactical Stop Loss: <span className="font-bold text-ink">{(screenerStopLoss * 100).toFixed(0)}%</span>
              </label>
              <input
                type="range"
                min={0.03}
                max={0.15}
                step={0.01}
                value={screenerStopLoss}
                onChange={(e) => onChangeScreenerStopLoss(Number(e.target.value))}
                className="mt-1.5 w-full"
              />
            </div>
          </div>
        )}
      </div>

      {/* Model 4: Standard Technical Oscillators (RSI / MACD / EMA Cross) */}
      <div className="rounded border border-line bg-surface-raised/40 p-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold text-ink-muted uppercase tracking-wider">
            Indicator Overlay Alphas
          </span>
        </div>

        {/* RSI */}
        <div className="space-y-1.5 pt-1">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer text-[11px] text-ink">
              <input
                type="checkbox"
                checked={alphaRsi}
                onChange={(e) => onToggleAlphaRsi(e.target.checked)}
                className="rounded border-line"
              />
              <span>RSI Mean-Reversion</span>
            </label>
            <span className="font-mono text-[9.5px] text-ink-faint">RsiAlphaModel ({rsiPeriod}d, {rsiResolution})</span>
          </div>
          {alphaRsi && (
            <div className="grid grid-cols-2 gap-2 pl-5 pt-1 text-[10.5px]">
              <div>
                <label className="text-[10px] text-ink-faint">Period: {rsiPeriod}d</label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  value={rsiPeriod}
                  onChange={(e) => onChangeRsiPeriod(Number(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[10px] text-ink-faint">Resolution</label>
                <select
                  value={rsiResolution}
                  onChange={(e) => onChangeRsiResolution(e.target.value)}
                  className="w-full rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink"
                >
                  <option value="Daily">Daily</option>
                  <option value="Hour">Hour</option>
                </select>
              </div>
            </div>
          )}
        </div>

        {/* MACD */}
        <div className="space-y-1.5 pt-1">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer text-[11px] text-ink">
              <input
                type="checkbox"
                checked={alphaMacd}
                onChange={(e) => onToggleAlphaMacd(e.target.checked)}
                className="rounded border-line"
              />
              <span>MACD Momentum</span>
            </label>
            <span className="font-mono text-[9.5px] text-ink-faint">MacdAlphaModel ({macdFast}/{macdSlow}/{macdSignal})</span>
          </div>
          {alphaMacd && (
            <div className="grid grid-cols-3 gap-1.5 pl-5 pt-1 text-[10.5px]">
              <div>
                <label className="text-[9.5px] text-ink-faint">Fast: {macdFast}</label>
                <input
                  type="range"
                  min={5}
                  max={20}
                  value={macdFast}
                  onChange={(e) => onChangeMacdFast(Number(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[9.5px] text-ink-faint">Slow: {macdSlow}</label>
                <input
                  type="range"
                  min={15}
                  max={40}
                  value={macdSlow}
                  onChange={(e) => onChangeMacdSlow(Number(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[9.5px] text-ink-faint">Signal: {macdSignal}</label>
                <input
                  type="range"
                  min={3}
                  max={15}
                  value={macdSignal}
                  onChange={(e) => onChangeMacdSignal(Number(e.target.value))}
                  className="w-full"
                />
              </div>
            </div>
          )}
        </div>

        {/* EMA Cross */}
        <div className="space-y-1.5 pt-1">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer text-[11px] text-ink">
              <input
                type="checkbox"
                checked={alphaEmaCross}
                onChange={(e) => onToggleAlphaEmaCross(e.target.checked)}
                className="rounded border-line"
              />
              <span>EMA Trend Cross</span>
            </label>
            <span className="font-mono text-[9.5px] text-ink-faint">EmaCrossAlphaModel ({emaFast}/{emaSlow})</span>
          </div>
          {alphaEmaCross && (
            <div className="grid grid-cols-2 gap-2 pl-5 pt-1 text-[10.5px]">
              <div>
                <label className="text-[10px] text-ink-faint">Fast EMA: {emaFast}</label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  value={emaFast}
                  onChange={(e) => onChangeEmaFast(Number(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[10px] text-ink-faint">Slow EMA: {emaSlow}</label>
                <input
                  type="range"
                  min={20}
                  max={100}
                  step={5}
                  value={emaSlow}
                  onChange={(e) => onChangeEmaSlow(Number(e.target.value))}
                  className="w-full"
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
