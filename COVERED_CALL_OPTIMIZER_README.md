# Covered-call optimizer

The optimizer is a USD scenario comparison. Recorded historical fees are included
in P/L; future execution fees and taxes are excluded. It compares a
fixed captured Close today reference with the top three performing rollovers.
These are estimates, not validated forecasts or trade instructions.

## Using the page

The holding selector applies to both toolbar groups. **Optimization** groups
Refresh data & analyze with Recommendation. **Holdings & records** groups New,
Transactions, Close, Expired worthless, Closed holdings and Delete.

Use **New** beside the holding selector to start with a stock purchase: account,
ticker, purchase date, shares, USD price and fees (0 for none). No option details
are needed at this stage. The new holding appears as **Stock only** and opens in
Transactions. Record its option opening sale when ready; optimization becomes
available after the active call is recorded. An earlier worthless expiry can be
recorded first using its explicit confirmation, followed by the current call.
Past-dated opening sales can also be saved with worthless expiry unchecked when
the call was bought back or rolled. Rollover immediately uses that recorded call
as its buyback contract. Current-quote optimization waits until the historical
call's outcome is entered; an elapsed expiry date never automatically realizes
its premium or records a worthless expiry.

Use **Delete** to remove the selected holding and its owned transactions,
expired-cycle history, saved analyses and recommendations. Review and confirm
the deletion in the dialog. Purchase allocations and historical records shared
by another holding are retained for that holding. Deleted imported holdings do
not return on reload. New purchase lots retain their own USD purchase price and
fees, so adding or deleting a different lot does not change their profit basis.

1. Choose a holding and click **Refresh data & analyze** to retrieve current market
   quotes. A saved chart on page load uses its displayed capture timestamp.
2. Move the stock-price slider to reprice rollover scenarios. The fixed current
   midpoint marker stays in place. Close today remains at captured actual quotes.
3. Hover, focus or tap an individual bar segment for its value.
4. Use **Transactions** beside the holding selector for Stock purchase, Option Opening
   Sale and Rollover records. The shared selector defaults to the dashboard holding.
   Closing Transactions updates historical accounting using saved quotes without a
   broker refresh. Profile settings contain only the profile name.

The **Transaction report** shows the selected holding's stock purchase, option
opening sales, combined rollovers and linked confirmed worthless expiries.
**Realized option cash** is the app's cash-tracking measure: recorded opening and
replacement premiums minus buybacks and option fees. Each rollover contributes
its net credit or debit immediately, with both prices and contracts in one row.
A worthless-expired sale remains one row, with its premium counted once.

For the reviewed RKLB entries, earlier expired calls contributed $2,560, the next
opening sale $650, and four rollovers $7,442.15: $10,652.15 realized option cash.
This includes the sale premium on the still-open call. It is distinct from the
full covered-call closing result, which includes stock proceeds, the current call
buyback, original stock cost and applicable fees. Ownership of the stock covers
call delivery; the optimizer continues to value both the stock and call when
comparing exits. No simulated profit is added to recorded cash.

Main report totals show signed gross cash flow before fees beside realized option
cash after option fees. Gross stock purchases and option buybacks are negative;
sales are positive. Prices preserve entered precision and linked history follows
the allocated retained shares. Closed-call accounting is expandable supporting
detail in Transactions only; it compares each completed call's own sale and closing
outcome and does not appear on the decision dashboard.

The dashboard's cash summary uses the same cumulative option cash measure.
The **If you close today** summary prominently shows estimated total position
P/L and a reconciliation of stock sale, call buyback, realized option cash and
stock purchase cost. It uses captured bid/ask quotes and remains fixed when the
scenario slider changes. Recorded fees are included; future closing fees excluded.
Each purple P/L bar shows one overall net result from zero, above zero for profit
and below zero only for an actual net loss. Completed-call accounting components
are supporting detail and never drawn as diverging positive/negative bars.
Missing total P/L stays unavailable. Expire mode is labeled option-only P/L and
excludes retained stock value; it is distinct from full-position closing P/L.
Historical option net cash equals the original opening premium plus linked
rollover sale premiums, less buybacks and recorded option fees, each counted once.
Close P/L equals closing cash plus that historical net cash, less stock purchase
cost including recorded purchase fees. Historical cash is not added to sale bars.

The current contract is traced backward through a single constant-size rollover
chain per position to its opening sale. Unrelated trades and duplicate latest-sale records are
not added. Missing or ambiguous links, missing/duplicate original openings, cycles
and changing contract counts make cumulative P/L unavailable. Record all previous
rollovers to obtain full recorded-history P/L. Unrecorded fees/trades cannot be
inferred; USD-only opening-sale entry excludes opening fees. Purchase fees are
allocated proportionally to held shares; future fees and taxes remain excluded.

## Multiple covered-call positions

A position allocates shares in one account to one current call contract. For
example, 2,000 RKLB shares can cover two positions: 1,000 shares and 10 January
2028 $20 calls, plus 1,000 shares and 10 February 2028 $20 calls.

In Transactions, select the stock/account and use **Allocate shares** to adjust
an existing position's allocation, then **Add position** for the second contract.
Each call needs at least 100 shares. The form shows recorded, allocated and
available shares; concurrent requests cannot allocate the same shares twice.
Stock purchase quantity establishes the share pool (saved basis takes precedence
over the imported snapshot). Purchase quantity cannot be reduced below existing
allocations. Fully closed positions continue consuming the shares recorded as sold;
closing does not turn sold shares back into available coverage. Calls recorded as
expired worthless release their allocation because the shares were retained.

Each position has a permanent ID and exactly one **Option Opening Sale**. Once
saved, the form shows **Edit** instead of adding another opening. A different
strike or expiry normally needs a separate position or a rollover. To backfill
the original sale for an already-rolled holding, check **This is an earlier
original call**. This permits an earlier contract without changing the
current holding or adding another opening. Enter its historical rollovers in
trade order through the current call. Cumulative P/L stays unavailable until the
chain connects. The original sale remains recorded in Transactions while links
are missing. Subsequent rollovers of the current call update the holding.
Contract-count, date and confirmation checks still apply. A different settlement
date alone does not create a different call contract; an identical active call
contract cannot be added as another position.

If that earlier original call **expired worthless**, check its expiration
confirmation in Option Opening Sale, including under **Edit** for a saved sale.
Enter expiration fees (0 for none). The expiry must be in the past, with no
buyback or assignment, and the shares must have been retained. Saving archives
that completed cycle under **Expired option history** and realizes its premium
less recorded fees once. The current short call stays active with its existing
share allocation. Record its own opening sale separately when available. The
confirmed prior gain can be shown while current-call and total P/L remain unknown.
An opening already linked to buybacks must be resolved through its rollover
history rather than also being marked expired.

Opening sale, rollover history, chart captures, scenario requests, recommendation
snapshots and closing records all belong to the position ID. A rollover changes
that position's current strike/expiry while preserving its ID and original sale.
Close affects only the selected position. After a rollover or allocation change,
refresh that position's quotes; snapshots for a different contract or share count
are never reused. Legacy captures are used only for their matching imported
position, not for a newly created one.

Existing records are preserved. Imported positions claim legacy openings and
rollovers only when ownership is unambiguous; one legacy transaction cannot be
claimed by two positions. The original archive tables remain intact. New records
use the position-owned ledger, so another expiry's premiums never enter P/L.

## Record an actual worthless expiry

Use **Expired worthless** beside Close on the dashboard or inside
**Transactions → Rollover**. Both act on the selected position's current call,
including a previously recorded replacement call. The action is available after
the contract's expiry date and requires confirmation that the broker reports
worthless expiry, no assignment, and shares still held. Enter expiration fees in
USD (0 for none). This is a record of an actual event, not an order or forecast.

Realized option P/L equals the original opening premium plus all position-owned
rollover sales, minus historical buybacks and recorded option fees, minus the
expiration fee. Stock cost and stock gains/losses are excluded. Stock sale and
current-call buyback are both zero; cash at expiry is only the expiration fee
outflow, because the premiums were already received earlier. Missing history
leaves realized P/L unavailable rather than inventing a result.

The expired call is archived, while its retained shares remain selectable as
**Stock only** with the original purchase basis and realized history. Record the
next call through **Transactions → Option Opening Sale** without a new purchase.
Older expiries that left unconsumed stock missing from the selector are restored
once, limited to shares still held and not assigned to another position or deleted.
The dashboard stays focused on the selected stock/call holding;
it does not switch to the closed-stock report. **Expired option history** inside
Transactions retains the immutable option-P/L receipt. A new call has a new
position ID and one new opening sale; previously realized premiums are not
counted again in that new call's history.

Expiration cannot also be recorded as a full position close, and duplicate or
stale requests cannot release the same shares twice. Assignment is not implemented
by this action. The chart's existing **Expire** radio option remains a hypothetical
scenario and never records an actual expiration or releases shares.

## Net P/L bars and closing decision

The purple P/L column plots the entire strategy's total result. Its endpoint
and the prominent Net P/L label agree. Hover or keyboard focus shows only that
net result. A genuine zero stays at zero, a genuine loss extends below zero, and
incomplete history shows Total P/L unavailable without inventing a result.

The model still retains completed-call and open/simulated components for detailed
accounting. The overall result includes accumulated option cash and the stock/call
exit values exactly once; this chart change does not modify model ranking.
Close today uses captured quotes; rollover and conditional Expire results are
simulations. Changing the slider or exit controls never records a gain or trade.

When shares released by a worthless expiry fund a new position, their realized
option P/L follows those shares. Available retained-share lots are reused in
oldest-first order; partial allocations receive proportional P/L. Cent remainders
are assigned by child-position creation order, so split positions cannot duplicate
a rounding cent. Subsequent expiration cycles carry their own result plus earlier
linked results once. Existing unrelated positions, different accounts, and fresh
shares do not receive another position's old gains. Missing source results keep
the chart total unavailable rather than assuming zero.

Chart total = linked earlier realized P/L + current-cycle position P/L.
Current-cycle realized call results are already inside that position P/L; they
are split out for display, not added a second time. Conditional Expire excludes
stock gains/losses as before. Closed-holding exit amounts remain current-cycle
results, with earlier realized and combined results shown in Accounting details.

## Process and data

1. Read the saved account holding, confirmed original USD stock purchase price and
   original call sale linked to the current contract through recorded rollovers.
   Ambiguous or incomplete history is not automatically aggregated.
2. Retrieve three months of completed Yahoo daily stock closes. Retrieve Questrade
   stock and listed call quotes, validating standard contracts, size and quote quality.
3. Select replacement strikes **at least 1.20× the original USD stock purchase
   price and strictly above the current stock midpoint**. There is no fixed upper
   strike cap. In slider scenarios, use the selected hypothetical midpoint.
4. Include listed future expirations from tomorrow through one calendar year after
   the held call's expiry. Same-day expirations are excluded.
5. Sample historical daily log returns to build 600 repeatable stock-price paths.
   The valuation period is fixed at **30 trading days**, roughly six calendar weeks.
   The slider changes the hypothetical starting price, not the terminal stock price.
6. Calibrate each option's IV to its captured midpoint. Estimate future calls using
   the [Black–Scholes European call formula](https://www.maths.dur.ac.uk/users/nicholas.georgiou/Teaching/2021-22/MF/the-blackscholes-formula.html#the-formula)
   with constant IV and captured absolute half-spreads. The linked Durham University
   notes explain the formula, its inputs and assumptions (section 5.4).
   Model expiration/assignment when the replacement expires before the exit date.
7. Calculate rollover cash flows: buy back the held call and sell its replacement
   now; then sell retained stock and buy back the replacement after 30 trading days.
   Future cash flows are discounted to today at the selected continuously compounded annual interest rate.
8. Compute total profit and display the top three rollovers, even if negative:
   **Net profit = discounted closing cash + original gross call premium − original
   gross stock purchase cost.**

**Close today cash = stock shares × captured stock midpoint − call contracts × 100 ×
captured held-call midpoint.** This value does not move with the slider.

## Sale floor and assignment

The stock-sale floor is **original stock purchase price × 1.10**. The chart shows
the fraction of simulated outcomes meeting that floor, rather than hiding a
strategy because one path falls below it. These are model-path frequencies, not
guaranteed probabilities. Assignment-strike compliance is checked separately:
**replacement strike ≥ sale floor**. If a call expires worthless, the stock is
still held and exposed until sold at the model's exit date. Early assignment is
not simulated.

## Limitations and objectives

Volatility and spreads remain fixed; three months of return history is a short
sample. Dividends, early assignment, changing liquidity, corporate actions, taxes
and fees are not modelled. Quotes are estimates of executable levels, not fill
guarantees. Historical option predictions have not been backtested.

The current model still assumes liquidation at the review horizon. The user's
newly stated preference—retain stock in healthy conditions, free cash during
unacceptable downside or deteriorating macro conditions—is a future design input,
not an implemented market-health decision rule. No macro signal currently
selects hold versus exit. Hugging Face TFT integration remains a proposal.

## Storage and design

The app owns quotes, SQLite and private reports. The independent implementation
is `models/financials/covered_call_exit/model.py`. USD premium capture uses the
existing `/api/option-premiums/usd` endpoint and `option_premium_sales_usd` table;
legacy converted premium records remain supported.

Design diagrams: `models/financials/covered_call_exit/DESIGN.svg` (current design)
and `design1.svg` (proposed TFT architecture).


## Per-roll Close / Expire controls

Each rollover has radio buttons, defaulting to Close. Close uses the existing
30-trading-day liquidation simulation. Expire is a conditional what-if: the
replacement call expires worthless with no assignment and all shares retained.
It is not a forecast of worthless expiration or a full-position liquidation.
The top three contracts remain selected by Close-mode ranking; changing a toggle
does not reorder them. Modes survive slider changes for matching contracts and
reset to Close when the holding changes or market data is refreshed.

In Expire mode:

- Stock sale = zero; stock remains held.
- Replacement-call buyback = zero.
- Existing held call is still bought back TODAY to establish the rollover.
- Sale bar = new replacement premium received today.
- Red buyback bar = original held-call buyback today, not zero.
- Cash = new premium − held-call buyback (may be a debit).
- Purple bar = **cumulative option-only P/L = historical option net cash + new premium −
  held-call buyback**. It excludes unrealized stock gain/loss and purchase cost.

Do not compare this purple bar directly with full-position Close profit without
also valuing the retained shares. The stock-sale floor is not applicable when no
stock is sold. If assignment occurs, this conditional case no longer applies;
assignment proceeds and stock realization require a different outcome.

## Rollover cash funding indicator

Each rollover displays **Roll cash needed = max(held-call buyback at ask − new
replacement premium at bid, 0)**. A net-credit rollover shows zero needed and the
credit separately. Both legs use contract quantity × 100. Fees remain excluded.
This indicator is identical for Close and Expire, since the opening rollover is
the same; hypothetical slider prices reprice both opening legs consistently.
It does not include the later buyback in Close mode or count original premium as
currently available cash. It is not a broker margin/buying-power requirement or
an additional-deposit figure: account balances and collateral are not queried.
The calculation assumes simultaneous rollover legs. Closing the old call before
selling the new one can require funding the full buyback first.

## Product direction

See [Reusable optimizer direction](docs/optimizer-product-direction.md) for proposed advanced capabilities and the priority of comparing retained-stock and liquidated-stock outcomes consistently.

## Profile location

The **My profile → Settings** menu is on the optimizer page. It opens the shared
purchase-basis and opening-premium forms in a local dialog; it does not navigate
to the portfolio dashboard. The dashboard links to
`covered-call-optimizer.html#profile-settings`. Shared profile scripts load through
an explicit server allowlist and `/api/profile/holdings` supplies saved positions.
No purchase or premium records are moved or rewritten by relocating this menu.

## Archived equity dashboard

The optimizer is the home page. The old equity dashboard and its exclusive renderer/UI scripts are preserved under `coveredCallOptimizer/archive/equity-dashboard/`. Old home URLs redirect to the optimizer. My profile and shared settings remain active on the optimizer; financial data are unchanged.

## Optimizer recommendations

Use **Recommendation** beside **Refresh data & analyze**, select an objective, then generate an assessment. The app rebuilds the selected chart scenario on the server, preserves Close today at captured quotes, and applies each rollover’s Close / Expire selection. An assessment uses the existing `.secrets/openai.json` configuration (or server environment overrides); the independent model has no OpenAI dependency.

The app sends the position, original transaction references, chart cash flows, funding estimates and assumptions to OpenAI’s Responses API with API response storage disabled. It does not send credentials or fetch news. Successful results and immutable input snapshots are stored in `data/fx-samples.sqlite3`, table `recommendation_runs`, with prompt version `optimizer-assessment-v1`. Saved assessments are available in the recommendation panel. Input changes mark the displayed assessment stale; a changed quote capture is rejected until the chart is reloaded. The API connection and history are verified with mocked responses; no paid call is made by the test suite.

The assessment separates liquidation profit from conditional option-only P&L and highlights funding needs. Account cash, broker margin, fees, taxes and market-health evidence are unavailable. Read the panel’s Assessment process for the sequence.

Close today uses (bid + ask) / 2 for both legs; midpoint execution is not guaranteed.
The Close execution form preserves captured bid/ask and manual actual fills.
Slider Close scenarios and rollover execution assumptions retain bid/ask pricing.

## Interest rate

My profile → Settings offers a maturity-matched U.S. Treasury par-yield default
and manual annual-yield override. The app converts semiannual bond-equivalent
yields with `2 * log1p(annual_percent / 200)` and passes the rate explicitly to
`evaluate()` and `stock_price_scenario()`. A single held-maturity rate is used
for replacement calls and discounting too; this is a par-yield proxy, not a full
zero-curve implementation. Source and observation date are retained in snapshots
and CSV. See [interest-rate settings](README.md#interest-rate-settings) for
cache, unavailable-data behavior and browser preference storage.
