import copy
import unittest
from import_archive import build
from tpaw_lab.baseline import reference_view


def fixture():
    def goal(ident,amount,retirement):
        return {'id':ident,'label':ident,'nominal':True,'amountAndTiming':{'type':'recurring','baseAmount':amount,
            'delta':None,'everyXMonths':1,'monthRange':{'type':'startAndDuration','start':
                {'type':'namedAge','age':'retirement','person':'person1'} if retirement else
                {'type':'calendarMonth','calendarMonth':{'year':2027,'month':2}},'duration':{'inMonths':1 if retirement else 24}}}}
    risk={'riskTolerance':{'at20':12,'deltaAtMaxAge':-2},'timePreference':0,'additionalAnnualSpendingTilt':0}
    case={'retirement_month':'2027-02','run':{'seed':1,'currency':'TEST'},'plan':{'v':30,'people':{'withPartner':False,
        'person1':{'ages':{'currentAgeInfo':{'monthOfBirth':{'year':1986,'month':11}}}}},'risk':{'tpaw':risk},
        'adjustmentsToSpending':{'extraSpending':{'essential':{'reserve':goal('reserve',100,True),'rent':goal('rent',10,False)},'discretionary':{}}}}}
    cash={k:{'totalX100':([0,1000,2000]+[0]*9 if k=='wealthFutureSavings' else [0]*12)} for k in ('wealthFutureSavings','wealthIncomeDuringRetirement')}
    p={'amountTimed':cash,'risk':{'tpaw':{'rraUnclampedIncludingPosInfinityByMfn':[4]*12,'legacyRraIncludingPosInfinity':4}},
       'returnsStatsForPlanning':{k:{'empiricalAnnualNonLogExpectedReturn':.04 if k=='stocks' else .01,'empiricalAnnualLogVariance':.04 if k=='stocks' else 0} for k in ('stocks','bonds')},
       'adjustmentsToSpending':{'tpawAndSpaw':{'legacy':{'target':0}}},'annualInflation':.02}
    decoded={'request_sha256':'request','result_sha256':'result','result':{'planParamsProcessed':p,'numRuns':5,'arrays':{
       'byPercentileByMfnSimulatedPercentileMajorBalanceStartX100':[100000]*36,
       'byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneralX100':[100]*36}}}
    config={'name':'TEST ONLY','cny_per_source_unit':.8,'evaluation_month':'2026-11','reserve_goal_id':'reserve','annual_budget_cny':100,
       'baseline_id':'test-native','budget_phases':[{'kind':'budget','start':'2027-02','amount':200,'duration_months':24}],
       'retirement_relative_goal_ids':['rent'],'reserve_draws':[{'kind':'reserve_draw','reference':'retirement','start':0,'amount':20}]}
    return config,case,decoded


class ArchiveImportTests(unittest.TestCase):
    def test_original_goals_preserved_and_extension_partitions_once(self):
        config,case,decoded=fixture();before=copy.deepcopy(case)
        baseline,original,extended=build(config,case,decoded)
        self.assertEqual(case,before)
        self.assertEqual(extended['reserve'],80)
        self.assertEqual(extended['reserve_funding'],'retirement')
        self.assertEqual(extended['reserve_basis'],'nominal')
        self.assertTrue(any(r.get('source_id')=='reserve' for r in original['cashflow_rows']))
        self.assertFalse(any(r.get('source_id')=='reserve' for r in extended['cashflow_rows']))
        rent=next(r for r in extended['cashflow_rows'] if r.get('source_id')=='rent')
        self.assertEqual((rent['reference'],rent['start']),('retirement',0))
        income=[r['amount'] for r in extended['cashflow_rows'] if r['kind']=='net_savings']
        self.assertEqual(income,[0,8,16])
        self.assertTrue(reference_view(extended,baseline)['import_inputs_unchanged'])
        changed={**extended,'reserve_cash_rate':.02}
        self.assertIn('reserve_cash_rate',reference_view(changed,baseline)['additional_input_changes'])

    def test_unsupported_household_does_not_silently_import(self):
        config,case,decoded=fixture();case['plan']['people']['withPartner']=True
        with self.assertRaises(ValueError):build(config,case,decoded)
