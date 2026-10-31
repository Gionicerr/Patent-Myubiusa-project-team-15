import json,hashlib,zipfile
from pathlib import Path
r=Path.cwd();run=r/'runs/parking-sessions'
env=dict(l.split('=',1) for l in (run/'runtime.env').read_text().splitlines() if '=' in l)
secrets=[v.encode() for k,v in env.items() if 'TOKEN' in k or 'PASSWORD' in k]
for line in (r/'.env').read_text().splitlines():
 if line.startswith('QWEN_API_KEY='):secrets.append(line.split('=',1)[1].strip().strip('"').strip("'").encode())
files=[]
for p in r.rglob('*'):
 if not p.is_file() or any(k in p.parts for k in ('runner-home','__pycache__','bin','obj','.git')):continue
 if p.name in ('runtime.env','spb.json','parking-api-verified.zip','archive-manifest.json'):continue
 if p.name.endswith('.tar.gz'):continue
 if p.name.startswith('.env') and p.name!='.env.example':continue
 files.append(p)
manifest={}
for p in files:
 data=p.read_bytes()
 assert not any(s and s in data for s in secrets),'Secret detected, archive withheld'
 manifest[p.relative_to(r).as_posix()]=hashlib.sha256(data).hexdigest()
(r/'archive-manifest.json').write_text(json.dumps(manifest,indent=2));files.append(r/'archive-manifest.json')
with zipfile.ZipFile('parking-api-verified.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,p.relative_to(r).as_posix())
print(json.dumps({'files':len(files),'secret_scan':'passed','bytes':Path('parking-api-verified.zip').stat().st_size}))
