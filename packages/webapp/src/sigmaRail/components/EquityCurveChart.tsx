import { useMemo } from "react";
import type { EquityCurvePoint } from "../types";

const W = 640;
const H = 180;
const PAD = { top: 12, right: 12, bottom: 24, left: 48 };

export function EquityCurveChart({
  points,
  className,
  valueFormatter = formatEquity,
  title,
  ariaLabel = "Strategy equity curve",
  strokeColor = "text-accent",
}: {
  points: EquityCurvePoint[];
  className?: string;
  valueFormatter?: (v: number) => string;
  title?: string;
  ariaLabel?: string;
  strokeColor?: string;
}) {
  const geometry = useMemo(() => {
    if (points.length < 2) return null;
    const xs = points.map((p) => p.t);
    const ys = points.map((p) => p.equity);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const dx = maxX - minX || 1;
    const dy = maxY - minY || 1;
    const innerW = W - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;
    const toX = (t: number) => PAD.left + ((t - minX) / dx) * innerW;
    const toY = (eq: number) => PAD.top + (1 - (eq - minY) / dy) * innerH;
    const path = points
      .map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.t).toFixed(1)},${toY(p.equity).toFixed(1)}`)
      .join(" ");
    return {
      path,
      minY,
      maxY,
      startLabel: formatTs(points[0]!.t),
      endLabel: formatTs(points[points.length - 1]!.t),
    };
  }, [points]);

  if (!geometry) {
    return (
      <div className={className ?? "rounded border border-line bg-surface px-3 py-6 text-center text-[12px] text-ink-muted"}>
        {title ? <div className="font-medium text-ink-muted mb-2">{title}</div> : null}
        Series unavailable for this run.
      </div>
    );
  }

  return (
    <div className={className}>
      {title ? (
        <div className="mb-1 text-[11px] font-medium text-ink-muted">{title}</div>
      ) : null}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-44 w-full rounded border border-line bg-surface"
        role="img"
        aria-label={ariaLabel}
      >
        <text
          x={PAD.left}
          y={PAD.top + 4}
          className="fill-ink-faint"
          fontSize="10"
          fontFamily="ui-monospace, monospace"
        >
          {valueFormatter(geometry.maxY)}
        </text>
        <text
          x={PAD.left}
          y={H - PAD.bottom + 2}
          className="fill-ink-faint"
          fontSize="10"
          fontFamily="ui-monospace, monospace"
        >
          {valueFormatter(geometry.minY)}
        </text>
        <text
          x={PAD.left}
          y={H - 6}
          className="fill-ink-faint"
          fontSize="9"
          fontFamily="ui-monospace, monospace"
        >
          {geometry.startLabel}
        </text>
        <text
          x={W - PAD.right}
          y={H - 6}
          textAnchor="end"
          className="fill-ink-faint"
          fontSize="9"
          fontFamily="ui-monospace, monospace"
        >
          {geometry.endLabel}
        </text>
        <path
          d={geometry.path}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className={strokeColor}
        />
      </svg>
    </div>
  );
}

function formatEquity(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return v.toFixed(0);
}

function formatTs(t: number): string {
  try {
    const ms = t > 1e12 ? t : t * 1000;
    return new Date(ms).toISOString().slice(0, 10);
  } catch {
    return String(t);
  }
}
