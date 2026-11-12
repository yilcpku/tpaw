import unittest
from global_rmb import real_rmb_gross,fx_month_ends,issuer_returns,portfolio_replay,un_cpi,cpi_chain,index,month

class GlobalRmbTests(unittest.TestCase):
    def test_fx_direction_inflation_and_no_double_count(self):
        self.assertAlmostEqual(real_rmb_gross(1.1,.9,1.02),.9705882352941176)
        self.assertEqual(real_rmb_gross(1,1,1),1)
        # Reinvested NAV total return is used once; cash distributions are not
        # appended to an already total-return series.
        obj={'portId':'9505','currencyCode':'USD','fundData':{'annualNAVReturns':{'returns':[{'asOfDate':'2020-01-31','monthPercent':2}]}}}
        self.assertEqual(issuer_returns(obj,'9505'),{'2020-01':1.02})
        with self.assertRaises(ValueError):issuer_returns(obj,'9679')

    def test_monthend_holidays_and_partial_month_excluded(self):
        data={'2020-01-30':6.9,'2020-01-31':7,'2020-02-28':7.1,'2020-03-04':7.2}
        result=fx_month_ends(data,'2020-02')
        self.assertEqual(result['2020-02']['date'],'2020-02-28')
        self.assertNotIn('2020-03',result)
        with self.assertRaises(ValueError):fx_month_ends({'2020-01-01':7},'2020-01')

    def test_hypothetical_rmb_cash_is_not_usd_fx_exposure(self):
        rows=[{'month':'2020-01','equity_usd_gross':1,'fx_gross':1,'cpi_gross':1}]
        self.assertAlmostEqual(portfolio_replay(rows,1,0,fx_shock=-.1)['ending_wealth_per_100_initial'],90)
        self.assertAlmostEqual(portfolio_replay(rows,.8,0,fx_shock=-.1)['ending_wealth_per_100_initial'],92)
        self.assertAlmostEqual(portfolio_replay(rows,0,0,fx_shock=-.1)['ending_wealth_per_100_initial'],100)

    def test_un_all_items_grain_excludes_food_duplicate(self):
        text='<table><tr><td>Price indices - Consumer price indices: general (all items)</td></tr><tr><td>2016JAN</td><td>100</td><td>2086/</td></tr><tr><td>2086/ Base: 2015=100.</td></tr></table>'
        text+='<table><tr><td>Price indices - Consumer price indices: food and non-alcoholic beverages</td></tr><tr><td>2016JAN</td><td>200</td><td>2086/</td></tr></table>'
        self.assertEqual(un_cpi(text)['2016-01']['value'],100)

    def test_cpi_rebase_crossing_never_becomes_deflation(self):
        un={month(i):{'value':100,'notes':'2086/'} for i in range(index('2016-01'),index('2025-05')+1)}
        un['2015-12']={'value':115.6,'notes':''};un['2025-05']['value']=101
        oecd={month(i)+'-01':100 for i in range(index('2024-01'),index('2025-04')+1)}
        out,audit=cpi_chain(oecd,un)
        self.assertEqual(out['2025-05']['value'],101)
        self.assertLess(audit['un_2015_dec_to_2016_jan_level_ratio_excluded'],.9)
