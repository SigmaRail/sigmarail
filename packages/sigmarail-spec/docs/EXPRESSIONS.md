# SigmaRail expression dialect

Everything a Vera spec or screener query can say, in one page. The dialect is a pydantic
discriminated union: the `type` field selects the node class, every field is validated, and
`extra="forbid"` rejects typos instead of ignoring them.

Two unions exist, and picking the right one matters:

| Union | Accepts | Use for |
|---|---|---|
| `BoolExprItem` | boolean nodes + comparators | anything that answers true/false — filters, gates, eligibility |
| `SpecExpr` | `BoolExprItem` **plus** `col`, `lit`, `formula` at the root | fields that may hold a bare value, e.g. `weight_expr`, `confidence_expr` |

`WhereExpr` is the filter-only subset (`all`, `any`, `not`, `gt`, `gte`, `lt`, `lte`, `eq`, `neq`).

**Scope boundary.** This dialect expresses *predicates and operands* — classification and
arithmetic over rows and runtime contexts. It deliberately does **not** express effects
(state mutation, order emission, bookkeeping): those live in the bounded `then` action
vocabulary the slots interpret (`enter`/`resize`/`displace`/`exit`/…, versioned). A node
that would need sequencing, iteration, or writes does not belong here — that's the line
between a decision document and a program. Side effects, sequencing, and state changes belong to
the strategy actions that consume expressions.

## Boolean combinators

| `type` | Class | Fields |
|---|---|---|
| `all` | `AllExpr` | `items: BoolExprItem[]`, `name: str \| None` |
| `any` | `AnyExpr` | `items: BoolExprItem[]`, `name: str \| None` |
| `not` | `NotExpr` | `item: BoolExprItem` |

`all` / `any` with an empty `items` list evaluate to **true**. `name` is a label only — it has
no runtime effect.

## Comparisons over operands

| `type` | Class | Fields |
|---|---|---|
| `gt` / `gte` / `lt` / `lte` / `eq` / `neq` | `CmpGt` / `CmpGte` / `CmpLt` / `CmpLte` / `CmpEq` / `CmpNeq` | `left: Operand`, `right: Operand` |

These compare two **operands**, so `col OP col`, `col OP literal` and arithmetic on either side
all work. If either side resolves to `None` — a missing column, or division by zero — the
comparison is **false**.

## Flat column predicates

Shorthand for "this column against one value". `between` and `in_tickers` are inclusive and
case-sensitive respectively.

| `type` | Class | Fields | Meaning |
|---|---|---|---|
| `col_gte` | `ColGteExpr` | `column: str`, `value: float \| int` | `row[column] >= value` |
| `col_lte` | `ColLteExpr` | `column: str`, `value: float \| int` | `row[column] <= value` |
| `col_eq` | `ColEqExpr` | `column: str`, `value: bool \| float \| int` | `row[column] == value` |
| `between` | `ColBetweenExpr` | `column: str`, `min: float \| int`, `max: float \| int` | `min <= row[column] <= max` (**inclusive**); `min` must be `<= max` |
| `in_tickers` | `InTickersExpr` | `tickers: str[]` (non-empty) | `row["ticker"]` is in the list. This is how an ETF universe restricts itself |

## Operands

| `type` | Class | Fields |
|---|---|---|
| `col` | `ColRef` | `name: str`, `offset: int = 0` |
| `pos` | `PosRef` | `field: str` — a **runtime position binding** (see below); deprecated spelling of `ref{ns:"pos"}` |
| `ref` | `BindingRef` | `ns: str`, `field: str` — a **namespaced runtime binding** (see below) |
| `lit` | `LitVal` | `value: float \| int \| str \| bool` |
| `formula` | `FormulaExpr` | `op: "+" \| "-" \| "*" \| "/"`, `args: Operand[]` — **exactly two** |
| `min` | `MinExpr` | `args: Operand[]` — non-empty; smallest of the args |
| `max` | `MaxExpr` | `args: Operand[]` — non-empty; largest of the args |
| `clamp` | `ClampExpr` | `value: Operand`, `min: Operand`, `max: Operand` — `min(max(value, lo), hi)` |
| `abs` | `AbsExpr` | `arg: Operand` — absolute value |
| `cond` | `CondExpr` | `when: BoolExprItem`, `then: Operand`, `otherwise: Operand` — piecewise |

The V2 operand set exists so model quantities — initial stops, sizing budgets, regime
scales — can live **in the spec** rather than in code. `cond` is the piecewise node:
its `when` is evaluated with **fail-closed slot semantics**, so a missing column or an
unevaluatable predicate selects `otherwise`. That makes `otherwise` the graceful-
fallback branch by design (`cond(atr > 0, max(entry − 2·atr, 0.95·entry), 0.95·entry)`).
The name is `otherwise`, not `else`, because `else` is a Python keyword and a field
alias would leak into every serializer.

`offset` is a prior-bar reference (`0` = current row, `1` = the previous one). **The row
evaluators ignore it**: they look the column up in the row dict as-is, so `offset: 5` and
`offset: 0` return the same value. It is honoured by the **SQL compiler**
(`compile_bool_expr_sql` in VeraBase emits a correlated subquery for a non-zero offset).
So a prior-bar reference only takes effect on the warehouse/query path, not in the LEAN
runtime — do not rely on it in a row-evaluated slot expression.

`formula` nests through `args`, so `(a + b) / 2` is a `formula` whose division `args` are
another `formula` and a `lit`. A third argument is rejected. Division by zero yields `None`
rather than infinity, which makes the enclosing comparison false.

`pos` names a field of the **runtime position context**, not a row column —
`entry`, `r`, `current_stop`, `highest_price`, `days_held`, `runner_active`, and friends.
The slot evaluators (`evaluate_slot_number` / `evaluate_slot_bool`) accept a `position`
dict and merge it into the lookup namespace, so `{"type": "pos", "field": "r"}` resolves
exactly where a live position exists. In a **row-only** evaluation (universe `where` /
`computed`, ClickHouse lowering) no position exists: `pos` resolves to `None`, comparisons
fail closed, and consumers compiling to SQL **reject the node outright** — it can never
silently mean "some column". This replaced the older `{"type": "col", "name":
"__position.<field>"}` spelling, which encoded the binding as a magic name prefix.

`ref` generalizes `pos` to **any runtime namespace**: `{"type": "ref", "ns": "hold",
"field": "weight"}` resolves a field of the named context dict — `pos` (position;
the `pos` node is a deprecated spelling of `ref{ns:"pos"}`), `hold` (held-holding
state), `cand` (candidate insight), `acct` (portfolio/account), `pyr` (pyramid
phase), `regime` (regime inputs), or any namespace a consumer registers. Slot
evaluators take `contexts={ns: dict}` and merge each under `__<ns>.`; a missing
namespace or field resolves to `None` (fails closed in comparisons). Same
row-only rule as `pos`: not a column, SQL compilers must reject it.

All operand nodes share one failure convention: **any operand that resolves to `None`
propagates `None`** — `min`/`max`/`clamp`/`abs` return `None` if any input is `None`, and
`cond` returns whatever the selected branch evaluates to (which may itself be `None`).

## Context-requiring nodes

These need a **regime or signal context**, not a plain screener row. They are deliberately not
row-evaluable, and `evaluate_where_ast` / `evaluate_slot_bool` do **not** claim them — the
latter returns its fallback (`False`) so a slot gate stays closed. Evaluate them through the
runtime's trigger path instead.

| `type` | Class | Fields | Notes |
|---|---|---|---|
| `signal` | `SignalExpr` | `ticker: str`, `column: str`, and **exactly one** of `gt` / `gte` / `lt` / `lte` / `eq` | Reads a stored signal column for a named ticker |
| `signal_compare` | `SignalCompareExpr` | `ticker: str`, `left: str`, `op: lt\|lte\|gt\|gte\|eq`, `right: str` | Compares two signal columns for one ticker |
| `regime` | `RegimeExpr` | `field: str`, `source: str = "regime"`, and **exactly one** of `eq` / `gte` | `source` names the data source (`regime`, `vix`, `macro`, `technical`, …) |
| `regime_allows_entries` | `RegimeAllowsEntriesExpr` | `eq: bool \| int = 1` | Admission gate |
| `regime_mart_allows_entries` | `RegimeMartAllowsEntriesExpr` | `eq: bool \| int = 1` | Admission gate (MART variant) |

## Sites: where an expression may live

The dialect is one global union, but **legibility is per-site** — a node that
parses is not necessarily resolvable where it sits. The site contract is data,
declared once in `vera_query_core/ir/expression_sites.py` (the manifest
`spec_lint` reads for E111/E112/E113 and the legibility-matrix tests assert
against evaluator reality):

| Site | Evaluator | `ref` namespaces | Boundary |
|---|---|---|---|
| Universe `where`/`screen`/`computed`, stage filters, `eligibility_expr` | `row` (screener columns + SQL lowering) | — | fail-open |
| Graph-policy `if` `condition` | `policy_eval` (SignalContext) | — | raise |
| PCM `size_expr`/rule `when`/`then` args | `slot` | `cand` `hold` `acct` `pyr` `regime` | fail-closed |
| PCM `scale_expr`/`slots_expr` (book) | `slot` | `acct` `regime` | fail-closed |
| PCM `order_expr` (unit sort) | `slot` | `cand` `hold` `acct` `regime` | fail-closed |
| `displace.incumbent_score` | `slot` | `hold` `acct` `regime` — `hold` = the *incumbent* | fail-closed |
| Risk `rules[].when`/`then` args, `risk_skip_time_stop_expr` | `slot` | `pos` `acct` `regime` — acct/regime read-only | fail-closed |
| Risk `init_stop` | `slot` | `pos` only — fill-time | fail-closed |

Two consequences worth remembering: `signal`/`regime`/`signal_compare`/
`regime_*` nodes are legible **only** inside graph-policy `condition`s (E113
elsewhere — a `regime` node in an `eligibility_expr` is silently dead), and
`ref`/`pos` outside their site's namespace set is E112 (`cand` in a Risk rule
fails at lint, not mysteriously at runtime). Path→site matching is
segment-boundary aware: graph-policy `condition` (singular) vs stage-filter
`conditions[]` (plural) classify differently.

## Evaluating

| Function | Returns | Empty node | Unknown node |
|---|---|---|---|
| `evaluate_where_ast(row, node)` | `bool` | `True` (no filter = keep) | `True` — **fail-open** |
| `evaluate_slot_bool(row, node, *, position=None, contexts=None)` | `bool` | `False` (no rule = refuse) | `False` — **fail-closed** |
| `evaluate_slot_number(row, expr, *, position=None, contexts=None)` | `float \| None` | `None` | `None` |
| `evaluate_single_trigger(row, trigger, *, current_price=None)` | `bool` | `True` | `True` |
| `evaluate_entry_triggers(row, triggers, *, current_price=None)` | `bool` | `True` (OR over an empty list) | — |

**The `where` / slot asymmetry is deliberate and is the easiest thing to get wrong.** An
unimplemented node inside a `where` filter returns `True`, so it filters out nothing — a filter
that silently does nothing rather than failing loudly. Inside a slot expression the same node
returns `False`, which refuses the entry. `tests/test_coverage.py` exists to keep every
declared node implemented, so this fallback should never carry real weight.

Both bool evaluators share a tri-state core: an *unresolvable* node type evaluates to `None`
internally and propagates through `all`/`any`/`not`, so `not <unknown>` can never be laundered
into `True` by negation — at the slot boundary it is still `False`. Missing **data** is not
tri-state: a comparator with a `None` operand resolves `False` before negation, so
`not (absent_col > 0)` stays `True` — the permissive reading an optional-context `when` wants.

`position=` merges the caller's position fields in as `__position.*` keys, which is how a
`risk_skip_time_stop_expr` can reference the open position.

## Validating

**Parsing and evaluating take different things.** `parse_bool_expr` / `TypeAdapter` return
**pydantic models**; the evaluators take a **plain dict** (`node.get("type")`), which is
what the stored IR holds. So validate with the model, then evaluate the dict — or call
`node.model_dump()` if you only have the model.

`parse_bool_expr(data)` validates against `BoolExprItem`; `TypeAdapter(SpecExpr)` does the same
for operand-rooted fields. `bool_expr_depth(node)` reports nesting, and
`validate_bool_expr_depth(node)` raises past `MAX_BOOL_DEPTH` (24). `MAX_FORMULA_DEPTH` is 8.
`is_runtime_only_expr(node)` is true for the context-requiring nodes above.

Note `bool_expr_depth` raises `TypeError` on an operand root — it walks boolean trees only.

## Lowering: what this compiles to

The same tree is consumed two ways, and because the *shape* is shared they agree by
construction:

| Path | Lowered by | Produces |
|---|---|---|
| warehouse / query | `compile_bool_expr_sql` and the `query_compile` builders, in **VeraBase** | ClickHouse SQL |
| LEAN runtime | `evaluate_where_ast` / `evaluate_slot_bool`, in this package | a boolean per row |

SigmaRail Spec owns the shape; the consumers own the lowering. That split is why this package can be
pydantic-only and still be the single source of truth.

Literals never reach the SQL string — they become **query parameters**, so an expression cannot
inject SQL. The placeholder names are **generated from position**, so they carry no meaning:
`w_a4_Rlit_0` is `w_` prefix · `a4` the 5th child of the `all` (0-indexed) · `R` its right
operand · `lit` a literal · `_0` the first literal on that path. Read the `params` mapping.
In every snippet below, `{...}` is a placeholder for a value supplied separately — never a
value that was dropped:

```sql
-- {"type": "gte", "left": {"type": "col", "name": "rs_rating"}, "right": {"type": "lit", "value": 85}}
px.rs_rating >= {w_Rlit_0:Int64}                    -- params: w_Rlit_0 = 85

-- {"type": "col_gte", "column": "rs_rating", "value": 85}
px.rs_rating >= {w_cg:Float64}

-- {"type": "between", "column": "rs_rating", "min": 80, "max": 99}
px.rs_rating BETWEEN {w_b0:Float64} AND {w_b1:Float64}

-- {"type": "in_tickers", "tickers": ["SPY", "QQQ"]}
px.ticker IN ({w_t0:String}, {w_t1:String})
```

Operands and formulas both lower, including column-vs-column comparison:

```sql
-- close >= ema21d AND volume <= 0.7 * avg_vol_20d
(px.close >= px.ema21d) AND (px.volume <= ({w_a1_RfLlit_0:Float64} * px.avg_vol_20d))

-- the trend template: close above the 50/150/200-day, the 150 above the 200, RS >= 85
(px.close >= px.sma50d) AND (px.close >= px.sma150d) AND (px.close >= px.sma200d)
  AND (px.sma150d >= px.sma200d) AND (px.rs_rating >= {w_a4_Rlit_0:Int64})
```

And here is the compiled filter inside a whole `universe_query_v1` query — the L7 spine, the
`FINAL` on each table, the satellite join, the `ORDER BY` and `LIMIT` that the spec's
`limit_per_day` carries:

```sql
SELECT
    toDate(px.date) AS date,
    px.ticker AS ticker,
    rt.overall_score AS overall_score,
    px.atr_14_pct AS atr_14_pct
FROM screener_price_tech_daily AS px FINAL
LEFT ANY JOIN screener_ratings_daily AS rt FINAL
    ON px.ticker = rt.ticker AND px.date = rt.date
WHERE px.date = toDate('2026-03-02')
  AND ((px.ticker IN ('SPY')) OR ((px.close >= 10.0) AND (px.volume >= 500000.0)
       AND (rt.has_vcp_setup = 1) AND (rt.is_stage_2_advancing = 1)
       AND (px.minervini_tt_score_full >= 80.0)))
ORDER BY rt.overall_score DESC, px.ticker ASC
LIMIT 500
FORMAT JSONEachRow
```

Two things that SQL block demonstrates, both easy to get wrong in an expression:

* **Column names must exist in the registry.** `sma50d` does; `sma_50d` does not, and the
  compiler raises `unknown or disallowed column`. The *row* evaluator will not complain — it
  reads whatever key is in the row dict — so a typo looks fine until it reaches the warehouse.
* **`FINAL` follows the alias** (`AS px FINAL`). ClickHouse does not overwrite rows, so a
  satellite read without it can return a stale version.

> These SQL snippets are snapshots emitted by the named VeraBase functions; the compiler's own
> tests live with it. The expressions quoted above are the same ones used in
> [`../examples/01_parse_and_validate.py`](../examples/01_parse_and_validate.py) and
> [`../examples/02_evaluate_a_row.py`](../examples/02_evaluate_a_row.py), which are executed by
> `tests/test_examples.py`.

## What is not here

* **Column resolution.** Whether `rs_rating` exists is a database question. VeraBase answers it
  against the live catalog and its DDL-derived registry; this package never queries anything.
* **SQL compilation.** `compile_bool_expr_sql` (VeraBase) and the graph criteria lowerer
  (VeraTradingLab) turn these trees into ClickHouse SQL — see
  [Lowering](#lowering-what-this-compiles-to) above. Lowering is layer-specific; *shape* is
  not, which is why only shape lives here.
* **Per-`Type` parameter models** and the LEAN-bound runtime classes. Those impose the Lean
  five-slot design and belong in VeraTradingLab.
* **`E100`/`E110`/`E200`/`E201` spec linting.** That is `C-SPEC-LINT-V1` in VeraBase, which
  consumes this dialect rather than re-declaring it.
