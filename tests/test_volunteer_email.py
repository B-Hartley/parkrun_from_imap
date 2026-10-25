import unittest
from datetime import date
from test_email_import import module, parsed, name
from parkrun_email_tests.records import structured_update

SUBJECT = 'Thank you for volunteering at Example Park parkrun on 2026-04-11'
BODY = '''Thank you very much for your support at Example Park parkrun on 2026-04-11.
You've now volunteered at this event on 15 separate occasions, and your total number of milestone credits is 15.
<a href="https://www.parkrun.com/runner/mylinks/?Ath=1234567">Update details</a>'''

def volunteer(subject=SUBJECT, body=BODY):
    return module.parse_email(subject, body, '1234567')

class VolunteerTests(unittest.TestCase):
    def test_parse_forward_and_identity(self):
        v = volunteer('Fwd: '+SUBJECT, '> '+BODY)
        self.assertEqual(v['reportedVolunteerCredits'],15)
        self.assertEqual(v['venueVolunteerCount'],15)
        for body in (BODY.replace('1234567','123'), BODY.split('<a')[0], BODY.replace('is 15','is 14'), BODY.replace('2026-04-11','2026-04-12')):
            with self.assertRaises(ValueError):
                volunteer(body=body)

    def test_duplicate_and_independent_run_records(self):
        d=module.merge_email(None,parsed(),'Test Runner',name)
        v=volunteer()
        new=module.merge_email(d,v,'Test Runner',name)
        self.assertEqual(new['runs'],d['runs'])
        self.assertEqual(new['personal_best'],d['personal_best'])
        self.assertEqual(new['volunteer_count'],15)
        self.assertFalse(new['volunteer_history_complete'])
        self.assertEqual(new,module.merge_email(new,v,'Test Runner',name))
        self.assertEqual(len(new['visited_location_details']),1)
        self.assertTrue(new['visited_location_details'][0]['run'])
        self.assertTrue(new['visited_location_details'][0]['volunteer'])
        self.assertEqual(new['volunteer_location_details'][0]['reported_occasions'],15)

    def test_out_of_order_and_latest_correction(self):
        d=module.merge_email(None,volunteer(),'Test Runner',name)
        newer=dict(volunteer(),date='2026-05-01T00:00:00',reportedVolunteerCredits=16,eventName='Other Park',venueVolunteerCount=1)
        d=module.merge_email(d,newer,'Test Runner',name)
        d=module.merge_email(d,volunteer(),'Test Runner',name)
        self.assertEqual(d['volunteer_count'],16)
        self.assertEqual(len(d['volunteer_location_details']),2)
        d=module.merge_email(d,dict(newer,reportedVolunteerCredits=15),'Test Runner',name)
        self.assertEqual(d['volunteer_count'],15)

    def test_seed_total_does_not_regress_with_old_emails(self):
        d=module.merge_email({'volunteer_count':20},volunteer(),'Test Runner',name)
        d=module.merge_email(d,dict(volunteer(),date='2026-03-01T00:00:00',reportedVolunteerCredits=14),'Test Runner',name)
        self.assertEqual(d['volunteer_count'],20)

    def test_location_seeds_union_and_validation(self):
        d=structured_update(None,{'locations':{'run':['Example Park'],'volunteer':['Example Park parkrun','Other Park']}},'Test Runner',date(2026,10,25),name)
        d=module.merge_email(d,volunteer(),'Test Runner',name)
        self.assertEqual(len(d['visited_location_details']),2)
        self.assertEqual(len(d['volunteer_location_details']),2)
        with self.assertRaises(ValueError):
            structured_update(d,{'locations':{'run':[None]}},'Test Runner',date(2026,10,25),name)

    def test_api_roles_are_preserved_and_deduplicated_by_venue_day(self):
        api={'eventShortName':'Example Park','eventName':'examplepark','date':'2026-04-11T00:00:00','roleName':'Marshal'}
        d=module.merge_email({'volunteers':[api,dict(api,roleName='Setup')],'volunteer_roles':[{'name':'Marshal','count':1}]},volunteer(),'Test Runner',name)
        self.assertEqual(d['volunteer_roles'][0]['count'],1)
        self.assertEqual(d['volunteer_location_details'][0]['known_occasions'],1)
