PostgreSQL deployment: training reads the configured `DATABASE_URL` read-only.
Explicit SQLite paths remain available for archived datasets. See [database setup](../../../POSTGRESQL.md).

# CIBC FX conversion model

A Python standard-library baseline trained on reviewed transactions in
`coveredCallOptimizer/data/fx-samples.sqlite3`. Training opens SQLite read-only.

For each conversion direction, training takes the median of
`applied_rate / yahoo_close - 1`. Prediction multiplies the supplied reference
rate by `1 + adjustment`, then multiplies by the USD subtotal to estimate CAD.
The subtotal already includes deducted/added commission; do not add it twice.
Ticker and security type are not features. No network access is needed.

From the repository root:

Run from the `coveredCallOptimizer` repository root.

```sh
python3 models/financials/cibc_fx/train.py
python3 models/financials/cibc_fx/predict.py --direction buy_usd --reference-rate 1.40 --usd 1000
python3 -m unittest discover -s models/financials/cibc_fx/tests
```

Use `sell_usd` for USD proceeds converted into CAD. The prediction command uses
an explicitly supplied CAD-per-USD reference; it does not fetch a live quote.

## Artifacts and evaluation

- `artifacts/model.json`: final model refitted on all eligible samples, with
  date range, training timestamp, dataset hash and amount ranges.
- `evaluation/holdout.json`: metrics from an earlier-data model evaluated on
  later transactions, including the parameters actually evaluated.

Both directories are private local outputs excluded from Git. Retraining replaces
the outputs. The investment closing simulator consumes the saved model; dashboard rollover calculations remain separate.

Evaluation splits at 80% of distinct settlement dates, keeping transactions
on the same date together. It reports CAD and rate errors, conversion direction,
amount bands and a reference-only comparison. Invalid/missing inputs and
non-reconciling totals are excluded and recorded. At least three training samples
per direction and holdout coverage of both directions are required.

Initial run: 55 eligible samples; 35 training samples through April 10, 2025;
20 holdout samples from April 24 through November 3, 2025. Holdout mean absolute
CAD error was $25.60 (mean absolute percentage error 0.149%); maximum absolute
CAD error was $88.93. These are observed holdout results, not an accuracy guarantee.

## Limits

Yahoo settlement-day daily closes are retrospective and may differ from the
broker's conversion-time reference. Estimated adjustments therefore combine
broker spread and reference timing differences; they are not isolated broker fees.
Live-reference and trade-day prediction accuracy is unvalidated. Shared dates
reduce the independence of the 20 holdout samples. There are no samples after
November 2025 in this training run. Model complexity is deliberately limited for
this small dataset. Amount range warnings identify extrapolation; they are not
prediction intervals. The model does not forecast future market FX rates.

See [Model interactions](INTERACTIONS.md) for the UML sequence diagram.
Run `python3 models/financials/cibc_fx/plot.py` to rebuild the standalone plot report with the diagram.

## Application boundary

This directory contains model training, prediction, evaluation, plots and tests.
It contains no OpenAI client, credentials, recommendation service or application
server. The investment app consumes the fitted parameters and pure prediction
function through its own adapter; model training and prediction run independently.

See the [investment closing-simulator documentation](../../../CLOSING_SIMULATOR.md)
for application setup, quote refresh and AI assessments.

## Hugging Face publication

The inference-only package is prepared with an explicit six-file allowlist:
model card, model.py, predict.py, fitted model JSON, aggregate evaluation JSON,
and a checksum manifest. It excludes raw data, application code and credentials.
It is a custom statistical model, not a Transformers checkpoint or hosted API.

Run from the `coveredCallOptimizer` repository root.

```sh
python3 models/financials/cibc_fx/publish_huggingface.py
python3 models/financials/cibc_fx/publish_huggingface.py --login
python3 models/financials/cibc_fx/publish_huggingface.py --upload
```

Login accepts a Hugging Face write-capable token through hidden terminal input.
The token is stored mode 0600 in ignored `.secrets/hf-token`; `HF_TOKEN` or an
existing Hugging Face token cache is also supported. Do not paste tokens into chat.
The uploader infers the personal username from the token and uses a private
`username/cibc-fx` repository. Change only the name with `--repo-name`.
An existing public repository is rejected; visibility is never silently changed.
After upload, repository privacy and every published file checksum are verified.
The upload URL and commit are saved in ignored `artifacts/huggingface-upload.json`.
