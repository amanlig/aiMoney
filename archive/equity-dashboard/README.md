# Archived equity dashboard

Archived October 20, 2026 at the user's request. The active home page is
`/covered-call-optimizer.html`; `/`, `/index.html` and `/equity-chart.html`
redirect there. The archived report can be opened at `/archive/equity-chart.html`.

Moved together:

- Private generated `equity-chart.html` (ignored by Git).
- Its renderer, `chart.py`.
- Dashboard-only `roll_ui.js`, `roll_pricing.js`, `stock_details_ui.js` and
  `fx_samples_ui.js`.
- Dashboard-specific `test_chart.py` and `test_roll_pricing.js`.

Shared components remain active: Profile / Settings, entry-price helpers,
purchase and premium persistence, portfolio data shaping, market-data clients,
backend helpers, accounting, vendor assets used by other reports and the separate
closing worksheet. They are not unused merely because the dashboard is archived.
The shared `account_widget` data helper is now in `coveredCallOptimizer/portfolio_data.py`.

The archived generator reads shared code/data from the active investment folder
and writes to this archive by default. Running it is optional:

```sh
python3 coveredCallOptimizer/archive/equity-dashboard/chart.py
```

Broker position imports no longer regenerate this page automatically. The optional
`questrade_positions.py --archive-chart` switch explicitly requests regeneration.
The original `--no-chart` switch remains accepted for command compatibility.
No financial database or broker credentials were moved or changed.
