# Investment closing simulator and OpenAI assessments

## Covered-call closing visualization

Run `python3 coveredCallOptimizer/simulate_close.py` to generate
`coveredCallOptimizer/reports/covered-call-close.html`, a standalone interactive ASTS example.
It reads the confirmed RRSP stock basis, exact opening-premium record, saved
broker bids/asks and FX reference. It displays the confirmed opening cash flows
beside hypothetical closing cash flows, plus a cumulative cash-flow waterfall.
The simulation assumes closing today. Change stock bid, call ask, closing fees,
reference FX and conversion treatment. Each leg uses the corresponding fitted buy/sell adjustment. Saved quotes are timestamped snapshots, not a live feed. It does not retrieve
historical data or forecast future prices.
Inputs are temporary browser scenarios, not database edits. This first worksheet
covers the full 500-share position and five standard calls, not partial closes.

Run `python3 coveredCallOptimizer/close_simulator_server.py` and open
http://localhost:8766/covered-call-close.html to enable **Refresh quotes**.
The button fetches Questrade quotes/Greeks and Yahoo FX; fees and conversion
treatment remain unchanged. The model is not retrained. Page reload alone uses
the generated snapshot; press Refresh quotes for a new capture.

## Independent OpenAI assessments

The **Recommendation** panel supports fresh assessments outside the chat, using
an explicit goal, quote/scenario snapshot and server-calculated cash flows.
Opening the panel does not call OpenAI; **Generate new assessment** does.

Configure from the repository root:

```sh
python3 coveredCallOptimizer/setup_openai.py
python3 coveredCallOptimizer/close_simulator_server.py
```

Setup accepts hidden key input and saves it in the ignored, mode-0600 file
`coveredCallOptimizer/.secrets/openai.json`. Never enter a key into chat, HTML or browser
storage. Alternatively configure `OPENAI_API_KEY` and optionally `OPENAI_MODEL`
in the server environment. Configuration is checked on each request, so the
setup file does not require a server restart. Default model: `gpt-6-astra`;
model access and API billing depend on your OpenAI project.

The process displayed in the panel:

1. Use the displayed prices; optionally Refresh quotes first.
2. Read confirmed basis, exact opening premium and fitted FX parameters locally.
3. Recalculate the two closing legs, conversion and total position gain server-side.
4. Send the selected scenario and goal to OpenAI Responses API with `store=false`.
5. Save the successful assessment and immutable input/calculation snapshot in
   SQLite `recommendation_runs`, including model, prompt version, timestamp,
   response ID and usage. View the latest 20 saved runs in the panel.

Trading details and scenario amounts are transmitted to OpenAI only when you
click Generate. API keys and broker credentials are not assessment inputs.
The server never submits trades. Requests have no research tools or chat history;
company news, the full portfolio and replacement investment are not evaluated.
The UI marks an assessment as belonging to an older snapshot after inputs change.
Viewing history is replaying a saved result, not regenerating it; a fresh run may
differ even with the same inputs. Failed or incomplete API responses are not
saved as successful assessments. There is no silent rule-based fallback.

The standalone worksheet is still a full-position ASTS example. The assessment
server reads the shared SQLite `stock_cost_basis` table. Dashboard basis saves
are available to new assessments immediately, and to the closing worksheet on
page reload or quote refresh.

Official API setup: https://developers.openai.com/api/docs/quickstart
