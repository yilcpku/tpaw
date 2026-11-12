from dataclasses import asdict,replace
import unittest
from tpaw_lab.data_audit import audit_view
from tpaw_lab.market import return_statistics
from test_market import fixture


class DataAuditTests(unittest.TestCase):
    def test_synthetic_source_moments_and_dependencies_are_visible_without_mutating_snapshot(self):
        source=fixture()
        history=replace(source,kind='synthetic_stress',rows=tuple(replace(r,china_cpi_gross=1) for r in source.rows))
        record={'history':asdict(history),'audit':{'anchor_sha256':'unit-test'}}
        result=audit_view(record)
        self.assertEqual(result['data_kind'],'synthetic_stress')
        self.assertEqual(result['anchor_sha256'],'unit-test')
        self.assertEqual(result['return_statistics'],return_statistics(tuple(r.equity_gross('global','cny') for r in history.rows)))
        self.assertEqual(result['monthly_factor_correlation']['china_cpi_log']['china_cpi_log'],None)
        self.assertNotIn('data_kind',record['audit'])
