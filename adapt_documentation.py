"""Reformat saved analytical documents locally; no provider, server or model calls."""
import argparse
import hashlib
import json
from pathlib import Path
from app.artifacts import render_documents, write_files

MACHINE_FILES=('analysis.json','design.json','answers.json','quality-report.json','openapi.json',
               'data-model.json','screens.json','events.json','permissions.json')


def adapt_saved_documents(source, output):
    source,output=Path(source),Path(output)
    if source.resolve()==output.resolve():raise ValueError('Use a separate output directory to preserve the source run')
    load=lambda name:json.loads((source/name).read_text(encoding='utf-8-sig'))
    a,d,answers,report=(load(n) for n in ('analysis.json','design.json','answers.json','quality-report.json'))
    raw=(source/'requirements.md').read_text(encoding='utf-8-sig')
    marker='# Исходные требования\n\n'
    requirements=raw.split(marker,1)[1] if marker in raw else raw
    documents=render_documents(requirements,a,d,answers,report,demo=report.get('mode')=='prepared_example')
    output.mkdir(parents=True,exist_ok=True)
    # Preserve exact JSON bytes, including schema/IDs/OpenAPI and existing model metrics.
    hashes={}
    for name in MACHINE_FILES:
        p=source/name
        if p.exists():
            data=p.read_bytes();(output/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
    write_files(output,{n:t for n,t in documents.items() if n.endswith(('.md','.csv'))})
    profile={'profile':'russtech-preparation-1','scope':'markdown_formatting_only','machine_files_unchanged':hashes,
             'approval_recorded':False,'new_model_calls':0,'limitations':['Partial preparation: missing metadata and operational details remain explicitly unfilled.']}
    write_files(output,{'documentation-profile.json':json.dumps(profile,ensure_ascii=False,indent=2)+'\n'})
    return profile


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    profile=adapt_saved_documents(args.source,args.output)
    print(json.dumps({'status':'documents_adapted','preserved_machine_files':len(profile['machine_files_unchanged']),'new_model_calls':0}));return 0


if __name__=='__main__':
    import sys
    sys.exit(main())
