"""Document-format regression checks; no model/server/target application execution."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.artifacts import render_documents,write_files
from app.documentation import with_contents
from app.demo import REQUIREMENTS,fixture
from adapt_documentation import adapt_saved_documents
from check_documentation import check_preserved_hashes


class DocumentationTests(unittest.TestCase):
    def test_saved_hash_paths_support_both_separators(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);file=root/'runs'/'stage2'/'artifact-manifest.json'
            file.parent.mkdir(parents=True);file.write_bytes(b'unchanged contract')
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            for name in ('runs/stage2/artifact-manifest.json',r'runs\stage2\artifact-manifest.json'):
                with self.subTest(name=name):
                    self.assertEqual(check_preserved_hashes(root,{name:digest}),[])
                    self.assertEqual(check_preserved_hashes(root,{name:'0'*64}),['Preserved source changed: '+name])

    def test_controls_preserve_legacy_data_and_state_missing_approvals(self):
        a,d=fixture();before=copy.deepcopy((a,d));report={'metrics':{'model_calls':0}}
        docs=render_documents(REQUIREMENTS,a,d,{},report)
        self.assertEqual((a,d),before)
        self.assertEqual(json.loads(docs['analysis.json']),a);self.assertEqual(json.loads(docs['design.json']),d)
        for marker in ('TO BE','## Оглавление','### История изменений документа','### Лист согласования','Не проводилось','Не назначен'):
            self.assertIn(marker,docs['system-analysis.md'])
        self.assertIn('(#fr-001)',docs['system-analysis.md']);self.assertIn('<a id="fr-001">',docs['system-analysis.md'])
        self.assertNotIn('](openapi.json)',docs['system-analysis.md'])

    def test_adaptation_preserves_json_bytes_and_never_calls_provider(self):
        a,d=fixture();docs=render_documents(REQUIREMENTS,a,d,{}, {'metrics':{'model_calls':0}})
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source';target=Path(temp)/'target';write_files(source,docs)
            # Different whitespace must be preserved rather than reserialized.
            (source/'design.json').write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
            with patch('app.provider.Client.complete',side_effect=AssertionError('No model calls allowed')):
                profile=adapt_saved_documents(source,target)
            for name in ('analysis.json','design.json','answers.json','quality-report.json'):
                self.assertEqual((source/name).read_bytes(),(target/name).read_bytes())
            self.assertEqual(hashes,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
            self.assertFalse(profile['approval_recorded']);self.assertEqual(profile['new_model_calls'],0)
            with self.assertRaises(ValueError):adapt_saved_documents(source,source)

    def test_contents_skip_code_fences_and_make_unique_anchors(self):
        md=with_contents('# Title\n## Same\n```md\n## Not a heading\n```\n## Same\n### FR-001: Test\n')
        self.assertIn('](#doc-same)',md);self.assertIn('](#doc-same-2)',md)
        self.assertNotIn('](#doc-not-a-heading)',md);self.assertEqual(md.count('<a id="fr-001">'),1)


if __name__=='__main__':unittest.main()
