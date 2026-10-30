"""Treasury parsing, maturity matching, availability, and explicit model wiring."""
from datetime import date
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import interest_rates as rates

XML=b'''<feed xmlns:m="metadata" xmlns:d="data"><entry><m:properties>
<d:NEW_DATE>2026-10-29T00:00:00</d:NEW_DATE><d:BC_1YEAR>4.0</d:BC_1YEAR><d:BC_2YEAR>6.0</d:BC_2YEAR>
</m:properties></entry><entry><m:properties><d:NEW_DATE>2026-10-30T00:00:00</d:NEW_DATE>
<d:BC_1YEAR>9</d:BC_1YEAR><d:BC_2YEAR>10</d:BC_2YEAR></m:properties></entry></feed>'''


class InterestRates(unittest.TestCase):
    def curve(self):
        return dict(rates.parse_curve(XML,date(2026,10,29)),feed_url='https://home.treasury.gov/example',retrieved_at='2026-10-29T12:00:00+00:00',retrieved_epoch=1)

    def test_parse_latest_nonfuture_curve_and_interpolate(self):
        curve=self.curve()
        self.assertEqual(curve['observed_on'],'2026-10-29')
        with patch.object(rates,'latest_curve',return_value=curve):
            selected=rates.resolve({'mode':'treasury'},'2028-04-29','2026-10-29')
            years=(date(2028,4,29)-date(2026,10,29)).days/365
            percent=4+2*(years-1)
            self.assertAlmostEqual(selected['annual_percent'],percent)
            self.assertAlmostEqual(selected['rate'],2*math.log1p(percent/200))
            self.assertEqual((selected['lower_tenor_years'],selected['upper_tenor_years']),(1,2))
            short=rates.resolve(None,'2026-11-29','2026-10-29')
            self.assertEqual(short['annual_percent'],4)
            long=rates.resolve(None,'2035-10-29','2026-10-29')
            self.assertEqual(long['annual_percent'],6)

    def test_manual_override_has_no_network_dependency(self):
        with patch.object(rates,'latest_curve') as network:
            chosen=rates.resolve({'mode':'manual','annual_percent':5})
            self.assertAlmostEqual(chosen['rate'],2*math.log1p(.025))
            network.assert_not_called()
        for invalid in [True,float('nan'),float('inf'),-6,26,'5',None]:
            with self.assertRaises(ValueError): rates.resolve({'mode':'manual','annual_percent':invalid})
        with self.assertRaises(ValueError): rates.resolve({'mode':'unknown'})

    def test_cache_refresh_and_stale_source_never_becomes_fixed_four_percent(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(rates,'CACHE',Path(folder)/'curve.json'), patch.object(rates,'today',return_value=date(2026,10,29)), patch.object(rates,'_last_attempt',0):
            with patch.object(rates,'urlopen',return_value=io.BytesIO(XML)) as fetch:
                first=rates.latest_curve()
                self.assertEqual(fetch.call_count,1)
                self.assertEqual(rates.latest_curve(),first)
                self.assertEqual(fetch.call_count,1)
            recent=self.curve();rates.CACHE.write_text(json.dumps(recent))
            with patch.object(rates,'_last_attempt',0),patch.object(rates,'urlopen',side_effect=OSError('offline')):
                self.assertIn('warning',rates.latest_curve())
            recent['observed_on']='2026-10-01';rates.CACHE.write_text(json.dumps(recent))
            with patch.object(rates,'_last_attempt',0),patch.object(rates,'urlopen',side_effect=OSError('offline')):
                with self.assertRaises(rates.RateUnavailable): rates.latest_curve()
        for payload in [b'not XML',b'<feed/>',XML.replace(b'4.0',b'NaN')]:
            with self.assertRaises(rates.RateUnavailable): rates.parse_curve(payload,date(2026,10,29))

    def test_scenario_passes_same_rate_to_repricing_and_evaluation(self):
        import exit_optimizer as optimizer
        data=dict(as_of='2026-10-29',held=dict(expiry='2028-01-21'),stock=dict(bidPrice=40,askPrice=42))
        snapshot=dict(inputs=data)
        selection={'mode':'manual','annual_percent':5}
        request=dict(account='RRSP',symbol='TEST',stock_price=45,interest_rate=selection)
        with patch.object(optimizer,'select_holding'),patch.object(optimizer,'load_capture',return_value=snapshot),patch.object(optimizer.model,'stock_price_scenario',side_effect=lambda data, price, **kw:data) as reprice,patch.object(optimizer.model,'evaluate',return_value={'rate':rates.annual_rate(5)}) as evaluate:
            result=optimizer.scenario(request)
            self.assertAlmostEqual(reprice.call_args.kwargs['rate'],rates.annual_rate(5))
            self.assertAlmostEqual(evaluate.call_args.kwargs['rate'],rates.annual_rate(5))
            self.assertFalse(evaluate.call_args.kwargs['close_at_mid'])
            self.assertEqual(result['inputs']['interest_rate']['selection'],selection)
        self.assertNotIn('interest_rate',data)


if __name__=='__main__': unittest.main()
