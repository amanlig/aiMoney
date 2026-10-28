# React dashboard

The home page and optimizer are React components. All runtime dependencies are
pinned and vendored locally: React / React DOM 19.2.0 (MIT) and HTM 3.1.1
(Apache-2.0).
HTM provides tagged HTML templates compiled to React elements at runtime; no
JSX compilation, CDN, Node installation or package download is needed to run.

From the repository root:

```sh
python -m pip install -r requirements.txt
python frontend/build.py
python dashboard_server.py
```

Open http://localhost:8765/covered-call-optimizer. `/` and `/index.html`
render the React home page. Rebuild after changing `frontend/src/` or
`frontend/vendor/`. The checked-in distribution lets an existing installation
start the Python server immediately.

`src/App.js` owns holdings, captured baseline, scenario requests and UI state.
`src/Chart.js` renders the cash-flow SVG and per-roll controls through React.
`src/Settings.js` owns a separate profile-name dialog and the Transactions dialog,
opened beside the holding selector. Transactions contains Stock purchase, Option Opening Sale and Rollover tabs
with one shared holding selector above all three tabs, defaulting to the dashboard holding.
Stock purchase requires date, shares, USD price per share and fees (0 for none).
Stock purchase shows and saves only the selected account and ticker. Switching
tabs preserves form edits; changing holdings resets option-sale and rollover forms.
New purchases save a USD cost basis; existing CAD records are retained, and the
optimizer prefers the saved USD record when available. No FX input is required.
Option Opening Sale requires the original contract, settlement date and USD premium per share.
Saved sales can be corrected using Edit and the confirmation checkbox.
Closing Transactions updates accounting from saved quotes without a market refresh.

`src/Recommendations.js` owns explicit assessment generation and saved history.
`src/api.js` centralizes JSON requests. The existing pure `profile_settings.js`
cost-basis calculation is shared with the archived interface.

FastAPI serves the built assets through explicit routes. React loads all position
data, including saved captures, from `/api/` endpoints. Docker can serve the UI and
API together; see [Docker setup](../DOCKER.md). Broker authentication,
pricing, ranking, SQLite and OpenAI calls stay in the existing Python services.
Mounting the UI reads saved data only; refresh and assessment generation require
button clicks. Captured Close today is retained during hypothetical scenarios.

Dependency sources: `https://esm.sh/react@19.2.0/es2022/react.bundle.mjs`,
`https://esm.sh/react-dom@19.2.0/es2022/client.bundle.mjs?external=react`,
`https://esm.sh/htm@3.1.1/es2022/htm.mjs`. Licenses are in `vendor/`.

Browser contracts use synthetic API responses and the actual Python asset routes:

```sh
python -m pip install -r requirements-dev.txt
python -m pip install playwright
python -m playwright install chromium
python -m unittest discover -s tests -p test_react_dashboard.py
```

Tests start the FastAPI app under Uvicorn with the macro refresh disabled.
They use `CHROME_PATH`, an installed Chromium/Chrome, or Playwright's Chromium. Tests never call Questrade or OpenAI.

Rollover records a completed buyback and replacement sale together in USD, with
one contract count, settlement date and total fees. Both premiums are per share.
The form previews net credit/debit; duplicate rollovers are rejected. Saved rolls
feed cumulative chart P/L through the linked original opening and rollover chain.
Holdings remain unchanged. Missing or ambiguous chains make P/L unavailable;
partial rolls and contract re-entry are not supported. See ../TODO.md for accounting limits.

The Close button beside Recommendation records a completed full stock sale and
held-call buyback in USD, with one close date and total closing fees. It does not
place orders. Recording a close persists a closed-holding record, removes that
position from active selectors, and opens a dedicated Closed holdings report screen. The simulation and trading
controls are absent from this view; Back to active holdings returns to the dashboard. The report
shows actual execution cash flows and realized P/L from an immutable accounting
snapshot; missing history leaves P/L unavailable. Duplicate closes are rejected.
The closure identity includes account, ticker, shares, contracts, strike and expiry;
reopening the identical position requires a future lifecycle/reopen workflow.

Covered positions have stable IDs. The dashboard and Transactions selectors include
strike, expiry, contract count and allocated shares. Add position creates another
contract in the same account/ticker; Allocate shares adjusts coverage without
altering its opening or contract count. Each position's opening form becomes
Edit-only after the first save. Position-scoped endpoints own all new transactions;
legacy premium/rollover tables are retained as historical archives and are claimed
only when unambiguous. Captures, requests, rollover-mode keys and closing records
include the position ID. Closed shares remain consumed by their recorded sale.

Holdings.js provides dashboard New and Delete dialogs. New records a stock purchase
without requiring an option, then opens Transactions. Stock-only rows have zero
contracts and cannot run the optimizer until their first active opening sale.
That sale fills the existing position ID. Per-position stock purchase metadata
preserves independent lot prices/fees while the shared basis maintains share capacity.
The holding selector sits above two labeled action groups: Optimization contains
Refresh data & analyze and Recommendation; Holdings & records contains New,
Transactions, Close, Expired worthless, Closed holdings and Delete. The primary
group uses blue emphasis; record actions are subdued with Delete at the far right.
The groups stack below 1100px and buttons wrap within each group.

holding_records.py deletes owned openings, rollovers, exclusive prior expirations,
position-scoped recommendation records and saved analysis files under the existing
mutation lock. Confirmation and position revision are required; market refresh and
assessment locks prevent a late writer recreating a deleted snapshot. File renames
are restored on transaction failure. Shared ancestors and remaining purchase lots
are retained. Small internal deletion markers suppress stale snapshot imports and
reserve deleted share-source allocations, preserving other holders' cent rounding
and preventing reuse of deleted history. They contain no transaction cash amounts.

OptionExpiration.js provides one actual-expiry modal shared by the dashboard and
Transactions → Rollover. It records worthless expiry after the contract date,
keeps the active-holdings view in focus and exposes receipts under
Transactions → Transaction report.
TransactionReport.js shows grouped cash_entries as the main report. Each rollover
combines buyback and replacement sale, including precise leg prices, fees and net
cash. Non-rollover sales and confirmed expiry stay single rows. The main measure
is Realized option cash: net_option_cash_usd (actual recorded premiums minus
buybacks and option fees). The footer pairs gross_cash_flow_usd (including stock)
with that option cash measure. Open-call premiums are included in cash.
GET /api/positions/{id}/transactions retains entries and realized_option_pl_usd as
completed-call accounting detail. They appear only in an expandable section.
App.js shows historical_option_net_usd + prior_realized_option_usd as Realized
option cash. Completed-call accounting remains expandable in Transactions only;
the dashboard draws a single net P/L bar. Scenario P/L/ranking formulas remain unchanged;
all historical option cash, stock cost and simulated call closing cost count once.
Saving an opening, rollover, stock purchase or expiry reloads the report, with
stale requests aborted. No financial records are rewritten for this display.
The position-owned option net, less expiration fees, is realized; there is no
stock sale, no buyback and no second credit for historical premiums. The stock
purchase basis is unchanged. Expired calls are inactive; the expiry API atomically
returns a retained_position with the same shares as Stock only. Both dashboard
and Transactions keep that holding selected for its next opening sale. Older
unconsumed expiry stock is recovered idempotently on holding reads. A source
already represented by a retained position is not reclaimed after intentional
allocation changes. Closed/deleted shares are not restored. Assignment is outside
this action. Expiry receipts remain immutable and gains follow the retained shares.

Chart.js renders one purple total-P/L bar from zero. It uses total_pl_usd when
present, or the legacy net_profit_usd/option_profit_usd result; known missing totals
stay unavailable. Closed-call/open-position components do not create diverging
bars or influence the axis scale. True positive/negative/zero totals are preserved.
App.js emphasizes an If you close today summary with captured net P/L and its
stock sale − call buyback + accumulated option cash − stock cost reconciliation.
Scenario slider changes retain that captured closing reference. All changes are
presentation only; underlying accounting and strategy ranking remain unchanged.

The Optimization group includes **Download all rollovers (CSV)**. It downloads all
filtered rollover rows for the displayed stock-price scenario, sorted by estimated
whole-position profit descending (unknown profits last and blank). The UTF-8 CSV
includes saved quote time, criteria, funding, probability and sale-floor flags;
worthless-expiry cash is explicitly option-only. No market refresh is triggered.
The button is disabled without matching results or while analysis is updating.
Run `node tests/test_rollover_export.mjs` for isolated CSV checks.
