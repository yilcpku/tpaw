import unittest
from horizon_schedule import build_schedule

class HorizonScheduleTests(unittest.TestCase):
    def rows(self):
        return [{'age':a,'lx':1000000*.99**a,'qx':.01 if a<100 else 1,'ex':102-a} for a in range(101)]
    def test_birthday_updates_and_open_tail_censor(self):
        rows=self.rows()
        # Change expected death age as one survives, using internally valid lx/qx.
        rows[51]['ex']=52
        result=build_schedule(50*12+6,40*12,rows)
        self.assertEqual(result['evaluation_months'],50*12-6)
        self.assertEqual(result['rolling'][0],result['rolling'][5])
        self.assertEqual(result['rolling'][6]-result['rolling'][5],12)
        self.assertEqual(result['fixed'][-1],result['evaluation_months'])
        with self.assertRaises(ValueError):
            build_schedule(600,480,rows,evaluation_age=101)
