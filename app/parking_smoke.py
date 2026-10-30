"""Real HTTP/DB checks of six parking operations; no prepared mutation replies."""
import concurrent.futures
import json
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime,timedelta,timezone

from jsonschema import Draft202012Validator,FormatChecker
from referencing import Registry,Resource
from referencing.jsonschema import DRAFT202012
from .parking_generation import uid
from .provider import _NoRedirect


def verify(g):
    # Local import keeps the organizer client free of any HTTP test traffic.
    checks=[];evidence={};base=g.report['api_url']
    tokens={'a':g.secrets['DEMO_TOKEN_A'],'b':g.secrets['DEMO_TOKEN_B'],'admin':g.secrets['DEMO_TOKEN_ADMIN']}
    opmap={o['operation_id']:o for o in g.selected['operations']}
    document=json.loads((g.project/'contract/openapi.json').read_text())
    registry=Registry().with_resource('urn:parking',Resource.from_contents(document,default_specification=DRAFT202012))
    def valid(schema,value):
        return not list(Draft202012Validator({'$ref':'urn:parking'+schema['$ref']},registry=registry,format_checker=FormatChecker()).iter_errors(value))
    def request(method,path,who='a',body=None):
        headers={'Content-Type':'application/json'}
        if who:headers['Authorization']='Bearer '+tokens.get(who,who)
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try:
            with urllib.request.build_opener(_NoRedirect).open(req,timeout=8) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as ex:
            try:value=json.load(ex)
            except ValueError:value=None
            return ex.code,value
    def add(name,ok,detail=None):
        checks.append({'name':name,'status':'passed' if ok else 'failed',**({'detail':detail} if detail else {})})
        (g.root/'api-evidence.json').write_text(json.dumps({'checks':checks,**evidence},indent=2))
    def error(name,method,path,who,body,status):
        code,value=request(method,path,who,body)
        add(name,code==status and valid({'$ref':'#/components/schemas/Problem'},value),{'status':code})
    def future(hours=1):return (datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat()
    ready=False
    for _ in range(35):
        try:
            if request('GET','/api/vehicles')[0]==200:ready=True;break
        except (OSError,ValueError):pass
        time.sleep(1)
    add('api_ready',ready)
    if not ready:return checks
    error('no_token_401','GET','/api/vehicles',None,None,401)
    error('invalid_token_401','GET','/api/vehicles','bad-demo-token',None,401)
    error('driver_admin_forbidden','GET','/api/admin/sessions','a',None,403)
    for who in ('a','b','admin'):
        code,rows=request('GET','/api/vehicles',who)
        add('listVehicles_'+who,code==200 and valid({'$ref':'#/components/schemas/VehiclePage'},rows) and rows['total']==(2 if who=='admin' else 1))
        if who!='admin':add('vehicles_owner_'+who,all(r['driverId']==uid('driver-'+who) for r in rows['items']))
    code,objects=request('GET','/api/parking-objects?city=spb&page=1&pageSize=1')
    add('listObjects_paginated',code==200 and valid({'$ref':'#/components/schemas/ParkingObjectPage'},objects) and len(objects['items'])==1 and objects['total']==2)
    allobjects=request('GET','/api/parking-objects?city=spb')[1]['items']
    source={r['id']:r for r in g.sample['objects']}
    add('original_tariff_and_wkt',all(all(row[k]==source[row['id']][k] for k in ('geometry','price','priceDescription','minTime','timeStep','tariff')) for row in allobjects))
    error('city_required','GET','/api/parking-objects','a',None,400)
    error('invalid_pagination','GET','/api/vehicles?pageSize=101','a',None,400)
    error('invalid_page','GET','/api/vehicles?page=0','a',None,400)
    vehicles={w:uid('vehicle-'+w) for w in ('a','b')}
    create='/api/vehicles/'+vehicles['a']+'/sessions'
    body={'objectId':allobjects[0]['id'],'endAt':future(),'idempotencyKey':'create-a'}
    error('admin_cannot_create','POST',create,'admin',body,403)
    error('foreign_vehicle_create','POST',create,'b',body,403)
    error('missing_vehicle','POST','/api/vehicles/'+str(uuid.uuid4())+'/sessions','a',body,404)
    error('missing_object','POST',create,'a',{**body,'objectId':str(uuid.uuid4())},404)
    error('past_endAt','POST',create,'a',{**body,'endAt':'2000-01-01T00:00:00Z'},422)
    error('missing_endAt','POST',create,'a',{k:v for k,v in body.items() if k!='endAt'},400)
    error('unknown_input_field','POST',create,'a',{**body,'paymentConfirmed':True},400)
    error('empty_key','POST',create,'a',{**body,'idempotencyKey':''},422)
    error('long_key','POST',create,'a',{**body,'idempotencyKey':'x'*121},422)
    code,row=request('POST',create,'a',body);evidence['created_record']=row
    good=code==201 and valid({'$ref':'#/components/schemas/ParkingSession'},row)
    add('createSession',good,{'status':code})
    if not good:return checks
    add('session_server_fields',row['vehicleId']==vehicles['a'] and row['objectId']==body['objectId'] and row['paymentConfirmed'] is False and row['revision']==1 and row['status']=='active')
    code,replay=request('POST',create,'a',body)
    add('create_replay_identical',code==201 and replay==row)
    error('create_key_conflict','POST',create,'a',{**body,'endAt':future(2)},409)
    error('second_active_rejected','POST',create,'a',{**body,'idempotencyKey':'second-active'},409)
    for who in ('a','admin'):
        code,page=request('GET',create,who)
        add('listVehicleSessions_'+who,code==200 and valid({'$ref':'#/components/schemas/ParkingSessionPage'},page) and page['total']==1 and page['items']==[row])
    error('foreign_sessions_forbidden','GET',create,'b',None,403)
    code,page=request('GET','/api/admin/sessions?vehicleId='+vehicles['a'],'admin')
    add('listAllSessions',code==200 and valid({'$ref':'#/components/schemas/ParkingSessionPage'},page) and page['items']==[row])
    confirm='/api/sessions/'+row['id']+'/confirm'
    confirmation={'endAt':future(2),'expectedRevision':1,'idempotencyKey':'confirm-a'}
    error('foreign_confirmation_forbidden','POST',confirm,'b',confirmation,403)
    error('confirm_past_endAt','POST',confirm,'a',{**confirmation,'endAt':'2000-01-01T00:00:00Z'},422)
    error('confirm_invalid_revision','POST',confirm,'a',{**confirmation,'expectedRevision':0},422)
    error('confirm_unknown_field','POST',confirm,'a',{**confirmation,'objectId':body['objectId']},400)
    code,updated=request('POST',confirm,'a',confirmation);evidence['confirmed_record']=updated
    good=code==200 and valid({'$ref':'#/components/schemas/ParkingSession'},updated)
    add('confirmSession',good,{'status':code})
    if not good:return checks
    add('confirm_preserves_object_and_payment',updated['revision']==2 and updated['paymentConfirmed'] is False and all(updated[k]==row[k] for k in ('id','vehicleId','objectId','routeId','startedAt')))
    code,replay=request('POST',confirm,'a',confirmation)
    add('confirm_replay_identical',code==200 and replay==updated and replay['revision']==2)
    error('stale_revision_conflict','POST',confirm,'a',{**confirmation,'idempotencyKey':'stale'},409)
    error('confirm_key_conflict','POST',confirm,'a',{**confirmation,'endAt':future(3)},409)
    add('confirm_read_identical',request('GET',create)[1]['items']==[updated])
    # Exercise the independent owner's creation and atomic concurrent replay.
    otherpath='/api/vehicles/'+vehicles['b']+'/sessions'
    otherbody={**body,'idempotencyKey':'parallel-b'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:request('POST',otherpath,'b',otherbody),range(2)))
    add('concurrent_create_one_record',all(c==201 for c,_ in results) and results[0][1]==results[1][1] and request('GET',otherpath,'b')[1]['total']==1)
    add('sessions_owner_isolation',request('GET',create)[1]['total']==1 and request('GET',otherpath,'b')[1]['total']==1)
    code,_=g.runner.run(g.compose('restart','api'),cwd=g.project,timeout=60)
    persisted=False
    if code==0:
        for _ in range(30):
            try:
                if request('GET',create)[1]['items']==[updated]:persisted=True;break
            except (OSError,ValueError,TypeError):pass
            time.sleep(1)
    add('record_after_api_restart',persisted)
    add('create_replay_after_restart',request('POST',create,'a',body)==(201,row))
    add('confirm_replay_after_restart',request('POST',confirm,'a',confirmation)==(200,updated))
    add('revision_not_incremented_again',request('GET',create)[1]['items']==[updated])
    code,page=request('GET','/api/admin/sessions?page=1&pageSize=1','admin')
    add('admin_pagination',code==200 and page['total']==2 and len(page['items'])==1)
    code,db=g.runner.run(g.compose('exec','-T','db','psql','-U','app','-d','app','-tA','-c',
        'SELECT to_jsonb(s)::text FROM "ParkingSession" s WHERE id=\''+str(uuid.UUID(row['id']))+'\';'),cwd=g.project,timeout=30)
    add('sql_equals_api_after_restart',code==0 and json.loads(db)==updated)
    code,replays=g.runner.run(g.compose('exec','-T','db','psql','-U','app','-d','app','-tA','-c','SELECT count(*) FROM "RequestReplay";'),cwd=g.project,timeout=30)
    add('idempotency_atomic_records',code==0 and replays.strip()=='3')
    _,version=g.runner.run(g.compose('exec','-T','db','psql','-U','app','-d','app','-tA','-c','SELECT version();'),cwd=g.project,timeout=30)
    g.report['postgresql_build']=version.strip();add('postgresql_17_9',version.startswith('PostgreSQL 17.9'))
    return checks
