# Next to do

Session wrapped October 29, 2026 (Vancouver). Resume October 30 with the user;
no next feature selected or scheduled. See [latest handoff](docs/progress-2026-10-29.md).

## Future work — user-controlled rollover criteria and pricing assumptions

Requested October 28, 2026 (Vancouver), at session wrap-up. Planning only;
implement when the user resumes and selects the next change.

1. **Dynamic strike criteria — implemented locally October 30:** optimizer-page
   controls expose purchase-price multiplier (default 1.2×) and an inclusive
   percentage range relative to midpoint (default 0% to uncapped; negatives allow
   ITM calls while preserving the purchase floor). Changes apply only
   through Refresh data & analyze; no separate Reevaluate button. Model, slider,
   recommendations and CSV use the applied parameters. Awaiting deployment.
2. **Dynamic expiry-date range:** let users choose the earliest and latest
   replacement expirations used for selection. Validate date order and use
   listed, unexpired contracts within the chosen range.
3. **Editable implied volatility:** allow an explicit IV scenario override for
   option pricing, with clear annual-percent units, the captured/calibrated
   reference and reset. Decide whether the control applies to the held call,
   replacement calls or both; historical-return stock paths remain a separate
   input. Scenario changes must not overwrite saved market quotes.
4. **U.S. Treasury interest-rate default — deployed October 29:**
   Profile → Settings supports a maturity-matched Treasury default and manual
   annual-yield override, persisted per browser. The app interpolates the held
   call's maturity, converts the bond-equivalent yield to a continuous rate and
   passes it explicitly to evaluation/repricing/recommendations. Source/date and
   rate appear in settings, analysis and CSV. This uses one rate for all calls
   and discounting; full per-maturity curve pricing remains future work.
   Source: https://home.treasury.gov/treasury-daily-interest-rate-xml-feed


Apply selected criteria and pricing assumptions consistently to simulations,
rankings and the full CSV download. Show assumptions and quote/rate dates in
exports; fetching a wider contract range may require an explicit data refresh.
No implementation or cloud deployment is authorized by this backlog entry alone.

Latest cloud release: report-alignment-20261029-208da5c9d250. Interest-rate settings, rollover-field reset and numeric/text report heading alignment are deployed; no deployment pending.
Latest session handoff: status/handoff-2026-10-30.md. Configurable strike criteria are verified locally and await deployment.

## Outstanding — comparable Close versus Expire P/L

Carried forward from October 27. On October 28 the user accepted exploring an
editable stock-price-at-replacement-expiry scenario. That valuation control and
comparable full-position Expire result remain unimplemented.

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

## Liquidity model — canceled October 29, 2026

User canceled intraday liquidity-model research and quote-collection plans.
Close today instead uses the stock midpoint less the held-call midpoint, scaled
by shares and contracts. Midpoints estimate value; they do not guarantee fills.
Actual Close execution entries and captured bid/ask snapshots remain unchanged.

## Next session — October 30 checkpoint

Discuss adding Cox–Ross–Rubinstein (CRR) binomial option pricing alongside
Black–Scholes. Begin with model scope, American exercise handling, calibration
and runtime implications before implementation. No pricing-model change has
been implemented or authorized yet.

Latest local dashboard changes: owned-position slider left, replacement-call
criteria right; cash/buying power default to zero; over-budget rollover groups
have transparent diagonal hatching bounded by the chart's top and bottom grid
lines. Existing saved balances are preserved. Cloud deployment remains pending.
See `status/handoff-2026-10-30.md` for the detailed checkpoint.
