import unittest
from horizon_robustness import weighted_quantiles,expectation_identity,mortality_weights
from research import PeriodLifeTable

class HorizonRobustnessTests(unittest.TestCase):
    def test_censored_consumption_identity_and_estate_conditioning(self):
        s,m,e=expectation_identity([10,20],[100,80],[1,.75],[.25,.5],.25)
        self.assertEqual(s,25);self.assertEqual(m,25);self.assertEqual(e,65)
        self.assertAlmostEqual(e/.75,86.66666666666667)
        # Survivor consumption must contribute to the censored outcome, while
        # survivor wealth is not inserted into the estate-at-death distribution.
        self.assertEqual(weighted_quantiles([(0,.6),(100,.3),(200,.1)]),[0,0,200])

    def test_age100_survivors_are_retained_without_open_interval_deaths(self):
        table=PeriodLifeTable([{'age':a,'lx':1000000*.99**a,'qx':.01 if a<100 else 1,'ex':102-a} for a in range(101)])
        alive,death,tail=mortality_weights(table,98*12,0,24)
        self.assertAlmostEqual(sum(death)+tail,1)
        self.assertAlmostEqual(tail,.99**2)
        self.assertGreater(tail,0)
        self.assertEqual(len(death),24)
