# Questrade quote capture

## LIRA position sync

From this folder, run `python3 questrade_positions.py`. This uses the saved API
authorization, selects the unique active account with type LIRA, retrieves its
positions, validates the call deliverables, and captures stock bids/call asks.
It replaces `data/lira-closing.json`, preserves a dated prior snapshot, saves a
source report without account numbers, and regenerates the three-account page.
Refresh http://localhost:8765/covered-call-optimizer to view the result. Refreshes are
manual, not scheduled or streamed. No FX input is required because LIRA stays USD.

Use `--new-token` only when a new manual authorization token is needed, and
`--no-chart` to sync without regenerating the page. The account API permission
must permit reading accounts/positions. Multiple active LIRAs stop selection;
no account is silently guessed. Tokens remain owner-only, and no account numbers
are logged or put in the dashboard. The source report and new snapshot use
owner-only file permissions.

Current support is long USD stocks and standard, fully covered short calls with
one call series per underlying. Stock-only rows are preserved but excluded from
covered-call totals. Adjusted contracts, reorganization, unsupported holdings,
overcoverage and incomplete quotes stop the sync before replacing the snapshot.
Current stock totalCost and negative short-call totalCost supply the basis/premium
proxy; missing costs stay unknown. This is not a retrieval of original trade
cash flows or lifetime P/L. Cash, balances, activities and orders are not read.

## Saved CAD positions and FX

FX now uses Questrade Global only. Yahoo and Bank of Canada automatic retrieval
and fallback have been removed. Historical reports are preserved.

Stock bids and call asks still come from the authorized Questrade brokerage API.
A supported Global FX quote connection has not yet been verified.

Until then, run from this folder with the actual displayed FX rates and timestamp:

```bash
python3 questrade_quotes.py data/tfsa-closing.json --usd-sell-cad BID --usd-buy-cad ASK --fx-observed-at FULL_ISO_TIMESTAMP_WITH_OFFSET --output reports/NEW_CAPTURE.json
python3 simulator.py data/tfsa-closing.json --scenarios reports/NEW_CAPTURE.json --output reports/NEW_EXIT.json
```

Both rates are CAD per USD. Both legs settle in USD, then positive net proceeds
use the bid; a shortfall uses the ask. Saved closing fees are CAD equivalents.
Questrade Global FX trading quotes are not yet verified as TFSA conversion rates.

Alternatively pass `--fx-quotes PATH` containing a JSON array with source exactly
`Questrade Global`, `observed_at` (full date/time and UTC offset), `cad_per_usd`,
`bid_cad_per_usd`, and `ask_cad_per_usd`. Latest valid source timestamp wins.
No external FX source is contacted. A time-only screenshot is insufficient to
establish date and timezone. A missing FX input stops before authorization.

API tokens stay in `.secrets/questrade.json` with owner-only permissions. Use
`--new-token` to prompt for a newly generated manual authorization token.
The importer uses market endpoints only and does not submit orders.

## Local preview alongside AWS

The local source preview uses a separate private directory at
`.secrets/local-preview/`; the server's Questrade token copy is never mounted.
Create a separate personal application named **aiMoney Local** in Questrade API
Centre and generate its manual authorization token. Keep the cloud application's
authorization unchanged. Questrade documents the app registration and manual-token
steps at https://www.questrade.com/api/documentation/getting-started.

Run on the local host in this repository (not inside the container):

```sh
python3 setup_questrade_local.py
docker compose -f compose.yaml -f compose.local-preview.yaml up -d --no-build api
```

The prompt hides the token; never paste it into chat, a command argument or source.
The directory is private (700), the token file is 600, and only this dedicated
directory is writable/mounted for local refresh-token rotation. The setup refuses
a token matching the old shared copy. No live authentication occurs until an
explicit refresh. A missing authorization fails before any history/network request
and never prompts from a web worker. Provider-history errors identify Yahoo
Finance separately; the UI mentions retained results once, only if a saved result
exists. Startup still disables automatic macro refresh and local sign-in.
