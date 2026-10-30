"""Offline planning/context/measurement regressions; no organizer requests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.contracts import TECHNOLOGY_PROFILE, analysis_prompt
from app.designing import (Designer, batch_settings, digest, relevant_context,
                          task_names, tasks, validate_part)
from app.specifications import validate_contract
from tests.test_designing import Model
from tests.test_specifications import typed_example, part_reply


def large_example():
    analysis = {'title': 'Requests', 'functional_requirements': [
        {'id': f'FR-{n:03}', 'text': f'Rule {n}', 'acceptance_criteria': [f'Observable result {n}'],
         'source_quote': f'Original quote {n}'} for n in range(1, 6)]}
    design = typed_example(analysis)
    operation = copy.deepcopy(design['api'][0]);screen = copy.deepcopy(design['screens'][0])
    design['api'] = [{**copy.deepcopy(operation), 'operation_id': name,
                      'path': f'/api/group{n}/{{requestId}}'}
                     for n, name in enumerate(('readRequest', 'readSecond', 'readThird'))]
    design['roles'][0]['permissions'] = [{'operation_id': op['operation_id'], 'scope': 'own'} for op in design['api']]
    design['screens'] = [{**copy.deepcopy(screen), 'id': f'screen{n}', 'route': f'/group{n}/:id'} for n in range(3)]
    return analysis, design


class DesignOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.analysis, self.design = large_example()
        self.architecture = part_reply(self.design, 'Design/architecture')
        self.parts = {'architecture': {'data': self.architecture}}

    def test_fixed_small_batches_and_explicit_singletons(self):
        plan = tasks(self.parts, self.analysis)
        self.assertEqual([task_names(t) for t in plan if t[1] == ('api',)],
                         [('readRequest', 'readSecond'), ('readThird',)])
        self.assertEqual([len(task_names(t)) for t in plan if t[1] == ('screens',)], [2, 1])
        self.assertEqual([len(task_names(t)) for t in plan if t[1] == ('test_scenarios',)], [3, 2])
        singles = tasks(self.parts, self.analysis, {k: 1 for k in ('api', 'screens', 'test_scenarios')})
        self.assertTrue(all(len(task_names(t)) <= 1 for t in singles))
        for value in ({'api': 3}, {'screens': 0}, {'test_scenarios': 4}, {'api': True}, {'unknown': 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):batch_settings(value)

    def test_saved_notes_inventory_yields_eight_parts_without_resuming(self):
        inventory = {'data_model': ['Note'], 'schemas': [], 'roles': ['Employee'],
                     'api': ['createNote', 'listNotes'], 'screens': ['NoteListScreen', 'NoteCreateScreen'], 'events': []}
        plan = tasks({'architecture': {'data': {'inventory': inventory}}}, self.analysis)
        self.assertEqual(len(plan), 8)
        self.assertEqual(len([t for t in plan if t[1] == ('test_scenarios',)]), 2)

    def test_exact_composition_for_operations_screens_and_scenarios(self):
        for section in ('api', 'screens', 'test_scenarios'):
            task = next(t for t in tasks(self.parts, self.analysis) if t[1] == (section,))
            good = part_reply(self.design, 'Design/'+task[0])
            self.assertEqual(validate_part(good, task, self.parts, self.analysis), [])
            cases = []
            missing = copy.deepcopy(good);missing[section].pop();cases.append(missing)
            duplicate = copy.deepcopy(good);duplicate[section].append(copy.deepcopy(duplicate[section][0]));cases.append(duplicate)
            extra = copy.deepcopy(good);item = copy.deepcopy(extra[section][0])
            if section == 'api':item['operation_id'] = 'readThird'
            elif section == 'screens':item['id'] = 'screen2'
            else:item['requirement_ids'] = ['FR-005'];item['id'] = 'TC-999'
            extra[section].append(item);cases.append(extra)
            for bad in cases:
                with self.subTest(section=section, bad=bad):
                    self.assertTrue(validate_part(bad, task, self.parts, self.analysis))

    def test_batch_assembly_and_only_failed_batch_repaired(self):
        bad_key = 'api:readRequest+readSecond'
        model = Model(self.design, invalid=bad_key)
        designer = Designer(self.root, model, 'Business requirements', self.analysis, {})
        result = designer.run()
        self.assertEqual(result, self.design)
        self.assertEqual(validate_contract(result, self.analysis), [])
        self.assertEqual([a for key, a in model.seen if key == bad_key], [1, 2])
        self.assertEqual(sum(key == 'api:readThird' for key, _ in model.seen), 1)
        self.assertEqual(designer.state['deferred_references'], [])

    def test_final_validation_repairs_batch_without_other_requests(self):
        class MissingAccessError(Model):
            def complete(self, messages, stage, attempt):
                data = json.loads(super().complete(messages, stage, attempt))
                if stage == 'Design/api:readRequest+readSecond' and attempt == 1:
                    data['api'][1]['responses'].pop()  # 403; shape valid, full validation rejects it.
                return json.dumps(data)
        model = MissingAccessError(self.design)
        result = Designer(self.root, model, 'Business requirements', self.analysis, {}).run()
        self.assertEqual(validate_contract(result, self.analysis), [])
        self.assertEqual(sum(k == 'api:readRequest+readSecond' for k, _ in model.seen), 2)
        self.assertEqual(sum(k == 'api:readThird' for k, _ in model.seen), 1)

    def test_architecture_collision_and_mapping_errors_are_explicit(self):
        task = tasks({}, self.analysis)[0]
        broken = copy.deepcopy(self.architecture)
        broken['inventory']['schemas'].append('Request')
        issues = validate_part(broken, task, {}, self.analysis)
        self.assertTrue(any('collide: Request' in issue for issue in issues))
        for mutate in (lambda d: d['context_map']['elements'].pop(),
                       lambda d: d['context_map']['elements'].append(copy.deepcopy(d['context_map']['elements'][0])),
                       lambda d: d['context_map']['elements'][0].update(requirement_ids=['FR-999'])):
            bad = copy.deepcopy(self.architecture);mutate(bad)
            self.assertTrue(validate_part(bad, task, {}, self.analysis))

    def test_relevance_preserves_rules_acceptance_rights_and_global_answers(self):
        analysis = copy.deepcopy(self.analysis)
        analysis.update(scope=['Only own records; no deletion'], roles=[{'name': 'Reader', 'permissions': ['own']}],
                        nonfunctional_requirements=[{'text': 'Keep records private'}],
                        questions=[{'id': q, 'default_assumption': 'Unconfirmed default'} for q in ('Q-001', 'Q-002')])
        arch = copy.deepcopy(self.architecture)
        for link in arch['context_map']['elements']:
            link['requirement_ids'] = ['FR-001'] if link['name'] == 'readRequest' else ['FR-002', 'FR-003', 'FR-004', 'FR-005']
            link['question_ids'] = [] if link['name'] == 'readRequest' else ['Q-002']
        arch['context_map']['global_question_ids'] = ['Q-001']
        parts = {'architecture': {'data': arch}}
        inputs = {'requirements': 'ORIGINAL FULL BUSINESS TEXT', 'analysis': analysis,
                  'answers': {'Q-001': 'Server verifies bearer; never trust client owner', 'Q-002': 'Unrelated clarification'},
                  'source_summary': {}}
        task = ('api:readRequest', ('api',), 'readRequest')
        context = relevant_context(task, inputs, parts)
        self.assertEqual([fr['id'] for fr in context['requirements']], ['FR-001'])
        self.assertEqual(context['requirements'][0]['acceptance_criteria'], analysis['functional_requirements'][0]['acceptance_criteria'])
        self.assertEqual(context['common']['roles'], analysis['roles'])
        self.assertEqual(context['common']['scope'], analysis['scope'])
        self.assertEqual(context['common']['nonfunctional_requirements'], analysis['nonfunctional_requirements'])
        self.assertEqual([q['id'] for q in context['clarifications']], ['Q-001'])
        encoded = json.dumps(context)
        for absent in ('ORIGINAL FULL BUSINESS TEXT', 'Original quote', 'Unrelated clarification', 'Rule 5'):
            self.assertNotIn(absent, encoded)
        full = relevant_context(tasks({}, analysis)[0], inputs, {})
        self.assertEqual(full['analysis'], analysis);self.assertEqual(full['answers'], inputs['answers'])
        scenario = ('test_scenarios:FR-004+FR-005', ('test_scenarios',), ('FR-004', 'FR-005'))
        self.assertEqual([fr['id'] for fr in relevant_context(scenario, inputs, parts)['requirements']], ['FR-004', 'FR-005'])

    def test_context_map_cannot_lose_questions_or_requirements(self):
        analysis = copy.deepcopy(self.analysis)
        analysis['questions'] = [{'id': 'Q-001', 'default_assumption': 'Default'}]
        arch = copy.deepcopy(self.architecture)
        self.assertTrue(any('every question' in i for i in validate_part(arch, tasks({}, analysis)[0], {}, analysis)))
        arch['context_map']['global_question_ids'] = ['Q-001']
        for link in arch['context_map']['elements']:link['requirement_ids'] = ['FR-001']
        self.assertTrue(any('all FR-ID' in i for i in validate_part(arch, tasks({}, analysis)[0], {}, analysis)))

    def test_old_planner_and_changed_batch_sizes_rejected_without_overwrite(self):
        model = Model(self.design);designer = Designer(self.root, model, 'Business requirements', self.analysis, {})
        state = designer.state;state['revision'] = 'design-parts-1'
        designer.path.write_text(json.dumps(state), encoding='utf-8');before = designer.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'planner revision.*design-parts-1'):
            Designer(self.root, Model(self.design), 'Business requirements', self.analysis, {}, resume=True)
        self.assertEqual(designer.path.read_bytes(), before)
        with tempfile.TemporaryDirectory() as other:
            current = Designer(other, Model(self.design), 'Business requirements', self.analysis, {}, batch_sizes={'api': 1})
            before = current.path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'batch sizes'):
                Designer(other, Model(self.design), 'Business requirements', self.analysis, {}, resume=True)
            self.assertEqual(current.path.read_bytes(), before)

    def test_sizes_survive_repair_without_storing_reasoning(self):
        class Reasoning(Model):
            def complete(self, *args):return '<think>PRIVATE_REASONING_TEXT</think>\n'+super().complete(*args)
        model = Reasoning(self.design, invalid='api:readRequest+readSecond')
        designer = Designer(self.root, model, 'Business requirements', self.analysis, {})
        designer.run()
        self.assertNotIn('PRIVATE_REASONING_TEXT', designer.path.read_text(encoding='utf-8'))
        for call in model.calls:
            self.assertGreater(call['message_content_size']['characters'], call['parsed_json_size']['characters'])
            self.assertGreater(call['reasoning_prefix_size']['characters'], 0)
            self.assertIn('response_schema', call['context_block_sizes'])
            self.assertEqual(call['input_tokens'], 3)
            self.assertEqual(call['output_tokens'], 7)
        architecture = next(c for c in model.calls if c['stage'] == 'Design/architecture')
        api = next(c for c in model.calls if c['stage'].startswith('Design/api:'))
        self.assertIn('analysis', architecture['context_block_sizes'])
        self.assertNotIn('analysis', api['context_block_sizes'])

    def test_profile_is_configuration_for_analysis_and_conditional_mobile(self):
        prompt = analysis_prompt('Internal desktop web service; no mobile interface.')
        for value in ('20.1.6', 'Material', '.NET 10', 'C# 14', '17.9', 'Docker Compose'):
            self.assertIn(value, prompt)
        self.assertIn('PWA только при требовании мобильного интерфейса', prompt)
        self.assertIn('не новое бизнес-требование', prompt)
        self.assertIn('для обычного веб-приложения не требуется', TECHNOLOGY_PROFILE['mobile'])


if __name__ == '__main__': unittest.main()
