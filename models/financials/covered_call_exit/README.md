# Covered-call exit scenario model

## Hugging Face package

The current consolidated explanation is in [MODEL_CARD.md](MODEL_CARD.md), including
Black–Scholes equations, historical bootstrap, current criteria and synthetic data.
The original narrative and version history below contain superseded rules.

Prepare the standalone public package (no network or private data):

```sh
python3 models/financials/covered_call_exit/publish_huggingface.py
```

Publishing the chart requires the optional `huggingface_hub` upload library
(`python3 -m pip install huggingface_hub`). Model evaluation remains standard-library only.

Authenticate through a hidden terminal prompt, then publish to your personal
Hugging Face namespace as `covered-call-exit-model`:

```sh
python3 models/financials/covered_call_exit/publish_huggingface.py --login
python3 models/financials/covered_call_exit/publish_huggingface.py --upload
```

The explicit upload allowlist contains only model code, the model card, synthetic
inputs/outputs, a runnable example, model tests and a checksum manifest. The
publisher checks public visibility and verifies every uploaded file's checksum.
It does not change an existing private repository's visibility. Login tokens and
build outputs remain in ignored `.secrets/` and `artifacts/` directories.

Independent, standard-library model; no broker, dashboard, credentials or OpenAI dependency. The investment app supplies validated market data through `coveredCallOptimizer/exit_optimizer.py`.

Objective: rank the mean discounted USD liquidation wealth of closing now, closing after a specified number of trading days, or rolling now and liquidating the replacement covered call at the selected horizon. This is an experimental scenario model, not a trained or validated profit predictor. It does not claim to locate the best future exit day.

Inputs are the held standard 100-share call, stock bid/ask, verified listed replacement calls, and at least 40 unique completed daily stock closes from the preceding three calendar months. Replacement strikes are inclusive 50–150% of the held strike; expirations are inclusive ±6 calendar months from the held expiration and must remain unexpired. The exact held contract is excluded from rolls. Delayed, halted, missing, crossed or insufficient-size option quotes are excluded; the held contract must pass these checks to run.

For 600 reproducible paths (seed 42), sample historical daily log returns independently with replacement. Calibrate a constant implied volatility separately for each option from today's midpoint using a European call approximation. Estimate future ask prices with that volatility and today's absolute half-spread. Use stock bids and option asks for closing, and replacement bids for opening rolls. Fees are excluded to simplify the comparison. Values are discounted at an assumed 4% annual rate. Cash from an early close is treated as earning that rate through the comparison horizon. Roll credit/debit is added once; the remaining replacement option liability is deducted. At expiration, an in-the-money call is assigned at its strike; otherwise shares remain for sale at the exit horizon.

Original net premium and stock basis are common constants and do not affect USD strategy ordering; displayed values are proceeds, not realized gains. FX is deliberately outside this model; USD remains USD. Applying CAD conversion would require an explicit per-leg policy and future-FX assumption, rather than simply scaling every roll's net cash.

Limits: no historical option quote archive/backtest, out-of-sample validation, changing IV or liquidity, autocorrelation, dividends, early assignment, corporate actions, taxes, cash constraints or reinvestment opportunities. Bootstrap tail risk is restricted by a short historical window. Estimated probabilities are frequencies within these simulated paths. European pricing is an approximation for American equity calls. No order execution.

Run tests:

```sh
python3 -m unittest discover -s models/financials/covered_call_exit/tests
```

App: `http://localhost:8765/covered-call-optimizer`. Refresh retrieves Yahoo stock history and Questrade stock/options; saved captures are private ignored JSON under `coveredCallOptimizer/reports/exit-optimizer-ACCOUNT-SYMBOL.json`. Refresh uses the same server lock as the existing roll scanner to avoid simultaneous dashboard broker-token rotations.

References: [Questrade option quotes](https://www.questrade.com/api/documentation/rest-operations/market-calls/markets-quotes-options), [OIC covered calls](https://www.optionseducation.org/strategies/all-strategies/covered-call-buy-write), [OIC assignment](https://www.optionseducation.org/referencelibrary/faq/options-assignment).

Version 1.1 exposes mean discounted cash-flow components for the chart: stock sale
(or assignment proceeds), option purchases and replacement option sales.
Their signed sum reconciles to mean net proceeds for each strategy. Roll option
purchases include closing the original call now and closing its replacement at the
exit horizon. Expired calls have no buyback cost. The dashboard plots these as
positive/negative vertical stacks with strategies on the x-axis and a net-proceeds
diamond plus 10–90% simulated range. Every value is USD.

Version 1.2 removes fees from calculations, controls and cash-flow charts.

Version 1.3 requires `initial_purchase_price_usd` and sets the minimum stock sale
price to purchase × 1.10. The app reads the recorded USD purchase price from SQLite
for the exact account/symbol; missing values must be entered in Profile settings,
rather than inferred from CAD book value. Only strategies meeting the floor on
all sampled paths are plotted/ranked as eligible. Replacement strikes must also
meet the floor to avoid assignment below it. Nominal sale/assignment prices are
checked before discounting or interest accrual; paths are never clipped or dropped
to manufacture a qualifying result. Excluded rows remain in the private result
with pass rates. This finite-path screen cannot guarantee future prices and does
not place orders or enforce a broker limit price.

Version 1.4 supersedes the original search window: replacement strikes are now
80–120% of the original USD stock purchase price, and expiration dates are within
±12 calendar months of the held call's expiry. Listed, unexpired standard calls
only. `top_choices` contains at most five eligible roll-and-close strategies,
sorted by positive `net_profit_usd` (mean discounted closing wealth + original
gross call premium − original gross stock cost). Opening transaction references
are required to select on profit; absent references never imply zero opening cost.
The close-now/wait rows remain diagnostic benchmarks in the saved result, while
the chart displays the selected replacement contracts only. The existing 110%
minimum sale floor still applies to all paths and replacement strikes. Fewer than
five results, including none, is valid; constraints are never relaxed to fill slots.

Version 1.5 always shows the top five available replacement-call strategies by net
profit, including losses and sale-floor failures. Floor status remains labelled
for every plotted group; it no longer hides results. The strike/expiry ranges and
market-quote validation remain enforced. Missing opening records still prevent
profit ranking. This supersedes the positive-profit/eligible-only selection above.

Stock-price slider: `stock_price_scenario(data, price)` makes a temporary copy of
captured inputs and reprices held/replacement calls at a hypothetical stock
midpoint (±50% of the captured midpoint). Calibrate each IV against original
quotes, keep that IV and absolute bid/ask spread fixed, then recompute option
midpoints at the selected spot. The unchanged captured midpoint reproduces the
original inputs exactly. Evaluation uses the same paths/seed and fixed 30-day
period, so price scenarios can be compared without random resampling noise.
The app's `/api/exit-optimizer/scenario` reads the saved capture and performs no
broker/public requests or writes. The browser debounces slider movement, rejects
stale responses, keeps a fixed current-quote marker and offers reset. All changed
quotes, including the close-today column, are hypothetical during a scenario.

Design: [component diagram](DESIGN.svg) and [design / interaction sequence](DESIGN.md).

Proposed alternative: [TFT architecture (design1.svg)](design1.svg), with [design notes](design1.md). This is not the active runtime.

Version 1.6 supersedes the earlier strike band: replacement strike must be strictly above both the original USD stock purchase price and the current stock midpoint (hypothetical midpoint in slider scenarios), with no fixed upper cap. The adapter captures listed strikes above purchase price so lower slider scenarios can also select calls that were previously in the money. The ±12-month expiry window and top-three ranking remain.

Version 1.7: replacement strike must be **at least 1.20 × original USD stock
purchase price AND strictly above current stock midpoint** (selected midpoint for
slider scenarios). No fixed upper strike cap; expiry window remains ±12 months.
A strike exactly at 1.20× purchase qualifies if it is above spot; a strike exactly
at spot never qualifies. This supersedes the version 1.6 purchase-price minimum.

Version 1.8: search all listed FUTURE expirations from tomorrow through one calendar
year after the held call's expiry. The old held-expiry-minus-one-year lower bound
is removed. Same-day expiries are excluded because the model uses whole dates,
not intraday expiration timestamps. Contracts expiring before the 30-day exit use
the existing expiration-settlement logic. Strike rules and top-three ranking remain.


Version 1.9 adds an `expire_worthless` alternative for each valid rollover. It is
conditional on worthless expiry with no assignment: retain shares, zero stock
sale, zero replacement buyback; original held-call buyback remains deducted.
Only original and replacement option cash flows determine `option_profit_usd`;
`net_profit_usd` is null because the stock position remains open. The app labels
this option-only result separately from full-position Close profit. The controls
do not affect default Close-mode ranking or fixed Close today reference.

Version 1.10 adds `roll_funding` to each Close/Expire rollover outcome. It reports
opening held-call ask buyback, replacement bid premium, net debit floored at zero
and net credit floored at zero. This is gross USD trade funding, not a broker
margin calculation or account cash-shortfall estimate. Future closing liabilities
and historical opening premium are not counted as available rollover funding.

Version 1.13 permits confirmed earlier expired-cycle P/L to remain visible while
the active call's history is incomplete. `realized_pl_partial` identifies this
recorded amount. Unrealized, current-cycle and total P/L remain null until the
active history is complete; neither a missing opening nor a prospective slider
scenario realizes a gain. Expired premiums are attributed through retained-share
sources once and are excluded from the active cycle's opening cash flows.
