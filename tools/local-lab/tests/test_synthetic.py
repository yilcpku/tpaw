import math
import unittest
from tpaw_lab.synthetic import components,fit,long_stress
from test_market import fixture
from dataclasses import replace


class SyntheticTests(unittest.TestCase):
    def observed(self):
        # Artificial fixture relabeled solely to exercise the source-kind gate.
        return replace(fixture(180),kind="observed")

    def test_joint_fit_reconstructs_every_input_component(self):
        source=self.observed();model=fit(source)
        for i,row in enumerate(source.rows):
            x=math.log(row.equity_gross("us","usd"))
            predicted=[model["component_means"][j]+model["betas"][j]*(x-model["x_mean"])+model["joint_residuals"][i][j] for j in range(6)]
            for actual,value in zip(components(row),predicted):
                self.assertAlmostEqual(actual,value,places=12)

    def test_synthetic_tag_anchor_identity_and_residual_blocks(self):
        source=self.observed()
        anchor=[(f"{1871+i//12:04}-{i%12+1:02}",math.exp(.004+.05*math.sin(i))) for i in range(240)]
        h,a=long_stress(anchor,source,123)
        self.assertEqual(h.kind,"synthetic_stress")
        self.assertTrue(a["no_historical_rmb_claim"])
        for row,(_,gross) in zip(h.rows,anchor):
            self.assertAlmostEqual(row.equity_gross("us","usd"),gross,places=12)
            self.assertIn("SYNTHETIC",row.source)
        for i in range(0,len(anchor),60):
            block=a["residual_source_indices"][i:i+60]
            self.assertEqual(block,list(range(block[0],block[0]+60)))
        self.assertEqual(long_stress(anchor,source,123)[0],h)

    def test_forward_or_other_synthetic_inputs_cannot_masquerade_as_observed_calibration(self):
        with self.assertRaises(ValueError):
            fit(fixture())

    def test_joint_curve_shocks_fit_and_anchor_are_retained(self):
        source=self.observed()
        rows=tuple(replace(r,government_curve_before={'12':.02,'60':.03},government_curve={'12':.021,'60':.031},
                           deposit_curve_before={'12':.02,'60':.03},deposit_curve={'12':.02,'60':.03},
                           demand_rate_before=.001,demand_rate=.001) for r in source.rows)
        source=replace(source,rows=rows)
        model=fit(source)
        self.assertEqual(len(model['betas']),9)
        anchor=[(r.month,r.equity_gross('us','usd')) for r in source.rows]
        h,a=long_stress(anchor,source,1)
        self.assertTrue(a['rate_curve_fields_encode_monthly_shocks'])
        for row in h.rows:
            self.assertAlmostEqual(row.government_curve['60']-row.government_curve_before['60'],.001)
            self.assertEqual(row.deposit_curve,row.deposit_curve_before)


if __name__=="__main__":
    unittest.main()
