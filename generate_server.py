"""Explicit Qwen server generation from validated v2. Run real requests on organizer VM."""
import argparse
import json
from pathlib import Path

from app.config import load_env
from app.provider import Client, normalize_config
from app.server_generation import ServerGenerator


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,required=True)
    parser.add_argument('--design',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--origin',type=Path,help='Explicit provenance of the input specification')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--verify',action='store_true',help='Build and verify API/PostgreSQL in isolated Compose')
    parser.add_argument('--sudo-docker',action='store_true',help='Use already authorized sudo -n docker, without changing groups/services')
    parser.add_argument('--repair-truncated',action='store_true',help='Legacy option: rejected by split-file generation; use a new output directory')
    parser.add_argument('--resume',action='store_true',help='Explicitly continue the same split-file run, preserving generated files and total call budget')
    args=parser.parse_args(argv)
    load_env()
    analysis=json.loads(args.analysis.read_text(encoding='utf-8-sig'))
    design=json.loads(args.design.read_text(encoding='utf-8-sig'))
    origin=json.loads(args.origin.read_text(encoding='utf-8-sig')) if args.origin else 'provided_v2_contract; original author unverified'
    try:
        generator=ServerGenerator(args.output,Client(normalize_config({})),design,analysis,
            build=args.build,verify=args.verify,sudo_docker=args.sudo_docker,input_origin=origin,
            repair_truncated=args.repair_truncated,resume=args.resume)
        report=generator.run()
    except (ValueError,FileExistsError) as exc:
        print(json.dumps({'status':'not_started','error':str(exc),'model_calls':0},ensure_ascii=False));return 2
    print(json.dumps({'status':report['status'],'application_verified':report['application_verified'],
                     'metrics':{k:v for k,v in report['metrics'].items() if k!='calls'},
                     'report':str(args.output/'generation-report.json')},ensure_ascii=False))
    return 0 if report['status'] in ('generated','built','verified') and (not args.verify or report['application_verified']) else 1


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
