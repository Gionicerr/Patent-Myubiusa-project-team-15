"""Programmatic source inspection. No model calls and no tariff conversion."""
import collections
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

REQUIRED_FIELDS = ('externalZoneId', 'displayName', 'geometry', 'price', 'priceDescription',
                   'minTime', 'timeStep', 'tariff', 'entityState', 'initDate', 'lastSyncedAt')


def type_name(value):
    if value is None: return 'null'
    if isinstance(value, bool): return 'boolean'
    if isinstance(value, int): return 'integer'
    if isinstance(value, float): return 'number'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    return 'object'


def inspect_source(path):
    from shapely import from_wkt, get_coordinates
    from shapely.validation import explain_validity
    path = Path(path); raw = path.read_bytes(); source = json.loads(raw)
    data = source.get('data') if isinstance(source, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get('zones'), list) or not isinstance(data.get('city'), str):
        raise ValueError('Expected data.city and data.zones array')
    rows = data['zones']; kinds = collections.Counter(); children = collections.Counter()
    fields = {name: collections.Counter() for name in REQUIRED_FIELDS}
    tariff_types = collections.Counter(); period_types = collections.defaultdict(collections.Counter)
    period_keys = collections.Counter(); states = collections.Counter(); ids = collections.Counter()
    problems = collections.Counter(); samples = []; collections_detail = []
    bounds = [math.inf, math.inf, -math.inf, -math.inf]; geometry_hashes = collections.Counter()
    points = 0; lon_lat_valid = True; reversed_valid = True
    period_lengths = collections.Counter(); vehicle_types = collections.Counter(); numeric_ranges = {}
    problem_examples = []
    def problem(code, index, detail):
        problems[code] += 1
        if len(problem_examples) < 30: problem_examples.append({'row': index, 'externalZoneId': rows[index].get('externalZoneId') if isinstance(rows[index], dict) else None, 'code': code, 'detail': detail})
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problem('non_object', index, 'Object expected'); continue
        for name in REQUIRED_FIELDS:
            if name not in row: problem('missing_field', index, name)
            else: fields[name][type_name(row[name])] += 1
        key = row.get('externalZoneId')
        if not isinstance(key, str) or not key.strip(): problem('invalid_source_identifier', index, 'externalZoneId must be nonempty string')
        else: ids[key] += 1
        states[str(row.get('entityState'))] += 1
        wkt = row.get('geometry')
        try:
            if not isinstance(wkt, str): raise ValueError('WKT string expected')
            g = from_wkt(wkt); kinds[g.geom_type.upper()] += 1
            geometry_hashes[hashlib.sha256(wkt.encode()).hexdigest()] += 1
            if g.is_empty: problem('empty_geometry', index, g.geom_type)
            if not g.is_valid: problem('invalid_geometry', index, explain_validity(g))
            if g.geom_type == 'GeometryCollection':
                members = [part.geom_type.upper() for part in g.geoms]; children.update(members)
                collections_detail.append({'externalZoneId': key, 'members': members, 'wkt': wkt})
            coordinates = get_coordinates(g)
            for x, y in coordinates:
                points += 1
                if not math.isfinite(x) or not math.isfinite(y):
                    lon_lat_valid = reversed_valid = False
                    problem('nonfinite_coordinate', index, 'Coordinate is not finite'); continue
                bounds = [min(bounds[0], x), min(bounds[1], y), max(bounds[2], x), max(bounds[3], y)]
                lon_lat_valid = lon_lat_valid and -180 <= x <= 180 and -90 <= y <= 90
                reversed_valid = reversed_valid and -180 <= y <= 180 and -90 <= x <= 90
        except Exception as exc:
            problem('unparseable_wkt', index, type(exc).__name__)
        tariff = row.get('tariff'); tariff_types[type_name(tariff)] += 1
        if not isinstance(tariff, dict) or not isinstance(tariff.get('periods'), list):
            problem('invalid_tariff_structure', index, 'Expected tariff object with periods array')
        else:
            period_types['tariff.hasHolidays'][type_name(tariff.get('hasHolidays'))] += 1
            periods = tariff['periods']; period_lengths[len(periods)] += 1
            canonical = [json.dumps(p, sort_keys=True) for p in periods]
            if len(canonical) != len(set(canonical)): problem('duplicate_tariff_period', index, 'Exact duplicate periods')
            for period in periods:
                if not isinstance(period, dict): problem('invalid_tariff_period', index, 'Period object expected'); continue
                if set(('from','to','duration','price','type')) - set(period): problem('missing_tariff_period_field', index, 'Period fields missing')
                period_keys.update(period.keys())
                for name, value in period.items():
                    period_types['tariff.periods[].' + name][type_name(value)] += 1
                    if type(value) in (int, float):
                        label = 'tariff.periods[].' + name
                        if label not in numeric_ranges: numeric_ranges[label] = [value, value]
                        numeric_ranges[label] = [min(numeric_ranges[label][0], value), max(numeric_ranges[label][1], value)]
                vehicle_types[str(period.get('type'))] += 1
        try:
            init = datetime.fromisoformat(row['initDate'].replace('Z', '+00:00'))
            synced = datetime.fromisoformat(row['lastSyncedAt'].replace('Z', '+00:00'))
            if init > synced: problem('timestamp_order', index, 'initDate after lastSyncedAt')
        except (ValueError, TypeError, KeyError, AttributeError): problem('invalid_timestamp', index, 'ISO timestamp expected')
        if len(samples) < 2:
            sample = dict(row)
            if isinstance(sample.get('geometry'), str) and len(sample['geometry']) > 300: sample['geometry'] = sample['geometry'][:300] + ' [truncated example]'
            samples.append(sample)
    duplicate_ids = {key: n for key, n in ids.items() if n > 1}
    return {'file': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'city': data.get('city'), 'objects': len(rows), 'geometry_types': dict(kinds),
            'geometry_collection_members': dict(children), 'geometry_collections': collections_detail,
            'coordinate_count': points, 'xy_bounds': bounds if points and all(math.isfinite(v) for v in bounds) else None,
            'coordinates_fit_lon_lat_ranges': bool(points and lon_lat_valid), 'coordinates_fit_lat_lon_ranges': bool(points and reversed_valid),
            'crs_note': 'WKT has no SRID. EPSG:4326 and x=longitude,y=latitude are assumptions; ranges alone do not prove CRS or order.',
            'field_types': {k: dict(v) for k, v in fields.items()}, 'entity_states': dict(states),
            'duplicate_identifiers': duplicate_ids, 'repeated_geometry_strings': sum(n - 1 for n in geometry_hashes.values() if n > 1),
            'tariff': {'types': dict(tariff_types), 'nested_types': {k: dict(v) for k, v in period_types.items()},
                       'period_field_counts': dict(period_keys), 'periods_per_object': dict(period_lengths),
                       'vehicle_types': dict(vehicle_types), 'raw_numeric_ranges': numeric_ranges,
                       'interpretation': 'Raw values retained; currency subunits, time units, holiday/calendar and overlapping-period semantics are unconfirmed.'},
            'problem_counts': dict(problems), 'problem_examples': problem_examples, 'examples': samples}


def inspect_sources(paths, regions=None):
    reports = [inspect_source(p) for p in paths]
    for report in reports:
        box = (regions or {}).get(report['city'])
        if box and report['xy_bounds']:
            x1,y1,x2,y2=report['xy_bounds']
            contains=lambda a,b,c,d: box[0]<=a<=c<=box[2] and box[1]<=b<=d<=box[3]
            report['regional_order_check']={'assumed_region':box,'xy_fits':bool(contains(x1,y1,x2,y2)),'yx_fits':bool(contains(y1,x1,y2,x2)),'basis':'Approximate engineering sanity region, not authoritative boundaries or CRS proof'}
    return {'report_version': '1.0', 'method': 'Full JSON scan and Shapely/GEOS WKT parsing, no model calls',
            'sources': reports, 'limitations': ['Geometry validity does not prove authoritative parking boundaries.',
                'Line geometry is not a zone polygon. A distance corridor is a computed matching area.',
                'Source identifiers are object IDs; no merging by name or price is performed.']}



def render_input_report(report):
    lines = ['# Отчёт об исходных JSON', 'Полный программный разбор объектов и WKT. Это проверка входных данных, не испытание приложения.']
    for source in report['sources']:
        lines += ['## ' + source['file'], 'Город: ' + str(source['city']) + '; объектов: ' + str(source['objects']),
                  'SHA-256: `' + source['sha256'] + '`',
                  'Геометрия: ' + json.dumps(source['geometry_types'], ensure_ascii=False),
                  'Компоненты коллекций: ' + json.dumps(source['geometry_collection_members'], ensure_ascii=False),
                  'Диапазон x/y: ' + json.dumps(source['xy_bounds']),
                  'Проверка порядка: ' + json.dumps(source.get('regional_order_check', {}), ensure_ascii=False),
                  'Проблемы: ' + json.dumps(source['problem_counts'], ensure_ascii=False),
                  'Примеры проблем: ' + json.dumps(source['problem_examples'], ensure_ascii=False),
                  'Повторяющиеся ID: ' + str(len(source['duplicate_identifiers'])) + '; повторяющиеся строки геометрии: ' + str(source['repeated_geometry_strings']),
                  '### Типы исходных полей', '```json\n' + json.dumps(source['field_types'], ensure_ascii=False, indent=2) + '\n```',
                  '### Вложенные тарифы', '```json\n' + json.dumps(source['tariff'], ensure_ascii=False, indent=2) + '\n```',
                  source['crs_note']]
    lines += ['## Ограничения'] + ['- ' + x for x in report['limitations']]
    return '\n\n'.join(lines) + '\n'
