# Covered-call optimizer

The optimizer is a USD scenario comparison, with fees excluded. It compares a
fixed captured Close today reference with the top three performing rollovers.
These are estimates, not validated forecasts or trade instructions.

## Using the page

1. Choose a holding and click **Refresh data & analyze** to retrieve current market
   quotes. A saved chart on page load uses its displayed capture timestamp.
2. Move the stock-price slider to reprice rollover scenarios. The fixed current
   midpoint marker stays in place. Close today remains at captured actual quotes.
3. Hover, focus or tap a group for its detailed cash-flow amounts.
4. Use **Profile / Settings** for stock purchase records and original option sale
   premiums. Refresh the analysis after changing transaction records.

Green bars show stock sale or assignment proceeds. Red bars show call buyback
costs as positive magnitudes. Blue adds replacement premiums received; purple
shows total net profit. Original stock cost is a solid reference line, and original
option premium is dashed. The original opening premium is included once in total
profit, not added again to the closing-cash bar.

## Process and data

1. Read the saved account holding, confirmed original USD stock purchase price and
   exact-match original call sale. Multiple matching opening sales are not
   automatically aggregated.
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
   a European call formula with constant IV and captured absolute half-spreads.
   Model expiration/assignment when the replacement expires before the exit date.
7. Calculate rollover cash flows: buy back the held call and sell its replacement
   now; then sell retained stock and buy back the replacement after 30 trading days.
   Future cash flows are discounted to today at an assumed 4% annual rate.
8. Compute total profit and display the top three rollovers, even if negative:
   **Net profit = discounted closing cash + original gross call premium − original
   gross stock purchase cost.**

**Close today cash = stock shares × captured stock bid − call contracts × 100 ×
captured held-call ask.** This value does not move with the slider.

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
- Purple bar = **cumulative option-only P&L = original premium + new premium −
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
