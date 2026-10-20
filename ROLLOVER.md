# Short-call rollover simulator

> The equity dashboard described here is archived. Use the optimizer for the active UI; archived rendering is optional.

Select **QBTS** and **LIRA**, then **Simulate short-call rollover** in the stock
details. Market captures and the editor support all saved fully covered positions in
RRSP, TFSA and LIRA. It buys back
all existing calls at the entered ask and sells the same number of standard
100-share replacement calls at a manually entered bid, strike and expiry.
Replacement contract availability and quotes are not retrieved or verified.
Inputs are scenario drafts retained while the page is open; no orders are sent.

Net roll cash = replacement premium − existing buyback − entered roll fees.
At replacement expiry, combined P/L = shares × stock price − replacement call
intrinsic liability − stock cost + original premium + net roll cash. Original
premium is included once and defaults to the saved book-value proxy. The
simulator shows credit/debit, maximum profit/loss, conditional break-even,
required sale premium for the target price, and the owner's 5% loss rule.
Stock-only loss stays visible separately; a roll does not change stock cost.

The scenario table compares keeping the original call at its own expiry with
rolling at the replacement expiry. If the dates differ, the table assumes the
same terminal stock price at each separate date and explicitly warns that it
is not a comparison at one common horizon. It is an expiry payoff calculator,
not a prediction or early-exit option pricing model. Early assignment, taxes,
funding, final exit fees and prior roll history are excluded. Lower strikes cap
upside; net debits increase capital at risk. Entry-price edits update an open
simulator. All calculations use USD; CAD basis is converted with the editable
forecast FX assumption.

Reference: [Fidelity / Cboe — rolling covered calls](https://www.fidelity.com/learning-center/investment-products/options/rolling-covered-calls).

### Quote-based replacement recommendation

For any selected stock/account, **Refresh Questrade candidates** captures the listed standard
calls from 30 days ahead through the latest expiry actually listed by the
broker, from approximately purchase cost +
USD 5 through the existing strike + USD 5 (or a wider ceiling if required).
Every candidate's root, strike, expiry, USD currency and 100-share deliverable
are verified. The scan is explicit, not a continuously running broker feed.
`python3 roll_candidates.py --account TFSA --symbol QBTS` followed by
`python3 archive/equity-dashboard/chart.py` also refreshes one holding. Use `--all` to capture all holdings.

For each expiry, the recommendation chooses the lowest listed standard-call
strike at or above effective purchase price + USD 5. The $5 gap is fixed in the
UI; listed strikes can differ by expiry. Missing or thin quotes at that strike
do not cause substitution with a higher strike. Recommendations also require
positive cash credit after entered fees,
and combined loss strictly below 5% at the entered target stock price. It uses
stock purchase cost as that percentage's denominator. Existing ask size and
replacement bid size must cover all contracts; quotes must report zero delay
and no halt. Captures older than 15 minutes are excluded. The existing buyback
input starts at the ask plus a USD 0.05/share buffer; fees start at zero and must
be adjusted to actual charges. A buyback assumption below the captured ask
cannot generate a quote-based recommendation.

The expiry search defaults to dates after the existing call. Its dropdown
allows selecting a later starting date or including all captured expiries.
A minimum worthwhile net-credit input can exclude small credits. The table
shows each date’s exact next strike, credit/debit, size and eligibility reason,
including thin quotes and insufficient credits. Eligible dates are ranked by
earliest expiry within the chosen range. This is a disclosed selection rule, not ML optimization
or a guarantee of the best risk-adjusted return. The UI shows the selected
strike/expiry, bid/ask, size, credit, source time, scan bounds and reduction in
maximum expiry P/L. A lower strike can reduce upside substantially while adding
only a small credit. The user can load a candidate into the payoff simulator;
no account/order endpoints are requested and no trade is executed. A changed
basis below the scan's captured strike floor requires a new scan. Recommendations cover all saved covered-call holdings. Each account/stock has
its own captured chain and exact existing-call match. The refresh request uses
the effective USD purchase cost from the entry editor, so the scanned strike
floor tracks owner overrides and CAD conversion assumptions.

The refresh button uses the local server's origin-checked
`POST /api/roll-candidates/refresh` endpoint. Concurrent refreshes are rejected,
provider errors retain the last successful capture, and broker credentials stay
server-side. Use `dashboard_server.py`, rather than a static server, for this UI.

The macro panel below the stock filter displays a saved Yahoo USD/CAD (`CAD=X`)
market reference, previous-close change, and quote/retrieval times in Vancouver.
Run `python3 dashboard_server.py` for automatic 60-second refresh, last-update
status and failure notices. Reload the dashboard after switching from the old
static server. The browser polls the local cached feed; Yahoo quotes may be delayed.
For a one-time offline capture, use `python3 archive/equity-dashboard/chart.py --refresh-macro`. Other chart regenerations
reuse `reports/macro-data.json`; failed refreshes retain the dated capture.
This display does not change the editable forecast FX assumption or broker FX.

From the investment folder:

```sh
python3 forecast_data.py --as-of 2026-10-13
python3 forecast.py
python3 archive/equity-dashboard/chart.py --open
```

Use the intended Vancouver calendar date for `--as-of`. The collector excludes
that day's unfinished session and all later sessions. Inputs and the trained
models are local JSON files, and the generated page contains everything needed
to work offline. To use the existing local server, refresh
http://localhost:8765/archive/equity-chart.html after generating the chart.

The collector requests only public histories and SEC facts; it does not access
the Questrade token. The separate macro service uses Yahoo for the displayed
USD/CAD reference. Broker FX bid/ask and forecast conversion assumptions remain
separate; no automatic broker FX fallback is used.

LIRA's current marks and quantities can now be refreshed separately with
`python3 questrade_positions.py`. It regenerates the page using the saved stock
forecast model; it does not retrain that model. LIRA paired API bids/asks now
supply its IV inference inputs, rather than the original screenshot. Capture
time and quote delays remain separate from actual bid/ask observation times.


## Profile / Settings

The top-right profile menu opens on hover or keyboard focus and can also be
clicked on touch screens. **Settings** opens a modal containing the profile name
and one row per covered holding, grouped by account. Original purchase prices
and minimum acceptable stock bids use account currency: USD for LIRA and CAD
for RRSP/TFSA. Defaults are saved book-cost averages; owner edits replace stock
cost in current P/L, loss indicators and rollover calculations. Existing option
premium overrides are preserved, including entries previously converted to CAD.

Minimum bid thresholds are saved per account/currency/stock. Blank thresholds
use effective purchase-price break-even. Stock details compare Questrade stock
bids against that minimum (converted for CAD accounts) and show whether the
threshold is met. The separate 5% stock-loss rule remains visible. Settings and
entry prices persist in the same browser/origin; source files are not changed.
**Original values** restores the imported average and clears the custom minimum.
