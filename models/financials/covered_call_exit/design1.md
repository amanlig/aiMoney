# Proposed TFT option-pricing architecture

[View design1.svg](design1.svg). This is a proposal; no runtime model was replaced.

The [candidate TFT-Lite model](https://huggingface.co/major-year-project/tft-option-pricing)
uses SPY option data, ten-day per-contract sequences and twelve features including
IV, Greeks, liquidity and contract attributes. Its output is a single-step option
mark. The model card does not establish an ASTS thirty-day bid/ask forecast.

Proposed additions:

1. Investment-owned collectors and a private historical snapshot archive. Test
   Questrade option candles; separately collect bid/ask and Greek history. Confirm
   volume, open-interest and all other feature availability. Do not treat candles
   as historical bid/ask quotes.
2. An independent training pipeline under `models/financials`: chronological,
   purged splits; exact feature definitions; a direct thirty-trading-day mark target
   using only features available at the forecast date. Never use future observed
   Greeks or IV as forecast inputs. Exclude targets beyond contract expiry and
   retain the existing expiration-settlement logic for those cases.
3. Adapt / fine-tune the TFT architecture rather than assume its existing weights
   support ASTS and the required horizon. A separate spread model supplies a
   nonnegative spread estimate; verify the mark-to-midpoint convention before
   deriving bid and ask. Capture prediction uncertainty and pricing bounds.
4. Walk-forward evaluation against the current pricing baseline on the stocks we
   actually hold. Check errors by expiry/moneyness, interval coverage, quote
   availability, and net-profit ranking stability. Inspect license, code,
   checkpoint compatibility and pretrained-data overlap before promotion.
5. Approved versioned bundle: model, transforms, schema, forecast horizon,
   spread model and evaluation results. The app supplies data and retains its
   existing pricing baseline when the bundle or required features are unavailable.
6. At inference, use current market bids/asks for trades now and forecasts for
   later liquidation. Keep stock-scenario assumptions explicit and consistent
   with Greeks/IV inputs. This requires joint scenario validation; model outputs
   must not be interpreted as unconditional thirty-day market predictions.
7. Preserve the existing app chart: fixed captured Close today plus the top three
   rollovers, slider, USD gross original transactions and sale-floor flags.

Broker credentials and network access remain in `coveredCallOptimizer`. The pure model
package has no broker authentication, OpenAI client or order-execution functions.
The architecture diagram does not authorize or perform model uploads, external
publication, data purchases, training or runtime deployment.

Regenerate with:

Run from the `coveredCallOptimizer` repository root.

```sh
python3 models/financials/covered_call_exit/draw_design1.py
```
