"""Explicit six-operation parking slice; full input stays immutable."""
import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi

from .contracts import parse_json, validate_design
from .provider import ProviderError
from .server_generation import ServerGenerator, Runner, write_project
from .server_templates import scaffold
from .specifications import build_openapi, entity_schema
from .telemetry import request_sizes, size

OPERATIONS=('listVehicles','listObjects','createSession','listVehicleSessions','confirmSession','listAllSessions')
TABLES=('Account','Vehicle','ImportBatch','ParkingObject','Route','ParkingSession')
NS=uuid.UUID('1173c33c-8b5f-43d4-8e6c-f7f48c89fb13')
def uid(name):return str(uuid.uuid5(NS,name))
def literal(v):
    if v is None:return 'NULL'
    if isinstance(v,bool):return 'TRUE' if v else 'FALSE'
    if isinstance(v,(int,float)):return str(v)
    if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
    return "'"+str(v).replace("'","''")+"'"
def q(n):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',n):raise ValueError('Unsafe contract identifier')
    return '"'+n+'"'
def base_type(s):
    t=s.get('type')
    return next((k for k in t if k!='null'),None) if isinstance(t,list) else t
def cs_type(s):
    return {'string':{'uuid':'Guid','date-time':'DateTimeOffset'}.get(s.get('format'),'string'),
        'integer':'long','number':'decimal','boolean':'bool'}.get(base_type(s),'JsonElement')

def profile(design,analysis,openapi):
    errors=validate_design(design,analysis)
    if errors:raise ValueError('Full v2 contract invalid: '+'; '.join(errors[:8]))
    if openapi!=build_openapi(design,analysis['title']):raise ValueError('Source OpenAPI differs from full contract')
    validate_openapi(openapi)
    ops={op['operation_id']:op for op in design['api']}
    if any(n not in ops for n in OPERATIONS):raise ValueError('Parking profile operation missing')
    entities={e['name']:e for e in design['data_model']}
    for n in TABLES:
        for rel in entities[n]['relations']:
            if rel['target_entity'] not in TABLES:raise ValueError('Profile missing FK dependency')
    return {'version':'parking-sessions-1','operations':[ops[n] for n in OPERATIONS],
        'entities':[entities[n] for n in TABLES],
        'limitations':['Only six operations; all other routes absent','Demo identity, no corporate authentication',
            'Small valid spb sample, not a full import','No matching, coordinates, notifications or payments',
            'Derived optional geometryGeoJson stored as nullable JSONB; spatial GiST index deferred with PostGIS',
            'No scheduled expiry worker; active state changes outside this slice are not implemented',
            'PostgreSQL17.9 Debian13 instead of specified Debian12 package']}

def sql_schema(p):
    statements=[]
    for e in p['entities']:
        columns=[]
        for f in e['fields']:
            n=q(f['name']);s=f['schema'];t=base_type(s)
            typ=({'uuid':'uuid','date-time':'timestamptz'}.get(s.get('format'),
                'varchar('+str(s['maxLength'])+')' if 'maxLength' in s else 'text') if t=='string' else
                {'integer':'bigint','number':'numeric','boolean':'boolean'}.get(t,'jsonb'))
            col=n+' '+typ+(' NOT NULL' if f['required'] else '')
            rules=[]
            for key,op in [('minimum','>='),('maximum','<=')]:
                if key in s:rules.append(n+op+str(s[key]))
            if s.get('minLength',0)>0:rules.append('length(btrim('+n+'))>='+str(s['minLength']))
            if 'pattern' in s:rules.append(n+' ~ '+literal(s['pattern']))
            if 'enum' in s:rules.append(n+' IN ('+','.join(literal(v) for v in s['enum'])+')')
            if 'const' in s:rules.append(n+' = '+literal(s['const']))
            if rules:col+=' CHECK ('+' AND '.join(rules)+')'
            columns.append(col)
        columns.append('PRIMARY KEY ('+','.join(map(q,e['primary_key']))+')')
        for rel in e['relations']:
            columns.append('FOREIGN KEY ('+q(rel['field'])+') REFERENCES '+q(rel['target_entity'])+'('+q(rel['target_field'])+') ON DELETE '+rel['on_delete'])
        statements.append('CREATE TABLE '+q(e['name'])+' (\n'+',\n'.join(columns)+'\n);')
        for i in e['indexes']:
            if i['method']!='btree':continue
            pred=i.get('predicate')
            tail=' WHERE '+q(pred['field'])+' = '+literal(pred['value']) if pred else ''
            statements.append('CREATE '+('UNIQUE ' if i['unique'] else '')+'INDEX '+q(i['name'])+' ON '+q(e['name'])+' ('+','.join(map(q,i['fields']))+')'+tail+';')
    statements.append('''CREATE TABLE "RequestReplay" (
"actorId" uuid NOT NULL REFERENCES "Account"("id"), "key" varchar(120) NOT NULL,
"fingerprint" text NOT NULL, "response" jsonb NOT NULL, "status" integer NOT NULL,
PRIMARY KEY ("actorId","key"));''')
    return '\n'.join(statements)+'\n'

def sample_seed(source,p):
    from shapely import from_wkt,get_coordinates
    raw=Path(source).read_bytes();d=json.loads(raw)['data']
    if d['city']!='spb':raise ValueError('Demo source must be spb')
    entity=next(e for e in p['entities'] if e['name']=='ParkingObject')
    # The optional derived geometry is null; validate all original tariff fields.
    schema=entity_schema(entity);schema['properties']['geometryGeoJson']={'type':'null'}
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    rows=[];indices=[];batch=uid('sample-import')
    for index,z in enumerate(d['zones']):
        try:
            g=from_wkt(z['geometry']);coords=get_coordinates(g)
            if g.is_empty or not g.is_valid or any(not (-180<=x<=180 and -90<=y<=90) for x,y in coords):continue
            row={**z,'id':uid('object:'+z['externalZoneId']),'city':'spb','importBatchId':batch,'geometryGeoJson':None,'geometryState':'valid'}
            if list(validator.iter_errors(row)):continue
            rows.append(row);indices.append(index)
            if len(rows)==2:break
        except (ValueError,KeyError,TypeError):continue
    if len(rows)!=2:raise ValueError('Need two valid source objects')
    accounts=[{'id':uid(n),'displayName':n,'role':role} for n,role in [('driver-a','driver'),('driver-b','driver'),('admin','admin')]]
    vehicles=[{'id':uid('vehicle-'+n),'driverId':uid('driver-'+n),'registration':'DEMO-'+n.upper(),'displayName':'Demo '+n,'sourceCity':'spb'} for n in ('a','b')]
    batches=[{'id':batch,'city':'spb','sha256':hashlib.sha256(raw).hexdigest(),'createdAt':'2026-10-30T00:00:00Z','status':'completed','accepted':2,'quarantined':0,'issues':[]}]
    sql=[]
    for table,items in [('Account',accounts),('Vehicle',vehicles),('ImportBatch',batches),('ParkingObject',rows)]:
        for row in items:
            sql.append('INSERT INTO '+q(table)+' ('+','.join(map(q,row))+') VALUES ('+','.join(literal(v) for v in row.values())+');')
    meta={'source_sha256':hashlib.sha256(raw).hexdigest(),'source_count':len(d['zones']),'selected_indices':indices,
        'objects':rows,'accounts':accounts,'vehicles':vehicles,'sample_only':True,'tariffs':'original values, units not interpreted'}
    return '\n'.join(sql)+'\n',meta

def declarations(p,design,request_names=('SessionInput','SessionConfirmation')):
    result=[]
    for name,fields,request in [(e['name'],e['fields'],False) for e in p['entities']]+[
        (n,[{'name':k,'schema':s,'required':k in design['schemas'][n]['required']} for k,s in design['schemas'][n]['properties'].items()],True) for n in request_names]:
        args=[]
        for f in fields:
            t=cs_type(f['schema']);nullable=not f['required'] or 'null' in (f['schema'].get('type') if isinstance(f['schema'].get('type'),list) else [])
            args.append(('[property: JsonRequired] ' if request and f['required'] else '')+t+('?' if nullable else '')+' '+f['name'])
        result.append('public sealed record '+name+'('+', '.join(args)+');')
    return '\n'.join(result)

class ParkingGenerator(ServerGenerator):
    def __init__(self,output,client,design,analysis,openapi,source,verify=False,sudo_docker=False,verify_existing=False):
        self.selected=profile(design,analysis,openapi)
        sql=sql_schema(self.selected);seed,sample=sample_seed(source,self.selected)
        self.root=Path(output);self.project=self.root/'project';self.verify_existing=verify_existing
        self.client=client;self.design=design;self.analysis=analysis;self.verify=verify;self.sample=sample
        self.elapsed=0
        if verify_existing:
            saved=json.loads((self.root/'generation-report.json').read_text())
            if saved.get('profile')!='parking-sessions-1':raise ValueError('Incompatible parking checkpoint')
            if any(c.get('model') not in (None,client.config.get('model')) for c in saved['metrics']['calls']):
                raise ValueError('Checkpoint model differs')
            for name,value in [('design.json',design),('analysis.json',analysis),('openapi.json',openapi)]:
                if json.loads((self.project/'contract'/name).read_text())!=value:raise ValueError('Checkpoint input differs: '+name)
            if json.loads((self.root/'source-sample.json').read_text())!=sample:raise ValueError('Checkpoint source/sample differs')
            for op in ('createSession','confirmSession'):
                info=saved['model_handlers'].get(op)
                if not info or hashlib.sha256((self.project/'src'/f'{op}.cs').read_bytes()).hexdigest()!=info['sha256']:
                    raise ValueError('Missing or changed accepted handler: '+op)
            self.report=saved;self.elapsed=saved['metrics']['seconds'];client.calls[:]=copy.deepcopy(saved['metrics']['calls'])
            self.runner=Runner(self.root,[client.config.get('api_key','')],sudo_docker)
            self.runner.commands=json.loads((self.root/'commands.json').read_text())
            runtime_env=dict(l.split('=',1) for l in (self.root/'runtime.env').read_text().splitlines() if '=' in l)
            self.secrets={k:runtime_env[k] for k in ('DB_PASSWORD','DEMO_TOKEN_A','DEMO_TOKEN_B','DEMO_TOKEN_ADMIN')}
            self.runner.redactions.extend(self.secrets.values());self.compose_name=saved['compose_project'];self.port=int(runtime_env['API_PORT'])
            index=len(list(self.root.glob('report-before-verification-*.json')))+1
            (self.root/f'report-before-verification-{index}.json').write_text(json.dumps(saved,indent=2))
            from .parking_templates import runtime
            target=self.project/'src/Runtime.cs';before=hashlib.sha256(target.read_bytes()).hexdigest()
            code=runtime(self.selected,design)
            target.write_text(code,encoding='utf-8')
            self.report.setdefault('engineering_edits',[]).append({'file':'src/Runtime.cs','origin':'technical template refresh; model bodies unchanged','before_sha256':before,'after_sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
            self.report.update(application_verified=False,checks=[],status='rechecking')
            self.report.pop('error',None);self.report.pop('error_code',None)
            return
        self.root.mkdir(parents=True,exist_ok=False);self.project.mkdir()
        self.runner=Runner(self.root,[client.config.get('api_key','')],sudo_docker)
        self.report={'status':'prepared','profile':'parking-sessions-1','application_verified':False,'checks':[],
            'model_handlers':{},'repair_used':False,'input_origin':'existing reviewed v2; no new analysis/design',
            'files':{},'limitations':self.selected['limitations']}
        from .parking_templates import runtime
        files=scaffold();files.pop('src/Program.cs');files['src/Runtime.cs']=runtime(self.selected,design)
        files['src/Models.cs']='using System.Text.Json;\nusing System.Text.Json.Serialization;\n'+declarations(self.selected,design)
        files['db/001_init.sql']=sql;files['db/002_demo.sql']=seed
        files['compose.yaml']=files['compose.yaml'].replace('Demo__TokenA:','Demo__TokenAdmin: ${DEMO_TOKEN_ADMIN:?Set DEMO_TOKEN_ADMIN}\n      Demo__TokenA:')
        files['.env.example']+='DEMO_TOKEN_ADMIN=replace-with-random-admin-token\n'
        files['README.md']='# Parking sessions API slice\n\nOnly six operations in contract/profile.json. See provenance.json and validation report. Demo identity and a two-object source sample only. Tokens are configured via private runtime.env; never commit it. PostgreSQL17.9 Debian13 package difference remains.\n'
        for name,value in [('design.json',design),('analysis.json',analysis),('openapi.json',openapi),('profile.json',self.selected)]:files['contract/'+name]=json.dumps(value,ensure_ascii=False,indent=2)
        write_project(self.project,list(files.items()))
        (self.root/'source-sample.json').write_text(json.dumps(sample,ensure_ascii=False,indent=2))
        self.report['technical_origin']='contract-derived SQL/DTO/routes/read operations/transactions/idempotency; no model subject fallback'

    def prepare_runtime(self):
        if hasattr(self,'compose_name'):
            self.management();return
        super().prepare_runtime()
        import secrets
        token=secrets.token_hex(24);self.secrets['DEMO_TOKEN_ADMIN']=token;self.runner.redactions.append(token)
        with (self.root/'runtime.env').open('a') as f:f.write('DEMO_TOKEN_ADMIN='+token+'\n')
        self.report['demo_accounts']={n:uid(n) for n in ('driver-a','driver-b','admin')}
        self.management()

    def management(self):
        script='''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-status}" in
 start) set -- up -d --wait ;;
 stop) set -- down ;;
 restart) set -- restart api ;;
 build) set -- build api ;;
 status) set -- ps ;;
 *) echo 'Usage: manage.sh {build|start|stop|restart|status}' >&2; exit 2 ;;
esac
exec @DOCKER@ compose --env-file "$ROOT/runtime.env" -p @PROJECT@ -f "$ROOT/project/compose.yaml" "$@"
'''.replace('@DOCKER@',' '.join(self.runner.prefix)).replace('@PROJECT@',self.compose_name)
        path=self.root/'manage.sh';path.write_text(script,encoding='utf-8');path.chmod(0o700)

    def handler(self,op,feedback=None):
        if len(self.client.calls)>=3 or (feedback and self.report['repair_used']):raise ValueError('Parking call/repair budget exhausted')
        if feedback:self.report['repair_used']=True
        signature='public static async Task<ParkingSession> '+op+'(SessionContext tx, Guid '+('vehicleId, SessionInput input)' if op=='createSession' else 'sessionId, SessionConfirmation input)')
        blocks={'signature':signature,'session_dto':declarations({'entities':[next(e for e in self.selected['entities'] if e['name']=='ParkingSession')]},self.design,('SessionInput' if op=='createSession' else 'SessionConfirmation',)),
            'operation':next(o for o in self.selected['operations'] if o['operation_id']==op),
            'interfaces':{'Now':'DateTimeOffset tx.Now (DB UTC)','RequireVehicle':'Task tx.RequireVehicle(Guid) checks ownership and locks vehicle',
            'RequireObject':'Task tx.RequireObject(Guid) checks existence and valid state',
            'LoadSession':'Task<ParkingSession> tx.LoadSession(Guid) checks ownership and locks session',
            'InsertSession':'Task<ParkingSession> tx.InsertSession(ParkingSession) returns actual INSERT RETURNING record',
            'SaveSession':'Task<ParkingSession> tx.SaveSession(ParkingSession) returns actual UPDATE RETURNING record',
            'error':'throw new ApiError(422 or 409, "short_code", "message")'},'feedback':feedback}
        path=self.project/'src'/f'{op}.cs'
        if feedback and path.exists():blocks['previous_file']=path.read_text()
        rule=('Create: await RequireVehicle(vehicleId), RequireObject(input.objectId); endAt must be strictly greater than tx.Now (422). '
            'Construct ParkingSession with new Guid, routeId null, startedAt tx.Now, endAt input.endAt, active, paymentConfirmed false, revision 1. '
            'Return await tx.InsertSession. Unique active conflict is handled by wrapper.' if op=='createSession' else
            'Confirm: await tx.LoadSession(sessionId); require existing.revision == input.expectedRevision (409). '
            'Require input.endAt strictly greater than tx.Now (422). Preserve id, vehicleId, objectId, routeId, startedAt. '
            'Return await tx.SaveSession(existing with {endAt=input.endAt,status="active",paymentConfirmed=false,revision=existing.revision+1}).')
        messages=[{'role':'system','content':'Return only JSON {"body":"C# method body without outer braces"}. One short operation, no declarations or explanations.'},
            {'role':'user','content':'C#14 .NET10. Technical wrapper already handles JSON validation, driver authorization, atomic transaction, idempotency and PostgreSQL unique conflicts. Do not reimplement them. '+rule+'\n'+json.dumps(blocks,separators=(',',':'))}]
        self.report.update(status='generating',blocking_operation=op);self.save()
        count=len(self.client.calls)
        try:content=self.client.complete(messages,'Parking/'+op,2 if feedback else 1)
        finally:
            if len(self.client.calls)>count:self.client.calls[-1].update(request_sizes(messages,blocks),operation_id=op)
            self.save()
        # Preserve only the final result, never the reasoning prefix.
        try:
            data=parse_json(content);self.client.calls[-1]['parsed_json_size']=size(data)
            if not isinstance(data,dict) or set(data)!={'body'} or not isinstance(data['body'],str) or not data['body'].strip():raise ValueError('Expected one nonempty body string')
            body=data['body']
            if re.search(r'TODO|NotImplementedException|```',body):raise ValueError('Incomplete operation body')
            if any(s and s in body for s in self.runner.redactions):raise ValueError('Secret in model output; withheld')
            code='public static partial class ParkingHandlers {\n'+signature+' {\n'+body+'\n}\n}\n'
            path.write_text(code,encoding='utf-8')
            result=self.root/f'call-{len(self.client.calls)}.json';result.write_text(json.dumps(data,indent=2))
            self.report['model_handlers'][op]={'origin':'qwen','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'call_index':len(self.client.calls)-1}
            self.client.calls[-1]['validation_status']='passed'
        except (ValueError,TypeError,KeyError) as exc:
            self.client.calls[-1].update(validation_status='failed',validation_error=str(exc));self.save();raise ValueError(str(exc)) from None
        self.save()

    def run(self):
        self.started=time.monotonic()-self.elapsed
        try:
            for op in (() if self.verify_existing else ('createSession','confirmSession')):
                try:self.handler(op)
                except ValueError as exc:self.handler(op,str(exc))
            (self.project/'provenance.json').write_text(json.dumps({'technical_origin':self.report['technical_origin'],'model_handlers':self.report['model_handlers'],'engineering_edits':self.report.get('engineering_edits',[])},indent=2))
            self.report.update(status='generated',blocking_operation=None)
            if self.verify:
                self.prepare_runtime()
                (self.project/'db').chmod(0o755)
                for f in (self.project/'db').glob('*.sql'):f.chmod(0o644)
                code,log=self.runner.run(self.compose('build','api'),cwd=self.project,timeout=600)
                if code:
                    if self.verify_existing:raise RuntimeError('Build failed during model-free verification: '+log[-6000:])
                    matches=[o for o in ('createSession','confirmSession') if o+'.cs(' in log]
                    if len(matches)!=1:raise RuntimeError('Technical build failure: '+log[-6000:])
                    self.handler(matches[0],log[-5000:]);code,log=self.runner.run(self.compose('build','api'),cwd=self.project,timeout=600)
                    if code:raise RuntimeError('Build failed after repair: '+log[-5000:])
                self.report['build_passed']=True
                code,log=self.runner.run(self.compose('up','-d','--wait'),cwd=self.project,timeout=150)
                if code:raise RuntimeError('Infrastructure startup failed: '+log[-3000:])
                self.report['containers_stopped']=False
                from .parking_smoke import verify
                self.report['checks']=verify(self)
                self.report['application_verified']=bool(self.report['checks']) and all(c['status']=='passed' for c in self.report['checks'])
                self.report['status']='verified_running' if self.report['application_verified'] else 'verification_failed'
        except ProviderError as exc:self.report.update(status='provider_failed',error=str(exc),error_code=exc.code)
        except (ValueError,RuntimeError) as exc:self.report.update(status='failed',error=str(exc))
        except Exception as exc:self.report.update(status='failed',error='Unexpected '+type(exc).__name__+': '+str(exc))
        finally:
            if hasattr(self,'compose_name') and not self.report['application_verified']:
                self.runner.run(self.compose('logs','--no-color'),cwd=self.project,timeout=30)
                code,_=self.runner.run(self.compose('down'),cwd=self.project,timeout=60);self.report['containers_stopped']=code==0
            self.save()
        return self.report
