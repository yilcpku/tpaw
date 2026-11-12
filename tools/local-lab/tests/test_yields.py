import unittest
from tpaw_lab.yields import apply_observed_change,curve_yield,parse_chinabond,monthly_curves


class YieldTests(unittest.TestCase):
    def test_only_government_curve_and_percent_units(self):
        def row(name):return '<tr><td>'+name+'</td><td>2024-12-31</td>'+''.join('<td>2.5</td>' for _ in range(8))+'</tr>'
        html='<div id="gjqxData"><table>'+row('中债商业银行普通债收益率曲线(AAA)')+row('中债国债收益率曲线')+'</table></div>'
        daily=parse_chinabond(html,'2024-01-01','2024-12-31')
        self.assertEqual(len(daily),1)
        self.assertEqual(daily['2024-12-31']['60'],.025)
        self.assertEqual(monthly_curves(daily)['2024-12']['month_end_lag_days'],0)

    def test_remaining_maturity_interpolation(self):
        curve={'12':.01,'60':.03,'120':.04}
        self.assertAlmostEqual(curve_yield(curve,36),.02)
        self.assertEqual(curve_yield(curve,1),.01)
        self.assertEqual(curve_yield(curve,360),.04)

    def test_interpolation_stays_in_endpoint_bounds_including_zero(self):
        for rate in (.03,.010001,.00000000000007):
            for months in range(3,361):
                value=curve_yield({'3':rate,'360':0},months)
                self.assertGreaterEqual(value,0)
                self.assertLessEqual(value,rate)
            self.assertEqual(curve_yield({'3':rate,'360':0},360),0)

    def test_sample_block_does_not_reset_current_yield_level(self):
        known={'12':.01,'60':.015}
        before={'12':.04,'60':.05}
        after={'12':.039,'60':.051}
        changed,clamps=apply_observed_change(known,before,after)
        self.assertAlmostEqual(changed['12'],.009)
        self.assertAlmostEqual(changed['60'],.016)
        self.assertEqual(clamps,0)
        self.assertNotEqual(changed,after)


if __name__=='__main__':unittest.main()
