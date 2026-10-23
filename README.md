# coveredCallOptimizer

A local Python/React.js dashboard for covered-call holdings. It includes account
and stock filters, Questrade bid/ask quotes and Greeks, editable purchase prices,
minimum acceptable bids, stock-loss indicators and rollover payoff comparisons.
LIRA defaults to USD; RRSP/TFSA default to CAD. Yahoo provides a USD/CAD macro
reference with a past-month chart. The separate USD optimizer provides local stock-price scenarios, top-three rollover comparisons, Close/Expire outcomes and estimated rollover funding.

## AWS deployment

Manual single-EC2 deployment in us-west-2: [setup guide](deploy/README.md).
The separate `compose.aws.yaml` adds Caddy HTTPS and login; `compose.yaml`
continues to run the local application.

## Database

Docker Compose now uses PostgreSQL in a separate container with persistent storage.
See [migration, configuration and backups](POSTGRESQL.md). The original SQLite
file remains a legacy snapshot; host execution needs `DATABASE_URL` to use PostgreSQL.

## Run

Requires Python 3.12+ and the pinned FastAPI/Uvicorn dependencies in
`requirements.txt`. Node is used for calculation checks.

The active home page, optimizer, Profile / Settings and Recommendation panel use
React with pinned local dependencies. Rebuild UI changes with
`python frontend/build.py`; checked-in build artifacts work with the existing
FastAPI server immediately. See [frontend setup](frontend/README.md) and
[FastAPI / Docker setup](DOCKER.md).

```sh
python3 -m pip install -r requirements.txt
python3 dashboard_server.py
```

React calls FastAPI through `/api/` on the same origin. API documentation is at
http://localhost:8765/docs. To run in Docker, use `docker compose up --build -d`
after the local setup described in [DOCKER.md](DOCKER.md).

Open http://localhost:8765/covered-call-optimizer. My profile / Settings is
available there. Existing local records remain in `coveredCallOptimizer/data` and generated
captures in `coveredCallOptimizer/reports`; no data migration is required.

The old equity dashboard and its unused frontend components are preserved under
[archive/equity-dashboard](archive/equity-dashboard/README.md). Its former URL
redirects to the optimizer; optional archived view:
http://localhost:8765/archive/equity-chart.html. The archived generator writes to
the archive by default and is not part of normal startup or position refresh.
Synthetic examples remain in `examples/` for isolated checks, not live data replacement.

## Sources and refresh

Questrade supplies stock/option quotes, sizes, Greeks and listed contracts. Yahoo
supplies the dashboard reference feed and completed stock-price history for the USD optimizer; its reference is separate from actual brokerage FX
spread/charges. The local service refreshes FX every 60 seconds. Broker captures
refresh explicitly using these commands or the candidate refresh button:

```sh
python3 questrade_positions.py
python3 market_details.py
python3 roll_candidates.py --all
```

Configure Questrade authorization locally; see [setup](QUESTRADE.md). Position
sync currently supports a uniquely identified active LIRA. RRSP/TFSA snapshots
are entered locally; market quotes can still be sourced from Questrade.

Profile → Settings configures purchase prices and minimum stock bid per holding.
For CAD holdings, enter purchase-time CAD per USD FX in Settings. Original USD
purchase basis and the rollover strike floor use historical FX; current CAD
proceeds and break-even use the current conversion assumption. Missing historical
FX blocks rollover calculations instead of substituting today’s rate.
Settings are stored in your browser, separately by account and stock. The rollover
rule chooses purchase + USD 5 rounded up to the next listed strike, with editable
expiry range and minimum worthwhile net credit. Quote freshness and displayed
size are checked. Payoffs are conditional scenarios, not forecasts or guaranteed
fills. See [rollover details](ROLLOVER.md) and [physical architecture](ARCHITECTURE.md).

## Public checks

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -p 'test_public_*.py'
python3 -m unittest discover -s tests -p test_fastapi.py
node tests/test_public_calculations.js
```

These checks use synthetic fixtures and do not require account credentials or
private portfolio files.

## FX sample entry

Expand **FX model · add transaction samples** in the dashboard. Paste a PNG/JPEG
confirmation (up to 8 MB), or select a file. Local Tesseract OCR proposes fields;
review and correct every field, select the account and confirm before saving.
Manual entry works if OCR is unavailable. USD converted means the confirmation
subtotal after commission, not gross security value. CAD totals must reconcile
with the applied CAD/USD rate. Exact duplicate entries are rejected.

Structured data is stored in PostgreSQL for the Compose deployment, outside the application image.
Images are used in a temporary OCR directory that is removed after extraction;
they are not stored in the database or sent to an external image service. Yahoo
receives only a historical date query. Missing Yahoo observations remain missing;
there is no fallback to a different date. JSON export and sample deletion are
available in the entry panel. The dataset does not modify portfolio holdings.
No prediction model or 1% accuracy claim is included at this stage.

Install Tesseract with English language data on a new machine. The current local
setup uses isolated Ubuntu packages under `.tools/ocr` without requiring sudo.
Restart `dashboard_server.py` after updating its source. Existing browser profile
and holding settings remain separate from the transaction dataset.

## Financial models

New model projects live under [`models/financials/`](models/financials/README.md).
The CIBC FX model workspace is [`cibc_fx/`](models/financials/cibc_fx/README.md).
Reviewed transaction data lives in PostgreSQL for the Compose deployment; model
training reads it without modifying saved samples. The original SQLite file is retained as a legacy snapshot.

## Opening option premiums

Expand **Option premiums · record opening sale** to record an opening call sale.
Enter account, ticker, expiry, strike, contracts, settlement date, USD premium per
share, total USD fees, applied FX and actual net CAD received. Review before saving.
The `option_premiums` database table persists confirmations
separately from FX model training samples. Exact duplicate confirmations are
rejected. A single exact match on account/ticker/expiry/strike/contract quantity
supplies the holding's net premium for dashboard calculations. Multiple matching
opening lots require explicit aggregation; the dashboard does not choose a lot.
This form supports standard calls with a 100-share multiplier. It does not execute
trades or refresh the FX model.

## Closing simulator and AI assessments

The application owns OpenAI integration; statistical models stay independent.
See [setup and usage](CLOSING_SIMULATOR.md). From the repository root, run
`python3 coveredCallOptimizer/setup_openai.py` for server-side key setup and
`python3 coveredCallOptimizer/close_simulator_server.py` to serve the simulator on port 8766.

## Shared stock cost basis

Stock purchase basis is stored in the database table `stock_cost_basis`,
keyed by account, ticker and account currency. Profile → Settings saves it through
`/api/stock-cost-basis`. Average cost is calculated from total cost and quantity.
The closing simulator and assessment service read this same table. Reload the
simulator or refresh its quotes after saving changes. Old browser-only basis
records are backed up locally and can be imported with the settings import button;
that explicit import replaces matching database bases. Profile names, bid thresholds
and option entry overrides remain browser preferences. The old seed JSON has been
archived; it is not a runtime source. Migration can be rerun without replacing
later database edits.

## Optimizer product direction

See [Reusable optimizer direction and priorities](docs/optimizer-product-direction.md) for the agreed direction toward broader trader needs, consistent outcome accounting, configurable objectives, risk scenarios and validation. Proposed work is distinguished from current features.
