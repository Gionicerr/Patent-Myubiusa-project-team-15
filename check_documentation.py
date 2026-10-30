"""Check local documentation assets/links and unchanged contracts. No API calls."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parent

def strip_fences(text):
    lines=[];fence=None
    for line in text.splitlines():
        mark=line.lstrip()[:3]
        if mark in ('```','~~~'):
            fence=None if fence==mark else (mark if fence is None else fence);continue
        if fence is None:lines.append(line)
    return '\n'.join(lines)


def anchors(text):
    found=set(re.findall(r'<a\s+id="([^"]+)"',text));counts={}
    for title in re.findall(r'^#{1,6}\s+(.+)$',strip_fences(text),re.M):
        slug=re.sub(r'[^\w\s-]','',title.lower()).replace(' ','-');counts[slug]=counts.get(slug,0)+1
        found.add(slug if counts[slug]==1 else slug+'-'+str(counts[slug]-1))
    return found


def check_links(paths):
    issues=[];checked=0
    for p in paths:
        text=strip_fences(p.read_text(encoding='utf-8-sig'))
        for raw in re.findall(r'(?<!!)\[[^\]\n]+\]\(([^)]+)\)',text):
            raw=raw.strip().strip('<>');parts=urlsplit(raw)
            if parts.scheme or parts.netloc:continue
            checked+=1;target=(p.parent/unquote(parts.path)).resolve() if parts.path else p.resolve()
            if not target.exists():issues.append(str(p.relative_to(ROOT))+': missing '+raw)
            elif parts.fragment and target.suffix=='.md' and unquote(parts.fragment) not in anchors(target.read_text(encoding='utf-8-sig')):
                issues.append(str(p.relative_to(ROOT))+': missing anchor '+raw)
    return checked,issues


def audit():
    standards=ROOT/'resources/standards/russtech';documents=ROOT/'docs/stage2';checks=[]
    add=lambda name,issues,**extra:checks.append({'name':name,'status':'failed' if issues else 'passed','issues':issues,**extra})
    sources=json.loads((standards/'sources.json').read_text(encoding='utf-8'));issues=[]
    for s in sources:
        if hashlib.sha256((standards/s['file']).read_bytes()).hexdigest()!=s['sha256']:issues.append('Original PDF changed: '+s['id'])
        if len(re.findall(r'^=== PAGE \d+ ===$',(standards/s['text']).read_text(encoding='utf-8'),re.M))!=s['pages']:issues.append('Missing extracted pages: '+s['id'])
        tables=json.loads((standards/s['tables']).read_text(encoding='utf-8'))
        if len(tables)!=s['pages']:issues.append('Missing table page inventory: '+s['id'])
    add('pdf_identity_and_extraction_inventory',issues,files=len(sources),pages=sum(s['pages'] for s in sources))
    md=list(standards.rglob('*.md'))+list(documents.rglob('*.md'));count,issues=check_links(md);add('relative_links_and_anchors',issues,links_checked=count)
    issues=[]
    for name in ('system-analysis','api-method','service','adr'):
        text=(standards/'templates'/(name+'.md')).read_text(encoding='utf-8-sig')
        if 'ПУСТОЙ ШАБЛОН' not in text:issues.append('Unmarked empty template: '+name)
    diagram=(standards/'templates/sequence.puml').read_text(encoding='utf-8-sig')
    if '@startuml' not in diagram or '@enduml' not in diagram:issues.append('Missing editable PlantUML markers')
    add('template_scope_and_editable_diagram_scaffold',issues,diagram_rendered=False)
    profile=json.loads((documents/'documentation-profile.json').read_text(encoding='utf-8'));issues=[]
    for name,digest in profile['machine_files_unchanged'].items():
        original=ROOT/'runs/stage2/reviewed-specification'/name
        if hashlib.sha256((documents/name).read_bytes()).hexdigest()!=digest:issues.append('Adapted contract changed: '+name)
        if original.exists() and hashlib.sha256(original.read_bytes()).hexdigest()!=digest:issues.append('Original contract changed: '+name)
    a=json.loads((documents/'analysis.json').read_text(encoding='utf-8'));sa=(documents/'system-analysis.md').read_text(encoding='utf-8')
    if re.findall(r'^### (FR-\d{3,}):',sa,re.M)!=[fr['id'] for fr in a['functional_requirements']]:issues.append('FR headings changed')
    add('unchanged_contracts_and_fr_identifiers',issues,machine_files=len(profile['machine_files_unchanged']))
    design=json.loads((documents/'design.json').read_text(encoding='utf-8'));op=next(x for x in design['api'] if x['operation_id']=='getSession');api=json.loads((documents/'openapi.json').read_text(encoding='utf-8'));example=(documents/'api-method-example.md').read_text(encoding='utf-8');issues=[]
    codes=re.findall(r'^\| ([1-5]\d\d) \|',example,re.M)
    blocks=[json.loads(b) for b in re.findall(r'```json\n(.*?)\n```',example,re.S)]
    if op['method']+' '+op['path'] not in example or api['paths'][op['path']][op['method'].lower()]['operationId']!=op['operation_id']:issues.append('Example route differs from OpenAPI')
    if codes!=[r['status'] for r in op['responses']]:issues.append('Example response codes differ')
    if blocks!=[api['components']['schemas']['ParkingSession'],api['components']['schemas']['Problem']]:issues.append('Example response schemas differ')
    add('partial_api_example_matches_existing_contract',issues,application_method_executed=False)
    baseline=ROOT/'runs/documentation-standards/before-hashes.json'
    if baseline.exists():
        hashes=json.loads(baseline.read_text(encoding='utf-8'));issues=[]
        for name,digest in hashes.items():
            if name.replace('\\','/') in ('app/artifacts.py','README.md'):continue
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:issues.append('Preserved source changed: '+name)
        add('saved_stage2_and_schema_preservation',issues)
    return {'status':'passed' if all(x['status']=='passed' for x in checks) else 'failed','scope':'documentation_preparation_only','checks':checks,
            'model_requests':0,'vm_access':False,'server_restarted':False,'template_compliance':'partial; missing data and future tasks explicitly recorded','limitations':['Does not certify full corporate approval, operational readiness or application behaviour.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);args=p.parse_args();report=audit();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False));return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
