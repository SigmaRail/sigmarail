import { Tabs, TabsContent, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import type { StockIntrospectionData } from "../../types";
import { cn } from "../../lib/utils";
import { EarningsPanel } from "./EarningsPanel";
import { Button } from "@sb/webapp-core/components/ui/button";

interface FundamentalsRailProps {
  data?: StockIntrospectionData | null;
  open: boolean;
  onToggle: () => void;
  showOverviewTab?: boolean;
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function asPct(value: unknown): number | null {
  const n = num(value);
  if (n === null) return null;
  return Math.abs(n) <= 1.5 ? n * 100 : n;
}

function formatNum(value: number | null, digits = 1): string {
  if (value === null) return "—";
  return value.toFixed(digits);
}

function formatSignedPct(value: number | null, digits = 1): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function chgClass(value: number | null): string {
  if (value === null) return "text-ink";
  if (value > 0) return "text-emerald-500";
  if (value < 0) return "text-rose-500";
  return "text-ink";
}

function kpiNum(kpis: Record<string, unknown>, key: string): number | null {
  return num(kpis[key]);
}

function ratingRow(label: string, value: number | null, suffix = "") {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-ink-muted">{label}</span>
      <span className="font-bold text-ink">
        {value === null ? "—" : `${Math.round(value)}${suffix}`}
      </span>
    </div>
  );
}

function fundRow(label: string, value: string, valueClass?: string) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-ink-muted">{label}</span>
      <span className={cn("font-bold", valueClass ?? "text-ink")}>{value}</span>
    </div>
  );
}

export function FundamentalsRail({
  data,
  open,
  onToggle,
  showOverviewTab = true,
}: FundamentalsRailProps) {
  const kpis = (data?.as_of_kpis ?? {}) as Record<string, unknown>;
  // Prefer clamped *_display fields only — null means hide (do not fall back to raw)
  const cyRev = num(kpis.eps_cy_rev_pct_90d_display);
  const nyRev = num(kpis.eps_ny_rev_pct_90d_display);
  const salesNyRev = num(kpis.sales_ny_rev_pct_90d_display);

  const roe = asPct(kpis.mrt_roe);
  const roic = asPct(kpis.mrt_roic);
  const netMgn = asPct(kpis.mrt_netmargin);
  const grossMgn = asPct(kpis.mrt_grossmargin);

  if (!open) {
    return (
      <Button
        type="button"
        onClick={onToggle}
        variant="ghost"
        size="sm"
        aria-label="Open fundamentals rail"
        aria-expanded={false}
        data-testid="fundamentals-toggle"
        className="flex h-auto w-full flex-shrink-0 items-center justify-between rounded-none border-t border-border bg-muted px-3 py-2 text-[10px] font-mono font-bold text-muted-foreground hover:text-foreground"
        title="Open fundamentals rail"
      >
        <span>Overview and earnings</span>
        <span>Show</span>
      </Button>
    );
  }

  return (
    <section data-testid="fundamentals-panel" className="flex w-full min-w-0 flex-shrink-0 flex-col border-t border-border bg-card text-card-foreground text-[11px] font-mono">
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-2 py-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {showOverviewTab ? "Company data" : "Earnings & estimates"}
        </span>
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            onClick={onToggle}
            variant="ghost"
            size="sm"
            aria-label="Collapse fundamentals rail"
            aria-expanded={true}
            className="h-7 w-7 p-0 text-muted-foreground"
            title="Collapse fundamentals rail"
          >
            ‹
          </Button>
        </div>
      </div>

      <Tabs defaultValue="earnings" className="flex w-full flex-col">
        <TabsList className={`mx-2 mt-2 grid h-8 w-[calc(100%-1rem)] flex-shrink-0 ${showOverviewTab ? "grid-cols-2 sm:w-80" : "grid-cols-1"}`}>
          {showOverviewTab ? <TabsTrigger className="py-1 text-[10px]" value="overview">Overview</TabsTrigger> : null}
          <TabsTrigger className="py-1 text-[10px]" value="earnings">Earnings</TabsTrigger>
        </TabsList>
        {showOverviewTab ? <TabsContent value="overview" className="grid gap-x-8 gap-y-4 px-3 py-3 md:grid-cols-2">
          <section className="space-y-0.5">
            <div className="mb-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">Ratings</div>
            {ratingRow("RS", kpiNum(kpis, "rs_rating"))}
            {ratingRow("Tech", kpiNum(kpis, "technical_rating"))}
            {ratingRow("Setup", kpiNum(kpis, "setup_quality_rating"))}
            {ratingRow("Growth", kpiNum(kpis, "growth_rating"))}
            {ratingRow("Overall", kpiNum(kpis, "overall_score"))}
            <div className="flex items-center justify-between gap-2 pt-0.5">
              <span className="text-ink-muted">CY EPS revisions · 90d</span>
              <span className={cn("font-bold", chgClass(cyRev))}>{formatSignedPct(cyRev)}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-ink-muted">NY EPS revisions · 90d</span>
              <span className={cn("font-bold", chgClass(nyRev))}>{formatSignedPct(nyRev)}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-ink-muted">NY sales revisions · 90d</span>
              <span className={cn("font-bold", chgClass(salesNyRev))}>{formatSignedPct(salesNyRev)}</span>
            </div>
          </section>

          <section className="space-y-0.5 border-t border-line pt-2">
            <div className="mb-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">Company metrics</div>
            {fundRow("TTM EPS", kpiNum(kpis, "mrt_epsdil") !== null ? `$${formatNum(kpiNum(kpis, "mrt_epsdil"), 2)}` : "—")}
            {fundRow("ROE", formatSignedPct(roe))}
            {fundRow("ROIC", formatSignedPct(roic))}
            {fundRow("Net mgn", formatSignedPct(netMgn))}
            {fundRow("Gross mgn", formatSignedPct(grossMgn))}
            {fundRow("D/E", formatNum(kpiNum(kpis, "mrq_de"), 2))}
            {fundRow("P/E", formatNum(kpiNum(kpis, "pe"), 1))}
            {fundRow("P/S", formatNum(kpiNum(kpis, "ps"), 1))}
          </section>

        </TabsContent> : null}
        <TabsContent value="earnings" className="px-3 py-3">
          <EarningsPanel
            annual={data?.annual_growth ?? []}
            quarterly={data?.quarterly_growth ?? []}
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}
