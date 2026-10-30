"""Generator unit tests only; prepared replies never certify real Qwen generation."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.provider import ProviderError
from app.server_generation import ServerGenerator, Runner, binding, safe_path, validate_files, write_project
from app.server_templates import scaffold

ROOT=Path(__file__).resolve().parents[1]


def inputs():
    return (json.loads((ROOT/'examples/notes-server-analysis.json').read_text()),
            json.loads((ROOT/'examples/notes-server-design-v2.json').read_text()))


def reply():
    return {'files':[{'path':'src/Domain.cs','content':'// Unit fixture, not a working server\npublic static class DomainEndpoints {}'},
                     {'path':'db/001_init.sql','content':'CREATE TABLE "Note" ("id" uuid PRIMARY KEY, "ownerId" text NOT NULL, "title" text NOT NULL, "text" text NOT NULL, "createdAt" timestamptz NOT NULL);'}]}


class Fake:
    def __init__(self,replies=None,error=False):
        self.config={'model':'unit-only','api_key':'private-unit-secret'};self.calls=[];self.prompts=[]
        self.replies=replies;self.error=error
    def complete(self,messages,stage,attempt):
        self.prompts.append(messages)
        self.calls.append({'stage':stage,'attempt':attempt,'status':'error' if self.error else 'ok',
                           'input_tokens':None if self.error else 5,'output_tokens':None if self.error else 8,'seconds':.01})
        if self.error:
            self.calls[-1].update(http_status=429,error_code='rate_limit')
            raise ProviderError('HTTP 429','rate_limit')
        if self.replies is not None:return json.dumps(self.replies[min(len(self.calls)-1,len(self.replies)-1)])
        path=stage.removeprefix('Server/')
        return json.dumps({'files':[item for item in reply()['files'] if item['path']==path]})


class ServerGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.a,self.d=inputs()

    def generator(self,client=None,**kwargs):
        return ServerGenerator(self.root/'run',client or Fake(),self.d,self.a,**kwargs)

    def test_bindings_are_from_contract_not_note_names(self):
        d=json.loads(json.dumps(self.d).replace('Note','Ticket').replace('ownerId','subjectId')
                     .replace('title','heading').replace('text','details').replace('createdAt','openedAt')
                     .replace('/api/notes','/api/tickets'))
        for assumption in d['assumptions']:assumption['text']=assumption.pop('details')
        result=binding(d,self.a)
        self.assertEqual(result['entity'],'Ticket');self.assertEqual(result['owner'],'subjectId')
        self.assertEqual(result['created'],'openedAt');self.assertEqual(set(result['client_fields']),{'heading','details'})

    def test_invalid_or_unsupported_contract_never_creates_output(self):
        self.d['api'][0]['request_body']['schema']['properties']['ownerId']=self.d['data_model'][0]['fields'][1]['schema']
        with self.assertRaises(ValueError):self.generator()
        self.assertFalse((self.root/'run').exists())

    def test_paths_conflicts_and_symlinks_rejected_before_writes(self):
        for name in ('/absolute','../escape',r'..\escape',r'C:\escape',r'\\host\file','src/../file','src//file','src/file:stream','./file'):
            with self.subTest(name=name),self.assertRaises(ValueError):safe_path(self.root,name)
        with self.assertRaises(ValueError):write_project(self.root,[('a.txt','first'),('A.TXT','second')])
        self.assertFalse((self.root/'a.txt').exists())
        write_project(self.root,[('a.txt','keep')])
        with self.assertRaises(ValueError):write_project(self.root,[('a.txt','overwrite')])
        self.assertEqual((self.root/'a.txt').read_text(),'keep')
        try:(self.root/'link').symlink_to(self.root/'a.txt')
        except OSError:return
        with self.assertRaises(ValueError):safe_path(self.root,'link')

    def test_model_cannot_change_build_files_or_supply_commands(self):
        for data in ({'files':[{'path':'src/Api.csproj','content':'malicious'}]},
                     {**reply(),'commands':['rm -rf /']},
                     {'files':reply()['files']+[copy.deepcopy(reply()['files'][0])]}):
            with self.subTest(data=data),self.assertRaises(ValueError):validate_files(data,self.root)
        data=reply();data['files'][1]['content']='COPY x FROM PROGRAM \'bad\';'
        with self.assertRaises(ValueError):validate_files(data,self.root)

    def test_template_has_fixed_stack_and_demo_verifier_without_pipeline_key(self):
        files=scaffold()
        self.assertIn('net10.0',files['src/Api.csproj']);self.assertIn('14.0',files['src/Api.csproj'])
        self.assertIn('postgres:17.9',files['compose.yaml'])
        self.assertIn('pg_isready -h 127.0.0.1 -U app -d app',files['compose.yaml'])
        self.assertIn('FixedTimeEquals',files['src/Program.cs'])
        self.assertIn('UnmappedMemberHandling',files['src/Program.cs'])
        self.assertNotIn('QWEN',files['compose.yaml']);self.assertNotIn('src/Domain.cs',files)

    def test_generation_fixture_is_only_unit_test_no_build_claim(self):
        g=self.generator()
        with patch.object(g.runner,'tools',return_value={'dotnet_sdk_10':False,'docker_daemon':False,'docker_compose':False}):report=g.run()
        self.assertEqual(report['status'],'generated');self.assertFalse(report['application_verified'])
        self.assertEqual(report['domain_origin'],'qwen_generation')
        self.assertEqual(report['metrics']['model_calls'],2)
        self.assertTrue((g.project/'src/Domain.cs').exists())
        self.assertNotIn('private-unit-secret',(g.root/'generation-report.json').read_text())

    def test_429_stops_without_retry_or_prepared_domain_fallback(self):
        g=self.generator(Fake(error=True),verify=True)
        with patch.object(g.runner,'tools',return_value={}):report=g.run()
        self.assertEqual(report['status'],'provider_failed');self.assertEqual(report['metrics']['model_calls'],1)
        self.assertIsNone(report['metrics']['input_tokens']);self.assertFalse((g.project/'src/Domain.cs').exists())
        self.assertEqual(report['domain_origin'],'not_generated')

    def test_truncation_has_one_concise_repair_and_preserves_usage(self):
        class Truncated(Fake):
            def complete(self,messages,stage,attempt):
                if attempt==1 and stage.endswith('.sql'):
                    self.calls.append({'stage':stage,'attempt':1,'status':'error','input_tokens':7,'output_tokens':16000,
                                       'seconds':1,'finish_reason':'length','error_code':'truncated'})
                    raise ProviderError('Output truncated','truncated')
                return super().complete(messages,stage,attempt)
        model=Truncated();g=self.generator(model)
        with patch.object(g.runner,'tools',return_value={}):report=g.run()
        self.assertEqual(report['status'],'generated');self.assertEqual(report['metrics']['model_calls'],3)
        self.assertEqual(report['metrics']['output_tokens'],16016)
        self.assertEqual(report['metrics']['repair_attempts'],1)
        self.assertEqual(model.calls[1]['attempt'],2)
        self.assertEqual(model.calls[-1]['stage'],'Server/src/Domain.cs')

    def test_legacy_repair_flag_rejected_without_overwriting_results(self):
        g=self.generator();marker=g.root/'generation-report.json';marker.write_text('old report')
        with self.assertRaisesRegex(ValueError,'new output'):
            ServerGenerator(g.root,Fake(),self.d,self.a,repair_truncated=True)
        self.assertEqual(marker.read_text(),'old report')

    def test_one_targeted_build_repair_with_fixed_command(self):
        model=Fake();g=self.generator(model,build=True)
        with patch.object(g.runner,'tools',return_value={'dotnet_sdk_10':True,'docker_daemon':False,'docker_compose':False}),\
             patch.object(g.runner,'run',side_effect=[(1,'Domain.cs: CS1002'),(0,'Build succeeded')]) as command:
            report=g.run()
        self.assertEqual(report['status'],'built');self.assertEqual(len(model.calls),3)
        self.assertEqual(report['metrics']['repair_attempts'],1)
        self.assertIn('CS1002',model.prompts[2][1]['content'])
        self.assertEqual(sum(call['stage'].endswith('.sql') for call in model.calls),1)
        self.assertEqual(command.call_args_list[0].args[0],['dotnet','build','src/Api.csproj','-c','Release'])
        self.assertTrue((g.root/'attempt-1/generated-files.json').exists())

    def test_two_invalid_replies_exhaust_budget(self):
        g=self.generator(Fake([{'files':[]}]))
        with patch.object(g.runner,'tools',return_value={}):report=g.run()
        self.assertEqual(report['status'],'failed');self.assertEqual(report['metrics']['model_calls'],2)
        self.assertFalse((g.project/'src/Domain.cs').exists())

    def test_no_sdk_is_environment_limitation_not_success_or_model_retry(self):
        g=self.generator(build=True)
        with patch.object(g.runner,'tools',return_value={'dotnet_sdk_10':False,'docker_daemon':False,'docker_compose':False}):report=g.run()
        self.assertEqual(report['status'],'generated_build_unavailable')
        self.assertEqual(report['metrics']['model_calls'],2);self.assertFalse(report['application_verified'])

    def test_domain_failure_keeps_accepted_sql_and_never_regenerates_it(self):
        class DomainFailure(Fake):
            def complete(self,messages,stage,attempt):
                if stage.endswith('.cs'):
                    self.calls.append({'stage':stage,'attempt':attempt,'status':'error','input_tokens':1,'output_tokens':16000,'seconds':1})
                    raise ProviderError('Truncated Domain','truncated')
                return super().complete(messages,stage,attempt)
        model=DomainFailure();g=self.generator(model)
        with patch.object(g.runner,'tools',return_value={}):report=g.run()
        self.assertEqual(len(model.calls),3)
        self.assertEqual(sum(c['stage'].endswith('.sql') for c in model.calls),1)
        self.assertTrue((g.project/'db/001_init.sql').exists())
        self.assertFalse((g.project/'src/Domain.cs').exists())
        self.assertEqual(report['blocking_file'],'src/Domain.cs')
        self.assertEqual(report['status'],'provider_failed')

    def test_resume_skips_saved_sql_and_retains_call_history(self):
        model=Fake();g=self.generator(model)
        g.started=__import__('time').monotonic()
        g.generate_file('db/001_init.sql')
        (g.root/'commands.json').write_text('[]')
        original=(g.project/'db/001_init.sql').read_bytes();calls=copy.deepcopy(model.calls)
        second=Fake();resumed=ServerGenerator(g.root,second,self.d,self.a,resume=True)
        with patch.object(resumed.runner,'tools',return_value={}):report=resumed.run()
        self.assertEqual(report['metrics']['model_calls'],2)
        self.assertEqual(second.calls[:1],calls)
        self.assertEqual(second.calls[1]['stage'],'Server/src/Domain.cs')
        self.assertEqual((g.project/'db/001_init.sql').read_bytes(),original)

    def test_per_file_prompts_exclude_ui_and_pass_accepted_sql_to_csharp(self):
        model=Fake();g=self.generator(model)
        with patch.object(g.runner,'tools',return_value={}):g.run()
        self.assertEqual(len(model.calls),2)
        for messages in model.prompts:
            prompt=messages[1]['content']
            self.assertNotIn('future-web',prompt)
            self.assertNotIn('test_scenarios',prompt)
            self.assertNotIn('var builder =',prompt)
        self.assertIn('accepted_sql',model.prompts[1][1]['content'])
        self.assertIn('CREATE TABLE',model.prompts[1][1]['content'])
        self.assertEqual(set(g.report['files']),{'db/001_init.sql','src/Domain.cs'})

    def test_runner_logs_real_codes_redacts_secrets_and_scrubs_environment(self):
        runner=Runner(self.root,['PRIVATE_TOKEN'])
        with patch.dict(os.environ,{'QWEN_API_KEY':'PRIVATE_TOKEN','OTHER_SECRET':'PRIVATE_TOKEN'}),\
             patch('app.server_generation.subprocess.run',return_value=subprocess.CompletedProcess(['dotnet'],7,b'failure PRIVATE_TOKEN')) as command:
            code,log=runner.run(['dotnet','--list-sdks'])
        self.assertEqual(code,7);self.assertNotIn('PRIVATE_TOKEN',log)
        self.assertNotIn('QWEN_API_KEY',command.call_args.kwargs['env'])
        self.assertNotIn('OTHER_SECRET',command.call_args.kwargs['env'])
        self.assertFalse(command.call_args.kwargs['shell'])
        self.assertEqual(json.loads((self.root/'commands.json').read_text())[0]['exit_code'],7)


if __name__=='__main__':unittest.main()
