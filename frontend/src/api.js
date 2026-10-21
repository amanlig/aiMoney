export async function api(path, {body, signal, allowMissing = false, ...options} = {}) {
  const response = await fetch(path, {
    cache: 'no-store', ...options, signal,
    ...(body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    }),
  });
  if (!response.ok && response.status === 404 && allowMissing) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
export const money = value => Number.isFinite(value)
  ? value.toLocaleString('en-CA', {style: 'currency', currency: 'USD'}) : 'Not recorded';
export const midpoint = analysis => (analysis.inputs.stock.bidPrice + analysis.inputs.stock.askPrice) / 2;
export const rollKey = (analysis, row) => `${analysis.inputs.account}|${analysis.inputs.symbol}|${row.expiry}|${row.strike}`;
export const holdingLabel = h => `${h.account} · ${h.symbol} · $${h.call_strike_native_currency} · ${h.call_expiry}`;
export function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch { return fallback; }
}
