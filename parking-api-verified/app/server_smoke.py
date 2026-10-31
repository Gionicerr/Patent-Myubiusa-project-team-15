"""Actual HTTP/PostgreSQL checks for the deliberately supported server slice."""
import copy
import json
import time
import urllib.error
import urllib.request
import uuid

from jsonschema import Draft202012Validator, FormatChecker

from .server_generation import EMPLOYEES
from .specifications import entity_schema
from .provider import _NoRedirect


def example(schema):
    if 'enum' in schema: return schema['enum'][0]
    kind=schema['type']
    if kind=='string':
        length=max(1,schema.get('minLength',0));return 'x'*min(length,schema.get('maxLength',length))
    if kind=='boolean':return True
    return schema.get('minimum',min(0,schema.get('maximum',0)))


def verify_api(generator):
    b=generator.bindings;runner=generator.runner;checks=[]
    base=generator.report['api_url']+b['path']
    data={name:example(schema) for name,schema in b['client_fields'].items()}
    # Data values come from the contract; no hard-coded note field names.
    def request(method,token,payload=None):
        headers={'Content-Type':'application/json'}
        if token is not None:headers['Authorization']='Bearer '+token
        req=urllib.request.Request(base,data=json.dumps(payload).encode() if payload is not None else None,headers=headers,method=method)
        try:
            with urllib.request.build_opener(_NoRedirect).open(req,timeout=8) as response:
                return response.status,json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as exc:
            code=exc.code;exc.close();return code,None
    def add(name,passed,detail=None):
        checks.append({'name':name,'status':'passed' if passed else 'failed',**({'detail':detail} if detail else {})})
    a=generator.secrets['DEMO_TOKEN_A'];other=generator.secrets['DEMO_TOKEN_B']
    ready=False
    for _ in range(45):
        try:
            status,_=request('GET',a)
            if status==200:ready=True;break
        except (OSError,ValueError):pass
        time.sleep(1)
    add('api_ready',ready)
    if not ready:return checks
    add('missing_bearer_rejected',request('GET',None)[0]==401)
    add('invalid_bearer_rejected',request('GET','deliberately-invalid')[0]==401)
    code,row=request('POST',a,data)
    validator=Draft202012Validator(entity_schema(generator.design['data_model'][0]),format_checker=FormatChecker())
    valid=code==201 and isinstance(row,dict) and not list(validator.iter_errors(row))
    add('create_matches_contract',valid)
    if not valid:return checks
    key=row[b['id']]
    add('owner_from_verified_context',row[b['owner']]==EMPLOYEES[0])
    add('created_time_is_server_utc',isinstance(row[b['created']],str) and row[b['created']].endswith(('Z','+00:00')))
    code,listed=request('GET',a)
    add('read_created_record',code==200 and isinstance(listed,list) and any(item==row for item in listed))
    code,others=request('GET',other)
    add('owner_isolation',code==200 and isinstance(others,list) and all(item.get(b['owner'])==EMPLOYEES[1] for item in others) and not any(item.get(b['id'])==key for item in others))
    code,second=request('POST',other,data)
    add('second_owner_create',code==201 and isinstance(second,dict) and second.get(b['owner'])==EMPLOYEES[1])
    code,own=request('GET',a)
    add('first_owner_cannot_read_second_owner',code==200 and isinstance(own,list) and all(item.get(b['owner'])==EMPLOYEES[0] for item in own))
    forged={**data,b['owner']:EMPLOYEES[1]}
    add('client_owner_injection_rejected',request('POST',a,forged)[0]==400)
    add('client_id_injection_rejected',request('POST',a,{**data,b['id']:str(uuid.uuid4())})[0]==400)
    add('client_timestamp_injection_rejected',request('POST',a,{**data,b['created']:'2000-01-01T00:00:00Z'})[0]==400)
    for name in b['required']:
        bad=copy.deepcopy(data);bad.pop(name,None)
        add('required_'+name,request('POST',a,bad)[0]==400)
        add('null_required_'+name,request('POST',a,{**data,name:None})[0]==400)
    for name,schema in b['client_fields'].items():
        if name not in b['required'] and schema['type']=='string':
            omitted={**data};omitted.pop(name,None)
            status,defaulted=request('POST',a,omitted)
            add('optional_default_'+name,status==201 and isinstance(defaulted,dict) and defaulted.get(name)=='')
    for name,schema in b['client_fields'].items():
        if schema.get('minLength',0)>0:
            add('min_length_'+name,request('POST',a,{**data,name:''})[0]==400)
            add('whitespace_'+name,request('POST',a,{**data,name:'   '})[0]==400)
        if 'maxLength' in schema:
            add('max_length_'+name,request('POST',a,{**data,name:'x'*(schema['maxLength']+1)})[0]==400)
            add('max_length_boundary_'+name,request('POST',a,{**data,name:'x'*schema['maxLength']})[0]==201)
        if 'minimum' in schema:
            add('minimum_'+name,request('POST',a,{**data,name:schema['minimum']-1})[0]==400)
        if 'maximum' in schema:
            add('maximum_'+name,request('POST',a,{**data,name:schema['maximum']+1})[0]==400)
    code,_=runner.run(generator.compose('restart','api'),cwd=generator.project,timeout=60)
    persisted=False
    if code==0:
        for _ in range(30):
            try:
                status,items=request('GET',a)
                if status==200 and row in items:persisted=True;break
            except (OSError,ValueError):pass
            time.sleep(1)
    add('record_persists_after_server_restart',persisted)
    (generator.root/'api-evidence.json').write_text(json.dumps({'created_record':row,'second_owner_record':second,
        'read_before_restart':listed,'persisted_after_restart':persisted,'checks':checks},ensure_ascii=False,indent=2))
    def sql(command):
        return runner.run(generator.compose('exec','-T','db','psql','-U','app','-d','app','-tA',
                          '-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose','-c',command),cwd=generator.project,timeout=30)
    code,version=sql('SHOW server_version;')
    add('postgresql_17_9_actual',code==0 and version.strip().startswith('17.9'))
    code,count=sql(f'''SELECT count(*) FROM "{b['entity']}" WHERE "{b['id']}" = '{uuid.UUID(key)}';''')
    add('record_exists_in_postgresql',code==0 and count.strip()=='1')
    def literal(value):
        if isinstance(value,bool):return 'true' if value else 'false'
        if isinstance(value,(int,float)):return str(value)
        return "'"+str(value).replace("'","''")+"'"
    for name,schema in b['client_fields'].items():
        if 'maxLength' not in schema:continue
        bad={**row,name:'x'*(schema['maxLength']+1),b['id']:str(uuid.uuid4())}
        columns=','.join('"'+n+'"' for n in bad)
        values=','.join(literal(v) for v in bad.values())
        code,log=sql(f'''INSERT INTO "{b['entity']}" ({columns}) VALUES ({values});''')
        add('database_max_length_'+name,code!=0 and ('22001' in log or '23514' in log))
    evidence=generator.root/'api-evidence.json'
    saved=json.loads(evidence.read_text());saved['checks']=checks
    evidence.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
    return checks
