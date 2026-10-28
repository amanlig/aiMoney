import json
from datetime import date,timedelta
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('exit_model',Path(__file__).resolve().parents[1]/'model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ExitModelTests(unittest.TestCase):
    def fixture(self):
        today=date(2026,10,19)
        q=dict(bidPrice=14,askPrice=15,bidSize=10,askSize=10,delay=0,isHalted=False)
        history=[dict(date=(today-timedelta(days=i)).isoformat(),close=40+((i%7)-3)*.15) for i in range(1,89) if (today-timedelta(days=i)).weekday()<5]
        return dict(opening_reference=dict(stock_total_usd=12500,option_total_usd=20000),initial_purchase_price_usd=25,as_of=today.isoformat(),shares=500,contracts=5,stock=dict(q,bidPrice=40,askPrice=40.1),held=dict(q,strike=40,expiry='2028-01-21'),history=history,candidates=[])
    def test_cumulative_history_close_expire_and_saved_accounting(self):
        data=self.fixture()
        data['opening_reference'].update(historical_option_net_usd=2100, stock_cost_usd=12510)
        quote=dict(data['held'], validated=True, strike=45, bidPrice=12, askPrice=13)
        data['candidates']=[quote]
        result=m.evaluate(data, paths=100)
        close=next(r for r in result['rows'] if r['strategy']=='Close now')
        self.assertEqual(close['net_profit_usd'], close['mean']+2100-12510)
        expire=result['top_choices'][0]['expire_worthless']
        self.assertEqual(expire['option_profit_usd'], 2100+expire['mean'])
        cash=close['mean']
        data['opening_reference']['historical_option_net_usd']=-500
        m.apply_accounting(data,result)
        self.assertEqual(close['mean'],cash)
        self.assertEqual(close['net_profit_usd'],cash-500-12510)
        self.assertEqual(expire['option_profit_usd'],expire['mean']-500)
        data['opening_reference']['historical_option_net_usd']=None
        m.apply_accounting(data,result)
        self.assertFalse(result['profit_reference_available'])
        self.assertEqual(result['top_choices'],[])
        self.assertIsNone(close['net_profit_usd'])
        self.assertIsNone(expire['option_profit_usd'])

    def test_realized_and_unrealized_sum_to_total_and_slider_does_not_realize(self):
        data=self.fixture()
        data['opening_reference'].update(prior_realized_option_usd=1500,active_realized_option_usd=200)
        data['candidates']=[dict(data['held'],validated=True,strike=45,bidPrice=12,askPrice=13)]
        result=m.evaluate(data,paths=100)
        for row in result['rows']:
            self.assertEqual(row['realized_pl_usd'],1700)
            self.assertAlmostEqual(row['realized_pl_usd']+row['unrealized_pl_usd'],row['total_pl_usd'])
            self.assertEqual(row['total_pl_usd'],row['net_profit_usd']+1500)
        expire=result['top_choices'][0]['expire_worthless']
        self.assertEqual(expire['realized_pl_usd'],1700)
        self.assertEqual(expire['total_pl_usd'],expire['option_profit_usd']+1500)
        shifted=m.evaluate(m.stock_price_scenario(data,44),paths=100)
        self.assertTrue(all(r['realized_pl_usd']==1700 for r in shifted['rows']))
        original=next(r for r in result['rows'] if r['strategy']=='Close now')
        changed=next(r for r in shifted['rows'] if r['strategy']=='Close now')
        self.assertNotEqual(original['unrealized_pl_usd'],changed['unrealized_pl_usd'])
        data['opening_reference']['prior_realized_option_usd']=None
        m.apply_accounting(data,result)
        self.assertIsNone(result['rows'][0]['realized_pl_usd'])
        self.assertIsNone(result['rows'][0]['total_pl_usd'])

    def test_close_cash_and_seed(self):
        d=self.fixture();r=m.evaluate(d,paths=100)
        self.assertEqual(r['baseline'],12500)
        self.assertEqual(r,m.evaluate(d,paths=100))

    def test_recorded_expiry_is_visible_while_current_history_is_incomplete(self):
        data=self.fixture()
        data['opening_reference'].update(history_status='incomplete',historical_option_net_usd=None,
                                        prior_realized_option_usd=790,realized_sources=[dict(position_id='earlier')])
        result=m.evaluate(data,paths=100)
        row=result['rows'][0]
        self.assertEqual(row['realized_pl_usd'],790)
        self.assertTrue(row['realized_pl_partial'])
        self.assertIsNone(row['unrealized_pl_usd'])
        self.assertIsNone(row['total_pl_usd'])
        self.assertIsNone(row['net_profit_usd'])
        shifted=m.evaluate(m.stock_price_scenario(data,44),paths=100)
        self.assertEqual(shifted['rows'][0]['realized_pl_usd'],790)
        data['opening_reference']['realized_sources']=[]
        m.apply_accounting(data,result)
        self.assertIsNone(row['realized_pl_usd'])
        self.assertFalse(row['realized_pl_partial'])
    def test_candidate_band_and_liability(self):
        d=self.fixture();q=dict(d['held'],validated=True,strike=45,bidPrice=12,askPrice=13)
        d['candidates']=[q,dict(q,strike=40.05),dict(q,expiry='2029-01-22'),dict(q,delay=15)]
        r=m.evaluate(d,paths=100)
        self.assertEqual(r['excluded'],3)
        json.dumps(r)  # app persistence and HTTP response must serialize
        roll=next(x for x in r['rows'] if x['strategy']=='Roll then close')
        self.assertEqual(roll['roll_credit'],-1500)
        self.assertLess(roll['mean'],20000) # replacement liability is deducted
    def test_missing_and_stale_inputs(self):
        for field,value in [('history',[]),('shares',400)]:
            d=self.fixture();d[field]=value
            with self.assertRaises(ValueError):m.evaluate(d,paths=100)
        d=self.fixture();d['held']['askSize']=1
        with self.assertRaises(ValueError):m.evaluate(d,paths=100)
    def test_cash_flow_components_reconcile(self):
        d=self.fixture()
        d['candidates']=[dict(d['held'],validated=True,strike=45,bidPrice=12,askPrice=13)]
        r=m.evaluate(d,paths=100)
        for row in r['rows']:
            self.assertAlmostEqual(sum(row['cash_flows'].values()),row['mean'],places=7)
            self.assertGreater(row['cash_flows']['stock_sale'],0)
            self.assertLessEqual(row['cash_flows']['option_purchase'],0)
            self.assertNotIn('fees',row['cash_flows'])
        close=next(row for row in r['rows'] if row['days']==0)
        self.assertEqual(close['cash_flows']['stock_sale'],20000)
        self.assertEqual(close['cash_flows']['option_purchase'],-7500)
        roll=next(row for row in r['rows'] if row['strategy']=='Roll then close')
        self.assertAlmostEqual(roll['cash_flows']['option_sale'],6000)

    def test_minimum_sale_price(self):
        d=self.fixture();d['initial_purchase_price_usd']=40
        r=m.evaluate(d,paths=100)
        self.assertEqual(r['minimum_stock_sale_price_usd'],44)
        close=next(row for row in r['rows'] if row['days']==0)
        self.assertFalse(close['eligible'])
        d['initial_purchase_price_usd']=None
        with self.assertRaises(ValueError):m.evaluate(d,paths=100)

    def test_top_three_profit_and_new_search_bounds(self):
        d=self.fixture()
        d['candidates']=[dict(d['held'],validated=True,strike=45+i*.25,bidPrice=12,askPrice=13) for i in range(8)]
        r=m.evaluate(d,paths=100)
        self.assertEqual(len(r['top_choices']),3)
        profits=[row['net_profit_usd'] for row in r['top_choices']]
        self.assertEqual(profits,sorted(profits,reverse=True))
        self.assertTrue(all(p>0 for p in profits))
        self.assertEqual(r['search'],dict(minimum_strike=40.05,minimum_exclusive=True,maximum_strike=None,first_expiry='2026-10-20',last_expiry='2029-01-21'))
        d['opening_reference']['option_total_usd']=-100000
        losses=m.evaluate(d,paths=100)['top_choices']
        self.assertEqual(len(losses),3)
        self.assertTrue(all(row['net_profit_usd']<0 for row in losses))
        d['initial_purchase_price_usd']=38
        failures=m.evaluate(d,paths=100)['top_choices']
        self.assertTrue(failures)
        self.assertTrue(all(not row['eligible'] for row in failures))
        d.pop('opening_reference')
        self.assertFalse(m.evaluate(d,paths=100)['profit_reference_available'])

    def test_stock_slider_reprices_options_and_preserves_snapshot(self):
        d=self.fixture();d['candidates']=[dict(d['held'],validated=True,strike=45,bidPrice=12,askPrice=13)]
        original=json.dumps(d,sort_keys=True)
        current=(d['stock']['bidPrice']+d['stock']['askPrice'])/2
        unchanged=m.stock_price_scenario(d,current)
        self.assertEqual(m.evaluate(d,paths=100),m.evaluate(unchanged,paths=100))
        up=m.stock_price_scenario(d,current*1.1);down=m.stock_price_scenario(d,current*.9)
        self.assertGreater(up['held']['askPrice'],d['held']['askPrice'])
        self.assertLess(down['held']['askPrice'],d['held']['askPrice'])
        self.assertAlmostEqual(up['held']['askPrice']-up['held']['bidPrice'],1)
        self.assertNotEqual(m.evaluate(up,paths=100)['baseline'],m.evaluate(down,paths=100)['baseline'])
        self.assertEqual(json.dumps(d,sort_keys=True),original)
        for invalid in [0,current*2,float('nan'),True]:
            with self.assertRaises(ValueError):m.stock_price_scenario(d,invalid)

    def test_strikes_strictly_above_purchase_and_scenario_spot(self):
        d=self.fixture();d['initial_purchase_price_usd']=50
        q=dict(d['held'],validated=True,expiry='2028-03-17')
        d['candidates']=[dict(q,strike=50,bidPrice=8,askPrice=9),dict(q,strike=60,bidPrice=7,askPrice=8),dict(q,strike=100,bidPrice=2,askPrice=3)]
        r=m.evaluate(d,paths=100)
        self.assertEqual(r['excluded'],1)
        self.assertEqual({x['strike'] for x in r['rows'] if x['strategy']=='Roll then close'},{60,100})
        self.assertIsNone(r['search']['maximum_strike'])
        self.assertEqual(r['search']['minimum_strike'],60)
        self.assertFalse(r['search']['minimum_exclusive'])
        scenario=m.stock_price_scenario(d,60)
        changed=m.evaluate(scenario,paths=100)
        self.assertEqual({x['strike'] for x in changed['rows'] if x['strategy']=='Roll then close'},{100})

    def test_earliest_future_expiry_is_included(self):
        d=self.fixture();q=dict(d['held'],validated=True,strike=45,bidPrice=.1,askPrice=.2)
        d['candidates']=[dict(q,expiry='2026-10-20'),dict(q,expiry='2026-10-19'),dict(q,expiry='2029-01-22')]
        r=m.evaluate(d,paths=100)
        rolls=[row for row in r['rows'] if row['strategy']=='Roll then close']
        self.assertEqual([row['expiry'] for row in rolls],['2026-10-20'])
        self.assertEqual(r['excluded'],2)
        for row in rolls:self.assertAlmostEqual(sum(row['cash_flows'].values()),row['mean'],places=7)

    def test_expire_worthless_keeps_stock_and_accounts_for_original_buyback(self):
        d=self.fixture();q=dict(d['held'],validated=True,strike=45,bidPrice=12,askPrice=13)
        d['candidates']=[q];r=m.evaluate(d,paths=100)
        row=r['top_choices'][0]['expire_worthless']
        self.assertEqual(row['stock_retained'],500)
        self.assertEqual(row['cash_flows']['stock_sale'],0)
        self.assertEqual(row['replacement_buyback_usd'],0)
        self.assertEqual(row['held_buyback_usd'],7500)
        self.assertEqual(row['cash_flows']['option_sale'],6000)
        self.assertEqual(row['mean'],-1500)
        self.assertEqual(row['option_profit_usd'],18500)
        self.assertIsNone(row['net_profit_usd'])
        self.assertEqual(sum(row['cash_flows'].values()),row['mean'])
        # Expiring worthless does not realize the stock basis or forecast a stock gain.
        other=dict(d,opening_reference=dict(stock_total_usd=999999,option_total_usd=20000))
        self.assertEqual(m.expire_worthless_outcome(other,q)['option_profit_usd'],18500)
        missing=dict(d,opening_reference={})
        self.assertIsNone(m.expire_worthless_outcome(missing,q)['option_profit_usd'])

    def test_rollover_cash_funding_debit_credit_and_same_exit_modes(self):
        d=self.fixture();q=dict(d['held'],validated=True,strike=45,bidPrice=12,askPrice=13)
        f=m.rollover_funding(d,q)
        self.assertEqual(f['held_buyback_usd'],7500)
        self.assertEqual(f['replacement_premium_usd'],6000)
        self.assertEqual(f['net_debit_usd'],1500)
        self.assertEqual(f['net_credit_usd'],0)
        credit=m.rollover_funding(d,dict(q,bidPrice=17,askPrice=18))
        self.assertEqual(credit['net_debit_usd'],0)
        self.assertEqual(credit['net_credit_usd'],1000)
        d['candidates']=[q];row=m.evaluate(d,paths=100)['top_choices'][0]
        self.assertEqual(row['roll_funding'],row['expire_worthless']['roll_funding'])
        self.assertAlmostEqual(row['roll_funding']['net_debit_usd'],-row['roll_credit'])

    def test_volatility_roundtrip(self):
        p=m.call_price(40,45,1.2,.7,.04)
        self.assertAlmostEqual(m.implied_volatility(40,45,1.2,p,.04),.7)
        self.assertEqual(m.call_price(50,40,0,.7),10)
    def test_calendar_boundaries(self):
        self.assertEqual(m.month_shift(date(2028,8,31),-6),date(2028,2,29))

if __name__=='__main__':unittest.main()
