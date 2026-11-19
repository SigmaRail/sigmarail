import { Tabs, TabsContent, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import type { AnnualGrowthPoint, QuarterlyGrowthPoint } from "../../types";
import { EarningsEstimateChart } from "./EarningsEstimateChart";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@sb/webapp-core/components/ui/table";

function pct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function money(value: number | null | undefined, digits = 2): string {
  return value == null || !Number.isFinite(value) ? "—" : `$${value.toFixed(digits)}`;
}

function sales(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.abs(value) >= 1000 ? `$${(value / 1000).toFixed(1)}B` : `$${value.toFixed(0)}M`;
}

function beatLabel(status: QuarterlyGrowthPoint["eps_beat_miss"] | QuarterlyGrowthPoint["revenue_beat_miss"]) {
  if (status === "beat") return "Beat";
  if (status === "miss") return "Miss";
  if (status === "in_line") return "In line";
  return null;
}

function QuarterlyCard({ point }: { point: QuarterlyGrowthPoint }) {
  const epsActual = point.eps_actual ?? (!point.is_estimate ? point.eps : null);
  const epsEstimate = point.eps_estimate ?? (point.is_estimate ? point.eps : null);
  const salesActual = point.revenue_actual ?? (!point.is_estimate ? point.revenue_m : null);
  const salesEstimate = point.revenue_estimate ?? (point.is_estimate ? point.revenue_m : null);
  const epsStatus = beatLabel(point.eps_beat_miss);
  const salesStatus = beatLabel(point.revenue_beat_miss);

  return (
    <Card className="rounded-md p-2 text-[10px] shadow-none">
      <header className="mb-1.5 flex items-center justify-between gap-2 border-b border-line pb-1">
        <span className="font-bold text-ink">{point.report_date || "Undated quarter"}</span>
        <span className="flex gap-1 text-[9px]">
          {point.is_estimate && <span className="rounded bg-sky-500/10 px-1 text-sky-500">Estimate</span>}
          {epsStatus && <span className="rounded bg-muted px-1 text-muted-foreground">EPS {epsStatus}</span>}
          {salesStatus && <span className="rounded bg-muted px-1 text-muted-foreground">Sales {salesStatus}</span>}
        </span>
      </header>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        <div>
          <div className="text-[8px] uppercase text-ink-muted">EPS actual / est.</div>
          <div className="font-bold text-ink">{money(epsActual)} <span className="font-normal text-ink-muted">/ {money(epsEstimate)}</span></div>
        </div>
        <div className="text-right">
          <div className="text-[8px] uppercase text-ink-muted">EPS surprise</div>
          <div className="font-bold text-ink">{pct(point.eps_surprise_pct ?? (!point.is_estimate ? point.surprise_pct : null))}</div>
        </div>
        <div>
          <div className="text-[8px] uppercase text-ink-muted">Sales actual / est.</div>
          <div className="font-bold text-ink">{sales(salesActual)} <span className="font-normal text-ink-muted">/ {sales(salesEstimate)}</span></div>
        </div>
        <div className="text-right">
          <div className="text-[8px] uppercase text-ink-muted">Sales surprise</div>
          <div className="font-bold text-ink">{pct(point.revenue_surprise_pct)}</div>
        </div>
      </div>
    </Card>
  );
}

function AnnualRows({ rows }: { rows: AnnualGrowthPoint[] }) {
  if (!rows.length) return <p className="text-[10px] text-ink-muted">No annual series</p>;
  return (
    <div className="overflow-x-auto">
      <Table className="min-w-[340px] text-left text-[9px]">
        <TableHeader className="text-[8px] uppercase text-muted-foreground">
          <TableRow>
            <TableHead className="h-7 px-1 py-1 font-semibold">Year</TableHead>
            <TableHead className="h-7 px-1 py-1 text-right font-semibold">EPS</TableHead>
            <TableHead className="h-7 px-1 py-1 text-right font-semibold">EPS YoY</TableHead>
            <TableHead className="h-7 px-1 py-1 text-right font-semibold">Sales</TableHead>
            <TableHead className="h-7 px-1 py-1 text-right font-semibold">Sales YoY</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.year}>
              <TableCell className="px-1 py-1 text-foreground">{String(row.year).replace(/e$/i, "")}{row.is_estimate ? " e" : ""}</TableCell>
              <TableCell className="px-1 py-1 text-right font-semibold text-foreground" title={row.eps_actual != null && row.eps_estimate != null ? `Actual ${money(row.eps_actual)} · estimate ${money(row.eps_estimate)}` : undefined}>
                {row.eps !== null ? row.eps.toFixed(2) : "—"}
              </TableCell>
              <TableCell className="px-1 py-1 text-right text-foreground">{pct(row.eps_chg_pct)}</TableCell>
              <TableCell className="px-1 py-1 text-right font-semibold text-foreground" title={row.sales_actual != null && row.sales_estimate != null ? `Actual ${sales(row.sales_actual)} · estimate ${sales(row.sales_estimate)}` : undefined}>
                {row.sales_m !== null ? row.sales_m.toFixed(0) : "—"}
              </TableCell>
              <TableCell className="px-1 py-1 text-right text-foreground">{pct(row.sales_chg_pct)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function EarningsPanel({
  quarterly,
  annual,
  ticker,
  asOfDate,
}: {
  quarterly: QuarterlyGrowthPoint[];
  annual: AnnualGrowthPoint[];
  ticker: string;
  asOfDate?: string;
}) {
  const quarters = [...quarterly].sort((a, b) => (b.report_date || "").localeCompare(a.report_date || "")).slice(0, 10);
  const years = [...annual].sort((a, b) => String(b.year).localeCompare(String(a.year))).slice(0, 12);

  return (
    <section className="space-y-2">
      <p className="text-[9px] text-ink-muted">Reported results, estimates and trends</p>
      <Tabs defaultValue={quarters.length ? "quarterly" : "annual"}>
        <TabsList className="grid h-8 w-full grid-cols-3">
          <TabsTrigger className="py-1 text-[10px]" value="quarterly">Quarterly</TabsTrigger>
          <TabsTrigger className="py-1 text-[10px]" value="annual">Annual</TabsTrigger>
          <TabsTrigger className="py-1 text-[10px]" value="charts">Charts</TabsTrigger>
        </TabsList>
        <TabsContent value="quarterly" className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {quarters.length ? quarters.map((point) => <QuarterlyCard key={point.report_date} point={point} />) : (
            <p className="text-[10px] text-ink-muted">No quarterly series</p>
          )}
        </TabsContent>
        <TabsContent value="annual" className="mt-2">
          <AnnualRows rows={years} />
        </TabsContent>
        <TabsContent value="charts" className="mt-2">
          <EarningsEstimateChart
            ticker={ticker}
            asOfDate={asOfDate}
            quarterlyGrowth={quarterly}
            annualGrowth={annual}
            className="border-0 bg-transparent p-0 shadow-none"
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}
