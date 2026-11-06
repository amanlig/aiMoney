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

## Outstanding — comparable full-position P/L for rollover Close versus Expire

Clarified November 6, 2026. This item concerns the replacement-call rollover
choices, rather than the current-position Close / Assigned / Buyback controls.

Completed: current-position Close and Assigned include the value of excess shares
that remain owned, using the captured stock midpoint. Retained stock value is
shown separately from cash. Current-position Buyback remains option-only P/L.

Still outstanding: rollover Expire displays option-only P/L, while rollover Close
displays the full stock-plus-option result. Add an explicit stock valuation at the
replacement expiry so both rollover choices can show comparable full-position P/L,
with retained stock value separate from cash. The editable stock-price-at-replacement-
expiry scenario discussed October 28 remains unimplemented; agree its valuation
assumptions before changing the model.

The existing-call buyback remains required for a rollover; a replacement assumed
to expire worthless has no later buyback. Include recorded historical cash and fees
once. The option-only Expire calculation and its current label remain intentional
until the full-position comparison is implemented.

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

## Deployment checkpoint — November 2

Current local purchase/dashboard changes deployed successfully as
`purchase-rows-20261102-eef483c564ca`; earlier pending-deployment notes are
superseded. Detailed checkpoint: `status/handoff-2026-11-02.md`.
CRR pricing remains a future discussion item.

## Future work — predict call-selling profitability

Explore a predictive model using historical stock prices and the user's
validated trade outcomes/profitability to estimate whether selling call options
will produce a profit and the expected dollar amount. This is a research and
design backlog item; implementation has not started.

- Define the prediction target: option-only net profit versus total covered-call
  position profit, including fees, buybacks, rollovers and assignment outcomes.
- Use historical stock prices and validated transaction outcomes; assess what
  historical option premiums, strikes, expiries and volatility data are needed.
- Evaluate probability of profit and expected net profit with uncertainty, using
  chronological out-of-sample validation and safeguards against future-data
  leakage. Compare with the existing simulation baseline and assess whether
  sufficient validated trades exist before choosing a model.

## Future work — buy back call, hold shares, sell call at target

Explore a comparison strategy that buys back the existing short call now at its
captured ask, retains the shares, and waits to sell a new covered call until the
stock reaches a configurable target. Default target: 20% above the captured
current stock midpoint. Keep the target fixed until the user explicitly resets
it. This is a backlog item, not an implementation request.

- UI parameters: target percentage, maximum waiting period, and new call time
  to expiry; apply the user's replacement-strike rules at the trigger.
- Simulate the first target crossing on each stock-price path. Estimate the
  replacement premium at that time using simulated price, time to expiry,
  volatility and spread assumptions; today's quotes do not establish future
  executable premiums. Paths missing the target retain stock and sell no call.
- Compare against Close today and immediate rollover at a common evaluation
  date. Separate cash returned from retained stock value and total position P/L.
- Display initial buyback cash required, share of paths reaching the target,
  waiting-time statistics, premium if triggered, and ending cash/stock/P&L.
- Account for historical option cash and fees consistently. Specify handling of
  the new call at the common horizon and assignment. Show the uncapped stock
  downside and the possibility that the target is never reached.

## End-of-day checkpoint — November 3, 2026

Latest deployed release: `covered-close-report-20261103-bc38d082283b`.
Covered-only Close, retained-stock chart segments, excess-share support and
separate transaction-report purchase rows are live. Detailed handoff:
`status/handoff-2026-11-03.md`. Prior pending-deployment notes are superseded.

CIBC observations remain local and outside training. Outstanding reference
cleanup: retrieve Oct 29's same-day Yahoo close; confirm Oct 26's reference
date. Longer-term model research items remain above.

Certification and institutional credibility reference saved in `docs/certification-and-model-validation.md`, including independent validation, SOC 2, ISO 27001, CFA/FRM and a CQF overview with November 3, 2026 sources.

## Future work — Google authentication

Requested November 6, 2026. Add Sign in with Google to the app's authentication
flow. This is a backlog item; implementation has not started.

- Use Google's OpenID Connect flow and validate the returned identity on the server.
- Preserve the approved-user allowlist: a Google account alone must not grant access
  or automatically create an authorized user.
- Decide whether Google sign-in supplements or replaces the current email-code
  login, and define account linking for existing approved users.
- Preserve secure app sessions, sign-out, user disabling and access protection for
  portfolio pages and APIs. Configure separate local and production redirect URLs.

## End-of-day checkpoint — November 6, 2026

Latest deployed release: `progress-alignment-20261106-5d3e9bc9d224`.
Selected-holding purchase references, contract-matching diagnostics, Python 3.14,
calculation timer with gray/inert screen, and recommendation alignment are live.
AWS INTC purchase allocation corrected with user approval and verified against
saved quotes; account purchase totals unchanged. See
[session handoff](status/handoff-2026-11-06.md) for deployment, backups, tests,
local/cloud authorization distinctions and uncommitted working-tree state.
Prior pending-deployment notes are superseded. Google sign-in remains backlog;
rollover Close versus Expire still needs comparable full-position valuation.
No next feature selected or scheduled.
