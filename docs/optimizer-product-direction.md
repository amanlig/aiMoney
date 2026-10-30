# Covered-call optimizer: reusable product direction

Captured October 20, 2026, following discussion with the user.

## Intent

Build a reusable decision-support tool that serves both developing and experienced
options traders. Its assumptions, constraints and ranking logic must be explicit,
configurable and testable rather than encode one person's trading habits.
This document records agreed direction and proposed work, not completed features,
validated trading advice or a commitment to a delivery timeline.

The user's current preference is to retain shares when conditions look healthy,
and consider releasing cash when downside becomes unacceptable or macro conditions
deteriorate. That is one supported objective, not a universal default for all users.

## Current decision: retain the existing pricing model

On October 20, 2026, the user confirmed that the tool currently provides enough
information to support their decisions and explicitly accepted its constant
implied-volatility and absolute bid/ask-spread assumptions for now. Retain the
current pricing model; no TFT integration or volatility-model replacement is
required in the current scope. Acceptance of these assumptions does not validate
the forecasts or guarantee execution, profit or risk estimates.

Near-term work should improve clarity, consistent accounting, comparable outcomes
and configurable decision constraints. Keep the accepted assumptions visible,
without making further pricing-model research a prerequisite for using the tool.
The reusable design should let other traders choose or challenge assumptions
rather than treat this user's acceptance as universal.

## Three product layers

| Layer | Purpose | Capabilities |
| --- | --- | --- |
| Position and cash | Establish what is owned, owed and affordable | Verified transactions, quote snapshots, opening premiums, basis, rollover debit/credit, closing cash and profit |
| Risk and scenarios | Explain what could change and how outcomes differ | Stock and volatility scenarios, Greeks, assignment outcomes, downside ranges and retained-stock value |
| Decision preferences | Rank choices for the trader's actual objective | Retain shares, free cash, earn income or reduce risk, subject to explicit cash, downside and assignment constraints |

Progressive disclosure should keep the chart accessible while making advanced
controls, formulas, provenance and assumptions available without hiding material
limitations. Explanations belong in documentation; position inputs in settings.

## First priority: comparable outcomes

Current Close mode reports a fully liquidated position. Current Expire mode is
conditional on the replacement call expiring worthless: it retains shares and
reports cumulative option-only P&L. These quantities must not be treated as the
same performance measure or ranked together without valuing retained assets.

Define and show separately:

- Cash flow at trade entry, at review and at expiration.
- Cash needed to fund the rollover, distinct from broker buying power or margin.
- Realized option P&L, realized stock P&L and unrealized stock P&L.
- Retained shares and the outstanding short-option liability.
- Total position value / economic gain at a common valuation date.
- Time to review, expiration and potential capital release.

Compare hold, close, roll and expiration/assignment outcomes on a consistent basis.
A review horizon need not force a stock sale. A worthless-expiry scenario must
remain conditional, not be presented as the model's forecast or as free profit.
Use the original position consistently and include buyback costs once.

Success: users can reconcile each displayed amount and understand why retaining
shares and liquidating shares produce different cash and wealth outcomes.

## Next capabilities

### Independent stock and volatility controls

Future optional enhancement: add volatility scenarios alongside stock-price
scenarios. This is deferred, not required for the current accepted model. Explain the treatment
of skew, term structure, spreads and future Greeks. Preserve captured market
benchmarks; clearly distinguish observations from hypothetical values. Fixed
volatility remains the current baseline, not a claim about future market behavior.

### Broader outcome and risk comparisons

Evaluate keeping the existing position, buying back calls while retaining shares,
closing the position, rolling, worthless expiry and assignment. Add Greeks and
appropriate downside / uncertainty measures. Include timing and liquidity rather
than ranking solely by average dollar profit.

A healthy-market or macro assessment is proposed, not implemented. Define its
inputs, sources, thresholds, refresh frequency and failure behavior before using
it to change a ranking. It cannot guarantee advance warning of a rapid decline.

### Configurable preferences and constraints

Support per-account / per-position controls for:

- Available USD cash and maximum rollover debit.
- Maximum acceptable downside or loss, with an explicit reference point.
- Acceptable assignment price and willingness to sell shares.
- Expiry range and review horizon.
- Income, cash-release, share-retention and risk-reduction preferences.

Distinguish hard eligibility constraints from warnings and ranking preferences.
Let users inspect excluded choices and understand why a candidate was rejected.
Do not equate a simulated path frequency with a validated probability or guarantee.

### Transparent, explainable results

Show quote timestamps and freshness, source, observed versus estimated prices,
pricing model/version, uncertainty and assumptions. Explain ranking contributions
and constraint failures. Keep the cash-funding indicator separate from broker
margin requirements; no additional-deposit estimate without account data.

### Historical validation before model promotion

Test Questrade historical candles for exact contracts and document coverage.
Historical OHLCV does not establish historical bid/ask or Greek availability.
Collect or obtain suitable quote history for the held underlyings, then evaluate
pricing and ranking accuracy chronologically outside the fitting data.

Compare simple baselines with proposed alternatives on price error, uncertainty
coverage, downside behavior and decision/ranking stability. Include realistic
costs, spreads, quote quality and data gaps in validation even if a simplified UI
view excludes fees. Validate across stocks, expiries, moneyness and market regimes.
More complex models should be adopted only when evidence supports improvement.

The SPY-trained Hugging Face TFT is a research candidate, not a demonstrated upgrade
for individual-stock options or a validated thirty-day bid/ask predictor.

## TFT: deferred research option

The candidate is Hugging Face `major-year-project/tft-option-pricing`. Its
published description covers SPY-option mark prediction from ten-day sequences
with a single-step output. It is not established as an ASTS/NVDA model, a separate
bid/ask predictor or a thirty-trading-day forecast. `design1.svg` is a proposed
architecture only; no TFT checkpoint is used by the running application.

Potential value, if demonstrated on relevant data:

- More accurate future option mark / buyback estimates.
- Better rollover profit estimates and ordering of candidate trades.
- Better calibrated uncertainty when combined with a separately validated spread
  and uncertainty component; these are not automatically supplied by TFT.

TFT would not fix transaction accounting, determine available cash, calculate
broker buying power, or decide the trader's objectives. Those remain separate
responsibilities. Do not assume a more sophisticated model is a better model.

Revisit TFT only when a concrete pricing limitation warrants investigation and
suitable historical data are available. Before adoption:

1. Define the forecast target and horizon, and verify every input is available at
   prediction time; distinguish option marks from executable bid/ask prices.
2. Establish historical coverage for the actual underlyings and contracts.
3. Adapt / retrain as needed and evaluate chronologically against the existing
   baseline, without future-data leakage.
4. Demonstrate useful improvement in price errors and decision/ranking stability,
   including downside behavior, liquidity and costs.
5. Review the evidence before any runtime replacement; preserve baseline fallback.

No TFT download, training, data purchase, deployment or delivery date is implied
by this document. Historical-data and model-upgrade work remains a future option,
not the next mandatory task.

## Architecture principles

Keep these responsibilities separate:

1. **Transaction accounting:** original transactions, quantities, basis and premium
   history, with reconciliation and clear realized/unrealized accounting.
2. **Pricing and simulation:** interchangeable independent models, consistent
   scenario inputs and versioned evaluation evidence under `models/financials`.
3. **Decision rules:** explicit objectives, constraints, risk preferences and ranking
   explanations, rather than hidden assumptions inside a pricing formula.
4. **Application and presentation:** broker access, credentials, storage, settings,
   API adapters and chart interaction under `coveredCallOptimizer`.

No broker credentials or OpenAI integration inside independent model packages.
Allow data-provider and pricing-model replacements without rewriting accounting
or the dashboard. No order execution is added by this direction document.

## Current foundation versus proposed work

Existing foundation includes USD cash-flow comparisons, three ranked rollovers,
a fixed captured Close today benchmark, a stock-price slider, conditional
Close/Expire controls, original transaction references and net-debit funding
indicators. Read the implementation guide for exact current limitations.

Not yet implemented: a common-wealth ranking across retained and liquidated stock,
available-cash eligibility, an independent volatility control, a macro-health
exit rule, comprehensive risk ranking, historical option-model validation or TFT
runtime integration.

## Priorities under the accepted pricing assumptions

1. Agree on comparable cash, realized/unrealized P&L and position-value definitions.
2. Implement retained-stock and assignment outcomes on that basis.
3. Add available-cash and explicit risk/assignment constraints.
4. Improve explanations of rankings and existing downside/scenario information.
5. Extend objective-driven comparisons when user requirements justify them.

Deferred optional research: volatility sensitivity, historical option-data coverage,
walk-forward validation and evidence-based pricing upgrades such as TFT. These
remain important for establishing predictive performance, but are not prerequisites
for the user's current conditional scenario-analysis use.

Revisit the order as data coverage and user requirements become clearer; no dates
or numerical risk limits have been agreed.

## Liquidity research canceled October 29, 2026

The user canceled the proposed intraday liquidity model and quote collector.
Close today uses captured stock and held-call midpoints instead. Captured bid/ask
quotes remain available unchanged in the actual Close workflow, whose execution
inputs remain manual. Midpoint valuation is not a guaranteed execution price.

## Related documents

- [Optimizer usage and algorithm](../COVERED_CALL_OPTIMIZER_README.md)
- [Current model design](../models/financials/covered_call_exit/DESIGN.md)
- [Proposed TFT architecture](../models/financials/covered_call_exit/design1.md)
- [Investment architecture](../ARCHITECTURE.md)
