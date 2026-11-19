import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Slider } from "@sb/webapp-core/components/ui/slider";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

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
        <h4 className="text-[12.5px] font-bold text-ink">2. Alpha Model</h4>
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
            <Checkbox
              checked={alphaSwingBreakout}
              onCheckedChange={(checked) => onToggleAlphaSwingBreakout(checked === true)}
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
              <Slider
                min={3}
                max={15}
                value={[breakoutLookback]}
                onValueChange={([value]) => onChangeBreakoutLookback(value)}
                className="mt-1 w-full"
              />
            </div>
            <div>
              <label className="text-[10px] text-ink-faint">
                Volume Pace Trigger: <span className="font-bold text-accent">{breakoutVolSurge}x Avg</span>
              </label>
              <Slider
                min={1.0}
                max={2.5}
                step={0.1}
                value={[breakoutVolSurge]}
                onValueChange={([value]) => onChangeBreakoutVolSurge(value)}
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
            <Checkbox
              checked={alphaSwingPullback}
              onCheckedChange={(checked) => onToggleAlphaSwingPullback(checked === true)}
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
                <Button
                  key={period}
                  type="button"
                  onClick={() => onChangePullbackEmaPeriod(period)}
                  variant={pullbackEmaPeriod === period ? "default" : "outline"}
                  size="sm"
                  className="h-8 flex-1 px-2 text-[10.5px]"
                >
                  {period}-Day EMA
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Model 3: Screener Score-Ranked Alpha */}
      <div
        className={cn(
          "rounded border p-3 transition-all",
          alphaScreener ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60"
        )}
      >
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
            <Checkbox
              checked={alphaScreener}
              onCheckedChange={(checked) => onToggleAlphaScreener(checked === true)}
            />
            <span>Screener Score Direct Alpha</span>
          </label>
          <span className="font-mono text-[9px] text-ink-faint">ScreenerAlphaModel</span>
        </div>
        <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
          Emits immediate directional long insights for highest-scoring universe candidates.
        </p>
        {alphaScreener && (
          <div className="mt-2.5 grid grid-cols-2 gap-2 border-t border-line/60 pt-2 text-[11px]">
            <div>
              <label className="text-[10px] text-ink-faint">Max Open Positions</label>
              <Input
                type="number"
                min={1}
                max={50}
                value={screenerMaxPositions}
                onChange={(e) => onChangeScreenerMaxPositions(Number(e.target.value))}
                className="mt-1 h-8 w-full font-mono text-[11px]"
              />
            </div>
            <div>
              <label className="text-[10px] text-ink-faint">
                Tactical Stop Loss: <span className="font-bold text-ink">{(screenerStopLoss * 100).toFixed(0)}%</span>
              </label>
              <Slider
                min={0.03}
                max={0.15}
                step={0.01}
                value={[screenerStopLoss]}
                onValueChange={([value]) => onChangeScreenerStopLoss(value)}
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
              <Checkbox
                checked={alphaRsi}
                onCheckedChange={(checked) => onToggleAlphaRsi(checked === true)}
              />
              <span>RSI Mean-Reversion</span>
            </label>
            <span className="font-mono text-[9.5px] text-ink-faint">RsiAlphaModel ({rsiPeriod}d, {rsiResolution})</span>
          </div>
          {alphaRsi && (
            <div className="grid grid-cols-2 gap-2 pl-5 pt-1 text-[10.5px]">
              <div>
                <label className="text-[10px] text-ink-faint">Period: {rsiPeriod}d</label>
                <Slider
                  min={5}
                  max={30}
                  value={[rsiPeriod]}
                  onValueChange={([value]) => onChangeRsiPeriod(value)}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[10px] text-ink-faint">Resolution</label>
                <Select value={rsiResolution} onValueChange={onChangeRsiResolution}>
                  <SelectTrigger className="h-8 w-full text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Daily">Daily</SelectItem>
                    <SelectItem value="Hour">Hour</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>

        {/* MACD */}
        <div className="space-y-1.5 pt-1">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer text-[11px] text-ink">
              <Checkbox
                checked={alphaMacd}
                onCheckedChange={(checked) => onToggleAlphaMacd(checked === true)}
              />
              <span>MACD Momentum</span>
            </label>
            <span className="font-mono text-[9.5px] text-ink-faint">MacdAlphaModel ({macdFast}/{macdSlow}/{macdSignal})</span>
          </div>
          {alphaMacd && (
            <div className="grid grid-cols-3 gap-1.5 pl-5 pt-1 text-[10.5px]">
              <div>
                <label className="text-[9.5px] text-ink-faint">Fast: {macdFast}</label>
                <Slider
                  min={5}
                  max={20}
                  value={[macdFast]}
                  onValueChange={([value]) => onChangeMacdFast(value)}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[9.5px] text-ink-faint">Slow: {macdSlow}</label>
                <Slider
                  min={15}
                  max={40}
                  value={[macdSlow]}
                  onValueChange={([value]) => onChangeMacdSlow(value)}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[9.5px] text-ink-faint">Signal: {macdSignal}</label>
                <Slider
                  min={3}
                  max={15}
                  value={[macdSignal]}
                  onValueChange={([value]) => onChangeMacdSignal(value)}
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
              <Checkbox
                checked={alphaEmaCross}
                onCheckedChange={(checked) => onToggleAlphaEmaCross(checked === true)}
              />
              <span>EMA Trend Cross</span>
            </label>
            <span className="font-mono text-[9.5px] text-ink-faint">EmaCrossAlphaModel ({emaFast}/{emaSlow})</span>
          </div>
          {alphaEmaCross && (
            <div className="grid grid-cols-2 gap-2 pl-5 pt-1 text-[10.5px]">
              <div>
                <label className="text-[10px] text-ink-faint">Fast EMA: {emaFast}</label>
                <Slider
                  min={5}
                  max={30}
                  value={[emaFast]}
                  onValueChange={([value]) => onChangeEmaFast(value)}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-[10px] text-ink-faint">Slow EMA: {emaSlow}</label>
                <Slider
                  min={20}
                  max={100}
                  step={5}
                  value={[emaSlow]}
                  onValueChange={([value]) => onChangeEmaSlow(value)}
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
