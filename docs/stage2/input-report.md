# Отчёт об исходных JSON

Полный программный разбор объектов и WKT. Это проверка входных данных, не испытание приложения.

## spb.json

Город: spb; объектов: 6867

SHA-256: `7cb7243debf901a07e1347046609f9fd94f822cf9a017f524930a42bc3bbd9b7`

Геометрия: {"LINESTRING": 6563, "MULTILINESTRING": 299, "GEOMETRYCOLLECTION": 5}

Компоненты коллекций: {"LINESTRING": 5, "POINT": 5}

Диапазон x/y: [30.22977232933, 59.909061044776, 30.399878025055, 59.978680310734]

Проверка порядка: {"assumed_region": [29, 59, 32, 61], "xy_fits": true, "yx_fits": false, "basis": "Approximate engineering sanity region, not authoritative boundaries or CRS proof"}

Проблемы: {"invalid_geometry": 1}

Примеры проблем: [{"row": 6082, "externalZoneId": "513420", "code": "invalid_geometry", "detail": "Too few points in geometry component[30.3662109375 59.944971696943]"}]

Повторяющиеся ID: 0; повторяющиеся строки геометрии: 3

### Типы исходных полей

```json
{
  "externalZoneId": {
    "string": 6867
  },
  "displayName": {
    "string": 6867
  },
  "geometry": {
    "string": 6867
  },
  "price": {
    "integer": 6867
  },
  "priceDescription": {
    "string": 6867
  },
  "minTime": {
    "integer": 6867
  },
  "timeStep": {
    "integer": 6867
  },
  "tariff": {
    "object": 6867
  },
  "entityState": {
    "string": 6867
  },
  "initDate": {
    "string": 6867
  },
  "lastSyncedAt": {
    "string": 6867
  }
}
```

### Вложенные тарифы

```json
{
  "types": {
    "object": 6867
  },
  "nested_types": {
    "tariff.hasHolidays": {
      "boolean": 6867
    },
    "tariff.periods[].from": {
      "integer": 41202
    },
    "tariff.periods[].to": {
      "integer": 41202
    },
    "tariff.periods[].duration": {
      "null": 20601,
      "integer": 20601
    },
    "tariff.periods[].price": {
      "integer": 41202
    },
    "tariff.periods[].type": {
      "string": 41202
    }
  },
  "period_field_counts": {
    "from": 41202,
    "to": 41202,
    "duration": 41202,
    "price": 41202,
    "type": 41202
  },
  "periods_per_object": {
    "6": 6867
  },
  "vehicle_types": {
    "truck": 13734,
    "bus": 13734,
    "car": 13734
  },
  "raw_numeric_ranges": {
    "tariff.periods[].from": [
      480,
      480
    ],
    "tariff.periods[].to": [
      1200,
      1200
    ],
    "tariff.periods[].price": [
      10000,
      72000
    ],
    "tariff.periods[].duration": [
      60,
      60
    ]
  },
  "interpretation": "Raw values retained; currency subunits, time units, holiday/calendar and overlapping-period semantics are unconfirmed."
}
```

WKT has no SRID. EPSG:4326 and x=longitude,y=latitude are assumptions; ranges alone do not prove CRS or order.

## response.json

Город: moscow_partner; объектов: 16656

SHA-256: `babf3c8c30bee82c99fae38036a0596d63196bf45e58ad7567e2847d92e167e1`

Геометрия: {"LINESTRING": 16326, "POLYGON": 330}

Компоненты коллекций: {}

Диапазон x/y: [37.144749723075, 55.499464412108, 37.951421855483, 56.001536980502]

Проверка порядка: {"assumed_region": [36, 54, 39, 57], "xy_fits": true, "yx_fits": false, "basis": "Approximate engineering sanity region, not authoritative boundaries or CRS proof"}

Проблемы: {}

Примеры проблем: []

Повторяющиеся ID: 0; повторяющиеся строки геометрии: 0

### Типы исходных полей

```json
{
  "externalZoneId": {
    "string": 16656
  },
  "displayName": {
    "string": 16656
  },
  "geometry": {
    "string": 16656
  },
  "price": {
    "integer": 16656
  },
  "priceDescription": {
    "string": 16656
  },
  "minTime": {
    "integer": 16656
  },
  "timeStep": {
    "integer": 16656
  },
  "tariff": {
    "object": 16656
  },
  "entityState": {
    "string": 16656
  },
  "initDate": {
    "string": 16656
  },
  "lastSyncedAt": {
    "string": 16656
  }
}
```

### Вложенные тарифы

```json
{
  "types": {
    "object": 16656
  },
  "nested_types": {
    "tariff.hasHolidays": {
      "boolean": 16656
    },
    "tariff.periods[].from": {
      "null": 17322,
      "integer": 34748
    },
    "tariff.periods[].to": {
      "null": 17322,
      "integer": 34748
    },
    "tariff.periods[].duration": {
      "null": 49169,
      "integer": 2901
    },
    "tariff.periods[].price": {
      "integer": 52070
    },
    "tariff.periods[].type": {
      "string": 52070
    }
  },
  "period_field_counts": {
    "from": 52070,
    "to": 52070,
    "duration": 52070,
    "price": 52070,
    "type": 52070
  },
  "periods_per_object": {
    "2": 8641,
    "4": 6651,
    "6": 1364
  },
  "vehicle_types": {
    "car": 25868,
    "truck": 25972,
    "bus": 230
  },
  "raw_numeric_ranges": {
    "tariff.periods[].price": [
      0,
      100000
    ],
    "tariff.periods[].from": [
      480,
      1260
    ],
    "tariff.periods[].to": [
      480,
      1260
    ],
    "tariff.periods[].duration": [
      30,
      120
    ]
  },
  "interpretation": "Raw values retained; currency subunits, time units, holiday/calendar and overlapping-period semantics are unconfirmed."
}
```

WKT has no SRID. EPSG:4326 and x=longitude,y=latitude are assumptions; ranges alone do not prove CRS or order.

## Ограничения

- Geometry validity does not prove authoritative parking boundaries.

- Line geometry is not a zone polygon. A distance corridor is a computed matching area.

- Source identifiers are object IDs; no merging by name or price is performed.
