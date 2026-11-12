/**
 * Insights / Measures field picker = authored measure aliases ∪ L7.
 * Re-exports slotFieldCatalog (no phantom combinator aliases).
 *
 * Measures own math: gate/setup bools + Stage.computed_expr number aggregates.
 * Insights bind aliases: emit SlotExprs, Confidence col/formula, stop_loss, pyramid.
 */
export { slotFieldCatalog as insightsFieldCatalog } from "./slotFieldCatalog";
