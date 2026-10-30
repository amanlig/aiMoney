// Export exactly the filtered rows behind the dashboard, including scenario results.
const profit = row => Object.hasOwn(row, 'total_pl_usd') ? row.total_pl_usd : row.net_profit_usd;
const cell = value => {
  if (value == null || typeof value === 'number' && !Number.isFinite(value)) return '';
  const text = String(value);
  // Keep numeric losses numeric; prevent text from becoming Excel formulas.
  const safe = typeof value === 'string' && /^[\s]*[=+\-@]/.test(text) ? "'" + text : text;
  return '"' + safe.replaceAll('"', '""') + '"';
};
export function rolloverCsv(analysis, baseline = analysis) {
  const {inputs: d, result: result} = analysis;
  const reference = d.opening_reference || {};
  const close = baseline.result.rows.find(r => r.strategy === 'Close now');
  const closeProfit = close ? profit(close) : null;
  const rows = result.rows.filter(r => r.strategy === 'Roll then close').slice().sort((a, b) => {
    const ap = profit(a), bp = profit(b);
    return Number.isFinite(ap) && Number.isFinite(bp) ? bp - ap : Number.isFinite(ap) ? -1 : Number.isFinite(bp) ? 1 : 0;
  });
  const records = rows.map((r, i) => {
    const q = d.candidates.find(q => q.expiry === r.expiry && q.strike === r.strike) || {};
    const f = r.roll_funding || {}, exp = r.expire_worthless;
    return {
      rank: Number.isFinite(profit(r)) ? i + 1 : null,
      account: d.account, symbol: d.symbol, position_id: d.position_id,
      replacement_expiry: r.expiry, replacement_strike_usd: r.strike,
      estimated_total_position_profit_usd: profit(r),
      close_today_total_profit_usd: closeProfit,
      estimated_profit_difference_vs_close_today_usd: Number.isFinite(profit(r)) && Number.isFinite(closeProfit) ? profit(r) - closeProfit : null,
      replacement_bid_usd: q.bidPrice, replacement_ask_usd: q.askPrice,
      replacement_bid_size: q.bidSize, replacement_ask_size: q.askSize,
      held_call_buyback_usd: f.held_buyback_usd, replacement_premium_usd: f.replacement_premium_usd,
      net_rollover_debit_usd: f.net_debit_usd, net_rollover_credit_usd: f.net_credit_usd,
      model_probability_beating_close: r.probability_beating_close,
      sale_floor_pass_rate: r.sale_floor_pass_rate, all_paths_meet_sale_floor: r.eligible,
      expire_worthless_option_cash_only_usd: exp ? profit(exp) ?? exp.option_profit_usd : null,
      shares: d.shares, contracts: d.contracts, held_expiry: d.held.expiry, held_strike_usd: d.held.strike,
      stock_bid_usd: d.stock.bidPrice, stock_ask_usd: d.stock.askPrice,
      stock_purchase_cost_including_fees_usd: reference.stock_cost_usd,
      scenario: analysis.scenario ? 'Hypothetical stock price' : 'Captured quotes',
      scenario_stock_price_usd: analysis.scenario?.stock_price ?? (d.stock.bidPrice + d.stock.askPrice) / 2,
      quote_captured_at_utc: d.captured_at, valuation_date: d.as_of,
      interest_rate_continuous: result.rate ?? 0.04, interest_yield_annual_percent: d.interest_rate?.annual_percent,
      interest_rate_source: d.interest_rate?.source || (result.rate === undefined ? 'Legacy fixed 4%' : 'Explicit model argument'),
      interest_rate_source_url: d.interest_rate?.source_url, interest_rate_observed_on: d.interest_rate?.observed_on,
      interest_rate_matched_expiry: d.interest_rate?.expiry, interest_rate_valuation_date: d.interest_rate?.valuation_date,
      interest_rate_lower_tenor_years: d.interest_rate?.lower_tenor_years, interest_rate_upper_tenor_years: d.interest_rate?.upper_tenor_years,
      horizon_trading_days: r.days, simulation_paths: result.paths, model_version: result.version,
      minimum_strike_usd: result.search?.minimum_strike, minimum_strike_exclusive: result.search?.minimum_exclusive,
      first_expiry: result.search?.first_expiry, last_expiry: result.search?.last_expiry,
      sale_floor_usd: result.minimum_stock_sale_price_usd,
      criteria: 'Strike >= 120% of purchase price and > scenario stock midpoint; expiry after valuation date through held expiry + 12 months; validated nonhalted positive two-sided quotes, zero delay, full contract sizes, valid IV. Sale-floor failures remain included.',
      notes: 'Sorted by estimated whole-position profit; unavailable profits blank and last. Probabilities are fractions. Expire cash excludes retained stock value. Future fees excluded; quotes are saved, simulations are not forecasts.',
      model_assumptions: (result.assumptions || []).join('; '),
    };
  });
  if (!records.length) return null;
  const columns = Object.keys(records[0]);
  return '\uFEFF' + [columns.map(cell).join(','), ...records.map(r => columns.map(k => cell(r[k])).join(','))].join('\r\n') + '\r\n';
}
export function downloadRollovers(analysis, baseline) {
  const csv = rolloverCsv(analysis, baseline);
  if (!csv) return;
  const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8;'}));
  const link = document.createElement('a');
  const d = analysis.inputs;
  link.href = url;
  link.download = `${d.account}-${d.symbol}-all-rollovers-${d.captured_at?.slice(0, 10) || 'saved'}.csv`.replace(/[^a-zA-Z0-9._-]/g, '_');
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
