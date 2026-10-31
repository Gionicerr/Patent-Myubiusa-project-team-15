"""Unit-only replies; never certify Qwen or a runnable application."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.parking_generation import ParkingGenerator,OPERATIONS,profile,sql_schema,declarations
from app.parking_templates import runtime
from app.provider import ProviderError

ROOT=Path(__file__).resolve().parents[1]
class Fake:
    config={'model':'unit-only','api_key':'unit-private-value'}
    def __init__(self,replies=None,fail=None):self.calls=[];self.messages=[];self.replies=replies or [{'body':'throw new InvalidOperationException("unit fixture only");'}];self.fail=fail
    def complete(self,messages,stage,attempt):
        self.messages.append(messages);self.calls.append({'stage':stage,'attempt':attempt,'status':'error' if self.fail else 'ok','input_tokens':5,'output_tokens':7,'seconds':.01})
        if self.fail:raise ProviderError('unit failure',self.fail)
        return json.dumps(self.replies[min(len(self.calls)-1,len(self.replies)-1)])

class ParkingGenerationTests(unittest.TestCase):
    def setUp(self):
        self.design=json.loads((ROOT/'examples/parking-contracts-reviewed.json').read_text())
        self.analysis=json.loads((ROOT/'examples/parking-analysis-v2.json').read_text())
        self.openapi=json.loads((ROOT/'docs/stage2/openapi.json').read_text())
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
    def generator(self,client=None):
        return ParkingGenerator(Path(self.temp.name)/'run',client or Fake(),self.design,self.analysis,self.openapi,ROOT/'spb.json')
    def test_full_contract_then_exact_profile(self):
        p=profile(self.design,self.analysis,self.openapi)
        self.assertEqual([o['operation_id'] for o in p['operations']],list(OPERATIONS))
        original=copy.deepcopy(self.design)
        self.design['screens'][0]['requirement_ids']=['FR-999']
        with self.assertRaisesRegex(ValueError,'Full v2'):profile(self.design,self.analysis,self.openapi)
        self.design=original
    def test_original_openapi_mismatch_rejected(self):
        self.openapi['info']['title']='wrong'
        with self.assertRaisesRegex(ValueError,'OpenAPI differs'):self.generator()
    def test_sql_fks_and_unique_active_and_payment(self):
        sql=sql_schema(profile(self.design,self.analysis,self.openapi))
        for text in ['REFERENCES "Vehicle"','REFERENCES "ParkingObject"','REFERENCES "Route"',
                     'CREATE UNIQUE INDEX "ux_one_active_session"','WHERE "status" = \'active\'',
                     'CHECK ("paymentConfirmed" = FALSE)','CREATE TABLE "RequestReplay"']:
            self.assertIn(text,sql)
        self.assertNotIn('CREATE EXTENSION',sql)
    def test_source_sample_retains_tariffs_and_is_small(self):
        g=self.generator();source=json.loads((ROOT/'spb.json').read_text())['data']['zones']
        self.assertEqual(len(g.sample['objects']),2);self.assertTrue(g.sample['sample_only'])
        for row,index in zip(g.sample['objects'],g.sample['selected_indices']):
            for key in ('geometry','price','tariff','minTime','timeStep'):self.assertEqual(row[key],source[index][key])
    def test_two_model_bodies_and_no_fallback(self):
        g=self.generator();r=g.run()
        self.assertEqual(len(g.client.calls),2);self.assertFalse(r['application_verified'])
        self.assertEqual(set(r['model_handlers']),{'createSession','confirmSession'})
        for messages in g.client.messages:
            self.assertNotIn('screens',messages[1]['content']);self.assertNotIn('user_flows',messages[1]['content'])
    def test_only_failed_operation_repaired(self):
        client=Fake([{'body':'throw new Exception();'},{'wrong':True},{'body':'throw new Exception();'}])
        r=self.generator(client).run()
        self.assertEqual([c['stage'] for c in client.calls],['Parking/createSession','Parking/confirmSession','Parking/confirmSession'])
        self.assertTrue(r['repair_used']);self.assertEqual(r['metrics']['model_calls'],3)
    def test_length_or_rate_limit_stops_without_retry(self):
        for reason in ('truncated','rate_limit','network'):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as d:
                client=Fake(fail=reason)
                g=ParkingGenerator(Path(d)/'run',client,self.design,self.analysis,self.openapi,ROOT/'spb.json')
                r=g.run();self.assertEqual(len(client.calls),1);self.assertFalse(r['application_verified']);self.assertFalse(r['model_handlers'])
    def test_technical_atomicity_and_returning(self):
        p=profile(self.design,self.analysis,self.openapi);s=runtime(p,self.design)
        for text in ('pg_advisory_xact_lock','RequestReplay','CommitAsync','RETURNING','fingerprint','expectedRevision'):
            self.assertIn(text,s)
        self.assertEqual(s.count('app.MapMethods('),6)
        self.assertIn(r'SET \"vehicleId\"=x.\"vehicleId\"',s)
        self.assertIn('JsonRequired',declarations(p,self.design))
    def saved_run(self):
        g=self.generator();g.run();g.prepare_runtime();g.save()
        (g.root/'commands.json').write_text('[]')
        return g
    def test_verify_existing_never_calls_model_and_preserves_history(self):
        old=self.saved_run();client=Fake()
        g=ParkingGenerator(old.root,client,self.design,self.analysis,self.openapi,ROOT/'spb.json',verify=True,verify_existing=True)
        with patch.object(g.runner,'run',return_value=(127,'technical environment unavailable')):r=g.run()
        self.assertEqual(len(client.calls),2);self.assertFalse(client.messages)
        self.assertFalse(r['application_verified']);self.assertTrue(list(g.root.glob('report-before-verification-*.json')))
    def test_verify_existing_rejects_changed_handler(self):
        old=self.saved_run();(old.project/'src/createSession.cs').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed accepted handler'):
            ParkingGenerator(old.root,Fake(),self.design,self.analysis,self.openapi,ROOT/'spb.json',verify=True,verify_existing=True)
    def test_pagination_limits_are_read_from_selected_contract(self):
        p=profile(self.design,self.analysis,self.openapi)
        for op in p['operations']:
            for parameter in op['parameters']:
                if parameter['name']=='pageSize':parameter['schema']['maximum']=33
        self.assertIn('size>33',runtime(p,self.design))
