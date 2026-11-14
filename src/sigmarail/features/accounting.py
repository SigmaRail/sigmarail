"""Offline accounting contract C-ACCOUNTING-V1; decimal strings, indexed evidence.

Consumes an explicitly complete sanitized accountingEvidence envelope, never orders
as fills. FIFO is a diagnostic convention, not an assertion about engine matching.
The independent repository copies are checked against shared contract examples.
"""
from decimal import Decimal, InvalidOperation, localcontext


_REQUIRED = ("start_cash", "end_cash", "start_equity", "end_equity",
             "opening_lots", "fills", "marks", "adjustments", "orders",
             "corporate_actions", "fx", "rounding_bound", "currency", "complete")
def _allocate_fee(total, quantity, remaining_quantity):
    """Allocate at source precision; the final portion receives the exact remainder."""
    if quantity == remaining_quantity:
        return total
    return total * quantity / remaining_quantity


def reconcile_accounting(artifact):
    """Return JSON-safe diagnostics; missing evidence never means zero activity."""
    result = {"contract": "C-ACCOUNTING-V1", "status": "unreconciled",
              "missing_artifacts": [], "unresolved_reasons": [],
              "closed_portions": [], "holdings": [],
              "position_episodes_closed": 0, "unfilled_orders": [],
              "precision": "Decimal(50); decimal strings required; target 0.01",
              "matching": "FIFO diagnostic", "cash_residual": None,
              "equity_residual": None, "pnl_residual": None}
    evidence = artifact.get("accountingEvidence") if isinstance(artifact, dict) else None
    if not isinstance(evidence, dict):
        result["missing_artifacts"] = ["accountingEvidence." + k for k in _REQUIRED]
        return result
    missing = [k for k in _REQUIRED if k not in evidence]
    result["missing_artifacts"] = ["accountingEvidence." + k for k in missing]
    if missing:
        return result

    def dec(value):
        if not isinstance(value, str):
            raise ValueError("decimal_strings")
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("finite_decimals")
        return number

    def ref(section, index):
        return "accountingEvidence." + section + "[" + str(index) + "]"

    # Validate every record before accumulating: invalid late evidence must not
    # leave apparently usable partial totals or matches in the public result.
    path = "accountingEvidence"
    try:
        for section in ("orders", "opening_lots", "fills", "marks", "adjustments", "corporate_actions", "fx"):
            path = "accountingEvidence." + section
            if not isinstance(evidence[section], list):
                raise ValueError("array required")
            for i, row in enumerate(evidence[section]):
                path = ref(section, i)
                if not isinstance(row, dict):
                    raise ValueError("object required")
                fields = {
                    "opening_lots": ("symbol", "quantity", "price", "mark", "currency"),
                    "fills": ("symbol", "quantity", "price", "fee", "currency", "fee_currency", "order_index"),
                    "marks": ("symbol", "price", "currency"),
                    "adjustments": ("kind", "amount", "currency"),
                    "orders": ("id", "symbol", "quantity"),
                }.get(section, ())
                for field in fields:
                    path = ref(section, i) + "." + field
                    if field not in row:
                        raise ValueError("required field")
                    if field in ("quantity", "price", "mark", "fee", "amount"):
                        dec(row[field])
                    elif field == "order_index":
                        if type(row[field]) is not int or not 0 <= row[field] < len(evidence["orders"]):
                            raise ValueError("valid order reference required")
                    elif field == "id":
                        if not isinstance(row[field], str) or not row[field].strip():
                            raise ValueError("nonempty auditable order ID required")
                    elif not isinstance(row[field], str) or not row[field]:
                        raise ValueError("nonempty string required")
        order_ids = [row["id"] for row in evidence["orders"]]
        if len(set(order_ids)) != len(order_ids):
            duplicate_index = next(i for i, value in enumerate(order_ids) if value in order_ids[:i])
            path = ref("orders", duplicate_index) + ".id"
            raise ValueError("unique order IDs required")
        order_quantities = [dec(row["quantity"]) for row in evidence["orders"]]
        filled_quantities = [Decimal(0) for _ in evidence["orders"]]
        for i, fill in enumerate(evidence["fills"]):
            order_index = fill["order_index"]
            path = ref("fills", i) + ".symbol"
            order = evidence["orders"][order_index]
            if fill["symbol"] != order["symbol"]:
                raise ValueError("fill symbol must match referenced order")
            quantity = dec(fill["quantity"])
            order_quantity = order_quantities[order_index]
            path = ref("fills", i) + ".quantity"
            if (order_quantity == 0 or quantity * order_quantity <= 0 or
                    abs(filled_quantities[order_index] + quantity) > abs(order_quantity)):
                raise ValueError("fill quantity must match and not exceed referenced order")
            filled_quantities[order_index] += quantity
        for field in ("start_cash", "end_cash", "start_equity", "end_equity", "rounding_bound"):
            path = "accountingEvidence." + field
            dec(evidence[field])
        with localcontext() as ctx:
            ctx.prec = 50
            e = evidence
            path = "accountingEvidence.complete"
            if e.get("complete") is not True:
                raise ValueError("complete source coverage attestation")
            # Unsupported transformations must remain explicit, never ignored.
            for section in ("corporate_actions", "fx"):
                for i, row in enumerate(e[section]):
                    path = ref(section, i)
                    required = (("symbol", "action", "quantity_before", "quantity_after", "price_basis",
                                 "effective_date", "source_reference") if section == "corporate_actions" else
                                ("from_currency", "to_currency", "rate", "timestamp", "source_reference"))
                    missing_fields = [field for field in required if field not in row]
                    result["unresolved_reasons"].append({
                        "code": "unsupported_" + section + "_entry",
                        "source_entry": path,
                        "required_evidence": [path + "." + field for field in missing_fields] or
                                             [path + ".source_reference", "normalized_account_currency_entry"],
                        "requirement": "C-ACCOUNTING-V1 does not apply FX or corporate-action transformations. Supply the missing source fields and normalized account-currency entries, or leave the ledger unreconciled until this transformation is supported.",
                    })
                    raise ValueError("unsupported transformation")
            path = "accountingEvidence.currency"
            currency = e["currency"]
            if currency != "USD":
                raise ValueError("USD conversion evidence")
            lots = {}
            opening_value = Decimal(0)
            opening_unrealized = Decimal(0)
            for i, row in enumerate(e["opening_lots"]):
                path = ref("opening_lots", i)
                q, p, mark = (dec(row[k]) for k in ("quantity", "price", "mark"))
                if q <= 0 or p < 0 or mark < 0 or row["currency"] != currency:
                    raise ValueError("positive long opening lots in account currency")
                lots.setdefault(row["symbol"], []).append([q, p, Decimal(0), ref("opening_lots", i)])
                opening_value += q * mark
                opening_unrealized += q * (mark - p)
            cashflow = fees = gross = allocated = Decimal(0)
            for i, row in enumerate(e["fills"]):
                path = ref("fills", i)
                q, p, fee = (dec(row[k]) for k in ("quantity", "price", "fee"))
                if q == 0 or p < 0 or fee < 0 or row["currency"] != currency or row["fee_currency"] != currency:
                    raise ValueError("signed nonzero fills and evidenced fee currencies")
                cashflow -= q * p
                fees += fee
                book = lots.setdefault(row["symbol"], [])
                if q > 0:
                    book.append([q, p, fee, ref("fills", i)])
                    continue
                remaining = -q
                exit_fee_remaining = fee
                if sum(lot[0] for lot in book) < remaining:
                    raise ValueError("opening holdings or short-lot support")
                while remaining:
                    lot = book[0]
                    matched = min(remaining, lot[0])
                    entry_fee = _allocate_fee(lot[2], matched, lot[0])
                    exit_fee = _allocate_fee(exit_fee_remaining, matched, remaining)
                    exit_fee_remaining -= exit_fee
                    pnl = matched * (p - lot[1])
                    portion_fees = entry_fee + exit_fee
                    gross += pnl
                    allocated += portion_fees
                    result["closed_portions"].append({"entry": lot[3], "exit": ref("fills", i),
                        "quantity": str(matched), "gross_pnl": str(pnl),
                        "fees": str(portion_fees), "net_pnl": str(pnl - portion_fees)})
                    lot[0] -= matched
                    lot[2] -= entry_fee
                    remaining -= matched
                    if not lot[0]:
                        book.pop(0)
                if not book:
                    result["position_episodes_closed"] += 1
            adjustments = Decimal(0)
            for i, row in enumerate(e["adjustments"]):
                path = ref("adjustments", i)
                if row["kind"] not in ("dividend", "cash_adjustment") or row["currency"] != currency:
                    raise ValueError("typed cash adjustments in account currency")
                adjustments += dec(row["amount"])
            marked = unrealized = Decimal(0)
            for symbol, book in lots.items():
                if not book:
                    continue
                path = "accountingEvidence.marks for holding entries " + ",".join(lot[3] for lot in book)
                matches = [(i, r) for i, r in enumerate(e["marks"]) if r["symbol"] == symbol]
                if len(matches) != 1 or matches[0][1]["currency"] != currency:
                    raise ValueError("unique terminal marks for every remaining holding")
                mi, mark = matches[0]
                path = ref("marks", mi) + ".price"
                price = dec(mark["price"])
                if price < 0:
                    raise ValueError("nonnegative mark required")
                quantity = sum(lot[0] for lot in book)
                value = quantity * price
                upnl = sum(lot[0] * (price - lot[1]) for lot in book)
                marked += value
                unrealized += upnl
                result["holdings"].append({"quantity": str(quantity), "value": str(value),
                    "unrealized_pnl": str(upnl), "mark": ref("marks", mi),
                    "entries": [lot[3] for lot in book],
                    "remaining_fees": str(sum(lot[2] for lot in book))})
            sc, ec, se, ee = (dec(e[k]) for k in ("start_cash", "end_cash", "start_equity", "end_equity"))
            path = "accountingEvidence.rounding_bound"
            bound = dec(e["rounding_bound"])
            if bound < 0:
                raise ValueError("nonnegative source rounding bound")
            residuals = [ec - (sc + cashflow - fees + adjustments),
                         ee - (ec + marked),
                         ee - se - (gross + unrealized - opening_unrealized - fees + adjustments),
                         se - (sc + opening_value)]
            result.update(cash_residual=str(residuals[0]), equity_residual=str(residuals[1]),
                          pnl_residual=str(residuals[2]), opening_equity_residual=str(residuals[3]),
                          gross_realized_pnl=str(gross), closed_allocated_fees=str(allocated),
                          net_realized_pnl=str(gross - allocated), event_fees=str(fees),
                          unrealized_pnl=str(unrealized), adjustments=str(adjustments),
                          rounding_bound=str(bound), signed_fill_cashflows=str(cashflow),
                          sources={"balances": ["accountingEvidence." + k for k in
                              ("start_cash", "end_cash", "start_equity", "end_equity")],
                              "adjustments": [ref("adjustments", i) for i in range(len(e["adjustments"]))],
                              "fills": [ref("fills", i) for i in range(len(e["fills"]))]},
                          order_count=len(e["orders"]), fill_event_count=len(e["fills"]),
                          unfilled_orders=[{"order_index": i, "order_id": e["orders"][i]["id"],
                                            "remaining_quantity": str(order_quantities[i] - filled_quantities[i])}
                                           for i in range(len(e["orders"]))
                                           if order_quantities[i] != filled_quantities[i]])
            # Requirements name evidence to inspect, not invented balancing entries.
            equation_evidence = {
                "cash_residual": ("start_cash", "end_cash", "fills", "adjustments", "fx"),
                "equity_residual": ("end_cash", "end_equity", "opening_lots", "fills", "marks", "corporate_actions", "fx"),
                "pnl_residual": ("start_equity", "end_equity", "opening_lots", "fills", "marks", "adjustments", "corporate_actions", "fx"),
                "opening_equity_residual": ("start_cash", "start_equity", "opening_lots", "fx"),
            }
            for equation, residual in zip(equation_evidence, residuals):
                if abs(residual) > Decimal("0.01"):
                    result["unresolved_reasons"].append({
                        "code": "equation_residual_exceeds_tolerance",
                        "equation": equation, "residual": str(residual), "tolerance": "0.01",
                        "required_evidence": ["accountingEvidence." + k for k in equation_evidence[equation]],
                        "requirement": "Full-precision source entries and completeness attestations for the named sections; identify any correcting entry by source reference. No balancing adjustment.",
                    })
            if bound > Decimal("0.01"):
                result["unresolved_reasons"].append({
                    "code": "source_rounding_bound_exceeds_tolerance",
                    "required_evidence": ["accountingEvidence.rounding_bound"],
                    "requirement": "Full-precision source artifacts with a documented rounding bound at or below 0.01.",
                })
            # Rounding bounds explain uncertainty; never widen the acceptance target.
            if all(abs(r) <= Decimal("0.01") for r in residuals) and bound <= Decimal("0.01"):
                result["status"] = "reconciled"
    except (KeyError, TypeError, ValueError, InvalidOperation, IndexError, ArithmeticError):
        result["closed_portions"] = []
        result["holdings"] = []
        result["position_episodes_closed"] = 0
        result["missing_artifacts"].append(path)
    return result
