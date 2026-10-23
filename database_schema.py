"""Version 1 schema. Preserve legacy floating-point values during migration."""

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS samples (
        id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, account TEXT NOT NULL,
        symbol TEXT NOT NULL, instrument TEXT NOT NULL, action TEXT NOT NULL,
        direction TEXT NOT NULL, trade_date TEXT, settlement_date TEXT NOT NULL,
        usd_amount REAL NOT NULL, commission_usd REAL, cad_amount REAL NOT NULL,
        applied_rate REAL NOT NULL, yahoo_close REAL, yahoo_status TEXT NOT NULL,
        notes TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS stock_cost_basis (
      id INTEGER PRIMARY KEY, account TEXT NOT NULL, symbol TEXT NOT NULL,
      currency TEXT NOT NULL, purchase_date TEXT, quantity REAL NOT NULL,
      price_usd REAL, fees_usd REAL, purchase_fx REAL, total_cost REAL NOT NULL,
      updated_at TEXT NOT NULL, UNIQUE(account,symbol,currency))""",
    """CREATE TABLE IF NOT EXISTS option_premiums (
        id INTEGER PRIMARY KEY, account TEXT NOT NULL, symbol TEXT NOT NULL,
        expiry TEXT NOT NULL, strike REAL NOT NULL, contracts INTEGER NOT NULL,
        settlement_date TEXT NOT NULL, price_usd REAL NOT NULL,
        fees_usd REAL NOT NULL, fx REAL NOT NULL, net_cad REAL NOT NULL,
        net_usd REAL NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(account,symbol,expiry,strike,contracts,settlement_date))""",
    """CREATE TABLE IF NOT EXISTS option_premium_sales_usd (
          id INTEGER PRIMARY KEY, account TEXT NOT NULL, symbol TEXT NOT NULL,
          expiry TEXT NOT NULL, strike REAL NOT NULL, contracts INTEGER NOT NULL,
          settlement_date TEXT NOT NULL, price_usd REAL NOT NULL, gross_usd REAL NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(account,symbol,expiry,strike,contracts,settlement_date))""",
    """CREATE TABLE IF NOT EXISTS recommendation_runs (
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, model TEXT NOT NULL,
      prompt_version TEXT NOT NULL, snapshot_json TEXT NOT NULL,
      assessment TEXT NOT NULL, response_id TEXT, usage_json TEXT NOT NULL)""",
)

SCHEMA = {statement.split()[5]: statement for statement in STATEMENTS}
