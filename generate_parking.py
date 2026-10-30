"""Generate only the explicitly supported parking sessions profile on organizer VM."""
import argparse,json
from pathlib import Path
from app.config import load_env
from app.provider import Client,normalize_config
from app.parking_generation import ParkingGenerator

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--analysis',type=Path,default=Path('examples/parking-analysis-v2.json'))
 p.add_argument('--design',type=Path,default=Path('examples/parking-contracts-reviewed.json'))
 p.add_argument('--openapi',type=Path,default=Path('docs/stage2/openapi.json'))
 p.add_argument('--source',type=Path,default=Path('spb.json'))
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--verify',action='store_true')
 p.add_argument('--sudo-docker',action='store_true')
 p.add_argument('--verify-existing',action='store_true',help='Recheck accepted files with no model calls; retain call history')
 a=p.parse_args();load_env()
 try:
  read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
  if a.verify_existing and not a.verify:raise ValueError('--verify-existing requires --verify')
  g=ParkingGenerator(a.output,Client(normalize_config({})),read(a.design),read(a.analysis),read(a.openapi),a.source,a.verify,a.sudo_docker,a.verify_existing)
  r=g.run()
 except (ValueError,FileExistsError) as e:
  print(json.dumps({'status':'not_started','error':str(e)},ensure_ascii=False));return 2
 print(json.dumps({'status':r['status'],'application_verified':r['application_verified'],'metrics':{k:v for k,v in r['metrics'].items() if k!='calls'},'report':str(a.output/'generation-report.json')},ensure_ascii=False))
 return 0 if r['status']=='verified_running' or (not a.verify and r['status']=='generated') else 1
if __name__=='__main__':raise SystemExit(main())
