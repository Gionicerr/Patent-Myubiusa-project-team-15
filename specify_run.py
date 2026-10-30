"""Generate/validate a versioned specification from a reviewed analysis; never builds an app."""
import argparse
import copy
import json
import time
import uuid
from pathlib import Path
from app.config import load_env
from app.provider import Client, normalize_config, ProviderError
from app.contracts import validate_analysis, validate_design
from app.designing import Designer, compact_context
from app.artifacts import render_documents, write_files


def run(args):
    from app.specifications import require_validation_tools
    require_validation_tools()
    requirements=args.requirements.read_text(encoding='utf-8-sig')
    analysis=json.loads(args.analysis.read_text(encoding='utf-8-sig'))
    answers=json.loads(args.answers.read_text(encoding='utf-8-sig')) if args.answers else {}
    issues=validate_analysis(analysis,requirements)
    if issues: raise ValueError('Analysis invalid: '+'; '.join(issues[:10]))
    args.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();client=None;manual=[];run_id=uuid.uuid4().hex
    previous_metrics=None
    metrics_path=args.output/'generation-metrics.json'
    if args.design and metrics_path.exists(): previous_metrics=json.loads(metrics_path.read_text(encoding='utf-8'))
    if not args.design and metrics_path.exists() and not getattr(args, 'resume', False):
        raise ValueError('Existing metrics must be preserved; explicitly --resume or use a new output directory')
    if args.design and getattr(args, 'resume', False):
        raise ValueError('--resume cannot be combined with --design')
    designer = None
    try:
        if args.design:
            design=json.loads(args.design.read_text(encoding='utf-8-sig'))
            manual.append({'type':'contract_review','source_file':args.design.name})
        else:
            load_env(); overrides={}
            if args.max_tokens is not None:overrides['max_tokens']=args.max_tokens
            if args.timeout is not None:overrides['timeout']=args.timeout
            client=Client(normalize_config(overrides))
            context=compact_context(json.loads(args.context.read_text(encoding='utf-8-sig'))) if args.context else {}
            designer=Designer(args.output,client,requirements,analysis,answers,context,
                              resume=getattr(args,'resume',False), batch_sizes={
                                  'api':getattr(args,'api_batch_size',2),
                                  'screens':getattr(args,'screen_batch_size',2),
                                  'test_scenarios':getattr(args,'scenario_batch_size',3)})
            try:
                design=designer.run()
            finally:
                client.calls[:]=copy.deepcopy(designer.state['calls'])
        issues=validate_design(design,analysis)
        if issues:raise ValueError('Contract invalid: '+'; '.join(issues[:20]))
        if design.get('schema_version')!='2.0':raise ValueError('A typed v2.0 design is required for this command')
        status='structural_checks_passed';error=None
    except (ValueError,ProviderError) as exc:
        if designer is None and not args.design:
            raise  # Rejected checkpoints/configuration must not overwrite prior metrics.
        status='failed';error=str(exc)
    calls=copy.deepcopy(client.calls) if client else []
    def tokens(field):return sum(c[field] for c in calls) if calls and all(c[field] is not None for c in calls) else None
    metrics=previous_metrics or {'model_calls':len(calls),'calls':calls,'input_tokens':tokens('input_tokens'),'output_tokens':tokens('output_tokens'),
                                'seconds':round(time.monotonic()-started,3),'repair_attempts':sum(c['attempt']>1 for c in calls),'manual_actions':[]}
    if designer:
        run_id=designer.state['run_id']
        metrics['seconds']=round(designer.state['seconds'],3)
        metrics['resumptions']=designer.state['resumptions']
        metrics['validation_history']=copy.deepcopy(designer.state['validation_history'])
    metrics['manual_actions'].extend(manual)
    report={'status':status,'run_id':run_id,'parent_run_id':args.parent_run_id,'origin':'reviewed_contract' if args.design else 'qwen_generation',
            'checks_planned':['JSON Schema 2020-12 shape and typed fields','Entity, index, FK and FR references','Roles, operations, screens and event deduplication','OpenAPI 3.1 via openapi-spec-validator','Every FR has an acceptance scenario'],
            'limitations':['Structural document checks only; application tests, database, build and security scanning were not executed.'],
            'metrics':metrics,'error':error,'validation_seconds':round(time.monotonic()-started,3)}
    report['checks']=[{'name':name,'status':'passed' if status=='structural_checks_passed' else 'not_completed'} for name in report.pop('checks_planned')]
    write_files(args.output,{'generation-metrics.json':json.dumps(metrics,ensure_ascii=False,indent=2),'specification-run.json':json.dumps(report,ensure_ascii=False,indent=2)})
    if error:
        write_files(args.output,{'failure-report.json':json.dumps(report,ensure_ascii=False,indent=2)})
        print(json.dumps({'status':status,'error':error,'model_calls':metrics['model_calls']},ensure_ascii=False));return 1
    documents=render_documents(requirements,analysis,design,answers,report)
    write_files(args.output,documents)
    print(json.dumps({'status':status,'files':sorted(documents),'model_calls':metrics['model_calls']},ensure_ascii=False));return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--requirements',required=True,type=Path);p.add_argument('--analysis',required=True,type=Path)
    p.add_argument('--answers',type=Path);p.add_argument('--context',type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--parent-run-id');p.add_argument('--max-tokens',type=int);p.add_argument('--timeout',type=float)
    p.add_argument('--resume',action='store_true',help='Explicitly continue design-checkpoint.json in the same output directory')
    p.add_argument('--api-batch-size',type=int,choices=(1,2),default=2)
    p.add_argument('--screen-batch-size',type=int,choices=(1,2),default=2)
    p.add_argument('--scenario-batch-size',type=int,choices=(1,2,3),default=3)
    p.add_argument('--design',type=Path,help='Validate an explicitly reviewed design instead of calling the model; preserve existing generation metrics')
    args=p.parse_args()
    return run(args)


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
