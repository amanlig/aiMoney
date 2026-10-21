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
