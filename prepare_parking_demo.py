"""Add two free demo vehicles without touching sessions. No model or server restart.

Run on vm15: python prepare_parking_demo.py --run runs/parking-sessions --sudo-docker
Each invocation keeps a separate safety/HTTP verification report.
"""
import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import datetime,timezone
from pathlib import Path

NS=uuid.UUID('1173c33c-8b5f-43d4-8e6c-f7f48c89fb13')


def vehicles(sample):
    accounts={a['displayName']:a for a in sample['accounts']}
    return [{'id':str(uuid.uuid5(NS,'client-demo-vehicle-'+suffix)),
             'driverId':accounts['driver-'+suffix]['id'],
             'registration':'DEMO-CLIENT-'+suffix.upper(),
             'displayName':'Free client demo '+suffix.upper(),'sourceCity':'spb'}
            for suffix in ('a','b')]


def seed_sql(rows):
    def literal(value):return "'"+value.replace("'","''")+"'"
    statements=['BEGIN;',"SELECT pg_advisory_xact_lock(hashtextextended('parking-client-demo-preparation-v1',0));",
                'LOCK TABLE "Vehicle", "ParkingSession" IN SHARE ROW EXCLUSIVE MODE;']
    for row in rows:
        owner=literal(row['driverId'])
        statements.append('DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM "Account" WHERE id='+owner+" AND role='driver') THEN RAISE EXCEPTION 'Expected demo driver missing'; END IF; END $$;")
        statements.append('INSERT INTO "Vehicle" ('+','.join('"'+k+'"' for k in row)+') VALUES ('+
                          ','.join(literal(v) for v in row.values())+') ON CONFLICT (id) DO NOTHING;')
        conditions=' AND '.join('"'+k+'"='+literal(v) for k,v in row.items())
        statements.append('DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM "Vehicle" WHERE '+conditions+
                          ") THEN RAISE EXCEPTION 'Existing demo vehicle differs; no overwrite allowed'; END IF; END $$;")
    statements.append('COMMIT;')
    return '\n'.join(statements)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--sudo-docker',action='store_true')
    args=parser.parse_args(argv);root=args.run.resolve()
    config=json.loads((root/'generation-report.json').read_text())
    if config.get('profile')!='parking-sessions-1' or not config.get('application_verified'):
        raise ValueError('Expected the already verified parking sessions run')
    sample=json.loads((root/'source-sample.json').read_text());rows=vehicles(sample)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    output=root/'client-demo-preparation'/stamp;output.mkdir(parents=True)
    report={'status':'checking','new_model_calls':0,'new_vehicles':rows,'checks':[],
            'sessions_created':0,'server_restarts':0,'commands':[]}
    runtime=dict(line.split('=',1) for line in (root/'runtime.env').read_text().splitlines() if '=' in line)
    tokens={k:runtime[k] for k in ('DEMO_TOKEN_A','DEMO_TOKEN_B','DEMO_TOKEN_ADMIN')}
    command=(['sudo','-n','docker'] if args.sudo_docker else ['docker'])+[
        'compose','--env-file',str(root/'runtime.env'),'-p',config['compose_project'],
        '-f',str(root/'project/compose.yaml'),'exec','-T','db','psql','-U','app','-d','app',
        '-X','-q','-tA','-v','ON_ERROR_STOP=1']
    def sql(text):
        # No pipeline keys or tokens are inherited by the Docker command.
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','SystemRoot','WINDIR','TEMP','TMP')}
        result=subprocess.run(command,input=text.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=45,env=env,shell=False)
        report['commands'].append({'argv':command,'exit_code':result.returncode,'sql_sha256':hashlib.sha256(text.encode()).hexdigest()})
        if result.returncode:raise RuntimeError('Database command failed; exit='+str(result.returncode)+'; raw error withheld')
        return result.stdout.decode().strip()
    def snapshot():
        return {t:json.loads(sql('SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY '+order+"),'[]'::jsonb) FROM \""+t+'" t;'))
                for t,order in [('Vehicle','id'),('ParkingSession','id'),('RequestReplay','"actorId",key')]}
    def get(path,token):
        request=urllib.request.Request(config['api_url']+path,headers={'Authorization':'Bearer '+token},method='GET')
        try:
            with urllib.request.urlopen(request,timeout=8) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('API GET failed; status='+str(error.code)) from None
    def page(path,token):
        items=[];number=1
        while True:
            data=get(path+('?' if '?' not in path else '&')+'page='+str(number)+'&pageSize=100',token)
            if not all(k in data for k in ('items','page','pageSize','total')):raise RuntimeError('Expected contract page')
            items.extend(data['items'])
            if len(items)>=data['total']:return items
            if not data['items']:raise RuntimeError('Incomplete API pagination')
            number+=1
    def check(name,passed):
        report['checks'].append({'name':name,'status':'passed' if passed else 'failed'})
    try:
        before=snapshot();admin=tokens['DEMO_TOKEN_ADMIN']
        old_api_vehicles=page('/api/vehicles',admin);old_api_sessions=page('/api/admin/sessions',admin)
        (output/'seed.sql').write_text(seed_sql(rows))
        sql(seed_sql(rows));after=snapshot()
        by_id={r['id']:r for r in after['Vehicle']}
        check('old_vehicles_unchanged_sql',all(by_id.get(r['id'])==r for r in before['Vehicle']))
        check('only_expected_vehicles_added',set(by_id)=={r['id'] for r in before['Vehicle']}|{r['id'] for r in rows})
        check('sessions_unchanged_sql',before['ParkingSession']==after['ParkingSession'])
        check('idempotency_records_unchanged',before['RequestReplay']==after['RequestReplay'])
        check('new_vehicles_have_no_sessions_sql',not any(s['vehicleId'] in {r['id'] for r in rows} for s in after['ParkingSession']))
        for index,row in enumerate(rows):
            who='a' if index==0 else 'b';token=tokens['DEMO_TOKEN_A' if index==0 else 'DEMO_TOKEN_B']
            own=page('/api/vehicles',token)
            check('driver_'+who+'_sees_new_vehicle',row in own)
            check('driver_'+who+'_sees_only_own_vehicles',all(v['driverId']==row['driverId'] for v in own))
            sessions=get('/api/vehicles/'+row['id']+'/sessions',token)
            check('driver_'+who+'_new_vehicle_sessions_empty',sessions['items']==[] and sessions['total']==0)
            for previous in before['Vehicle']:
                if previous['driverId']==row['driverId']:
                    actual=page('/api/vehicles/'+previous['id']+'/sessions',token)
                    expected=[s for s in before['ParkingSession'] if s['vehicleId']==previous['id']]
                    check('driver_'+who+'_previous_sessions_preserved_'+previous['id'],actual==expected)
        admin_vehicles=page('/api/vehicles',admin);admin_sessions=page('/api/admin/sessions',admin)
        check('admin_sees_both_new_vehicles',all(r in admin_vehicles for r in rows))
        check('old_vehicles_unchanged_api',all(r in admin_vehicles for r in old_api_vehicles))
        check('old_sessions_unchanged_api',admin_sessions==old_api_sessions)
        report['vehicles_added_this_run']=len(after['Vehicle'])-len(before['Vehicle'])
        report['sessions_before']=len(before['ParkingSession']);report['sessions_after']=len(after['ParkingSession'])
        report['status']='verified' if all(c['status']=='passed' for c in report['checks']) else 'verification_failed'
    except Exception as error:
        report.update(status='failed',error=str(error))
    finally:
        text=json.dumps(report,ensure_ascii=False,indent=2)
        for key,value in runtime.items():
            if value and ('TOKEN' in key or key=='DB_PASSWORD'):text=text.replace(value,'[REDACTED]')
        (output/'report.json').write_text(text,encoding='utf-8')
    print(json.dumps({'status':report['status'],'new_vehicles':rows,'vehicles_added_this_run':report.get('vehicles_added_this_run'),
                      'checks_passed':sum(c['status']=='passed' for c in report['checks']),'checks_total':len(report['checks']),
                      'report':str(output/'report.json')},ensure_ascii=False))
    return 0 if report['status']=='verified' else 1


if __name__=='__main__':raise SystemExit(main())
