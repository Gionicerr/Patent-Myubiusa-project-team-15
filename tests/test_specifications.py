"""Domain-independent tests of document contracts, never application acceptance tests."""
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from app.contracts import validate_design, validate_analysis
from app.artifacts import render_documents, write_files
from check_specification import check_directory
from app.demo import fixture, REQUIREMENTS
from app.pipeline import Engine
from app.specifications import build_openapi, validate_contract, validate_openapi_document
from app.input_report import inspect_sources


def typed_example(analysis=None):
    ids=[x['id'] for x in (analysis or {'functional_requirements':[{'id':'FR-001'}]})['functional_requirements']]
    uid={'type':'string','format':'uuid'}
    event_schema={'type':'object','properties':{'id':uid,'time':{'type':'string','format':'date-time'},'key':{'type':'string'}},'required':['id','time','key']}
    return {'schema_version':'2.0','boundaries':'Generic request tracker specification',
        'user_flows':[{'role':'reader','steps':['Read request'],'requirement_ids':ids}],
        'components':[{'name':'API','responsibility':'Read records','technology':'.NET10'}],
        'data_model':[{'name':'Request','description':'Generic record','fields':[{'name':'id','schema':uid,'required':True,'description':'Identifier'},{'name':'state','schema':{'type':'string','enum':['new','done']},'required':True,'description':'State'}],'primary_key':['id'],'relations':[],'indexes':[{'name':'state_index','fields':['state'],'unique':False,'method':'btree'}]}],
        'schemas':{'Problem':{'type':'object','properties':{'code':{'type':'string'}},'required':['code']}},
        'roles':[{'id':'reader','name':'Reader','permissions':[{'operation_id':'readRequest','scope':'own'}]}],
        'api':[{'operation_id':'readRequest','method':'GET','path':'/api/requests/{requestId}','summary':'Read a record','roles':['reader'],'requirement_ids':ids,'parameters':[{'name':'requestId','in':'path','required':True,'description':'ID','schema':uid}],'request_body':None,'responses':[{'status':'200','description':'Record','schema':{'$ref':'#/components/schemas/Request'}},{'status':'401','description':'No identity','schema':{'$ref':'#/components/schemas/Problem'}},{'status':'403','description':'No permission','schema':{'$ref':'#/components/schemas/Problem'}}]}],
        'screens':[{'id':'request','route':'/requests/:id','name':'Request','roles':['reader'],'requirement_ids':ids,'display_fields':[{'entity':'Request','fields':['id','state']}],'actions':[{'id':'read','label':'Read','operation_id':'readRequest'}],'states':{k:k for k in ['loading','error','empty','forbidden','ready']}}],
        'events':[{'name':'ReadEvent','requirement_ids':ids,'schema':event_schema,'id_field':'id','time_field':'time','idempotency_key':['key'],'delivery':'at_least_once','deduplication':'Unique key prevents duplicates'}],
        'test_scenarios':[{'id':f'TC-{i:03}','requirement_ids':[id],'operation_ids':['readRequest'],'given':'Owned record','when':'Read request','then':'Record returned','type':'positive'} for i,id in enumerate(ids,1)],
        'assumptions':[],'open_questions':[],'validation_and_errors':['Validate ownership'],'security_recommendations':['Enforce role'],'limitations':['Document checks only']}


def part_reply(design, stage):
    from app.designing import INVENTORY, NOTES
    key=stage.removeprefix('Design/')
    if key=='architecture':
        return {**{k:copy.deepcopy(design[k]) for k in ('boundaries','components','user_flows')},
            'inventory':{section:list(design[section]) if field is None else [x[field] for x in design[section]]
                         for section,field in INVENTORY.items()}}
    if key=='notes':return {k:copy.deepcopy(design[k]) for k in NOTES}
    section,name=key.split(':',1)
    if section=='schemas':return {section:{name:copy.deepcopy(design[section][name])}}
    if section=='test_scenarios':return {section:[copy.deepcopy(t) for t in design[section] if name in t['requirement_ids']]}
    return {section:[copy.deepcopy(x) for x in design[section] if x[INVENTORY[section]]==name]}


class TypedContractTests(unittest.TestCase):
    def setUp(self):
        self.analysis={'title':'Request tracker','functional_requirements':[{'id':'FR-001'}]}
        self.design=typed_example(self.analysis)

    def test_nonparking_contract_and_openapi_pass(self):
        self.assertEqual(validate_design(self.design,self.analysis),[])
        api=build_openapi(self.design,self.analysis['title'])
        self.assertEqual(validate_openapi_document(self.design,self.analysis,api),[])
        self.assertNotIn('Parking',json.dumps(api))

    def test_required_fields_types_and_versions(self):
        for mutate in [lambda d:d.pop('screens'),lambda d:d.update(schema_version='9'),lambda d:d['data_model'][0]['fields'][0].update(required='yes'),lambda d:d['data_model'][0]['fields'][0].update(schema={'type':'imaginary'}),lambda d:d['screens'][0]['states'].pop('loading')]:
            d=copy.deepcopy(self.design);mutate(d)
            with self.subTest(design=d):self.assertTrue(validate_design(d,self.analysis))

    def test_closed_object_cannot_require_a_forbidden_property(self):
        self.design['schemas']['Broken']={'type':'object','properties':{'id':{'type':'string'}},
            'required':['ghost'],'additionalProperties':False}
        issues=validate_contract(self.design,self.analysis)
        self.assertTrue(any('Broken.required' in x and 'ghost' in x and 'forbidden' in x for x in issues),issues)

    def test_nested_value_schemas_must_be_typed(self):
        cases=[({'type':'object','properties':{'payload':{}},'required':['payload']},'properties.payload'),
               ({'type':'array','items':{'type':'object','properties':{'payload':{}}}},'items.properties.payload'),
               ({'allOf':[{'type':'object','properties':{'payload':{}}}]},'allOf[0].properties.payload'),
               ({'type':'object','properties':{'payload':{'type':'array'}}},'properties.payload')]
        for schema,location in cases:
            with self.subTest(schema=schema):
                self.design['schemas']['Broken']=schema
                issues=validate_contract(self.design,self.analysis)
                self.assertTrue(any('Broken.'+location in x for x in issues),issues)

    def test_compositions_conditions_and_schema_helpers_remain_supported(self):
        schemas=[
            {'oneOf':[{'$ref':'#/components/schemas/Problem'},{'type':'null'}]},
            {'anyOf':[{'type':'string'},{'type':'null'}]},
            {'allOf':[{'type':'object','properties':{'id':{'type':'string'}}},
                      {'properties':{'id':{'minLength':1}},'required':['id']}]},
            {'type':'object','properties':{'state':{'enum':['new','done']},'payload':{'type':['string','null']}},
             'if':{'properties':{'state':{'const':'done'}},'required':['state']},
             'then':{'required':['payload'],'properties':{'payload':{'minLength':1}}},
             'else':{'properties':{'payload':{}}}},
            {'type':'array','prefixItems':[{'const':'header'},{'type':'integer'}],'items':False},
            {'type':'object','patternProperties':{'^x-':{'type':'string'}},'required':['x-id'],'additionalProperties':False},
            {'type':'object','properties':{'payload':{'type':'array','items':{'enum':[1,2,None]}}},
             'examples':[{'$ref':'ordinary example data'}]},
        ]
        for schema in schemas:
            with self.subTest(schema=schema):
                self.design['schemas']['Valid']=schema
                self.assertEqual(validate_contract(self.design,self.analysis),[])

    def test_entity_links_indexes_and_primary_keys(self):
        mutations=[lambda d:d['data_model'][0]['relations'].append({'field':'id','target_entity':'Missing','target_field':'id','on_delete':'RESTRICT'}),lambda d:d['data_model'][0]['indexes'][0].update(fields=['missing']),lambda d:d['data_model'][0]['primary_key'].append('missing'),lambda d:d['data_model'][0]['fields'].append(copy.deepcopy(d['data_model'][0]['fields'][0])),lambda d:d['data_model'][0]['indexes'][0].update(predicate={'field':'missing','operator':'eq','value':'new'})]
        for mutate in mutations:
            d=copy.deepcopy(self.design);mutate(d);self.assertTrue(validate_contract(d,self.analysis))

    def test_api_and_role_integrity(self):
        mutations=[lambda d:d['api'].append(copy.deepcopy(d['api'][0])),lambda d:d['api'][0]['parameters'].clear(),lambda d:d['api'][0]['parameters'][0].update(required=False),lambda d:d['api'][0]['responses'][0].update(schema={'$ref':'https://unsafe.invalid/schema'}),lambda d:d['api'][0]['responses'].pop(),lambda d:d['roles'][0]['permissions'][0].update(operation_id='unknown'),lambda d:d['api'][0].update(roles=['unknown'])]
        for mutate in mutations:
            d=copy.deepcopy(self.design);mutate(d);self.assertTrue(validate_contract(d,self.analysis))

    def test_screens_events_and_fr_references(self):
        mutations=[lambda d:d['screens'][0]['actions'][0].update(operation_id='unknown'),lambda d:d['screens'][0]['display_fields'][0].update(fields=['unknown']),lambda d:d['events'][0].update(idempotency_key=['unknown']),lambda d:d['events'][0]['schema'].update(required=['time','key']),lambda d:d['test_scenarios'][0].update(requirement_ids=['FR-999']),lambda d:d['test_scenarios'].clear(),lambda d:d['test_scenarios'][0].update(operation_ids=['unknown'])]
        for mutate in mutations:
            d=copy.deepcopy(self.design);mutate(d);self.assertTrue(validate_contract(d,self.analysis))

    def test_saved_sidecars_and_openapi_checked(self):
        a,_=fixture();d=typed_example(a)
        with tempfile.TemporaryDirectory() as temp:
            docs=render_documents(REQUIREMENTS,a,d,{}, {'metrics':{'model_calls':0}})
            write_files(temp,docs)
            self.assertEqual(check_directory(temp)['status'],'passed')
            (Path(temp)/'screens.json').write_text('[]')
            self.assertEqual(check_directory(temp)['status'],'failed')

    def test_entity_constraints_and_event_schema_must_agree(self):
        d=copy.deepcopy(self.design)
        e=d['data_model'][0]
        e['constraints']={'allOf':[{'if':{'properties':{'state':{'const':'done'}}},'then':{'required':['id']}}]}
        self.assertEqual(validate_contract(d,self.analysis),[])
        self.assertIn('allOf',build_openapi(d)['components']['schemas']['Request'])
        d['events'][0]['name']='Request'
        self.assertTrue(any('differs from API/entity' in x for x in validate_contract(d,self.analysis)))

    def test_openapi_tampering_detected(self):
        api=build_openapi(self.design,self.analysis['title']);api['paths'].clear()
        self.assertTrue(validate_openapi_document(self.design,self.analysis,api))

    def test_legacy_reading_and_v2_exports(self):
        a,d=fixture();report={'metrics':{'model_calls':0}}
        legacy=render_documents(REQUIREMENTS,a,d,{},report)
        self.assertEqual(json.loads(legacy['design.json']),d)
        self.assertNotIn('openapi.json',legacy)
        typed=typed_example(a);self.assertEqual(validate_contract(typed,a),[])
        docs=render_documents(REQUIREMENTS,a,typed,{},report)
        self.assertEqual(json.loads(docs['design.json']),typed)
        self.assertEqual(validate_openapi_document(typed,a,json.loads(docs['openapi.json'])),[])
        self.assertTrue({'data-model.json','screens.json','events.json','permissions.json'} <= docs.keys())

    def test_default_engine_generates_typed_design_and_persists_gate(self):
        class Model:
            def __init__(self,config):self.calls=[]
            def complete(self,messages,stage,attempt):
                self.calls.append({'stage':stage,'attempt':attempt,'status':'ok','seconds':0.01,'input_tokens':1,'output_tokens':2})
                a,_=fixture();return json.dumps(a if stage=='Анализ' else part_reply(typed_example(a),stage))
        with tempfile.TemporaryDirectory() as temp:
            e=Engine(temp,Model);id=e.create(REQUIREMENTS,{})
            for _ in range(200):
                j=e.snapshot(id)
                if j['status']!='running':break
                time.sleep(.01)
            self.assertEqual(j['status'],'awaiting_answers')
            pending=json.loads((Path(temp)/id/'pending-report.json').read_text())
            self.assertEqual(pending['metrics']['model_calls'],1)
            e.continue_run(id,{'Q-001':'In foreground'})
            for _ in range(200):
                j=e.snapshot(id)
                if j['status']!='running':break
                time.sleep(.01)
            self.assertEqual(j['status'],'complete',j['error'])
            self.assertIn('openapi.json',j['files'])
            from app.designing import tasks
            checkpoint=json.loads((Path(temp)/id/'design-checkpoint.json').read_text(encoding='utf-8'))
            self.assertEqual(j['report']['metrics']['model_calls'],1+len(tasks(checkpoint['parts'],j['analysis'])))

    def test_default_engine_rejects_new_untyped_generation(self):
        class Untyped:
            def __init__(self,config):self.calls=[]
            def complete(self,messages,stage,attempt):
                self.calls.append({'stage':stage,'attempt':attempt,'status':'ok','seconds':.01,'input_tokens':1,'output_tokens':1})
                a,d=fixture();a['questions']=[]
                return json.dumps(a if stage=='Анализ' else d)
        with tempfile.TemporaryDirectory() as temp:
            e=Engine(temp,Untyped);id=e.create(REQUIREMENTS,{})
            for _ in range(200):
                j=e.snapshot(id)
                if j['status']!='running':break
                time.sleep(.01)
            self.assertEqual(j['status'],'failed')
            self.assertEqual(j['report']['metrics']['model_calls'],3)


class InputReportTests(unittest.TestCase):
    def row(self,geometry):
        return {'externalZoneId':'source-1','displayName':'Object','geometry':geometry,'price':10020,'priceDescription':'Raw tariff','minTime':60,'timeStep':15,'tariff':{'hasHolidays':True,'periods':[{'from':480,'to':1200,'duration':None,'price':10020,'type':'car'}]},'entityState':'Active','initDate':'2026-10-01T00:00:00Z','lastSyncedAt':'2026-10-02T00:00:00Z'}

    def inspect(self,rows):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.json';p.write_text(json.dumps({'data':{'city':'test','zones':rows}}))
            return inspect_sources([p],{'test':[29,59,32,61]})['sources'][0]

    def test_all_geometries_nested_tariff_and_order(self):
        geometries=['LINESTRING (30 60,30.1 60.1)','MULTILINESTRING ((30 60,30.1 60.1))','POLYGON ((30 60,31 60,31 61,30 60))','GEOMETRYCOLLECTION (LINESTRING (30 60,30.1 60.1), POINT (30 60))']
        rows=[{**self.row(g),'externalZoneId':str(i)} for i,g in enumerate(geometries)]
        report=self.inspect(rows)
        self.assertEqual(sum(report['geometry_types'].values()),4)
        self.assertEqual(report['geometry_collection_members'],{'LINESTRING':1,'POINT':1})
        self.assertEqual(report['tariff']['nested_types']['tariff.periods[].duration'],{'null':4})
        self.assertTrue(report['regional_order_check']['xy_fits']);self.assertFalse(report['regional_order_check']['yx_fits'])
        self.assertEqual(report['examples'][0]['price'],10020)

    def test_invalid_geometry_duplicate_identifier_and_missing_field(self):
        rows=[self.row('LINESTRING (30 60,30 60)'),self.row('broken')]
        rows[0].pop('price');rows[1]['tariff']['periods'][0].pop('duration')
        report=self.inspect(rows)
        self.assertEqual(report['duplicate_identifiers'],{'source-1':2})
        self.assertTrue({'invalid_geometry','unparseable_wkt','missing_field','missing_tariff_period_field'} <= report['problem_counts'].keys())

    def test_no_coordinates_not_claimed_as_valid_order(self):
        report=self.inspect([self.row('broken')])
        self.assertFalse(report['coordinates_fit_lon_lat_ranges']);self.assertIsNone(report['xy_bounds'])


if __name__=='__main__':unittest.main()
