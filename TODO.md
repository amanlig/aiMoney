# Next to do

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
