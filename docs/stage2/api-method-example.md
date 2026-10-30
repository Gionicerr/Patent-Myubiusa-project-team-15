# Неполный пример метода API: GET /api/sessions/{sessionId}

> ДЕМОНСТРАЦИОННОЕ ЗАПОЛНЕНИЕ по существующему stage2. Проект TO BE, целевой метод не реализован и не вызывался. Это не полная согласованная спецификация и не доказательство выполнения запроса.

Основание: [шаблон метода](../../resources/standards/russtech/templates/api-method.md). [Родительский сервис](service-example.md); [системный анализ](system-analysis.md); [контракт](design.json); [OpenAPI](openapi.json).

## Наименование и основная информация

operation_id: `getSession`. Назначение: Состояние и время окончания сессии своего автомобиля

FR: [FR-002](system-analysis.md#fr-002), [FR-011](system-analysis.md#fr-011), [FR-015](system-analysis.md#fr-015)

HTTP-транспорт/версия/защита и режим обмена отдельно не заданы. Live Swagger UI не предоставлен; ссылка выше ведёт на файл проекта OpenAPI.

## История изменений

История авторов, дат и Jira не предоставлена; согласование не проводилось.

## Входящие параметры

### Авторизация и права

Схема OpenAPI: `bearerAuth`, тип http/bearer. Роли и scope из действующего контракта:

| Роль | Scope |
|---|---|

| driver | own |

| admin | all |

### Заголовки

Отдельные параметры этой категории не заданы в контракте. Данные аутентификации описаны security scheme; значения токенов не публикуются.

### Параметры path

| Имя | Описание | JSON Schema | Required |
|---|---|---|---|

| sessionId | sessionId | `{"type": "string", "format": "uuid"}` | true |

### Параметры query

Отдельные параметры этой категории не заданы в контракте. Данные аутентификации описаны security scheme; значения токенов не публикуются.

### Модель тела запроса

В контракте `request_body=null`; тело запроса не описано.

### Пример запроса

Не подготовлен. Тестовые UUID и исполненный запрос отсутствуют; это пробел оформления, не результат вызова API.

## Исходящие параметры

### Успешная обработка

| Код | Описание | Схема |
|---|---|---|

| 200 | Описанный успешный результат | `{"$ref": "#/components/schemas/ParkingSession"}` |

#### Модель тела успешного ответа

Точное определение из компонента OpenAPI (данные экземпляра не выдумываются):

```json

{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "vehicleId": {
      "type": "string",
      "format": "uuid"
    },
    "objectId": {
      "type": "string",
      "format": "uuid"
    },
    "routeId": {
      "type": [
        "string",
        "null"
      ],
      "format": "uuid"
    },
    "startedAt": {
      "type": "string",
      "format": "date-time"
    },
    "endAt": {
      "type": "string",
      "format": "date-time"
    },
    "status": {
      "type": "string",
      "enum": [
        "active",
        "expired"
      ]
    },
    "paymentConfirmed": {
      "type": "boolean",
      "const": false
    },
    "revision": {
      "type": "integer",
      "minimum": 1
    }
  },
  "required": [
    "id",
    "vehicleId",
    "objectId",
    "startedAt",
    "endAt",
    "status",
    "paymentConfirmed",
    "revision"
  ]
}

```

#### Пример успешного ответа

Не подготовлен; фактический результат HTTP-вызова отсутствует.

### Неуспешная обработка

| Код | Описание | Схема |
|---|---|---|

| 400 | Неверный запрос | `{"$ref": "#/components/schemas/Problem"}` |

| 401 | Нет удостоверенной личности | `{"$ref": "#/components/schemas/Problem"}` |

| 403 | Недостаточно прав или чужой автомобиль | `{"$ref": "#/components/schemas/Problem"}` |

| 404 | Объект не найден | `{"$ref": "#/components/schemas/Problem"}` |

| 409 | Конфликт состояния/идемпотентности | `{"$ref": "#/components/schemas/Problem"}` |

| 422 | Нарушение предметной валидации | `{"$ref": "#/components/schemas/Problem"}` |

| 503 | Техническая недоступность | `{"$ref": "#/components/schemas/Problem"}` |

Точная схема ошибки:

```json

{
  "type": "object",
  "properties": {
    "code": {
      "type": "string",
      "minLength": 1,
      "maxLength": 100
    },
    "message": {
      "type": "string",
      "minLength": 1,
      "maxLength": 2000
    },
    "traceId": {
      "type": "string",
      "minLength": 1,
      "maxLength": 120
    }
  },
  "required": [
    "code",
    "message",
    "traceId"
  ],
  "additionalProperties": false
}

```

Response headers отдельно не представлены; примеры ошибок не подготовлены. Код 500 из образца организаторов не добавлен в существующий API.

## Взаимодействие с таблицами

Per-operation table_access в v2 отсутствует. Наличие `$ref` на ParkingSession описывает ответ и не доказывает конкретный SQL/набор чтений.

## Описание алгоритма

Пошаговый алгоритм/предусловия/исключения этого метода не представлены отдельной структурой. Общие правила находятся в [системном анализе](system-analysis.md); выводить из них непроверенный алгоритм не следует. [Заготовка PlantUML](../../resources/standards/russtech/templates/sequence.puml) не является диаграммой этого метода.

## Внешние компоненты и источники

Per-operation маппинг, кэширование и интеграции не определены; не объявлены отсутствующими или реализованными.

## Кэширование и производительность

Применимость, TTL, RPS, timeout и фактические замеры не предоставлены.

## Приёмочные сценарии

Связанные описания (не исполненные проверки): TC-002, TC-011, TC-015. См. [план](acceptance-tests.md).
