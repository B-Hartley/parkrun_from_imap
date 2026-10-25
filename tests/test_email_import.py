"""Offline tests of the actual parser and merge functions."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
import types
package = types.ModuleType('parkrun_email_tests')
package.__path__ = [str(ROOT / 'custom_components/parkrun5k')]
sys.modules['parkrun_email_tests'] = package
spec = importlib.util.spec_from_file_location('parkrun_email_tests.email_import', ROOT / 'custom_components/parkrun5k/email_import.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SUBJECT = 'Your result from Example Park parkrun, Event 207 on 2026-10-24'
BODY = '''Hello Test Runner,
Example Park parkrun results for event #207. Your time was 00:24:49.
Congratulations on completing your 175th parkrun and your 75th at Example Park parkrun today.
You finished in 65th place out of a field of 241 parkrunners.
You were the 48th male and came 6th in your age category VM50-54.
Your PB at Example Park parkrun remains 00:22:30. Your best time this year remains 00:23:25.
You achieved an age-graded score of 59.91%.
https://www.parkrun.com/runner/mylinks/?Ath=1234567
'''

def name(event_id):
    return {2970: 'Example Park'}.get(event_id, 'Unknown event')


def parsed(subject=SUBJECT, body=BODY):
    result = module.parse_email(subject, body, 'A1234567')
    result['eventId'] = 2970
    return result


class EmailImportTests(unittest.TestCase):
    def test_all_sample_fields(self):
        r = parsed()
        self.assertEqual((r['time'], r['reportedTotalRuns'], r['venueRuns']), ('00:24:49', 175, 75))
        self.assertEqual((r['position'], r['genderPosition'], r['ageCategoryPosition']), (65, 48, 6))
        self.assertEqual((r['ageGrade'], r['ageCategory'], r['totalAthletes']), (59.91, 'VM50-54', 241))
        self.assertEqual((r['venuePB'], r['yearBest']), ('00:22:30', '00:23:25'))

    def test_html_and_whitespace(self):
        body = '<p>' + BODY.replace('\n', '</p><p>').replace('00:24:49', '<b>00:24:49</b>') + '</p>'
        self.assertEqual(parsed(body=body)['time'], '00:24:49')

    def test_forwarded_subject_and_quoted_body(self):
        forwarded = 'Begin forwarded message:\nFrom: parkrun\n\n' + '\n'.join('> ' + line for line in BODY.splitlines())
        result = parsed(subject='Fwd: ' + SUBJECT, body=forwarded)
        self.assertEqual(result['reportedTotalRuns'], 175)
        self.assertEqual(result['time'], '00:24:49')

    def test_wrong_or_missing_barcode_rejected(self):
        for body in (BODY.replace('1234567', '123'), BODY.split('https:')[0]):
            with self.assertRaises(ValueError):
                parsed(body=body)

    def test_invalid_data_rejected(self):
        for body in (BODY.replace('00:24:49', '00:74:49'), BODY.replace('65th place', '999th place'), 'not a result'):
            with self.assertRaises(ValueError):
                parsed(body=body)
        with self.assertRaises(ValueError):
            parsed(subject=SUBJECT.replace('2026-10-24', '2026-99-24'))

    def test_no_body_or_links_stored(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        encoded = json.dumps(data)
        self.assertNotIn('mylinks', encoded)
        self.assertNotIn('Hello Test Runner', encoded)

    def test_incomplete_history_does_not_invent_all_time_statistics(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        self.assertEqual(data['total_runs'], 175)
        self.assertFalse(data['history_complete'])
        for key in ('unique_locations', 'volunteer_count'):
            self.assertIsNone(data[key])

    def test_duplicate_and_correction(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        again = module.merge_email(data, parsed(), 'Test Runner', name)
        self.assertEqual(data, again)
        corrected = module.merge_email(again, parsed(body=BODY.replace('00:24:49', '00:24:39')), 'Test Runner', name)
        self.assertEqual(len(corrected['runs']), 1)
        self.assertEqual(corrected['runs'][0]['time'], '00:24:39')

    def test_older_email_never_rolls_back_latest_or_total(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        older = parsed(subject=SUBJECT.replace('207', '195').replace('2026-10-24', '2026-07-25'), body=BODY.replace('175th', '163rd'))
        merged = module.merge_email(data, older, 'Test Runner', name)
        self.assertEqual(merged['runs'][0]['date'], '2026-10-24T00:00:00')
        self.assertEqual(merged['total_runs'], 175)
        self.assertEqual(len(data['runs']), 1)  # Input is never mutated.

    def test_newest_dated_report_and_correction_are_authoritative(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        corrected = parsed(body=BODY.replace('175th', '174th'))
        data = module.merge_email(data, corrected, 'Test Runner', name)
        self.assertEqual(data['total_runs'], 174)
        older = parsed(subject=SUBJECT.replace('207', '195').replace('2026-10-24', '2026-07-25'), body=BODY.replace('175th', '999th'))
        data = module.merge_email(data, older, 'Test Runner', name)
        self.assertEqual(data['total_runs'], 174)

    def test_api_run_is_enriched_not_duplicated(self):
        run = parsed()
        api_run = {k: v for k, v in run.items() if k not in ('eventName', 'source', 'reportedTotalRuns')}
        api_run['date'] += '+00:00'
        api_run['totalVolunteers'] = 30
        data = module.merge_email({'runs': [api_run], 'total_runs': 175}, run, 'Test Runner', name)
        self.assertEqual(len(data['runs']), 1)
        self.assertEqual(data['runs'][0]['totalVolunteers'], 30)

    def test_available_email_evidence_improves_records(self):
        run = parsed(body=BODY.replace('175th', '1st'))
        data = module.merge_email(None, run, 'Test Runner', name)
        self.assertTrue(data['history_complete'])
        self.assertEqual(data['personal_best'], '22:30')
        self.assertEqual(data['best_age_grade'], 59.91)
        self.assertEqual(data['unique_locations'], 1)

    def test_save_and_restore_json_preserves_results(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        restored = json.loads(json.dumps(data))
        self.assertEqual(module.merge_email(restored, parsed(), 'Test Runner', name), data)

    def test_unknown_venues_remain_distinct(self):
        first = parsed(body=BODY.replace('175th', '1st'))
        second = parsed(subject=SUBJECT.replace('Example Park', 'Other Place').replace('2026-10-24', '2026-10-31'), body=BODY.replace('175th', '2nd'))
        second['eventId'] = None
        data = module.merge_email(module.merge_email(None, first, 'Test Runner', name), second, 'Test Runner', name)
        self.assertEqual(data['unique_locations'], 2)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_saves_and_publishes_and_rejects_wrong_runner(self):
        import ast
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock
        tree = ast.parse((ROOT / 'custom_components/parkrun5k/__init__.py').read_text())
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'handle_import_email')
        class Coordinator:
            pass
        target = Coordinator()
        target.barcode = '1234567'
        target.runner_name = 'Test Runner'
        target.data = None
        target.import_lock = asyncio.Lock()
        target.store = SimpleNamespace(async_save=AsyncMock())
        target.async_set_updated_data = Mock()
        hass = SimpleNamespace(data={'parkrun5k': {'entry': target, 'auto_refresh_unsub': lambda: None}})
        namespace = {'hass': hass, 'DOMAIN': 'parkrun5k', 'CONF_ATHLETE_ID': 'athlete_id',
                     'ParkrunDataUpdateCoordinator': Coordinator, 'ServiceValidationError': ValueError,
                     'parse_email': module.parse_email, 'merge_email': module.merge_email,
                     'get_event_name': name, 'get_event_id': lambda value: 2970}
        exec(compile(ast.Module(body=[handler], type_ignores=[]), '<actual service handler>', 'exec'), namespace)
        call = SimpleNamespace(data={'athlete_id': 'A1234567', 'subject': SUBJECT, 'body': BODY})
        await namespace['handle_import_email'](call)
        saved = target.store.async_save.call_args.args[0]
        self.assertEqual(saved['total_runs'], 175)
        target.async_set_updated_data.assert_called_once_with(saved)
        call.data['body'] = BODY.replace('1234567', '111')
        with self.assertRaises(ValueError):
            await namespace['handle_import_email'](call)
        self.assertEqual(target.store.async_save.call_count, 1)

    async def test_failed_save_does_not_publish_unsaved_data(self):
        # Parser/merger tests cover rejected inputs; the handler orders durable
        # saving before publication, so a storage exception must stop publication.
        import ast
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock
        import asyncio
        tree = ast.parse((ROOT / 'custom_components/parkrun5k/__init__.py').read_text())
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'handle_import_email')
        class Coordinator:
            pass
        c = Coordinator()
        c.barcode, c.runner_name, c.data = '1234567', 'Test Runner', None
        c.import_lock = asyncio.Lock()
        c.store = SimpleNamespace(async_save=AsyncMock(side_effect=OSError('disk full')))
        c.async_set_updated_data = Mock()
        namespace = {'hass': SimpleNamespace(data={'parkrun5k': {'entry': c}}), 'DOMAIN': 'parkrun5k',
                     'CONF_ATHLETE_ID': 'athlete_id', 'ParkrunDataUpdateCoordinator': Coordinator,
                     'ServiceValidationError': ValueError, 'parse_email': module.parse_email,
                     'merge_email': module.merge_email, 'get_event_name': name, 'get_event_id': lambda value: 2970}
        exec(compile(ast.Module(body=[handler], type_ignores=[]), '<actual service handler>', 'exec'), namespace)
        with self.assertRaises(OSError):
            await namespace['handle_import_email'](SimpleNamespace(data={'athlete_id': '1234567', 'subject': SUBJECT, 'body': BODY}))
        c.async_set_updated_data.assert_not_called()


class RecordsTests(unittest.TestCase):
    def setUp(self):
        from parkrun_email_tests import records
        self.records = records

    def test_initial_records_and_year(self):
        data = module.merge_email(None, parsed(), 'Test Runner', name)
        self.assertEqual(data['personal_best'], '22:30')
        self.assertEqual(data['pb_location'], 'Example Park')
        self.assertIsNone(data['pb_date'])
        self.assertEqual(data['best_age_grade'], 59.91)
        self.assertEqual(data['year_bests'], {'2026': '23:25'})

    def test_better_saved_records_survive(self):
        data = module.merge_email({'personal_best': '21:10', 'pb_date': '2020-01-01',
                                  'best_age_grade': 70.0, 'unique_locations': 25}, parsed(), 'Test Runner', name)
        self.assertEqual(data['personal_best'], '21:10')
        self.assertEqual(data['pb_date'], '2020-01-01')
        self.assertEqual(data['best_age_grade'], 70.0)
        self.assertEqual(data['unique_locations'], 25)

    def test_faster_year_best_does_not_invent_venue_or_date(self):
        run = parsed()
        run['yearBest'] = '00:21:59'
        data = module.merge_email(None, run, 'Test Runner', name)
        self.assertEqual(data['personal_best'], '21:59')
        self.assertIsNone(data['pb_date'])
        self.assertIsNone(data['pb_location'])

    def test_years_are_independent(self):
        run = parsed()
        data = module.merge_email(None, run, 'Test Runner', name)
        run = dict(run, date='2027-01-02T00:00:00', yearBest='00:25:00', time='00:25:00')
        data = module.merge_email(data, run, 'Test Runner', name)
        self.assertEqual(data['year_bests'], {'2026': '23:25', '2027': '25:00'})
        self.assertEqual(data['personal_best'], '22:30')

    def test_manual_preserves_omitted_values_and_can_correct_record(self):
        old = module.merge_email(None, parsed(), 'Test Runner', name)
        new = self.records.manual_update(old, {'personal_best': '23:00', 'volunteer_count': 11}, 'Test Runner')
        self.assertEqual(new['total_runs'], 175)
        self.assertEqual(new['personal_best'], '23:00')
        self.assertIsNone(new['pb_location'])
        self.assertEqual(new['volunteer_count'], 11)
        self.assertEqual(old['personal_best'], '22:30')

    def test_manual_full_example(self):
        data = self.records.manual_update(None, {'personal_best': '00:22:30', 'pb_location': 'Example Park',
            'pb_date': '2025-06-01', 'best_age_grade': 65.2, 'total_runs': 175,
            'year_best': '23:25', 'year_best_year': 2026}, 'Test Runner')
        self.assertEqual(data['personal_best'], '22:30')
        self.assertEqual(data['year_bests']['2026'], '23:25')
        self.assertEqual(data['latest_milestone'], 100)
        self.assertEqual(data['result_source'], 'manual')
        self.assertEqual(data['pb_date'], '2025-06-01T00:00:00')

    def test_invalid_updates_are_atomic(self):
        original = {'total_runs': 175}
        for changes in ({}, {'runs': []}, {'total_runs': -1}, {'total_runs': True},
                        {'best_age_grade': float('nan')}, {'personal_best': '22:99'},
                        {'pb_date': '2026-02-30'}, {'year_best': '23:25'},
                        {'year_best_year': 2026}, {'total_runs': 5, 'volunteer_count': -1}):
            with self.assertRaises(ValueError):
                self.records.manual_update(original, changes, 'Test Runner')
            self.assertEqual(original, {'total_runs': 175})

    def test_sensor_uses_current_year_not_last_run_year(self):
        import ast
        from types import SimpleNamespace
        tree = ast.parse((ROOT / 'custom_components/parkrun5k/sensor.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ParkrunYearBestSensor')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'native_value')
        method.decorator_list = []
        namespace = {'dt_util': SimpleNamespace(now=lambda: SimpleNamespace(year=2027))}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<sensor>', 'exec'), namespace)
        sensor = SimpleNamespace(coordinator=SimpleNamespace(data={'year_bests': {'2026': '23:25'}}))
        self.assertIsNone(namespace['native_value'](sensor))

if __name__ == '__main__':
    unittest.main()
