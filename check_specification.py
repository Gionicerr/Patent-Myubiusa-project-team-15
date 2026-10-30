"""Validate saved analysis/contracts and their generated OpenAPI/sidecars, with no model calls."""
import argparse
import json
import time
from pathlib import Path
from app.contracts import validate_analysis, validate_design
from app.specifications import validate_openapi_document


def check_directory(directory, coverage=None):
    directory=Path(directory);started=time.monotonic();checks=[]
    load=lambda name:json.loads((directory/name).read_text(encoding='utf-8-sig'))
    a,d=load('analysis.json'),load('design.json')
    requirements=(directory/'requirements.md').read_text(encoding='utf-8-sig')
    def add(name,issues):checks.append({'name':name,'status':'failed' if issues else 'passed','issues':issues})
    add('analysis_types_quotes_and_ids',validate_analysis(a,requirements))
    add('design_types_relationships_access_and_fr',validate_design(d,a))
    typed=d.get('schema_version')=='2.0'
    if typed:
        add('openapi_structure_and_exact_contract_match',validate_openapi_document(d,a,load('openapi.json')))
        for file,section in [('data-model.json','data_model'),('screens.json','screens'),('events.json','events'),('permissions.json','roles')]:
            add('sidecar_'+section,[] if load(file)==d[section] else ['Sidecar differs from design.json'])
    else:checks.append({'name':'openapi_structure','status':'not_applicable','issues':['Legacy prose remains readable; typed generation requires explicit review.']})
    if coverage:
        matrix=json.loads(Path(coverage).read_text(encoding='utf-8-sig'));frs={fr['id']:fr for fr in a['functional_requirements']};issues=[]
        for item in matrix['items']:
            if not item['requirement_ids'] or set(item['requirement_ids'])-set(frs):issues.append('Missing/unknown FR in coverage')
            for criterion in item['acceptance_criteria']:
                if criterion['id'] not in frs or criterion['criteria']!=frs[criterion['id']]['acceptance_criteria']:issues.append('Coverage acceptance criteria differ from analysis')
        add('coverage_references_and_acceptance_criteria',issues)
    return {'status':'passed' if all(c['status']!='failed' for c in checks) else 'failed','scope':'document_and_input_contracts_only','typed_design':typed,'checks':checks,'seconds':round(time.monotonic()-started,3),'model_calls':0,'application_tests_executed':False,'limitations':['Does not prove semantic completeness or a working application.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--coverage',type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    try:report=check_directory(args.directory,args.coverage)
    except (ValueError,TypeError,KeyError,OSError) as exc:report={'status':'failed','scope':'document_and_input_contracts_only','error_type':type(exc).__name__,'application_tests_executed':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False));return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
