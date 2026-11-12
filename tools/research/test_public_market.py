import unittest
from public_market import normalize


class PublicMarketTests(unittest.TestCase):
    def test_units_dates_missingness_and_dst(self):
        # Fabricated values exercise parsing; these are not empirical data.
        sp = 'observation_date,SP500\n2026-10-21,1234\n2026-10-22,1250\n'
        inf = 'observation_date,T10YIE\n2026-10-21,2.5\n2026-10-22,\n'
        bonds = 'Date,5 YR,7 YR,10 YR,20 YR,30 YR\n10/21/2026,1,2,3,4,5\n'
        rows, dates = normalize(sp, inf, bonds)
        self.assertEqual(dates, ['2026-10-21'])
        self.assertEqual(rows[0]['inflation']['value'], .025)
        self.assertEqual(rows[0]['bond_rates']['twenty_year'], .04)
        self.assertEqual(rows[0]['sp500']['value'], 1234)
        self.assertEqual(rows[0]['closing_time_ms'], 1792612800000)

    def test_no_common_observations_and_nonfinite_fail(self):
        treasury = 'Date,5 YR,7 YR,10 YR,20 YR,30 YR\n10/21/2026,1,2,3,4,5\n'
        for sp in ['observation_date,SP500\n2026-10-22,1234\n',
                   'observation_date,SP500\n2026-10-21,NaN\n']:
            with self.assertRaises(ValueError):
                normalize(sp, 'observation_date,T10YIE\n2026-10-21,2.5\n', treasury)
