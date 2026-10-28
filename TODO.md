# Next to do

## Resume next — comparable Close versus Expire P/L

Paused at user request on October 27 evening (Vancouver); continue when they resume.
Current cloud release: net-pnl-chart-20261027-cc39240e0293. No deployment pending.

Main dashboard now emphasizes total close-today profit and draws a single net P/L
bar. Remaining issue: rollover Expire still displays option-only cash/P/L while
Close displays the full stock+option result. Agree an explicit retained-stock
valuation at replacement expiry before changing the model or labeling a comparable
whole-position result. Existing call buyback remains required for a rollover;
the worthless replacement has no later buyback. Preserve all recorded cash once.
The user has accepted that distinction; avoid repeating the closed-call-accounting
debate. Detailed saved RKLB arithmetic and last stopping point are in the handoff.

## Stock-first New and selected-holding Delete — deployed October 27, 2026

Dashboard New starts with a USD stock purchase and permits option history afterward.
Delete removes the selected holding's owned records after confirmation, preserving
shared purchase/history records and suppressing reimport of deleted snapshot rows.
Independent purchase lots keep their own price/fees. Optimization calculations are
unchanged. These changes are deployed; current release details are in status/handoff-2026-10-27.md.

## Cumulative chart P/L — implemented October 27, 2026

The original limitation (recorded October 26) was that chart P/L used only the
latest option sale. Transactions now records linked buyback and sale legs, and
P/L traces the current contract back to its original opening sale. It includes
that opening premium plus each linked rollover sale, less buybacks and recorded
option fees. Close P/L subtracts stock purchase cost including recorded purchase
fees; Expire remains option-only and conditional on worthless expiry.

Enter the original contract in Option Opening Sale and every completed rollover
in Rollover. Closing Transactions recalculates accounting using saved quotes,
without fetching market data. Existing snapshots and broker credentials are not
modified. Quote timestamps remain visible; accounting updates do not freshen quotes.

Missing/duplicate openings, ambiguous links, cycles and different contract counts
make cumulative P/L unavailable. This supports a single constant-size chain per
position ID; partial rolls within one position need a richer lot ledger. Separate positions for
different strikes/expiries are supported, with one opening and allocated shares each.
Unrecorded trades/fees cannot be inferred. USD-only opening premiums currently
store gross amounts without opening-fee entry; future execution fees and taxes
remain excluded. Purchase fees are allocated in proportion to held shares versus
saved basis quantity. This is position P/L for recorded history, not account equity.

## 1. Research intraday liquidity and trade timing

Captured October 21, 2026 at the user's request. Documentation only; no model,
quote collector, scheduling or order execution is implemented by this item.

**Challenge:** liquidity and bid–ask spreads can change during the trading day.
A suitable covered-call strategy may have different execution costs depending on
when its stock and option legs are traded.

**Proposed solution:** investigate an ML model that estimates upcoming windows
with narrower, executable bid–ask spreads for the selected holding / option
contract. Frame the result as a conditional liquidity window, rather than a
promise of the best time or price. Timing a narrow spread does not necessarily
maximize trade proceeds or overall profit.

Suggested first steps:

1. Verify access, timestamps, granularity, retention rights and rate limits for
   intraday stock and exact-contract option quotes. Collect bid, ask, displayed
   sizes and quote age across sessions; candles alone do not supply spread data.
2. Define the prediction horizon, trade size and intended action: open, close or
   roll. For a rollover, evaluate both option legs and their combined execution
   cost rather than the spread of just one leg.
3. Compare absolute spread and spread relative to midpoint, together with quote
   size, freshness and available execution evidence. Reject stale, crossed or
   otherwise unusable quotes. A narrow displayed spread is not a guaranteed fill.
4. Establish a simple time-of-day baseline, then test whether ML improves forecasts
   using only information available at the decision time. Evaluate chronologically
   on later sessions and across relevant stocks, contracts and market conditions.
5. Account for the cost of waiting: the stock and option prices can move while a
   spread narrows. Define success in terms of useful execution-cost improvement
   and reliable guidance, with uncertainty and an unavailable-data fallback.

**Architecture:** keep data acquisition and credentials in application services;
keep training, evaluation and inference in an independent model under
`models/financials/`. Expose any future predictions through FastAPI to React.
No replacement of the accepted option-pricing model is implied.

**First deliverable when authorized:** a feasibility / data-coverage assessment and
an agreed target and evaluation plan before model implementation. This is the next
item to discuss; implementation still follows the user's step-by-step direction.
