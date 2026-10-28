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
    """CREATE TABLE IF NOT EXISTS option_rollovers (
      id INTEGER PRIMARY KEY, account TEXT NOT NULL, symbol TEXT NOT NULL,
      settlement_date TEXT NOT NULL, contracts INTEGER NOT NULL,
      buyback_expiry TEXT NOT NULL, buyback_strike REAL NOT NULL, buyback_price_usd REAL NOT NULL,
      sale_expiry TEXT NOT NULL, sale_strike REAL NOT NULL, sale_price_usd REAL NOT NULL,
      fees_usd REAL NOT NULL, buyback_total_usd REAL NOT NULL, sale_total_usd REAL NOT NULL,
      net_cash_usd REAL NOT NULL, created_at TEXT NOT NULL,
      UNIQUE(account,symbol,settlement_date,contracts,buyback_expiry,buyback_strike,sale_expiry,sale_strike))""",
    """CREATE TABLE IF NOT EXISTS closed_holdings (
      id INTEGER PRIMARY KEY, position_key TEXT NOT NULL UNIQUE,
      account TEXT NOT NULL, symbol TEXT NOT NULL, close_date TEXT NOT NULL,
      shares REAL NOT NULL, contracts INTEGER NOT NULL, expiry TEXT NOT NULL, strike REAL NOT NULL,
      stock_price_usd REAL NOT NULL, buyback_price_usd REAL NOT NULL, fees_usd REAL NOT NULL,
      stock_sale_usd REAL NOT NULL, buyback_total_usd REAL NOT NULL, closing_cash_usd REAL NOT NULL,
      realized_pl_usd REAL, position_json TEXT NOT NULL, accounting_json TEXT NOT NULL,
      created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS covered_positions (
      id TEXT PRIMARY KEY, account TEXT NOT NULL, symbol TEXT NOT NULL,
      shares REAL NOT NULL, contracts INTEGER NOT NULL, expiry TEXT NOT NULL, strike REAL NOT NULL,
      source_key TEXT UNIQUE, base_json TEXT NOT NULL, opening_json TEXT,
      opening_source TEXT UNIQUE, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS covered_position_rollovers (
      id TEXT PRIMARY KEY, position_id TEXT NOT NULL REFERENCES covered_positions(id),
      source_key TEXT UNIQUE, record_json TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS option_expirations (
      id TEXT PRIMARY KEY REFERENCES covered_positions(id), account TEXT NOT NULL, symbol TEXT NOT NULL,
      expiry TEXT NOT NULL, strike REAL NOT NULL, contracts INTEGER NOT NULL, shares_retained REAL NOT NULL,
      fees_usd REAL NOT NULL, cash_flow_usd REAL NOT NULL, realized_option_pl_usd REAL,
      position_json TEXT NOT NULL, accounting_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS position_share_sources (
      id TEXT PRIMARY KEY REFERENCES covered_positions(id), links_json TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS deleted_position_sources (
      source_key TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS deleted_share_sources (
      id TEXT PRIMARY KEY, created_at TEXT NOT NULL, links_json TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS recommendation_runs (
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, model TEXT NOT NULL,
      prompt_version TEXT NOT NULL, snapshot_json TEXT NOT NULL,
      assessment TEXT NOT NULL, response_id TEXT, usage_json TEXT NOT NULL)""",
)

SCHEMA = {statement.split()[5]: statement for statement in STATEMENTS}
