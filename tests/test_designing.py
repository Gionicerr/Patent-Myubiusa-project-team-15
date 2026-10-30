"""Offline regressions of sequential design, not application acceptance tests."""
import argparse
import copy
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from app.designing import Designer, compact_context, tasks
from app.provider import ProviderError
from app.specifications import validate_contract
from tests.test_specifications import typed_example, part_reply


class Model:
    def __init__(self, design, fail=None, invalid=None):
        self.config={'model':'test-qwen','api_key':'test-secret-not-persisted'}
        self.design=design;self.calls=[];self.seen=[];self.fail=fail;self.invalid=invalid

    def complete(self, messages, stage, attempt):
        key=stage.removeprefix('Design/');self.seen.append((key,attempt))
        self.calls.append({'stage':stage,'attempt':attempt,'status':'ok','seconds':.01,
                           'input_tokens':3,'output_tokens':7})
        if key==self.fail:
            self.calls[-1].update(status='error',error_code='rate_limit',input_tokens=None,output_tokens=None)
            raise ProviderError('API returned HTTP 429','rate_limit')
        data=part_reply(self.design,stage)
        if key=='architecture':
            payload=json.loads(messages[1]['content'].split('\n',1)[1])
            data['context_map']['global_question_ids']=[q['id'] for q in payload['analysis'].get('questions',[])]
        if key==self.invalid and attempt==1:
            if key.startswith('api:'):data['api'][0]['responses']=[]
            else:data={}
        return json.dumps(data)


class DesignPartsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.analysis={'title':'Request tracker','functional_requirements':[{'id':'FR-001'}]}
        self.design=typed_example(self.analysis)

    def designer(self, model=None, **kwargs):
        return Designer(self.directory,model or Model(self.design),'Read owned requests',self.analysis,{},**kwargs)

    def test_assembles_v2_from_separate_answers_without_prepared_fallback(self):
        model=Model(self.design)
        with patch('app.demo.fixture',side_effect=AssertionError('No prepared result')):
            designer=self.designer(model);result=designer.run()
        self.assertEqual(result,self.design)
        self.assertEqual(validate_contract(result,self.analysis),[])
        self.assertEqual(len(model.calls),len(tasks(designer.state['parts'],self.analysis)))
        self.assertGreater(len(model.calls),6)
        saved=designer.path.read_text(encoding='utf-8')
        self.assertNotIn('test-secret-not-persisted',saved)
        self.assertEqual(designer.state['deferred_references'],[])
        self.assertTrue(all(p['origin']=='qwen_generation' for p in designer.state['parts'].values()))

    def test_repairs_only_invalid_part(self):
        model=Model(self.design,invalid='api:readRequest')
        self.assertEqual(self.designer(model).run(),self.design)
        self.assertEqual([v for v in model.seen if v[0]=='api:readRequest'],[('api:readRequest',1),('api:readRequest',2)])
        self.assertEqual(sum(key=='architecture' for key,_ in model.seen),1)
        self.assertEqual(sum(c.get('validation_status')=='error' for c in model.calls),1)

    def test_failure_persists_parts_and_resume_preserves_all_calls(self):
        model=Model(self.design,fail='api:readRequest');designer=self.designer(model)
        with self.assertRaises(ProviderError):designer.run()
        saved=json.loads(designer.path.read_text(encoding='utf-8'))
        completed=set(saved['parts']);previous=copy.deepcopy(saved['calls'])
        self.assertIn('data_model:Request',completed)
        self.assertIn('api:readRequest',saved['deferred_references'])
        model2=Model(self.design)
        resumed=self.designer(model2,resume=True)
        self.assertEqual(resumed.run(),self.design)
        self.assertFalse(completed & {key for key,_ in model2.seen})
        self.assertEqual(model2.seen[0],('api:readRequest',2))
        self.assertEqual(model2.calls[:len(previous)],previous)
        self.assertEqual(sum(c['status']=='error' for c in model2.calls),1)
        self.assertIsNone(model2.calls[len(previous)-1]['input_tokens'])

    def test_incompatible_and_tampered_checkpoints_rejected_without_calls(self):
        designer=self.designer();designer.run();before=designer.path.read_bytes()
        for change in ('requirements','analysis','answers','context','model','format'):
            model=Model(self.design);analysis=copy.deepcopy(self.analysis)
            if change=='analysis':analysis['title']='Other'
            if change=='model':model.config['model']='other-model'
            schema=__import__('app.designing',fromlist=['contract_schema']).contract_schema()
            if change=='format':schema['description']='changed format'
            with self.subTest(change=change),patch('app.designing.contract_schema',return_value=schema):
                with self.assertRaisesRegex(ValueError,'Incompatible'):
                    Designer(self.directory,model,'Other' if change=='requirements' else 'Read owned requests',
                        analysis,{'Q-001':'new'} if change=='answers' else {},
                        {'source':'other'} if change=='context' else {},resume=True)
                self.assertEqual(model.calls,[]);self.assertEqual(designer.path.read_bytes(),before)
        state=json.loads(before);state['parts']['data_model:Request']['data']['data_model'][0]['name']='Changed'
        designer.path.write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Invalid saved'):self.designer(resume=True)

    def test_two_attempt_limit_survives_restart_and_new_run_cannot_overwrite(self):
        class Invalid(Model):
            def complete(self,*args):super().complete(*args);return '{}'
        model=Invalid(self.design);designer=self.designer(model)
        with self.assertRaisesRegex(ValueError,'two attempts'):designer.run()
        self.assertEqual(len(model.calls),2)
        with self.assertRaisesRegex(ValueError,'already exists'):self.designer()
        model2=Model(self.design);resumed=self.designer(model2,resume=True)
        with self.assertRaisesRegex(ValueError,'two attempts'):resumed.run()
        self.assertEqual(model2.seen,[])

    def test_final_cross_reference_error_repairs_owning_part_only(self):
        class BadPrimaryKey(Model):
            def complete(self,messages,stage,attempt):
                data=json.loads(super().complete(messages,stage,attempt))
                if stage=='Design/data_model:Request' and attempt==1:
                    data['data_model'][0]['primary_key']=['missing']
                return json.dumps(data)
        model=BadPrimaryKey(self.design)
        self.assertEqual(self.designer(model).run(),self.design)
        self.assertEqual(sum(key=='data_model:Request' for key,_ in model.seen),2)
        self.assertEqual(sum(key=='api:readRequest' for key,_ in model.seen),1)

    def test_summary_excludes_raw_arrays_and_is_bounded_after_projection(self):
        context={'sources':[{'file':'input.json','objects':100,'zones':[{}]*100,
                             'examples':[{'id':1},{'id':2}]}]}
        summary=compact_context(context)
        self.assertNotIn('zones',str(summary));self.assertEqual(summary['sources'][0]['example'],[{'id':1}])
        with self.assertRaises(ValueError):compact_context({'data':{'zones':[]}})
        with self.assertRaises(ValueError):compact_context({'sources':[{'tariff':'x'*33000}]})

    def test_cli_and_engine_use_shared_designer_and_resume_history(self):
        from app.demo import fixture, REQUIREMENTS
        from specify_run import run
        analysis,_=fixture();design=typed_example(analysis)
        (self.directory/'requirements.md').write_text(REQUIREMENTS,encoding='utf-8')
        (self.directory/'analysis.json').write_text(json.dumps(analysis),encoding='utf-8')
        args=argparse.Namespace(requirements=self.directory/'requirements.md',analysis=self.directory/'analysis.json',
            answers=None,context=None,output=self.directory/'output',design=None,parent_run_id=None,
            max_tokens=None,timeout=None,resume=False)
        model=Model(design,fail='api:readRequest')
        with patch('specify_run.Client',return_value=model),patch('specify_run.load_env'),patch('specify_run.normalize_config',return_value={}):
            self.assertEqual(run(args),1)
        metrics=json.loads((args.output/'generation-metrics.json').read_text())
        model2=Model(design);args.resume=True
        with patch('specify_run.Client',return_value=model2),patch('specify_run.load_env'),patch('specify_run.normalize_config',return_value={}):
            self.assertEqual(run(args),0)
        after=json.loads((args.output/'generation-metrics.json').read_text())
        self.assertGreater(after['model_calls'],metrics['model_calls'])
        self.assertEqual(after['calls'][:len(metrics['calls'])],metrics['calls'])
        self.assertEqual(after['resumptions'],1)
        old=(args.output/'generation-metrics.json').read_bytes()
        (self.directory/'requirements.md').write_text(REQUIREMENTS+'\nNew requirement',encoding='utf-8')
        with patch('specify_run.Client',return_value=Model(design)),patch('specify_run.load_env'),patch('specify_run.normalize_config',return_value={}):
            with self.assertRaisesRegex(ValueError,'Incompatible'):run(args)
        self.assertEqual((args.output/'generation-metrics.json').read_bytes(),old)

    def test_web_resume_loads_disk_checkpoint_into_fresh_engine(self):
        from app.demo import fixture, REQUIREMENTS
        from app.pipeline import Engine
        from server import make_server
        from tests.test_pipeline import wait
        analysis,_=fixture();analysis['questions']=[];design=typed_example(analysis)
        class WebModel(Model):
            def complete(self,messages,stage,attempt):
                if stage=='Анализ':
                    self.calls.append({'stage':stage,'attempt':attempt,'status':'ok','seconds':.01,
                                       'input_tokens':3,'output_tokens':7})
                    return json.dumps(analysis)
                return super().complete(messages,stage,attempt)
        first=WebModel(design,fail='api:readRequest')
        engine=Engine(self.directory,lambda _:first)
        run_id=engine.create(REQUIREMENTS,{},context={'source':'summary'})
        self.assertEqual(wait(engine,run_id)['status'],'failed')
        before=copy.deepcopy(first.calls)
        second=WebModel(design)
        server=make_server('127.0.0.1',0,self.directory,lambda _:second)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(base+'/api/config') as response:token=json.load(response)['csrf_token']
            request=urllib.request.Request(base+f'/api/runs/{run_id}/resume-design',
                data=json.dumps({'config':{'base_url':'http://127.0.0.1/v1','model':'test-qwen'}}).encode(),
                headers={'Content-Type':'application/json','X-Pipeline-Token':token})
            with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['id'],run_id)
            job=wait(server.engine,run_id)
            self.assertEqual(job['status'],'complete',job['error'])
            self.assertEqual(job['report']['metrics']['calls'][:len(before)],before)
            self.assertEqual(second.seen[0],('api:readRequest',2))
            self.assertFalse(any(k=='architecture' for k,_ in second.seen))
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_interrupted_request_intent_preserves_unknown_usage(self):
        designer=self.designer()
        designer.state['attempts']['architecture']=1
        intent={'stage':'Design/architecture','attempt':1,'status':'interrupted_or_pending',
                'input_tokens':None,'output_tokens':None,'seconds':None}
        designer.state['calls'].append(intent);designer.save()
        model=Model(self.design);resumed=self.designer(model,resume=True)
        self.assertEqual(resumed.run(),self.design)
        self.assertEqual(model.calls[0],intent)
        self.assertEqual(model.seen[0],('architecture',2))


if __name__=='__main__':unittest.main()
