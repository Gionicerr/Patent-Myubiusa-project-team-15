"""Versioned, domain-neutral contracts and deterministic OpenAPI generation."""
import copy
import json
import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'schemas' / 'design-v2.schema.json'
METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}


def contract_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))


def entity_schema(entity):
    schema = {'type': 'object', 'additionalProperties': False,
              'properties': {f['name']: copy.deepcopy(f['schema']) for f in entity['fields']},
              'required': [f['name'] for f in entity['fields'] if f['required']]}
    schema.update(copy.deepcopy(entity.get('constraints', {})))
    return schema


def build_openapi(design, title='Generated application'):
    schemas = copy.deepcopy(design['schemas'])
    schemas.update({e['name']: entity_schema(e) for e in design['data_model']})
    paths = {}
    for op in design['api']:
        value = {'operationId': op['operation_id'], 'summary': op['summary'],
                 'x-requirement-ids': op['requirement_ids'], 'x-roles': op['roles'],
                 'parameters': copy.deepcopy(op['parameters']), 'responses': {}}
        if op['roles']:
            value['security'] = [{'bearerAuth': []}]
        else:
            value['security'] = []
        if op['request_body'] is not None:
            value['requestBody'] = {'required': op['request_body']['required'],
                                    'content': {'application/json': {'schema': copy.deepcopy(op['request_body']['schema'])}}}
        for response in op['responses']:
            item = {'description': response['description']}
            if response['schema'] is not None:
                item['content'] = {'application/json': {'schema': copy.deepcopy(response['schema'])}}
            value['responses'][response['status']] = item
        paths.setdefault(op['path'], {})[op['method'].lower()] = value
    return {'openapi': '3.1.0', 'info': {'title': title, 'version': '2.0.0'},
            'paths': paths, 'components': {'schemas': schemas, 'securitySchemes': {
                'bearerAuth': {'type': 'http', 'scheme': 'bearer'}}}}


def validate_contract(design, analysis):
    from jsonschema import Draft202012Validator
    issues = [f"{'.'.join(map(str, e.path))}: {e.message}" for e in
              Draft202012Validator(contract_schema()).iter_errors(design)]
    if issues:
        return issues[:100]
    expected = {fr['id'] for fr in analysis['functional_requirements']}
    def unique(items, label):
        if len(items) != len(set(items)):
            issues.append(f'{label}: duplicate identifiers')
    def refs(items, label):
        unknown = set(items) - expected
        if unknown:
            issues.append(f'{label}: unknown FR references {sorted(unknown)}')
    entities = {e['name']: e for e in design['data_model']}
    unique([e['name'] for e in design['data_model']], 'entities')
    if set(entities) & set(design['schemas']):
        issues.append('Entity and reusable schema names collide')
    all_schemas = {**design['schemas'], **{n: entity_schema(e) for n, e in entities.items()}}
    def check_schema(schema, label):
        if schema is None:
            return
        try:
            Draft202012Validator.check_schema(schema)
        except Exception:
            issues.append(f'{label}: invalid JSON Schema')
            return
        def walk(value, path, require_type=True, inherited=None, predicate=False):
            # Only schema-bearing keywords contain schemas; examples/const and
            # keyword maps are data, not independently typed value descriptions.
            if isinstance(value, dict):
                context = inherited if isinstance(inherited, dict) else {}
                if require_type and not any(k in value or k in context for k in
                        ('type', '$ref', 'oneOf', 'anyOf', 'allOf', 'enum', 'const')):
                    issues.append(f'{path}: schema must declare a machine-readable type/reference')
                ref = value.get('$ref')
                if ref is not None and (not isinstance(ref, str) or not ref.startswith('#/components/schemas/') or ref.split('/')[-1] not in all_schemas):
                    issues.append(f'{path}: unresolved or external schema reference')
                if value.get('additionalProperties') is False and value.get('type', context.get('type')) == 'object':
                    for name in value.get('required', []):
                        if name not in value.get('properties', {}) and not any(
                                re.search(pattern, name) for pattern in value.get('patternProperties', {})):
                            issues.append(f'{path}.required: {name!r} is required but forbidden by additionalProperties=false')
                types = value.get('type', [])
                if (types == 'array' or isinstance(types, list) and 'array' in types) and not any(
                        k in value or k in context for k in ('items', 'prefixItems', '$ref', 'allOf', 'anyOf', 'oneOf')):
                    issues.append(f'{path}: array items must be typed')
                inherited = context
                context = {**context, **value}
                properties = dict(inherited.get('properties', {}))
                for branch in value.get('allOf', []):
                    if isinstance(branch, dict):
                        for name, child in branch.get('properties', {}).items():
                            if isinstance(child, dict):
                                previous = properties.get(name, {})
                                properties[name] = {**(previous if isinstance(previous, dict) else {}), **child}
                for name, child in value.get('properties', {}).items():
                    if isinstance(child, dict):
                        previous = properties.get(name, {})
                        properties[name] = {**(previous if isinstance(previous, dict) else {}), **child}
                context['properties'] = properties
                for keyword in ('properties', 'patternProperties', '$defs', 'definitions'):
                    for name, child in value.get(keyword, {}).items():
                        previous = context.get(keyword, {}).get(name)
                        walk(child, f'{path}.{keyword}.{name}', not predicate, previous, predicate)
                for keyword in ('items', 'additionalProperties', 'contains', 'propertyNames',
                                'unevaluatedProperties', 'unevaluatedItems', 'contentSchema'):
                    if keyword in value:
                        walk(value[keyword], f'{path}.{keyword}', not predicate, inherited.get(keyword), predicate)
                for index, child in enumerate(value.get('prefixItems', [])):
                    previous = inherited.get('prefixItems', [])
                    walk(child, f'{path}.prefixItems[{index}]', not predicate,
                         previous[index] if index < len(previous) else None, predicate)
                for keyword in ('oneOf', 'anyOf', 'allOf'):
                    for index, child in enumerate(value.get(keyword, [])):
                        walk(child, f'{path}.{keyword}[{index}]', False, context, predicate)
                for keyword in ('if', 'then', 'else', 'not'):
                    if keyword in value:
                        walk(value[keyword], f'{path}.{keyword}', False, context, predicate or keyword in ('if', 'not'))
                for name, child in value.get('dependentSchemas', {}).items():
                    walk(child, f'{path}.dependentSchemas.{name}', False, context)
        walk(schema, label)
    for entity in design['data_model']:
        check_schema(entity_schema(entity), entity['name'])
        fields = {f['name']: f for f in entity['fields']}
        unique([f['name'] for f in entity['fields']], entity['name'] + '.fields')
        for field in fields.values(): check_schema(field['schema'], entity['name'] + '.' + field['name'])
        for name in entity['primary_key']:
            if name not in fields or not fields[name]['required']:
                issues.append(f"{entity['name']}: primary key must reference required fields")
        unique([x['name'] for x in entity['indexes']], entity['name'] + '.indexes')
        for index in entity['indexes']:
            if index.get('predicate') and index['predicate']['field'] not in fields: issues.append(f"{entity['name']}: index predicate references unknown field")
            if set(index['fields']) - set(fields): issues.append(f"{entity['name']}: index references unknown fields")
        for relation in entity['relations']:
            target = entities.get(relation['target_entity'])
            target_fields = {} if target is None else {f['name']: f for f in target['fields']}
            if relation['field'] not in fields or relation['target_field'] not in target_fields:
                issues.append(f"{entity['name']}: unresolved entity relation")
            else:
                source_type = fields[relation['field']]['schema'].get('type')
                target_type = target_fields[relation['target_field']]['schema'].get('type')
                if isinstance(source_type, list): source_type = next((t for t in source_type if t != 'null'), None)
                if isinstance(target_type, list): target_type = next((t for t in target_type if t != 'null'), None)
                if fields[relation['field']]['schema'].get('format') != target_fields[relation['target_field']]['schema'].get('format'):
                    issues.append(f"{entity['name']}: foreign key format mismatch")
                if source_type != target_type: issues.append(f"{entity['name']}: foreign key type mismatch")
                if relation['on_delete'] == 'SET NULL' and 'null' not in fields[relation['field']]['schema'].get('type', []):
                    issues.append(f"{entity['name']}: SET NULL requires nullable field")
                target_key = relation['target_field']
                if [target_key] != target['primary_key'] and not any(i['unique'] and i['fields'] == [target_key] for i in target['indexes']):
                    issues.append(f"{entity['name']}: FK target must be uniquely indexed")
    for name, schema in design['schemas'].items(): check_schema(schema, name)
    operations = {o['operation_id']: o for o in design['api']}
    unique([o['operation_id'] for o in design['api']], 'operations')
    unique([o['method'] + ' ' + o['path'] for o in design['api']], 'routes')
    role_ids = {r['id'] for r in design['roles']}
    unique([r['id'] for r in design['roles']], 'roles')
    for role in design['roles']:
        unique([p['operation_id'] for p in role['permissions']], role['id'] + '.permissions')
        for p in role['permissions']:
            if p['operation_id'] not in operations or role['id'] not in operations[p['operation_id']]['roles']:
                issues.append(f"{role['id']}: permission has no matching operation/role")
    for op in design['api']:
        refs(op['requirement_ids'], op['operation_id'])
        if set(op['roles']) - role_ids: issues.append(f"{op['operation_id']}: unknown role")
        for role in design['roles']:
            if role['id'] in op['roles'] and not any(p['operation_id'] == op['operation_id'] for p in role['permissions']):
                issues.append(f"{op['operation_id']}: missing permission grant")
        path_params = re.findall(r'\{([^{}]+)\}', op['path'])
        if set(path_params) != {p['name'] for p in op['parameters'] if p['in'] == 'path'}:
            issues.append(f"{op['operation_id']}: path parameters mismatch")
        unique([p['in'] + ':' + p['name'] for p in op['parameters']], op['operation_id'] + '.parameters')
        for param in op['parameters']:
            if param['in'] == 'path' and not param['required']: issues.append('Path parameters must be required')
            check_schema(param['schema'], op['operation_id'] + '.parameter')
        if op['request_body']: check_schema(op['request_body']['schema'], op['operation_id'] + '.body')
        codes = [r['status'] for r in op['responses']]
        unique(codes, op['operation_id'] + '.responses')
        if not any(c.startswith('2') for c in codes): issues.append(f"{op['operation_id']}: missing success response")
        if op['roles'] and not {'401', '403'} <= set(codes): issues.append(f"{op['operation_id']}: missing access errors")
        for response in op['responses']: check_schema(response['schema'], op['operation_id'] + '.response')
    unique([s['id'] for s in design['screens']], 'screens')
    for screen in design['screens']:
        refs(screen['requirement_ids'], screen['id'])
        if set(screen['roles']) - role_ids: issues.append(f"{screen['id']}: unknown role")
        for action in screen['actions']:
            if action['operation_id'] not in operations: issues.append(f"{screen['id']}: unknown action operation")
            elif not set(screen['roles']) & set(operations[action['operation_id']]['roles']): issues.append(f"{screen['id']}: action is inaccessible to screen roles")
        for display in screen['display_fields']:
            if display['entity'] not in entities or set(display['fields']) - {f['name'] for f in entities[display['entity']]['fields']}:
                issues.append(f"{screen['id']}: unknown display entity/field")
    unique([e['name'] for e in design['events']], 'events')
    for event in design['events']:
        check_schema(event['schema'], event['name'])
        if event['name'] in all_schemas and event['schema'] != all_schemas[event['name']]:
            issues.append(f"{event['name']}: event schema differs from API/entity schema")
        fields = set(event['schema'].get('properties', {}))
        required = set(event['schema'].get('required', []))
        if not {event['id_field'], event['time_field'], *event['idempotency_key']} <= fields & required:
            issues.append(f"{event['name']}: event identity/time/deduplication fields must exist and be required")
        refs(event['requirement_ids'], event['name'])
    covered = set()
    unique([t['id'] for t in design['test_scenarios']], 'scenarios')
    for test in design['test_scenarios']:
        refs(test['requirement_ids'], test['id']); covered.update(test['requirement_ids'])
        if set(test['operation_ids']) - set(operations): issues.append(f"{test['id']}: unknown operation")
    if expected - covered: issues.append('Missing acceptance scenarios: ' + ', '.join(sorted(expected - covered)))
    for flow in design['user_flows']: refs(flow['requirement_ids'], 'user_flows')
    if not issues:
        try:
            from openapi_spec_validator import validate
            validate(build_openapi(design, analysis['title']))
        except Exception as exc:
            issues.append('OpenAPI validation: ' + type(exc).__name__)
    return issues


def legacy_view(design):
    """Render both versions without inventing structured types for legacy prose."""
    if design.get('schema_version') != '2.0': return design
    d = copy.deepcopy(design)
    d['data_model'] = [{'entity': e['name'], 'fields': [f"{f['name']}: {json.dumps(f['schema'], ensure_ascii=False)}; required={f['required']} — {f['description']}" for f in e['fields']],
                        'relations': [json.dumps(r, ensure_ascii=False) for r in e['relations']]} for e in design['data_model']]
    d['api'] = [{'method': o['method'], 'path': o['path'], 'description': o['summary'],
                 'request': json.dumps({'parameters': o['parameters'], 'body': o['request_body']}, ensure_ascii=False),
                 'response': json.dumps(o['responses'], ensure_ascii=False), 'auth': ', '.join(o['roles']),
                 'requirement_ids': o['requirement_ids']} for o in design['api']]
    d['events'] = [{'name': e['name'], 'schema': json.dumps(e['schema'], ensure_ascii=False),
                    'delivery': e['delivery'] + '; dedup=' + ','.join(e['idempotency_key'])} for e in design['events']]
    return d


def validate_openapi_document(design, analysis, document):
    if document != build_openapi(design, analysis['title']):
        return ['OpenAPI differs from structured API/data contracts']
    try:
        from openapi_spec_validator import validate
        validate(document)
    except Exception as exc:
        return ['OpenAPI validation: ' + type(exc).__name__]
    return []


def require_validation_tools():
    try:
        import jsonschema
        import openapi_spec_validator
    except ImportError:
        raise ValueError('Install contract dependencies with python -m pip install -r requirements.txt') from None
