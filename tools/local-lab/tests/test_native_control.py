import csv
import io
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from tpaw_lab.native_control import control_plan,adjusted_column,summarize_control,private_output_path
from tpaw_lab.policy import TpawPolicy
from test_simulation import scenario


class NativeControlTests(unittest.TestCase):
    def test_native_output_rejects_dangling_file_symlink_before_parent_validation(self):
        with patch.object(Path,'is_symlink',return_value=True),patch('tpaw_lab.native.private_root') as root:
            with self.assertRaises(ValueError):private_output_path(Path('paths.csv'))
            root.assert_not_called()

    def test_current_inputs_and_retirement_relative_nominal_goals_are_mapped_once(self):
        s=scenario();s.update(reserve=120,reserve_funding='retirement',reserve_basis='nominal',planning_cpi=.12,
            policy_variance_annual=.035,cashflow_rows=[{'kind':'essential','amount':50,'basis':'real',
            'reference':'retirement','start':0,'duration_months':2}],monthly_savings=10)
        p=control_plan(s,'2027-02','fixed100')
        self.assertEqual(p.initial_balance,1200);self.assertEqual(p.stock_annual_log_variance,.035)
        self.assertEqual(p.income[:4],(10,10,10,0));self.assertEqual(p.essential[4],50)
        self.assertAlmostEqual(p.essential[3],50+120/1.12**.25)
        s.update(reserve_funding='initial');p=control_plan(s,'2027-02','fixed100')
        self.assertEqual(p.initial_balance,1080);self.assertEqual(p.essential[3],50)
        with self.assertRaises(ValueError):control_plan(s,'2027-03','fixed100')
        with self.assertRaises(ValueError):control_plan(s,'2027-02','rolling')

    def test_native_block_correction_is_distinct_from_source_rolling_mean(self):
        values=[math.expm1(.003+.03*math.sin(i)) for i in range(120)]
        text='\n'.join('EmpiricalStats32::new(0.08,0.04)' for _ in range(1441))
        adjusted,audit=adjusted_column(values,text,.04,.2)
        logs=[math.log1p(x) for x in adjusted]
        self.assertAlmostEqual(audit['source_rolling_statistics']['monthly_log_volatility_times_sqrt12_sample'],.2)
        source_mean=sum(math.log1p(x) for x in values)/len(values)
        expected=math.log1p(.04)/12-(math.log1p(.07999999821186066)/12-source_mean)*audit['monthly_log_vol_scale']**2
        self.assertAlmostEqual(sum(logs)/len(logs),expected)
        self.assertNotAlmostEqual(audit['source_rolling_statistics']['rolling_12m_arithmetic_mean'],.04,places=5)

    def test_full_path_summary_detects_error_and_preserves_short_period(self):
        s=scenario();s.update(current_age=99.5,candidates='2027-02',runs=1)
        p=control_plan(s,'2027-02','fixed100');policy=TpawPolicy(p)
        file=Path('unit-test-in-memory.csv');balance=p.initial_balance
        rows=[]
        for m in range(len(p.income)):
            result=policy.step(balance,m,-.05 if m==2 else .01,.001);balance=result['balance_end']
            rows.append({'month':m,'run':0,**{k:result[k] for k in ('balance_start','general','total','stock_fraction','balance_end')},
                'sample_index':m,'stock_return':-.05 if m==2 else .01,'bond_return':.001})
        def summary():
            handle=io.StringIO();writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            data=handle.getvalue()
            with patch.object(Path,'open',return_value=io.StringIO(data)),patch.object(Path,'read_bytes',return_value=data.encode()):
                return summarize_control(p,s,file)
        result=summary()
        self.assertTrue(result['paired_replay']['pass']);self.assertEqual(result['first_retirement_period_months'],4)
        self.assertEqual(result['profiles'][0]['months_summed'],7)
        self.assertAlmostEqual(result['terminal_core_balance_q5_q50_q95'][1],balance)
        rows[3]['balance_end']+=20
        self.assertFalse(summary()['paired_replay']['pass'])
