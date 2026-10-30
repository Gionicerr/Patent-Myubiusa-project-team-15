"""Small operation bodies from Qwen; deterministic declarations from validated v2."""
import hashlib
import json
import re
import time
from pathlib import Path

from .contracts import parse_json
from .provider import ProviderError
from .server_generation import ServerGenerator, binding, write_project, validate_files
from .telemetry import request_sizes, size


def declarations(design, bindings):
    def kind(schema):
        return {'string': {'uuid':'Guid','date-time':'DateTimeOffset'}.get(schema.get('format'),'string'),
                'integer':'long','number':'decimal','boolean':'bool'}[schema['type']]
    def record(name, fields, optional=False):
        return 'public sealed record '+name+'('+', '.join(
            '[property: JsonPropertyName('+json.dumps(n)+')] '+kind(s)+('?' if optional else '')+' '+n+
            (' = null' if optional else '') for n,s in fields)+');'
    return '\n'.join([record('CreateRequest',bindings['client_fields'].items(),True),
        record(bindings['entity'],[(f['name'],f['schema']) for f in design['data_model'][0]['fields']])])


class HandlerGenerator(ServerGenerator):
    def __init__(self, *args, accepted_run, accepted_sha256, **kwargs):
        source=Path(accepted_run)
        sql_path=source/'project/db/001_init.sql'
        data=sql_path.read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        report=json.loads((source/'generation-report.json').read_text(encoding='utf-8'))
        info=report['files']['db/001_init.sql']
        if digest!=accepted_sha256 or digest!=info['sha256'] or not info.get('database_schema_verified') or info.get('origin')!='qwen_generation':
            raise ValueError('Accepted SQL hash/provenance/database validation mismatch')
        design=args[2]; analysis=args[3]
        binding(design,analysis)
        for name,value in [('design',design),('analysis',analysis)]:
            if json.loads((source/f'project/contract/{name}.json').read_text(encoding='utf-8-sig'))!=value:
                raise ValueError('Accepted SQL source contract differs: '+name)
        validate_files({'files':[{'path':'db/001_init.sql','content':data.decode('utf-8')}]},source/'project',expected_files={'db/001_init.sql'})
        super().__init__(*args,**kwargs)
        (self.project/'db').mkdir()
        (self.project/'db/001_init.sql').write_bytes(data)
        self.sql=data.decode('utf-8');self.bodies={}
        self.report.update(generator_version='server-handlers-1',handlers={})
        self.report['files']['db/001_init.sql']={**info,'reused_from':str(source.resolve()),'source_report':'generation-report.json'}
        self.dto=declarations(self.design,self.bindings)

    def signature(self, operation):
        return 'public static async Task<IResult> '+operation+'(HttpContext context, '+('CreateRequest request, ' if operation=='Create' else '')+'NpgsqlDataSource db)'

    def handler(self, operation, feedback=None):
        if len(self.client.calls)>=3 or (feedback and self.report['repair_used']):
            raise ValueError('New stage call/repair budget exhausted')
        if feedback:self.report['repair_used']=True
        self.report.update(status='generating',blocking_file='src/'+operation+'.cs');self.save()
        method='POST' if operation=='Create' else 'GET'
        op=next(o for o in self.design['api'] if o['method']==method)
        blocks={'signature':self.signature(operation),'dto':self.dto,'fields':self.design['data_model'][0]['fields'],
            'binding':self.bindings,'operation':op,'accepted_sql':self.sql,'error':feedback}
        if feedback:blocks['previous_body']=self.bodies.get(operation)
        instruction=('Return only JSON {"body":"C# method body without outer braces"}. Implement ONLY the supplied method. '
            'Do not repeat declarations, routes, usings, project, SQL or other methods. C#14 .NET10 Npgsql10.0.3. '
            'Available usings Npgsql, System.Text.Json.Serialization and Web implicit usings. '
            'string DemoIdentity.Employee(context) returns verified owner. Use await db.OpenConnectionAsync(), '
            'NpgsqlCommand and parameterized SQL with exact quoted identifiers. Return Results.Json for 201 or Results.Ok for 200. '
            'Validation errors Results.BadRequest(new {code="invalid_request",message="Invalid fields"}). '
            'Create: validate required/null/empty/whitespace and every contract limit; optional string null/missing defaults empty; '
            'generate Guid.NewGuid and DateTimeOffset.UtcNow; use INSERT ... RETURNING and read the persisted entity '
            'for the 201 response, including the database timestamp precision; never return the pre-insert in-memory entity. '
            'List: SELECT only current verified owner and return typed entity array/list. '
            'Read timestamptz with reader.GetFieldValue<DateTimeOffset>. No placeholders or NotImplementedException. '
            'Be concise: one operation only. Input data follows.\n')
        messages=[{'role':'system','content':'Produce only the requested single operation body in JSON.'},
                  {'role':'user','content':instruction+json.dumps(blocks,separators=(',',':'))}]
        count=len(self.client.calls)
        try:content=self.client.complete(messages,'Server/handler/'+operation,2 if feedback else 1)
        finally:
            if len(self.client.calls)>count:self.client.calls[-1].update(request_sizes(messages,blocks),file='src/'+operation+'.cs')
            self.save()
        data=parse_json(content);self.client.calls[-1]['parsed_json_size']=size(data)
        if not isinstance(data,dict) or set(data)!={'body'} or not isinstance(data['body'],str):raise ValueError('Expected exactly one body string')
        body=data['body']
        if not body.strip() or re.search(r'NotImplementedException|TODO|```|public\s+(?:static\s+)?class',body):raise ValueError('Incomplete/invalid method body')
        if any(s and s in body for s in self.runner.redactions):raise ValueError('Secret in body; withheld')
        self.bodies[operation]=body
        file=self.project/'src'/f'{operation}.cs'
        file.write_text('using Npgsql;\npublic static partial class DomainEndpoints {\n'+self.signature(operation)+' {\n'+body+'\n}\n}\n',encoding='utf-8')
        self.report['handlers'][operation]={'origin':'qwen_generation','call_index':len(self.client.calls)-1,
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
        folder=self.root/f'attempt-{len(self.client.calls)}';folder.mkdir()
        (folder/'result.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
        self.client.calls[-1]['validation_status']='ok';self.save()

    def failed_handler(self, error):
        matches=[n for n in ('Create','List') if n+'.cs(' in error]
        if len(matches)==1:return matches[0],error[-6000:]
        evidence=self.root/'api-evidence.json'
        if evidence.exists():
            data=json.loads(evidence.read_text())
            created=data.get('created_record',{})
            for row in data.get('read_before_restart') or []:
                if row.get(self.bindings['id'])==created.get(self.bindings['id']):
                    changed={k for k in set(row)|set(created) if row.get(k)!=created.get(k)}
                    if changed=={self.bindings['created']}:
                        return 'Create',('Actual POST timestamp differs from the same persisted record returned by GET. '
                            'PostgreSQL timestamptz precision is microseconds (10 .NET ticks); normalize server timestamp '
                            'before INSERT and response, or return the actual persisted timestamp. Preserve other behavior. '
                            +json.dumps({'created':created[self.bindings['created']],'read':row[self.bindings['created']]}))
        raise ValueError('Build/API failed; cannot safely identify one handler: '+error[-6000:])

    def run(self):
        self.started=time.monotonic()
        try:
            self.report['tools']=self.runner.tools()
            routes='global using NpgsqlTypes;\nusing Npgsql;\nusing System.Text.Json.Serialization;\n'+self.dto+'\npublic static partial class DomainEndpoints {\npublic static void Map(WebApplication app, NpgsqlDataSource db) {\n'
            for method,handler in [('Post','Create'),('Get','List')]:
                parameters='HttpContext context, CreateRequest request' if method=='Post' else 'HttpContext context'
                arguments='context, request, db' if method=='Post' else 'context, db'
                delegate='Func<HttpContext, CreateRequest, Task<IResult>>' if method=='Post' else 'Func<HttpContext, Task<IResult>>'
                routes+=delegate+' '+handler+'Handler = ('+parameters+') => '+handler+'('+arguments+');\n'
                routes+='app.Map'+method+'('+json.dumps(self.bindings['path'])+', '+handler+'Handler);\n'
            write_project(self.project,[('src/Domain.cs',routes+'}\n}\n')])
            if self.verify:
                ok,error=self.sql_check()
                if not ok:raise RuntimeError('SQL infrastructure failed: '+error)
            for operation in ('Create','List'):
                try:self.handler(operation)
                except ValueError as exc:
                    self.client.calls[-1]['validation_status']='error'
                    self.report['attempts'].append({'file':'src/'+operation+'.cs','diagnostic':str(exc)})
                    self.handler(operation,str(exc))
            self.report.update(domain_origin='qwen_handlers_with_contract_templates',blocking_file=None,status='generated')
            (self.project/'provenance.json').write_text(json.dumps({'input_origin':self.report['input_origin'],
                'sql':self.report['files']['db/001_init.sql'],'handlers':self.report['handlers'],
                'technical_files':'contract-derived templates; not model subject implementations'},indent=2))
            if self.build:
                ok,error=self.docker_check(1)
                if not ok:
                    if self.environment_failure(error):raise RuntimeError('Infrastructure: '+error[-3000:])
                    operation,diagnostic=self.failed_handler(error)
                    self.report['attempts'].append({'file':'src/'+operation+'.cs','diagnostic':diagnostic})
                    evidence=self.root/'api-evidence.json'
                    if evidence.exists():
                        (self.root/'api-evidence-before-repair.json').write_bytes(evidence.read_bytes())
                    self.handler(operation,diagnostic)
                    ok,error=self.docker_check(2)
                    if not ok:raise ValueError('Build/API failed after repair: '+error[-6000:])
        except ProviderError as exc:self.report.update(status='provider_failed',error=str(exc),error_code=exc.code)
        except (ValueError,RuntimeError) as exc:self.report.update(status='failed',error=str(exc))
        finally:
            if hasattr(self,'compose_name') and not self.report.get('containers_stopped'):
                code,_=self.runner.run(self.compose('down'),cwd=self.project,timeout=60)
                self.report['containers_stopped']=code==0
            self.save()
        return self.report
