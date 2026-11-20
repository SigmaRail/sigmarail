import { useMemo, useState } from "react";
import { compareSectorNames, sectorColor } from "./sectorColors";

type Props = {
  dates: string[];
  memberCounts: number[];
  sectorCounts: Array<{ date: string; sector: string; count: number }>;
  height?: number;
  onHoverDate?: (date: string | null) => void;
  onClickDate?: (date: string) => void;
};

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 176;
const PLOT = { left: 42, right: 46, top: 8, bottom: 26 };

function shortDate(date: string): string {
  return date.length >= 10 ? `${date.slice(5, 7)}-${date.slice(8, 10)}-${date.slice(2, 4)}` : date;
}

export function SectorMembershipAreaChart({
  dates,
  memberCounts,
  sectorCounts,
  height = 148,
  onHoverDate,
  onClickDate,
}: Props) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const data = useMemo(() => {
    const sectors = [...new Set(sectorCounts.map((row) => row.sector))].sort(compareSectorNames);
    const countsByDate = new Map<string, Map<string, number>>();
    for (const row of sectorCounts) {
      const bySector = countsByDate.get(row.date) ?? new Map<string, number>();
      bySector.set(row.sector, (bySector.get(row.sector) ?? 0) + row.count);
      countsByDate.set(row.date, bySector);
    }
    const totals = dates.map((date, index) => {
      const values = countsByDate.get(date);
      return values
        ? [...values.values()].reduce((sum, count) => sum + count, 0)
        : memberCounts[index] ?? 0;
    });
    const percentages = dates.map((date, index) => {
      const values = countsByDate.get(date);
      const total = totals[index] ?? 0;
      return sectors.map((sector) => total > 0 ? ((values?.get(sector) ?? 0) / total) * 100 : 0);
    });
    return { sectors, totals, percentages };
  }, [dates, memberCounts, sectorCounts]);

  if (dates.length < 2 || data.sectors.length === 0) {
    return (
      <p className="font-mono text-[10px] text-ink-faint">
        Sector share needs at least two membership dates with sector data.
      </p>
    );
  }

  const plotWidth = VIEW_WIDTH - PLOT.left - PLOT.right;
  const plotHeight = VIEW_HEIGHT - PLOT.top - PLOT.bottom;
  const minMembers = Math.min(...data.totals);
  const maxMembers = Math.max(...data.totals);
  const xAt = (index: number) => PLOT.left + (index / (dates.length - 1)) * plotWidth;
  const yAt = (percent: number) => PLOT.top + ((100 - percent) / 100) * plotHeight;
  const yMembersAt = (count: number) => {
    const relative = maxMembers === minMembers ? 0.5 : (count - minMembers) / (maxMembers - minMembers);
    return PLOT.top + (1 - relative) * plotHeight;
  };
  const stackedBounds = dates.map((_, dateIndex) => {
    let cumulative = 0;
    return data.sectors.map((_, sectorIndex) => {
      const lower = cumulative;
      cumulative += data.percentages[dateIndex]?.[sectorIndex] ?? 0;
      return { lower, upper: cumulative };
    });
  });
  const paths = data.sectors.map((sector, sectorIndex) => {
    const topPoints = stackedBounds.map((bounds, index) => `${xAt(index)},${yAt(bounds[sectorIndex]?.upper ?? 0)}`);
    const bottomPoints = stackedBounds
      .map((bounds, index) => `${xAt(index)},${yAt(bounds[sectorIndex]?.lower ?? 0)}`)
      .reverse();
    return { sector, points: [...topPoints, ...bottomPoints].join(" "), color: sectorColor(sector).hex };
  });

  const indexAtPointer = (clientX: number, bounds: DOMRect) => {
    const viewX = (clientX - bounds.left) / bounds.width * VIEW_WIDTH;
    const normalized = Math.min(1, Math.max(0, (viewX - PLOT.left) / plotWidth));
    return Math.round(normalized * (dates.length - 1));
  };
  const hoveredDate = hoverIndex == null ? null : dates[hoverIndex] ?? null;
  const memberLine = data.totals.map((count, index) => `${xAt(index)},${yMembersAt(count)}`).join(" ");
  const hoveredSectors = hoverIndex == null
    ? []
    : data.sectors
        .map((sector, index) => ({
          sector,
          percent: data.percentages[hoverIndex]?.[index] ?? 0,
          color: sectorColor(sector).hex,
        }))
        .filter((item) => item.percent > 0.01);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 font-mono text-[10px] text-ink-muted">
        <span>Sector mix · 100% stacked</span>
        <span>Area: member share · Line: member count (right scale)</span>
      </div>
      <div
        className="relative w-full touch-pan-y overflow-hidden rounded border border-line bg-surface"
        style={{ height }}
        onPointerMove={(event) => {
          const index = indexAtPointer(event.clientX, event.currentTarget.getBoundingClientRect());
          setHoverIndex(index);
          onHoverDate?.(dates[index] ?? null);
        }}
        onPointerLeave={() => {
          setHoverIndex(null);
          onHoverDate?.(null);
        }}
        onClick={(event) => {
          const index = indexAtPointer(event.clientX, event.currentTarget.getBoundingClientRect());
          const date = dates[index];
          if (date) onClickDate?.(date);
        }}
        role="img"
        aria-label="100 percent stacked sector membership over time"
      >
        <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} className="h-full w-full" preserveAspectRatio="none" aria-hidden="true">
          {paths.map((path) => (
            <polygon key={path.sector} points={path.points} fill={path.color} fillOpacity="0.72" />
          ))}
          {[0, 25, 50, 75, 100].map((value) => {
            const y = yAt(value);
            return (
              <g key={value}>
                <line x1={PLOT.left} x2={VIEW_WIDTH - PLOT.right} y1={y} y2={y} stroke="rgba(148,163,184,0.18)" strokeDasharray="3 4" />
                <text x={PLOT.left - 7} y={y + 3} textAnchor="end" fill="#94a3b8" fontSize="9">{value}%</text>
              </g>
            );
          })}
          <polyline points={memberLine} fill="none" stroke="#e2e8f0" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          <text x={VIEW_WIDTH - 4} y={PLOT.top + 3} textAnchor="end" fill="#e2e8f0" fontSize="9">{maxMembers.toLocaleString()}</text>
          <text x={VIEW_WIDTH - 4} y={VIEW_HEIGHT - PLOT.bottom + 3} textAnchor="end" fill="#e2e8f0" fontSize="9">{minMembers.toLocaleString()}</text>
          {hoverIndex != null ? (
            <line x1={xAt(hoverIndex)} x2={xAt(hoverIndex)} y1={PLOT.top} y2={VIEW_HEIGHT - PLOT.bottom} stroke="rgba(226,232,240,0.72)" strokeDasharray="3 3" />
          ) : null}
          {[0, Math.floor((dates.length - 1) / 2), dates.length - 1].filter((value, i, all) => all.indexOf(value) === i).map((index) => (
            <text key={`${dates[index]}-${index}`} x={xAt(index)} y={VIEW_HEIGHT - 7} textAnchor={index === 0 ? "start" : index === dates.length - 1 ? "end" : "middle"} fill="#94a3b8" fontSize="9">
              {shortDate(dates[index]!)}
            </text>
          ))}
        </svg>
        {hoveredDate ? (
          <div className="pointer-events-none absolute right-2 top-2 max-h-[calc(100%-1rem)] max-w-[min(18rem,85%)] overflow-auto rounded border border-line bg-popover/95 px-2 py-1.5 text-[9px] shadow-panel">
            <div className="mb-1 font-mono text-ink">{hoveredDate} · {data.totals[hoverIndex!] ?? 0} members</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {hoveredSectors.map((item) => (
                <span key={item.sector} className="flex items-center gap-1 truncate text-ink-muted" title={item.sector}>
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="truncate">{item.sector}</span>
                  <span className="ml-auto font-mono text-ink">{item.percent.toFixed(1)}%</span>
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-ink-muted">
        <span className="inline-flex items-center gap-1">
          <span className="h-0.5 w-3 bg-slate-200" />
          Members
        </span>
        {data.sectors.map((sector) => (
          <span key={sector} className="inline-flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: sectorColor(sector).hex }} />
            {sector}
          </span>
        ))}
      </div>
    </div>
  );
}
