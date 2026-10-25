"""Exercise local setup/reload/migration and guard against remote-access regressions."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock
from test_email_import import ROOT, module, parsed, name
from parkrun_email_tests.local_data import prepare_saved_data, get_event_name

class MigrationTests(TestCase):
    def test_existing_records_survive_and_names_are_materialised(self):
        cached = {'runs':[{'eventId':1,'date':'2026-01-01','time':'00:23:00'},
                          {'eventId':2,'date':'2026-01-02','time':'00:24:00'}],
                  'total_runs':2,'personal_best':'22:00','pb_event_id':1,'pb_location':'Old Park',
                  'records_version':1,'history_complete':True}
        data=prepare_saved_data(cached,'Runner')
        self.assertEqual(data['runs'][0]['eventName'],'Old Park')
        self.assertEqual(data['runs'][1]['eventName'],'Event 2')
        self.assertEqual(data['personal_best'],'22:00')
        self.assertEqual(data['unique_locations'],2)
        self.assertNotIn('eventName',cached['runs'][0])
        self.assertEqual(data,prepare_saved_data(data,'Runner'))

    def test_empty_setup_does_not_invent_totals(self):
        data=prepare_saved_data(None,'Runner')
        self.assertIsNone(data['total_runs'])
        self.assertIsNone(data['volunteer_count'])
        self.assertFalse(data['history_complete'])

    def test_no_network_clients_or_removed_platforms(self):
        root=ROOT/'custom_components/parkrun5k'
        banned={'aiohttp','requests','httpx','urllib','socket','selenium','playwright','subprocess'}
        for path in root.glob('*.py'):
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                imports = [a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                self.assertFalse({m.split('.')[0] for m in imports}&banned,path.name)
        for removed in ('events.py','button.py','select.py','binary_sensor.py','html_import.py'):
            self.assertFalse((root/removed).exists())

class LifecycleTests(IsolatedAsyncioTestCase):
    async def test_startup_offline_cleanup_and_reload(self):
        tree=ast.parse((ROOT/'custom_components/parkrun5k/__init__.py').read_text())
        nodes=[n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name in ('async_setup_entry','async_unload_entry')]
        class Schema:
            def Schema(self,value): return value
            def Required(self,value): return value
            def Optional(self,value): return value
        class Services:
            def __init__(self): self.actions={}
            def has_service(self,domain,service): return service in self.actions
            def async_register(self,domain,service,handler,**kwargs): self.actions[service]=handler
            def async_remove(self,domain,service): self.actions.pop(service,None)
        cached={'total_runs':17,'personal_best':'24:00','records_version':1}
        store=SimpleNamespace(async_load=AsyncMock(return_value=cached),async_save=AsyncMock())
        class Coordinator:
            def __init__(self,hass,entry):
                self.runner_name='Runner';self.barcode='1234567';self.entry_id=entry.entry_id
                self.store=store;self.import_lock=asyncio.Lock()
            def async_set_updated_data(self,data): self.data=data
        registry=SimpleNamespace(async_remove=Mock())
        entries=[SimpleNamespace(platform='parkrun5k',unique_id='parkrun5k_test_refresh',entity_id='button.old'),
                 SimpleNamespace(platform='parkrun5k',unique_id='parkrun5k_test_pb',entity_id='sensor.pb')]
        hass=SimpleNamespace(data={},services=Services(),config_entries=SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),async_unload_platforms=AsyncMock(return_value=True)))
        namespace={'HomeAssistant':object,'ConfigEntry':object,'ParkrunDataUpdateCoordinator':Coordinator,
                   'prepare_saved_data':prepare_saved_data,'DOMAIN':'parkrun5k','PLATFORMS':['sensor'],
                   'er':SimpleNamespace(async_get=lambda h:registry,async_entries_for_config_entry=lambda r,e:entries),
                   'vol':Schema(),'cv':SimpleNamespace(string=str),'CONF_ATHLETE_ID':'athlete_id','MANUAL_FIELDS':set()}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual lifecycle>','exec'),namespace)
        entry=SimpleNamespace(entry_id='test')
        self.assertTrue(await namespace['async_setup_entry'](hass,entry))
        self.assertEqual(hass.data['parkrun5k']['test'].data['personal_best'],'24:00')
        registry.async_remove.assert_called_once_with('button.old')
        self.assertEqual(set(hass.services.actions),{'import_email','update_data'})
        self.assertTrue(await namespace['async_unload_entry'](hass,entry))
        self.assertEqual(hass.services.actions,{})
        self.assertTrue(await namespace['async_setup_entry'](hass,entry))
        self.assertEqual(set(hass.services.actions),{'import_email','update_data'})

    async def test_config_flow_accepts_local_identity_and_rejects_bad_input(self):
        tree=ast.parse((ROOT/'custom_components/parkrun5k/config_flow.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='async_step_user')
        import re
        namespace={'re':re,'CONF_ATHLETE_ID':'athlete_id','CONF_RUNNER_NAME':'runner_name',
                   'vol':SimpleNamespace(Schema=lambda x:x,Required=lambda x:x)}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<actual config flow>','exec'),namespace)
        flow=SimpleNamespace(async_set_unique_id=AsyncMock(),_abort_if_unique_id_configured=Mock(),
                             async_create_entry=lambda **kw:kw,async_show_form=lambda **kw:kw)
        result=await namespace['async_step_user'](flow,{'athlete_id':' A1234567 ','runner_name':' Runner '})
        self.assertEqual(result['data'],{'athlete_id':'1234567','runner_name':'Runner'})
        flow.async_set_unique_id.assert_awaited_once_with('1234567')
        result=await namespace['async_step_user'](flow,{'athlete_id':'invalid','runner_name':'Runner'})
        self.assertEqual(result['errors'],{'athlete_id':'invalid_barcode'})
