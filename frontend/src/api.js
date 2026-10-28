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
  if (response.status === 401 && !path.startsWith('/api/auth/')) location.assign('/signin');
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}
export const money = value => Number.isFinite(value)
  ? value.toLocaleString('en-CA', {style: 'currency', currency: 'USD'}) : 'Not recorded';
export const midpoint = analysis => (analysis.inputs.stock.bidPrice + analysis.inputs.stock.askPrice) / 2;
export const rollKey = (analysis, row) => `${analysis.inputs.account}|${analysis.inputs.symbol}|${analysis.inputs.position_id ? analysis.inputs.position_id + '|' : ''}${row.expiry}|${row.strike}`;
export const holdingIdentity = h => h?.position_id || h?.position_key || JSON.stringify([h?.account,h?.symbol,h?.call_expiry,h?.call_strike_native_currency]);
export const positionRequest = h => ({account:h.account,symbol:h.symbol,...(h.position_id ? {position_id:h.position_id} : {})});
export const captureQuery = h => new URLSearchParams(positionRequest(h)).toString();
export const holdingLabel = h => h.call_contracts===0 ? `${h.account} · ${h.symbol} · ${h.shares} shares · Stock only` : `${h.account} · ${h.symbol} · $${h.call_strike_native_currency} · ${h.call_expiry} · ${h.call_contracts} calls / ${h.shares} shares`;
export function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch { return fallback; }
}
