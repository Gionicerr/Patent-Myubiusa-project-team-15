"""Sequential Qwen design parts, durable checkpoints, unchanged v2 output."""
import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from .contracts import SYSTEM_PROMPT, parse_json, validate_design
from .specifications import contract_schema, entity_schema, validate_value_schema

REVISION = 'design-parts-1'
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


def tasks(parts, analysis):
    result = [('architecture', ('boundaries', 'components', 'user_flows'), None)]
    if 'architecture' not in parts:
        return result
    for section in INVENTORY:
        for name in parts['architecture']['data']['inventory'][section]:
            result.append((f'{section}:{name}', (section,), name))
    result.extend((f'test_scenarios:{fr["id"]}', ('test_scenarios',), fr['id'])
                  for fr in analysis['functional_requirements'])
    result.append(('notes', NOTES, None))
    return result


def assemble(parts):
    design = {'schema_version': '2.0', **{k: {} if k == 'schemas' else [] for k in INVENTORY},
              'test_scenarios': []}
    for part in parts.values():
        for key, value in part['data'].items():
            if key == 'inventory': continue
            if key == 'schemas': design[key].update(copy.deepcopy(value))
            elif key in INVENTORY or key == 'test_scenarios': design[key].extend(copy.deepcopy(value))
            else: design[key] = copy.deepcopy(value)
    return design


def summary(parts):
    design = assemble(parts)
    def short(schema):
        return {k: schema[k] for k in ('type', '$ref', 'enum', 'format', 'required') if k in schema}
    return {'inventory': parts.get('architecture', {}).get('data', {}).get('inventory', {}),
        'entities': [{'name': e['name'], 'fields': {f['name']: short(f['schema']) for f in e['fields']},
                      'primary_key': e['primary_key']} for e in design['data_model']],
        'schemas': {name: {**short(s), 'properties': {k: short(v) for k, v in s.get('properties', {}).items()}}
                    for name, s in design['schemas'].items()},
        'roles': design['roles'],
        'operations': [{k: op[k] for k in ('operation_id', 'method', 'path', 'roles', 'requirement_ids')}
                       for op in design['api']]}


def validate_part(data, task, parts, analysis):
    from jsonschema import Draft202012Validator
    key, fields, name = task
    issues = [f"{'.'.join(map(str, e.path))}: {e.message}" for e in
              Draft202012Validator(part_schema(fields, key == 'architecture')).iter_errors(data)]
    if issues: return issues[:30]
    inventory = data['inventory'] if key == 'architecture' else parts['architecture']['data']['inventory']
    if set(inventory['data_model']) & set(inventory['schemas']):
        issues.append('inventory: entity and schema names collide')
    section = fields[0]
    if name is not None and section in INVENTORY:
        names = list(data[section]) if section == 'schemas' else [v[INVENTORY[section]] for v in data[section]]
        if names != [name]: issues.append(f'{key}: return exactly the planned item {name}')
    expected = {fr['id'] for fr in analysis['functional_requirements']}
    schema_names = inventory['data_model'] + inventory['schemas']
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
                if field == 'inventory': continue
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
        if not any(name in t['requirement_ids'] for t in data[section]):
            issues.append(f'{key}: must cover {name}')
        used = {t['id'] for p, value in parts.items() if p != key
                for t in value['data'].get('test_scenarios', [])}
        ids = [t['id'] for t in data[section]]
        if len(ids) != len(set(ids)) or used & set(ids): issues.append(f'{key}: duplicate scenario IDs')
    return issues


class Designer:
    def __init__(self, directory, client, requirements, analysis, answers, context=None,
                 resume=False, ensure_active=lambda: None, event=lambda text: None):
        self.path = Path(directory) / 'design-checkpoint.json'
        self.client, self.ensure_active, self.event = client, ensure_active, event
        inputs = {'requirements': requirements, 'analysis': analysis, 'answers': answers,
                  'source_summary': compact_context(context or {})}
        identity = digest({'inputs': inputs, 'format': contract_schema(), 'revision': REVISION,
                           'system_prompt': SYSTEM_PROMPT,
                           'model': getattr(client, 'config', {}).get('model')})
        if resume:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if self.state.get('identity') != identity or self.state.get('revision') != REVISION:
                raise ValueError('Incompatible design checkpoint: requirements, analysis, answers, context, model or format changed')
            for task in tasks(self.state['parts'], analysis):
                if task[0] not in self.state['parts']: continue
                part = self.state['parts'][task[0]]
                if part.get('sha256') != digest(part['data']) or validate_part(part['data'], task, self.state['parts'], analysis):
                    raise ValueError('Invalid saved design part: '+task[0])
            expected = {t[0] for t in tasks(self.state['parts'], analysis)}
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
                'validation_history': []}
        self.save()

    def save(self):
        inventory = self.state['parts'].get('architecture', {}).get('data', {}).get('inventory', {})
        self.state['deferred_references'] = [f'{section}:{name}' for section, names in inventory.items()
            for name in names if f'{section}:{name}' not in self.state['parts']]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        temporary.replace(self.path)

    def prompt(self, task):
        key, fields, name = task
        inputs = self.state['inputs']
        context = summary(self.state['parts'])
        if len(json.dumps(context, ensure_ascii=False)) > 32000:
            raise ValueError('Agreed summary exceeds 32000 characters; explicit plan review required')
        return ('Составь только указанную часть спецификации v2.0. Один JSON-объект. '
            'Не возвращай полный design.json. Сохрани стабильные имена inventory и FR-ID. '
            'inventory перечисляет будущие элементы; ссылки на них допустимы, новые имена запрещены. '
            'Роли и API согласуй по operation_id; защищённым API нужны 401/403. '
            'JSON Schema 2020-12: все значения типизированы, $ref только #/components/schemas/Name; '
            'имена сущностей также являются схемами. Состояния экранов loading/error/empty/forbidden/ready. '
            'Численные решения — допущения, внешние неопределённости — open_questions. '
            'Angular20.1.6/PWA/Material, ASP.NET Core .NET10 C#14, PostgreSQL17.9; PostGIS при геоданных. '
            'Kafka только с обоснованием. Код и проверки приложения не выполнялись. '
            'На архитектурном шаге спланируй минимальный inventory; на остальных верни ровно один '
            'элемент с указанным именем. Для сценариев верни небольшую группу по данному FR, '
            'используй TC-<номер FR><двузначный номер сценария>, чтобы ID не повторялись.\n'
            + json.dumps({'part': key, 'item': name, 'response_schema': part_schema(fields, key == 'architecture'),
                **inputs, 'agreed_summary': context, 'corrections': self.state['feedback'].get(key, [])},
                ensure_ascii=False, separators=(',', ':')))

    def generate_part(self, task):
        key = task[0]
        while self.state['attempts'].get(key, 0) < 2:
            self.ensure_active()
            attempt = self.state['attempts'].get(key, 0) + 1
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': self.prompt(task)}]
            self.state.update(status='designing', current_part=key)
            self.state['attempts'][key] = attempt
            # Persist intent before sending: an interrupted request has unknown usage.
            self.state['calls'].append({'stage': 'Design/'+key, 'attempt': attempt, 'status': 'interrupted_or_pending',
                'input_tokens': None, 'output_tokens': None, 'seconds': None})
            self.save()
            count = len(self.client.calls)
            self.event(f'Проектирование {key}: попытка {attempt}/2')
            started = time.monotonic()
            try:
                content = self.client.complete(messages, 'Design/'+key, attempt)
                self.ensure_active()
                try:
                    data = parse_json(content)
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
                    self.state['calls'][-1:] = copy.deepcopy(self.client.calls[count:])
                self.save()
        raise ValueError('Part exhausted its two attempts: '+key+'; '+'; '.join(self.state['feedback'].get(key, [])[:8]))

    def owner(self, issue, design):
        label = issue.split(':', 1)[0]
        candidates = []
        for task in tasks(self.state['parts'], self.state['inputs']['analysis']):
            key, fields, name = task
            if name and (label == name or label.startswith(name+'.')): candidates.append(task)
            for field in fields:
                if label == field and name is None: candidates.append(task)
                if field == 'schemas' and name and label.startswith('schemas.'+name): candidates.append(task)
                match = re.match(r'^'+re.escape(field)+r'\.(\d+)(?:\.|$)', label)
                if match and name and field != 'schemas':
                    item = design[field][int(match[1])]
                    if field == 'test_scenarios':
                        if name in item['requirement_ids']: candidates.append(task)
                    elif item[INVENTORY[field]] == name: candidates.append(task)
        candidates = {task[0]: task for task in candidates}
        return next(iter(candidates.values())) if len(candidates) == 1 else None

    def run(self):
        try:
            while True:
                for task in tasks(self.state['parts'], self.state['inputs']['analysis']):
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
