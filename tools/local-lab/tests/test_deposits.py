import unittest
from tpaw_lab.deposits import parse_posted,at_month_end,index_links


class DepositSourceTests(unittest.TestCase):
    def test_only_lump_sum_product_and_missing_demand_not_invented(self):
        text='2006-08-19<table><tr><td>1.整存整取</td><td></td></tr>'
        for label in ('三个月','半年','一年','二年','三年','五年'):
            text+=f'<tr><td>{label}</td><td>2.50</td></tr>'
        text+='<tr><td>2.零存整取</td><td></td></tr><tr><td>一年</td><td>0.50</td></tr></table>'
        quote=parse_posted(text,'2006-08-19')
        self.assertEqual(quote['curve']['12'],.025)
        self.assertIsNone(quote['demand'])
        previous={'date':'2004-10-29','curve':quote['curve'],'demand':.0072}
        quotes={'2004-10-29':previous,'2006-08-19':quote,
                '2007-01-01':{**quote,'date':'2007-01-01','demand':.01}}
        result=at_month_end(quotes,'2006-09')
        self.assertEqual(result['demand'],.0072)
        self.assertEqual(result['demand_quote_date'],'2004-10-29')
        with self.assertRaises(ValueError): at_month_end(quotes,'2003-12')

    def test_effective_date_comes_from_title_not_url_upload_date(self):
        links=index_links('<a href="./200809/t20080918_2356.html">人民币存款利率表2004-10-29</a>')
        self.assertIn('2004-10-29',links)
        self.assertTrue(links['2004-10-29'].endswith('200809/t20080918_2356.html'))
