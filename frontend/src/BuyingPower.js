export function availableBuyingPower(accountFunds,account) {
  const value=accountFunds?.[account]?.USD?.buyingPower;
  return typeof value==='number' && Number.isFinite(value) ? value : 0;
}
// USD chart funding is compared only with the same account's entered USD value.
// This is a net-cash comparison, not a broker margin/eligibility calculation.
export function buyingPowerCheck(row,accountFunds,account) {
  const buyingPower=availableBuyingPower(accountFunds,account);
  const required=row.roll_funding?.net_debit_usd;
  if(typeof required!=='number' || !Number.isFinite(required) || required<0) return {status:'unavailable',buyingPower};
  const requiredCents=Math.round(required*100), availableCents=Math.round(buyingPower*100);
  if(!Number.isFinite(requiredCents) || !Number.isFinite(availableCents)) return {status:'unavailable',buyingPower};
  return {status:requiredCents>availableCents ? 'exceeds' : 'within',buyingPower,required,
    shortfall:Math.max(0,requiredCents-availableCents)/100};
}
