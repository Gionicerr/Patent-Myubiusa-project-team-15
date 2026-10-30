"""Run: python report_inputs.py spb.json response.json --output runs/input-report.json"""
import argparse
import json
from pathlib import Path
from app.input_report import inspect_sources, render_input_report


def main():
    parser = argparse.ArgumentParser(description='Inspect all source records without sending them to a model')
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--regions',type=Path,help='Optional city->approximate [minX,minY,maxX,maxY] sanity regions')
    args = parser.parse_args()
    report = inspect_sources(args.sources, json.loads(args.regions.read_text(encoding='utf-8')) if args.regions else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    args.output.with_suffix('.md').write_text(render_input_report(report),encoding='utf-8')
    for source in report['sources']:
        print(json.dumps({k:source[k] for k in ('file','city','objects','geometry_types','problem_counts')},ensure_ascii=False))


if __name__=='__main__': main()
