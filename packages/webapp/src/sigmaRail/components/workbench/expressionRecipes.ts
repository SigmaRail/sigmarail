import type { ExpressionRecipe } from "../../lib/fieldPick";

/**
 * Shared library of named expression recipes (filters / rankers). One source of
 * truth used by the unified Field/Expression browser and the filter editor.
 */
export const EXPRESSION_RECIPES: ExpressionRecipe[] = [
  {
    id: "exclude-ipo-history",
    label: "Exclude Recent IPOs (2Y+ History)",
    expr: "growth_rate_pct > -100",
    desc: "Excludes recent IPOs by requiring 2+ years of historical financial reports",
    category: "IPO Filter",
    purposes: ["filter"],
  },
  {
    id: "exclude-ipo-sma",
    label: "Exclude Recent IPOs (200d+ SMA)",
    expr: "sma200d > 0",
    desc: "Excludes recent IPOs by requiring an established 200-day moving average",
    category: "IPO Filter",
    purposes: ["filter"],
  },
  {
    id: "atr-breakout",
    label: "ATR Breakout",
    expr: "(close - sma50d) / atr_14 >= 2.0",
    desc: "Price expands 2+ ATRs above 50-day SMA",
    category: "Technical",
    purposes: ["filter"],
  },
  {
    id: "pct-above-52w-low",
    label: "+30% from 52W Low",
    expr: "close >= low_52w * 1.30",
    desc: "Stage 2 criterion: at least 30% above 52-week low",
    category: "Trend",
    purposes: ["filter"],
  },
  {
    id: "within-52w-high",
    label: "Within 25% of 52W High",
    expr: "close >= high_52w * 0.75",
    desc: "Near all-time/annual highs (Minervini rule)",
    category: "Trend",
    purposes: ["filter"],
  },
  {
    id: "golden-cross-spread",
    label: "Golden Cross Spread",
    expr: "(sma50d - sma200d) / sma200d >= 0.05",
    desc: "50-day SMA is 5%+ above 200-day SMA",
    category: "Technical",
    purposes: ["filter"],
  },
  {
    id: "volume-surge",
    label: "Volume Surge (2x)",
    expr: "volume / avg_vol_20d >= 2.0",
    desc: "Volume is double the 20-day average",
    category: "Volume",
    purposes: ["filter"],
  },
  {
    id: "rs-leader",
    label: "RS Leader (≥70)",
    expr: "rs_rating >= 70",
    desc: "Relative Strength in top 30% of market",
    category: "Momentum",
    purposes: ["filter", "column"],
  },
  {
    id: "stage-2",
    label: "Stage 2 Advancing",
    expr: "is_stage_2_advancing == 1",
    desc: "Stan Weinstein Stage 2 markup phase",
    category: "Trend",
    purposes: ["filter", "column"],
  },
  {
    id: "volume-thrust-breakout",
    label: "Volume Thrust Breakout",
    expr: "high >= high_90d and volume >= avg_vol_50d * 1.40",
    desc: "High clears 90d high with volume ≥ 1.4× 50d average. Setup arm (not a screens_hit gate).",
    category: "Setup",
    purposes: ["filter"],
  },
  {
    id: "vcp-compression",
    label: "VCP Compression",
    expr:
      "vcp_atr_compression_5d_90d <= 0.40 and vcp_volume_dryup_5d_90d <= 0.70 and close >= high_90d * 0.90",
    desc: "Minervini VCP dry-up + proximity to 90d high. Add as setup_pass ALL-group / OR arm.",
    category: "Setup",
    purposes: ["filter"],
  },
  {
    id: "pocket-pivot",
    label: "Pocket Pivot",
    expr: "pocket_pivot_score >= 30",
    desc: "L7 pocket pivot score. Optional OR arm with breakout / VCP for setup_pass.",
    category: "Setup",
    purposes: ["filter"],
  },
  {
    id: "close-vs-sma50-atr",
    label: "ATR-Distance from 50 SMA",
    expr: "(close - sma50d) / atr_14",
    desc: "How many ATRs price sits above its 50-day SMA",
    category: "Rank / Sort",
    purposes: ["sort"],
  },
  {
    id: "close-vs-sma200-pct",
    label: "% Above 200 SMA",
    expr: "(close - sma200d) / sma200d",
    desc: "Percentage distance above the 200-day SMA",
    category: "Rank / Sort",
    purposes: ["sort"],
  },
  {
    id: "close-vs-sma50-pct",
    label: "% Above 50 SMA",
    expr: "(close - sma50d) / sma50d",
    desc: "Percentage distance above the 50-day SMA",
    category: "Rank / Sort",
    purposes: ["sort"],
  },
];

export default EXPRESSION_RECIPES;