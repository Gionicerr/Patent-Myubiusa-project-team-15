"""Sequential Qwen design parts, durable checkpoints, unchanged v2 output."""
import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from .contracts import SYSTEM_PROMPT, TECHNOLOGY_PROFILE, parse_json, validate_design
from .specifications import contract_schema, entity_schema, validate_value_schema
from .telemetry import size, request_sizes, content_sizes

REVISION = 'design-parts-2'
BATCH_LIMITS = {'api': 2, 'screens': 2, 'test_scenarios': 3}
INVENTORY = {'data_model': 'name', 'schemas': None, 'roles': 'id',
             'api': 'operation_id', 'screens': 'id', 'events': 'name'}
NOTES = ('assumptions', 'open_questions', 'validation_and_errors',
         'security_recommendations', 'limitations')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def compact_context(value):
    """Accept source statistics, never full parking arrays; bound the final summary."""
    if not isinstance(value, dict):
        raise ValueError('Source summary must be an object')
    if 'sources' in value:
        keep = ('file', 'sha256', 'city', 'objects', 'geometry_types', 'geometry_collection_members',
                'xy_bounds', 'field_types', 'tariff', 'problem_counts', 'crs_note')
        value = {'sources': [{**{k: s[k] for k in keep if k in s},
                              'example': s.get('examples', [])[:1]} for s in value['sources']],
                 'limitations': value.get('limitations', [])}
    def raw_array(node):
        if isinstance(node, dict):
            return 'zones' in node or any(raw_array(v) for v in node.values())
        return isinstance(node, list) and any(raw_array(v) for v in node)
    if raw_array(value) or len(json.dumps(value, ensure_ascii=False)) > 32000:
        raise ValueError('Supply a compact source summary, not raw arrays (maximum 32000 characters)')
    return value


def part_schema(keys, inventory=False):
    source = contract_schema()
    properties = {k: copy.deepcopy(source['properties'][k]) for k in keys}
    if inventory:
        properties['inventory'] = {'type': 'object', 'additionalProperties': False,
            'required': list(INVENTORY), 'properties': {
                key: {'type': 'array', 'maxItems': 150, 'uniqueItems': True,
                      'minItems': 0 if key in ('schemas', 'events') else 1,
                      'items': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_-]*$'}}
                for key in INVENTORY}}
        properties['context_map'] = {'type': 'object', 'additionalProperties': False,
            'required': ['elements', 'global_question_ids'], 'properties': {
                'global_question_ids': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}},
                'elements': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                    'required': ['section', 'name', 'requirement_ids', 'question_ids'], 'properties': {
                        'section': {'enum': list(INVENTORY)}, 'name': {'type': 'string'},
                        'requirement_ids': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': {'type': 'string'}},
                        'question_ids': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}}}}}}}
    # Include only definitions reachable from this part's shape.
    definitions = {}
    def collect(node):
        if isinstance(node, dict):
            ref = node.get('$ref', '')
            if ref.startswith('#/$defs/'):
                name = ref.split('/')[-1]
                if name not in definitions:
                    definitions[name] = source['$defs'][name]
                    collect(definitions[name])
            for child in node.values(): collect(child)
        elif isinstance(node, list):
            for child in node: collect(child)
    collect(properties)
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False, '$defs': definitions}


def batch_settings(values=None):
    result = {**BATCH_LIMITS, **(values or {})}
    if set(result) != set(BATCH_LIMITS) or any(type(v) is not int or not 1 <= v <= BATCH_LIMITS[k] for k, v in result.items()):
        raise ValueError('Batch sizes must be api/screens=1..2, test_scenarios=1..3')
    return result


def task_names(task):
    value = task[2]
    return () if value is None else (value,) if isinstance(value, str) else value


def tasks(parts, analysis, batch_sizes=None):
    sizes = batch_settings(batch_sizes)
    result = [('architecture', ('boundaries', 'components', 'user_flows'), None)]
    if 'architecture' not in parts:
        return result
    for section in INVENTORY:
        names = parts['architecture']['data']['inventory'][section]
        for start in range(0, len(names), sizes.get(section, 1)):
            group = tuple(names[start:start+sizes.get(section, 1)])
            result.append((f'{section}:{"+".join(group)}', (section,), group[0] if len(group) == 1 else group))
    ids = [fr['id'] for fr in analysis['functional_requirements']]
    for start in range(0, len(ids), sizes['test_scenarios']):
        group = tuple(ids[start:start+sizes['test_scenarios']])
        result.append((f'test_scenarios:{"+".join(group)}', ('test_scenarios',), group[0] if len(group) == 1 else group))
    result.append(('notes', NOTES, None))
    return result


def assemble(parts):
    design = {'schema_version': '2.0', **{k: {} if k == 'schemas' else [] for k in INVENTORY},
              'test_scenarios': []}
    for part in parts.values():
        for key, value in part['data'].items():
            if key in ('inventory', 'context_map'): continue
            if key == 'schemas': design[key].update(copy.deepcopy(value))
            elif key in INVENTORY or key == 'test_scenarios': design[key].extend(copy.deepcopy(value))
            else: design[key] = copy.deepcopy(value)
    return design


def summary(parts, relevant_ids=None):
    design = assemble(parts)
    links = parts.get('architecture', {}).get('data', {}).get('context_map', {}).get('elements', [])
    names = {section: {link['name'] for link in links if link['section'] == section and
                      (relevant_ids is None or set(link['requirement_ids']) & relevant_ids)} for section in INVENTORY}
    if relevant_ids is None:
        names = {section: set(parts.get('architecture', {}).get('data', {}).get('inventory', {}).get(section, [])) for section in INVENTORY}
    for role in design['roles']:
        if any(p['operation_id'] in names['api'] for p in role['permissions']): names['roles'].add(role['id'])
    for op in design['api']:
        if op['operation_id'] in names['api']: names['roles'].update(op['roles'])
    # Keep complete machine constraints for selected values, including referenced
    # schemas/entities. Selection never truncates a string or a schema.
    def references(node):
        if isinstance(node, dict):
            ref = node.get('$ref', '')
            if ref.startswith('#/components/schemas/'): yield ref.rsplit('/', 1)[-1]
            for child in node.values(): yield from references(child)
        elif isinstance(node, list):
            for child in node: yield from references(child)
    while True:
        previous = (set(names['data_model']), set(names['schemas']))
        selected = [e for e in design['data_model'] if e['name'] in names['data_model']]
        selected += [s for n, s in design['schemas'].items() if n in names['schemas']]
        selected += [o for o in design['api'] if o['operation_id'] in names['api']]
        targets = set(references(selected))
        targets.update(r['target_entity'] for e in design['data_model'] if e['name'] in names['data_model'] for r in e['relations'])
        names['data_model'].update(targets & {e['name'] for e in design['data_model']})
        names['schemas'].update(targets & design['schemas'].keys())
        if previous == (names['data_model'], names['schemas']): break
    return {'inventory': parts.get('architecture', {}).get('data', {}).get('inventory', {}),
        'entities': [{'name': e['name'], 'fields': {f['name']: f['schema'] for f in e['fields']},
                      'required': [f['name'] for f in e['fields'] if f['required']],
                      'primary_key': e['primary_key'], 'relations': e['relations'], 'indexes': e['indexes'],
                      'constraints': e.get('constraints', {})} for e in design['data_model'] if e['name'] in names['data_model']],
        'schemas': {name: s for name, s in design['schemas'].items() if name in names['schemas']},
        'roles': [r for r in design['roles'] if r['id'] in names['roles']],
        'operations': [{k: op[k] for k in ('operation_id', 'method', 'path', 'roles', 'requirement_ids')}
                       for op in design['api'] if op['operation_id'] in names['api']]}


def relevant_context(task, inputs, parts):
    if task[0] == 'architecture': return {**inputs, 'technology_profile': TECHNOLOGY_PROFILE}
    analysis = inputs['analysis']
    mapping = parts['architecture']['data']['context_map']
    section = task[1][0]
    links = [link for link in mapping['elements'] if link['section'] == section and link['name'] in task_names(task)]
    ids = set(task_names(task)) if section == 'test_scenarios' else {
        id for link in links for id in link['requirement_ids']}
    if task[0] == 'notes': ids = {fr['id'] for fr in analysis['functional_requirements']}
    if section == 'test_scenarios' or task[0] == 'notes':
        links = [link for link in mapping['elements'] if set(link['requirement_ids']) & ids]
    question_ids = set(mapping['global_question_ids']) | {q for link in links for q in link['question_ids']}
    questions = {q['id']: q for q in analysis.get('questions', [])}
    clarifications = [{'id': qid, 'value': inputs['answers'].get(qid) or questions[qid]['default_assumption'],
                       'origin': 'user_answer' if inputs['answers'].get(qid) else 'unconfirmed_assumption'}
                      for qid in sorted(question_ids)]
    return {'common': {k: analysis[k] for k in ('title', 'purpose', 'scope', 'roles',
                            'nonfunctional_requirements', 'assumptions', 'risks') if k in analysis},
            'technology_profile': TECHNOLOGY_PROFILE,
            'requirements': [{k: value for k, value in fr.items() if k != 'source_quote'}
                             for fr in analysis['functional_requirements'] if fr['id'] in ids],
            'clarifications': clarifications, 'source_summary': inputs['source_summary'],
            'agreed_summary': summary(parts, ids),
            'used_scenario_ids': [test['id'] for test in assemble(parts)['test_scenarios']]}


def validate_part(data, task, parts, analysis):
    from jsonschema import Draft202012Validator
    key, fields, name = task
    issues = [f"{'.'.join(map(str, e.path))}: {e.message}" for e in
              Draft202012Validator(part_schema(fields, key == 'architecture')).iter_errors(data)]
    if issues: return issues[:30]
    inventory = data['inventory'] if key == 'architecture' else parts['architecture']['data']['inventory']
    collisions = set(inventory['data_model']) & set(inventory['schemas'])
    if collisions:
        issues.append('inventory: entity and schema names collide: '+', '.join(sorted(collisions)))
    section = fields[0]
    if name is not None and section in INVENTORY:
        names = list(data[section]) if section == 'schemas' else [v[INVENTORY[section]] for v in data[section]]
        if len(names) != len(set(names)) or set(names) != set(task_names(task)):
            issues.append(f'{key}: return exactly the planned items {list(task_names(task))}, without duplicates')
    expected = {fr['id'] for fr in analysis['functional_requirements']}
    schema_names = inventory['data_model'] + inventory['schemas']
    if key == 'architecture':
        mapping = data['context_map'];links = mapping['elements']
        planned = {(section, name) for section, names in inventory.items() for name in names}
        actual = [(link['section'], link['name']) for link in links]
        if set(actual) != planned or len(actual) != len(set(actual)):
            issues.append('context_map: must map every planned element exactly once')
        if {id for link in links for id in link['requirement_ids']} != expected:
            issues.append('context_map: must cover all FR-ID without unknown requirements')
        question_ids = {q['id'] for q in analysis.get('questions', [])}
        mapped = set(mapping['global_question_ids']) | {q for link in links for q in link['question_ids']}
        if mapped != question_ids:
            issues.append('context_map: must assign every question globally or to elements, without unknown IDs')
    def walk(node, path):
        if isinstance(node, dict):
            if 'requirement_ids' in node and set(node['requirement_ids']) - expected:
                issues.append(f'{path}: unknown FR references')
            for field, target in (('operation_id', 'api'), ('target_entity', 'data_model'), ('entity', 'data_model')):
                if field in node and node[field] not in inventory[target]:
                    issues.append(f'{path}.{field}: unplanned reference {node[field]}')
            if isinstance(node.get('roles'), list) and any(isinstance(r, str) and r not in inventory['roles'] for r in node['roles']):
                issues.append(f'{path}.roles: unknown role')
            for field, child in node.items():
                if field in ('inventory', 'context_map'): continue
                if field == 'schema': issues.extend(validate_value_schema(child, path+'.schema', schema_names))
                elif field == 'schemas':
                    for n, s in child.items(): issues.extend(validate_value_schema(s, n, schema_names))
                else: walk(child, path+'.'+field)
        elif isinstance(node, list):
            for index, child in enumerate(node): walk(child, f'{path}[{index}]')
    walk(data, key)
    if section == 'data_model':
        entity = data[section][0]
        issues.extend(validate_value_schema(entity_schema(entity), name, schema_names))
    if section == 'test_scenarios':
        covered = {id for t in data[section] for id in t['requirement_ids']}
        if covered != set(task_names(task)):
            issues.append(f'{key}: must cover exactly the planned FR-ID {list(task_names(task))}')
        used = {t['id'] for p, value in parts.items() if p != key
                for t in value['data'].get('test_scenarios', [])}
        ids = [t['id'] for t in data[section]]
        if len(ids) != len(set(ids)) or used & set(ids): issues.append(f'{key}: duplicate scenario IDs')
    return issues


class Designer:
    def __init__(self, directory, client, requirements, analysis, answers, context=None,
                 resume=False, ensure_active=lambda: None, event=lambda text: None, batch_sizes=None):
        self.path = Path(directory) / 'design-checkpoint.json'
        self.client, self.ensure_active, self.event = client, ensure_active, event
        self.batch_sizes = batch_settings(batch_sizes)
        inputs = {'requirements': requirements, 'analysis': analysis, 'answers': answers,
                  'source_summary': compact_context(context or {})}
        identity = digest({'inputs': inputs, 'format': contract_schema(), 'revision': REVISION,
                           'system_prompt': SYSTEM_PROMPT, 'batch_sizes': self.batch_sizes,
                           'technology_profile': TECHNOLOGY_PROFILE,
                           'model': getattr(client, 'config', {}).get('model')})
        if resume:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if self.state.get('revision') != REVISION:
                raise ValueError('Incompatible checkpoint planner revision: '+str(self.state.get('revision'))+
                                 '; expected '+REVISION+'. Saved state unchanged; no new run started.')
            if self.state.get('identity') != identity:
                raise ValueError('Incompatible design checkpoint: requirements, analysis, answers, context, model, format or batch sizes changed')
            for task in tasks(self.state['parts'], analysis, self.batch_sizes):
                if task[0] not in self.state['parts']: continue
                part = self.state['parts'][task[0]]
                if part.get('sha256') != digest(part['data']) or validate_part(part['data'], task, self.state['parts'], analysis):
                    raise ValueError('Invalid saved design part: '+task[0])
            expected = {t[0] for t in tasks(self.state['parts'], analysis, self.batch_sizes)}
            if set(self.state['parts']) - expected:
                raise ValueError('Unexpected saved design parts')
            client.calls[:] = copy.deepcopy(self.state['calls'])
            self.state['resumptions'] += 1
        else:
            if self.path.exists(): raise ValueError('Checkpoint already exists; explicitly resume or use a new output directory')
            self.state = {'revision': REVISION, 'identity': identity, 'inputs': inputs,
                'parts': {}, 'attempts': {}, 'calls': copy.deepcopy(client.calls),
                'status': 'designing', 'seconds': 0.0, 'resumptions': 0,
                'origin': 'qwen_generation', 'feedback': {}, 'run_id': uuid.uuid4().hex,
                'validation_history': [], 'batch_sizes': self.batch_sizes}
        if set(answers) - {q['id'] for q in analysis.get('questions', [])}:
            raise ValueError('Unknown clarification IDs; cannot safely select context')
        self.save()

    def save(self):
        inventory = self.state['parts'].get('architecture', {}).get('data', {}).get('inventory', {})
        design = assemble(self.state['parts'])
        completed = {section: set(design[section]) if field is None else {v[field] for v in design[section]}
                     for section, field in INVENTORY.items()}
        self.state['deferred_references'] = [f'{section}:{name}' for section, names in inventory.items()
            for name in names if name not in completed[section]]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        temporary.replace(self.path)

    def request(self, task):
        key, fields, name = task
        context = relevant_context(task, self.state['inputs'], self.state['parts'])
        if len(json.dumps(context.get('agreed_summary', {}), ensure_ascii=False)) > 32000:
            raise ValueError('Agreed summary exceeds 32000 characters; explicit plan review required')
        instructions = (
            'Составь только указанный пакет спецификации v2.0. Один JSON-объект, не полный design.json. '
            'Сохрани стабильные имена inventory и FR-ID. Ссылки на запланированные будущие элементы допустимы. '
            'Имена сущностей УЖЕ входят в пространство components.schemas: '
            'НЕ повторяй их в inventory.schemas, там только дополнительные DTO с другими именами. '
            'На архитектурном шаге сформируй context_map: каждый элемент inventory ровно один раз, '
            'с релевантными FR-ID и вопросами. Покрой все FR и все вопросы; сквозные уточнения '
            'вынеси в global_question_ids. Учитывай все влияющие бизнес-правила и права. '
            'Для других пакетов верни ВСЕ items и только их, без дубликатов. '
            'Для сценариев покрой ровно указанные FR-ID; не повторяй used_scenario_ids. '
            'Используй TC-<номер первого FR пакета><двузначный номер сценария>, например TC-00401 для FR-004. '
            'Роли и API согласуй по operation_id; защищённым API нужны 401/403. '
            'Все значения типизированы JSON Schema 2020-12; $ref только #/components/schemas/Name. '
            'Для экранов loading/error/empty/forbidden/ready. '
            'Численные проектные решения — assumptions, неопределённости — open_questions. '
            'Технический профиль — конфигурация конкурса. PWA только при требовании мобильного интерфейса. '
            'Код и испытания приложения не выполнялись.\n')
        payload = {'part': key, 'items': list(task_names(task)),
                   'response_schema': part_schema(fields, key == 'architecture'),
                   **context, 'corrections': self.state['feedback'].get(key, [])}
        return instructions + json.dumps(payload, ensure_ascii=False, separators=(',', ':')), {'instructions': instructions, **payload}

    def prompt(self, task):
        return self.request(task)[0]

    def generate_part(self, task):
        key = task[0]
        while self.state['attempts'].get(key, 0) < 2:
            self.ensure_active()
            attempt = self.state['attempts'].get(key, 0) + 1
            prompt, blocks = self.request(task)
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': prompt}]
            measurements = request_sizes(messages, blocks)
            self.state.update(status='designing', current_part=key)
            self.state['attempts'][key] = attempt
            # Persist intent before sending: an interrupted request has unknown usage.
            self.state['calls'].append({'stage': 'Design/'+key, 'attempt': attempt, 'status': 'interrupted_or_pending',
                'input_tokens': None, 'output_tokens': None, 'seconds': None,
                'message_content_size': None, 'parsed_json_size': None, 'reasoning_prefix_size': None,
                'usage_numeric': None, 'finish_reason': None, 'rate_limit_headers': None,
                **measurements})
            self.save()
            count = len(self.client.calls)
            self.event(f'Проектирование {key}: попытка {attempt}/2')
            started = time.monotonic()
            try:
                content = self.client.complete(messages, 'Design/'+key, attempt)
                if len(self.client.calls) > count:
                    self.client.calls[-1].update(content_sizes(content))
                self.ensure_active()
                try:
                    data = parse_json(content)
                    if len(self.client.calls) > count: self.client.calls[-1]['parsed_json_size'] = size(data)
                    issues = validate_part(data, task, self.state['parts'], self.state['inputs']['analysis'])
                except (ValueError, TypeError, RecursionError):
                    issues = ['Invalid JSON object']
                if len(self.client.calls) > count:
                    self.client.calls[-1].update(validation_status='error' if issues else 'ok', validation_issues=len(issues))
                if not issues:
                    self.state['parts'][key] = {'data': data, 'sha256': digest(data), 'origin': 'qwen_generation',
                                               'call_index': len(self.state['calls'])-1, 'attempt': attempt}
                    self.state['feedback'].pop(key, None)
                    return
                self.state['feedback'][key] = issues[:30]
                self.state['validation_history'].append({'part': key, 'attempt': attempt,
                                                         'scope': 'part', 'issues': issues[:30]})
            finally:
                self.state['seconds'] += time.monotonic() - started
                if len(self.client.calls) > count:
                    for call in self.client.calls[count:]:
                        call.update(measurements)
                        for field in ('message_content_size', 'parsed_json_size', 'reasoning_prefix_size',
                                      'usage_numeric', 'finish_reason', 'rate_limit_headers'):
                            call.setdefault(field, None)
                    self.state['calls'][-1:] = copy.deepcopy(self.client.calls[count:])
                self.save()
        raise ValueError('Part exhausted its two attempts: '+key+'; '+'; '.join(self.state['feedback'].get(key, [])[:8]))

    def owner(self, issue, design):
        label = issue.split(':', 1)[0]
        candidates = []
        for task in tasks(self.state['parts'], self.state['inputs']['analysis'], self.batch_sizes):
            key, fields, name = task
            if any(label == n or label.startswith(n+'.') for n in task_names(task)): candidates.append(task)
            for field in fields:
                if label == field and name is None: candidates.append(task)
                if field == 'schemas' and any(label.startswith('schemas.'+n) for n in task_names(task)): candidates.append(task)
                match = re.match(r'^'+re.escape(field)+r'\.(\d+)(?:\.|$)', label)
                if match and name and field != 'schemas':
                    item = design[field][int(match[1])]
                    if field == 'test_scenarios':
                        if set(task_names(task)) & set(item['requirement_ids']): candidates.append(task)
                    elif item[INVENTORY[field]] in task_names(task): candidates.append(task)
        candidates = {task[0]: task for task in candidates}
        return next(iter(candidates.values())) if len(candidates) == 1 else None

    def run(self):
        try:
            while True:
                for task in tasks(self.state['parts'], self.state['inputs']['analysis'], self.batch_sizes):
                    if task[0] not in self.state['parts']: self.generate_part(task)
                if 'notes' not in self.state['parts']: continue  # Architecture established the plan.
                design = assemble(self.state['parts'])
                issues = validate_design(design, self.state['inputs']['analysis'])
                self.state['final_issues'] = issues
                if not issues:
                    self.state.update(status='complete', deferred_references=[])
                    self.save()
                    return design
                owners = {}
                for issue in issues:
                    task = self.owner(issue, design)
                    if task is None: raise ValueError('Final contract validation requires review: '+'; '.join(issues[:10]))
                    owners.setdefault(task[0], (task, []))[1].append(issue)
                for key, (task, feedback) in owners.items():
                    self.state['validation_history'].append({'part': key, 'scope': 'assembled_contract', 'issues': feedback})
                    call = self.state['calls'][self.state['parts'][key]['call_index']]
                    call.update(final_validation_status='error', final_validation_issues=len(feedback))
                    self.state['feedback'][key] = feedback
                    if self.state['attempts'][key] >= 2:
                        raise ValueError('Final validation failed; repair budget exhausted: '+key)
                    self.state['parts'].pop(key)
                    self.save()
                    self.generate_part(task)
        except Exception:
            self.state['status'] = 'failed'
            self.save()
            raise
