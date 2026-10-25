import unittest
from datetime import date
from test_email_import import module, parsed, name
from parkrun_email_tests.records import structured_update, rolling_records, refresh_locations

def history():
    return structured_update(None, {'results': [
        {'date':'2026-10-24','location':'Example Park','time':'24:49','age_grade':59.91},
        {'date':'2025-11-01','location':'Other Park','time':'22:30','age_grade':65.0}
    ]}, 'Test Runner', date(2026,10,24), name)



class RollingTests(unittest.TestCase):
    def test_window_expiry_and_attributes(self):
        d=history()
        r=rolling_records(d,date(2026,10,24),name)
        self.assertEqual(r['time']['value'],'22:30')
        self.assertEqual(r['age_grade']['value'],65.0)
        self.assertEqual(r['time']['date'],'2025-11-01')
        self.assertEqual(r['time']['location'],'Other Park')
        expired=rolling_records(d,date(2026,11,1),name)
        self.assertEqual(expired['time']['value'],'24:49')
        self.assertEqual(d['personal_best'],'22:30')
        self.assertIsNone(rolling_records(d,date(2027,10,24),name)['time']['value'])

    def test_leap_year_window(self):
        d={'runs':[{'date':'2023-02-28','eventName':'A','time':'00:22:00'},
                   {'date':'2023-03-01','eventName':'B','time':'00:23:00'}]}
        r=rolling_records(d,date(2024,2,29),name)
        self.assertEqual(r['time']['location'],'B')
        self.assertEqual(r['window_start_exclusive'],'2023-02-28')

    def test_undated_email_pb_is_not_rolling_evidence(self):
        d=module.merge_email(None,parsed(),'Test Runner',name)
        r=rolling_records(d,date(2026,10,24),name)
        self.assertEqual(d['personal_best'],'22:30')
        self.assertEqual(r['time']['value'],'24:49')

    def test_structured_seed_and_correction(self):
        d=structured_update(None,{'results':[{'date':'2026-01-31','location':'Example Park','time':'23:25','age_grade':62.99}]},'Test Runner',date(2026,10,24),name)
        self.assertEqual(rolling_records(d,date(2026,10,24),name)['time']['value'],'23:25')
        corrected=structured_update(d,{'results':[{'date':'2026-01-31','location':'Example Park','time':'24:00'}],
            'personal_best':{'time':'24:00','date':'2026-01-31','location':'Example Park'}},'Test Runner',date(2026,10,24),name)
        self.assertEqual(rolling_records(corrected,date(2026,10,24),name)['time']['value'],'24:00')
        self.assertEqual(corrected['personal_best'],'24:00')
        self.assertEqual(corrected['best_age_grade'],62.99)

    def test_remove_bad_rolling_evidence(self):
        d=structured_update(None,{'results':[{'date':'2026-01-31','location':'Example Park','time':'23:25'}]},'Test Runner',date(2026,10,24),name)
        d=structured_update(d,{'remove_results':[{'date':'2026-01-31','location':'Example Park'}]},'Test Runner',date(2026,10,24),name)
        self.assertIsNone(rolling_records(d,date(2026,10,24),name)['time']['value'])

    def test_email_supersedes_same_manual_result(self):
        d=structured_update(None,{'results':[{'date':'2026-10-24','location':'Example Park','time':'23:25'}]},'Test Runner',date(2026,10,24),name)
        d=module.merge_email(d,parsed(),'Test Runner',name)
        self.assertEqual(d['manual_results'],[])
        self.assertEqual(rolling_records(d,date(2026,10,24),name)['time']['value'],'24:49')

    def test_bad_structured_update_is_atomic(self):
        d={'total_runs':175}
        for updates in ({'oops':1},{'results':[{'date':'2099-01-01','location':'A','time':'23:00'}]},
                        {'results':[{'date':'2026-01-01','location':'A','age_grade':float('inf')}]},
                        {'personal_best':{'time':'23:00','extra':'x'}}):
            with self.assertRaises(ValueError):
                structured_update(d,updates,'Test Runner',date(2026,10,24),name)
            self.assertEqual(d,{'total_runs':175})
