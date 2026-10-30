> Инженерная ревизия на основании анализа и уточнений пользователя; не результат нового вызова модели.

# Помощник парковки для водителя служебного автомобиля

## Оглавление

- [Общие положения](#doc-общие-положения)
  - [Статус и область документа](#doc-статус-и-область-документа)
  - [История изменений документа](#doc-история-изменений-документа)
  - [Ответственные](#doc-ответственные)
  - [Лист согласования](#doc-лист-согласования)
  - [Термины и определения](#doc-термины-и-определения)
  - [Использованные документы](#doc-использованные-документы)
- [Назначение](#doc-назначение)
- [Цели](#doc-цели)
- [Границы](#doc-границы)
- [Роли и права](#doc-роли-и-права)
  - [Водитель](#doc-водитель)
  - [Администратор](#doc-администратор)
- [Функциональные требования](#doc-функциональные-требования)
  - [FR-001: Система определяет парковочную зону по координатам и показывает ее номер.](#fr-001)
  - [FR-002: Водитель подтверждает парковочную сессию и время ее окончания.](#fr-002)
  - [FR-003: За 10 минут до окончания система предупреждает водителя.](#fr-003)
  - [FR-004: При переходе в другую зону система предлагает проверить необходимость новой оплаты.](#fr-004)
  - [FR-005: Администратор просматривает историю сессий и событий.](#fr-005)
  - [FR-006: Реальную оплату выполнять не нужно; внешний сервис заменяется mock-адаптером.](#fr-006)
  - [FR-007: Определение местоположения автомобиля.](#fr-007)
  - [FR-008: Отображение номера, границ и доступных параметров зоны.](#fr-008)
  - [FR-009: Отслеживание перемещения и отображение маршрута.](#fr-009)
  - [FR-010: Определение выезда из текущего объекта парковки.](#fr-010)
  - [FR-011: Контроль состояния и времени окончания парковочной сессии.](#fr-011)
  - [FR-012: Переход к официальному сервису оплаты.](#fr-012)
  - [FR-013: История парковочных сессий водителя.](#fr-013)
  - [FR-014: Административный просмотр автомобилей, зон, сессий, маршрутов, событий и истории.](#fr-014)
  - [FR-015: Мобильный интерфейс водителя с картой, текущей зоной, статусом сессии, временем, уведомлениями и переходом к оплате.](#fr-015)
- [Нефункциональные требования](#doc-нефункциональные-требования)
- [Допущения, не подтвержденные заказчиком](#doc-допущения-не-подтвержденные-заказчиком)
- [Уточнения и ответы](#doc-уточнения-и-ответы)
  - [Q-001: Как именно определяется переход в другую зону: по изменению рассчитанного номера зоны, по геозоне или по ручному выбору?](#doc-q-001-как-именно-определяется-переход-в-другую-зону-по-изменению-рассчитанного-номера-зоны-по-геозоне-или-по-ручному-выбору)
  - [Q-002: Что система должна делать, если по координатам не удается определить парковочную зону?](#doc-q-002-что-система-должна-делать-если-по-координатам-не-удается-определить-парковочную-зону)
  - [Q-003: Какие события должны отображаться администратору: только сессии, предупреждения, переходы, mock-оплата?](#doc-q-003-какие-события-должны-отображаться-администратору-только-сессии-предупреждения-переходы-mock-оплата)
- [Пользовательские сценарии](#doc-пользовательские-сценарии)
  - [Водитель](#doc-водитель-2)
  - [Администратор](#doc-администратор-2)
- [Компоненты](#doc-компоненты)
- [Модель данных](#doc-модель-данных)
  - [Account](#doc-account)
  - [Vehicle](#doc-vehicle)
  - [ImportBatch](#doc-importbatch)
  - [ParkingObject](#doc-parkingobject)
  - [Route](#doc-route)
  - [PositionObservation](#doc-positionobservation)
  - [ParkingSession](#doc-parkingsession)
  - [ParkingEvent](#doc-parkingevent)
  - [Notification](#doc-notification)
  - [MatchConfiguration](#doc-matchconfiguration)
- [Проект API-контрактов](#doc-проект-api-контрактов)
  - [GET /api/vehicles](#doc-get-api-vehicles)
  - [GET /api/parking-objects](#doc-get-api-parking-objects)
  - [GET /api/parking-objects/{objectId}](#doc-get-api-parking-objects-objectid)
  - [POST /api/vehicles/{vehicleId}/positions](#doc-post-api-vehicles-vehicleid-positions)
  - [GET /api/vehicles/{vehicleId}/match](#doc-get-api-vehicles-vehicleid-match)
  - [POST /api/vehicles/{vehicleId}/sessions](#doc-post-api-vehicles-vehicleid-sessions)
  - [GET /api/vehicles/{vehicleId}/sessions](#doc-get-api-vehicles-vehicleid-sessions)
  - [GET /api/sessions/{sessionId}](#doc-get-api-sessions-sessionid)
  - [POST /api/sessions/{sessionId}/confirm](#doc-post-api-sessions-sessionid-confirm)
  - [POST /api/sessions/{sessionId}/payment-link](#doc-post-api-sessions-sessionid-payment-link)
  - [GET /api/vehicles/{vehicleId}/routes](#doc-get-api-vehicles-vehicleid-routes)
  - [GET /api/routes/{routeId}/positions](#doc-get-api-routes-routeid-positions)
  - [GET /api/vehicles/{vehicleId}/notifications](#doc-get-api-vehicles-vehicleid-notifications)
  - [GET /api/admin/events](#doc-get-api-admin-events)
  - [GET /api/admin/sessions](#doc-get-api-admin-sessions)
  - [GET /api/admin/routes](#doc-get-api-admin-routes)
  - [GET /api/admin/matching](#doc-get-api-admin-matching)
  - [PUT /api/admin/matching](#doc-put-api-admin-matching)
  - [POST /api/admin/imports](#doc-post-api-admin-imports)
  - [GET /api/admin/imports/{batchId}](#doc-get-api-admin-imports-batchid)
  - [POST /api/admin/clock/advance](#doc-post-api-admin-clock-advance)
- [События и интеграции](#doc-события-и-интеграции)
- [Валидация и обработка ошибок](#doc-валидация-и-обработка-ошибок)
- [Рекомендации по безопасности](#doc-рекомендации-по-безопасности)
- [Риски](#doc-риски)
- [Ограничения и открытые вопросы](#doc-ограничения-и-открытые-вопросы)
- [Допущения проектирования](#doc-допущения-проектирования)
- [Открытые вопросы](#doc-открытые-вопросы)
- [Экраны и состояния](#doc-экраны-и-состояния)
  - [Мобильная PWA: карта, позиция, объект, сессия, предупреждение, оплата (/driver)](#doc-мобильная-pwa-карта-позиция-объект-сессия-предупреждение-оплата-driver)
  - [Состояние, подтверждение сессии и переход к оплате (/driver/sessions/:id)](#doc-состояние-подтверждение-сессии-и-переход-к-оплате-driver-sessions-id)
  - [Сессии и маршруты водителя (/driver/history)](#doc-сессии-и-маршруты-водителя-driver-history)
  - [Автомобили, объекты, сессии, маршруты, события и история (/admin)](#doc-автомобили-объекты-сессии-маршруты-события-и-история-admin)
  - [Импорт, карантин, параметры сопоставления и demo-время (/admin/import)](#doc-импорт-карантин-параметры-сопоставления-и-demo-время-admin-import)
- [Права операций](#doc-права-операций)


<a id="doc-общие-положения"></a>
## Общие положения

<a id="doc-статус-и-область-документа"></a>
### Статус и область документа

Проектируемое поведение (TO BE). Реализация целевого приложения этим документом не подтверждается. Настоящее время в исходных требованиях не означает внедрения. Сценарии приёмки описаны, но не исполнены; структурные проверки документов учитываются отдельно.

<a id="doc-история-изменений-документа"></a>
### История изменений документа

Версия документа не равна версии контракта. История автора/дат/задач в исходных данных не предоставлена; эти сведения не восстанавливаются предположениями.

| Версия документа | Изменение / основание | Автор | Дата | Jira |
|---|---|---|---|---|
| Не задана | Подготовка проектного описания по входным данным | Не назначен | Не задана | Не предоставлена |

<a id="doc-ответственные"></a>
### Ответственные

| Роль | Подразделение | ФИО |
|---|---|---|
| Заказчик | Не предоставлено | Не назначен |
| Руководитель проекта | Не предоставлено | Не назначен |
| Аналитик | Не предоставлено | Не назначен |
| Разработчик | Не предоставлено | Не назначен |
| Представитель ИБ | Не предоставлено | Не назначен |

<a id="doc-лист-согласования"></a>
### Лист согласования

Согласование не проводилось. Ответственные, замечания и даты согласования не предоставлены.

| Артефакт | Статус | Ответственный | Дата |
|---|---|---|---|
| Текущее описание | Не проводилось; сведения не предоставлены | Не назначен | Не задана |

<a id="doc-термины-и-определения"></a>
### Термины и определения

| Термин | Значение |
|---|---|
| FR-ID | Идентификатор функционального требования |
| TC-ID | Идентификатор описанного приёмочного сценария, не доказательство его выполнения |
| AS IS / TO BE | Фактически реализованное / проектируемое поведение |

Предметный и корпоративный глоссарии не предоставлены; определения по умолчанию не приписываются заказчику.

<a id="doc-использованные-документы"></a>
### Использованные документы

- [Бизнес-требования](requirements.md)
- [Структурированный анализ](analysis.json)
- [Проект решения](design.json)
- [Сценарии приёмки](acceptance-tests.md)
- [Трассировка](traceability.csv)
- [Фактические проверки документов](quality-report.json)
- [Локальный проект OpenAPI (не Swagger UI)](openapi.json)

<a id="doc-назначение"></a>
## Назначение
Помощник парковки с автоматическим сопоставлением с геометрией источника, сохранением сессий, маршрутов и событий без реальных платежей.

<a id="doc-цели"></a>
## Цели
- Определить парковочную зону по координатам и показать ее номер
- Подтвердить парковочную сессию и время ее окончания
- Предупредить водителя за 10 минут до окончания сессии
- Предложить водителю проверить необходимость новой оплаты при переходе в другую зону
- Обеспечить администратору просмотр истории сессий и событий

<a id="doc-границы"></a>
## Границы
- Определение парковочной зоны по координатам и отображение ее номера
- Подтверждение водителем парковочной сессии и времени окончания
- Предупреждение водителя за 10 минут до окончания сессии
- Предложение водителю проверить необходимость новой оплаты при переходе в другую зону
- Просмотр администратором истории сессий и событий
- Имитация оплаты через mock-адаптер без реальной оплаты
- Позиция, исходная геометрия, маршруты, история и мобильный интерфейс
- Административные списки автомобилей, объектов, сессий, маршрутов и событий

Спецификация парковочного помощника Санкт-Петербурга, сервер и БД; карта и PWA водителя, административный web. Реальных платежей нет. Это контракт, не реализованное приложение.

<a id="doc-роли-и-права"></a>
## Роли и права

<a id="doc-водитель"></a>
### Водитель
- видит номер парковочной зоны
- подтверждает парковочную сессию и время ее окончания
- получает предупреждение за 10 минут до окончания
- получает предложение проверить необходимость новой оплаты при переходе в другую зону

<a id="doc-администратор"></a>
### Администратор
- просматривает историю сессий и событий

<a id="doc-функциональные-требования"></a>
## Функциональные требования

<a id="fr-001"></a>
### FR-001: Система определяет парковочную зону по координатам и показывает ее номер.
Основание: Система определяет парковочную зону по координатам и показывает ее номер.

Критерии приемки:
- При координатах в допустимом расстоянии от линии или внутри полигона возвращаются объект источника и отображаемый идентификатор; никакой тарифный номер не выдумывается.
- NO_MATCH, NO_COORDINATES и TECHNICAL_ERROR различаются; NO_MATCH не означает бесплатность; текущая сессия сохраняется.

<a id="fr-002"></a>
### FR-002: Водитель подтверждает парковочную сессию и время ее окончания.
Основание: Водитель подтверждает парковочную сессию и время ее окончания.

Критерии приемки:
- Только явное действие водителя создаёт/подтверждает сессию с автомобилем, объектом и временем окончания.
- После перезагрузки интерфейса сессия читается из БД; подтверждение сессии не устанавливает факт оплаты.

<a id="fr-003"></a>
### FR-003: За 10 минут до окончания система предупреждает водителя.
Основание: За 10 минут до окончания система предупреждает водителя.

Критерии приемки:
- При достижении endAt минус 10 минут создаётся одно предупреждение и одно событие с идентификатором сессии.
- Повторная обработка того же момента не создаёт дубликат.

<a id="fr-004"></a>
### FR-004: При переходе в другую зону система предлагает проверить необходимость новой оплаты.
Основание: При переходе в другую зону система предлагает проверить необходимость новой оплаты.

Критерии приемки:
- Устойчивая смена объекта формирует событие и предложение проверить необходимость оплаты.
- Сессия и её оплата не изменяются автоматически при смене объекта.

<a id="fr-005"></a>
### FR-005: Администратор просматривает историю сессий и событий.
Основание: Администратор просматривает историю сессий и событий.

Критерии приемки:
- Администратор получает историю въезда, выезда, смены зоны, начала/подтверждения, предупреждения, окончания и ошибок позиции.
- У события есть id, type, occurredAt, vehicleId и применимые ссылки previousObjectId/objectId/sessionId.

<a id="fr-006"></a>
### FR-006: Реальную оплату выполнять не нужно; внешний сервис заменяется mock-адаптером.
Основание: Реальную оплату выполнять не нужно; внешний сервис заменяется mock-адаптером.

Критерии приемки:
- Демонстрационный адаптер не обращается к реальному платёжному шлюзу и явно обозначает демонстрационный режим.
- Результат адаптера и переход по ссылке не устанавливают paymentConfirmed=true.

<a id="fr-007"></a>
### FR-007: Определение местоположения автомобиля.
Основание: Определение местоположения автомобиля.

Критерии приемки:
- Получены координаты с timestamp и accuracyMeters; водитель видит текущую позицию.
- Отсутствие разрешения/координат отличается от технической ошибки; чужой автомобиль недоступен водителю.

<a id="fr-008"></a>
### FR-008: Отображение номера, границ и доступных параметров зоны.
Основание: Отображение номера, границ и доступных параметров зоны.

Критерии приемки:
- На карте показана исходная геометрия объекта, включая все компоненты MULTILINESTRING и GEOMETRYCOLLECTION.
- Для линейного источника подпись сообщает, что полигональных границ нет; вычисленный коридор отделён от исходной линии.
- Параметры показывают исходный тариф без неподтверждённых пересчётов.

<a id="fr-009"></a>
### FR-009: Отслеживание перемещения и отображение маршрута.
Основание: Отслеживание перемещения.

Критерии приемки:
- Последовательность координат автомобиля сохраняется с временем; маршрут восстанавливается после перезагрузки.
- Устаревшие и повторные наблюдения не вызывают переключения и дублирования событий.

<a id="fr-010"></a>
### FR-010: Определение выезда из текущего объекта парковки.
Основание: Определение выезда и перехода в другую зону.

Критерии приемки:
- При устойчивом отсутствии совпадения регистрируется выезд и предложение проверить оплату.
- Одиночная неточная точка не вызывает выезд; существующая сессия остаётся до её срока/явного действия.

<a id="fr-011"></a>
### FR-011: Контроль состояния и времени окончания парковочной сессии.
Основание: Контроль времени окончания сессии.

Критерии приемки:
- Текущее состояние и endAt видны водителю; при достижении endAt сессия получает статус expired и событие окончания.
- Управляемый демонстрационный Clock воспроизводит предупреждение и окончание без ожидания реальных минут.

<a id="fr-012"></a>
### FR-012: Переход к официальному сервису оплаты.
Основание: Переход к официальному сервису оплаты.

Критерии приемки:
- Действие водителя открывает только заранее настроенный разрешённый официальный URL через платёжный адаптер.
- Если URL не настроен, виден явный статус unavailable; переход и смена зоны не подтверждают оплату.

<a id="fr-013"></a>
### FR-013: История парковочных сессий водителя.
Основание: Отображение маршрута и истории сессий.

Критерии приемки:
- Водитель видит свои прошлые и текущую сессию и связанные маршруты; данные чужих автомобилей не выдаются.

<a id="fr-014"></a>
### FR-014: Административный просмотр автомобилей, зон, сессий, маршрутов, событий и истории.
Основание: Административный просмотр автомобилей, зон, сессий, маршрутов, событий и истории.

Критерии приемки:
- Администратор открывает списки автомобилей, объектов источника, сессий, маршрутов, событий с фильтром и пагинацией.
- Водитель не может получить административные списки.

<a id="fr-015"></a>
### FR-015: Мобильный интерфейс водителя с картой, текущей зоной, статусом сессии, временем, уведомлениями и переходом к оплате.
Основание: Мобильный интерфейс водителя с картой, текущей зоной, статусом сессии, временем, уведомлениями и переходом к оплате.

Критерии приемки:
- Мобильный экран PWA содержит карту, текущий объект/неопределённое состояние, сессию, endAt, предупреждение и оплату.
- Предусмотрены loading, error, empty, forbidden и ready; отсутствие сети не изображается как успешная оплата/бесплатная парковка.

<a id="doc-нефункциональные-требования"></a>
## Нефункциональные требования
Не задано / неприменимо.

<a id="doc-допущения-не-подтвержденные-заказчиком"></a>
## Допущения, не подтвержденные заказчиком
- A-001: Координаты водителя поступают от мобильного устройства или приложения. (Исходный текст не указывает источник координат.)
- A-003: Время окончания сессии задается водителем при подтверждении. (Текст говорит, что водитель подтверждает сессию и время ее окончания.)
- A-004: Предупреждение и предложение отображаются в интерфейсе приложения водителя. (Канал уведомления не указан.)
- A-006: История сессий и событий хранится в системе и доступна администратору. (Администратор просматривает историю.)
- A-007: Исходные WKT интерпретируются как EPSG:4326 с порядком longitude,latitude. (Диапазоны согласуются с Санкт-Петербургом и Москвой; SRID в WKT отсутствует.)
- A-008: Начальные проектные пороги: вход 25 м, выход 40 м, 3 последовательных точки на протяжении не менее 15 с, точность не хуже 50 м; все параметры конфигурируемые. (Численные значения не заданы пользователем; требуют полевой проверки.)
- A-009: При нескольких кандидатах сохраняется текущий объект в пределах выхода; иначе выбирается минимальная дистанция; при разнице менее 5 м результат ambiguous и переключение откладывается. (Защита от неоднозначности и дрожания; порог 5 м — проектное допущение.)
- A-010: Для импортированных точечных компонентов применяется тот же конфигурируемый допуск, полигон сопоставляется по покрытию, коллекция — по объединению подходящих компонентов без переименования объекта. (В коллекциях источника присутствуют POINT; требуется явное правило до реализации.)

<a id="doc-уточнения-и-ответы"></a>
## Уточнения и ответы

<a id="doc-q-001-как-именно-определяется-переход-в-другую-зону-по-изменению-рассчитанного-номера-зоны-по-геозоне-или-по-ручному-выбору"></a>
### Q-001: Как именно определяется переход в другую зону: по изменению рассчитанного номера зоны, по геозоне или по ручному выбору?
Влияние: Влияет на логику события и на то, когда показывать предложение проверить оплату.

Ответ пользователя: Автомобиль сопоставляется с парковочными объектами автоматически по координатам и геометрии источника spb.json. Для линейных объектов нужен настраиваемый допуск по расстоянию в метрах. Переключение устойчиво к погрешности координат. Порог расстояния, неоднозначные совпадения и защита от частого переключения — явно обозначаемые проектные допущения. externalZoneId — идентификатор объекта источника, не подтверждённый номер тарифной зоны. Все типы WKT, включая LINESTRING, MULTILINESTRING и GEOMETRYCOLLECTION с LINESTRING и POINT, должны учитываться. Числовые тарифные поля сохраняются без неподтверждённых пересчётов. Смена объекта не подтверждает оплату и не завершает/создаёт сессию.

<a id="doc-q-002-что-система-должна-делать-если-по-координатам-не-удается-определить-парковочную-зону"></a>
### Q-002: Что система должна делать, если по координатам не удается определить парковочную зону?
Влияние: Влияет на возможность начать сессию и на пользовательский сценарий.

Ответ пользователя: Показывать «зона не определена». Существующая сессия сохраняется. Предлагать пользователю проверить необходимость оплаты. Отсутствие совпадения само по себе не подтверждает бесплатность парковки. Различать отсутствие подходящего объекта, отсутствие координат и техническую ошибку.

<a id="doc-q-003-какие-события-должны-отображаться-администратору-только-сессии-предупреждения-переходы-mock-оплата"></a>
### Q-003: Какие события должны отображаться администратору: только сессии, предупреждения, переходы, mock-оплата?
Влияние: Влияет на состав истории и требования к логированию.

Ответ пользователя: Показывать въезд, выезд, смену зоны, запуск или подтверждение сессии, предупреждение за 10 минут, окончание сессии и ошибки определения местоположения. Событие содержит идентификатор, тип, время, автомобиль, необходимые ссылки на парковочные объекты и сессию. Численные пороги и алгоритмические детали отдельно помечаются как проектные допущения.

<a id="doc-пользовательские-сценарии"></a>
## Пользовательские сценарии

<a id="doc-водитель-2"></a>
### Водитель
Требования: FR-015

- Получить данные только в разрешённой области доступа.
- Открыть экран, увидеть загрузку/ошибку/данные.
- Выполнить явное действие; сервер проверяет права, схему и идемпотентность.

<a id="doc-администратор-2"></a>
### Администратор
Требования: FR-014

- Получить данные только в разрешённой области доступа.
- Открыть экран, увидеть загрузку/ошибку/данные.
- Выполнить явное действие; сервер проверяет права, схему и идемпотентность.

<a id="doc-компоненты"></a>
## Компоненты
- DriverAdminPwa — Мобильный и административный интерфейсы с картой, состояниями и UI Kit. Технология: Angular 20.1.6, PWA, совместимый Angular Material; версия UI Kit фиксируется при реализации
- ApplicationApi — Права, позиции, matching, сессии, события, Clock и демонстрационный PaymentAdapter. Технология: ASP.NET Core .NET 10 C#14
- Persistence — Сохранение исходных объектов, геометрии, сессий, маршрутов, событий и идемпотентности. Технология: PostgreSQL17.9 + PostGIS (версия сервера открытый вопрос); транзакции и фоновые задачи, Kafka не требуется

<a id="doc-модель-данных"></a>
## Модель данных

<a id="doc-account"></a>
### Account
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- displayName: {"type": "string", "minLength": 1, "maxLength": 200}; required=True — displayName
- role: {"type": "string", "enum": ["driver", "admin"]}; required=True — role

Связи:
Не задано / неприменимо.

<a id="doc-vehicle"></a>
### Vehicle
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- driverId: {"type": "string", "format": "uuid"}; required=True — driverId
- registration: {"type": "string", "minLength": 1, "maxLength": 30}; required=True — registration
- displayName: {"type": "string", "minLength": 1, "maxLength": 100}; required=True — displayName
- sourceCity: {"type": "string", "enum": ["spb", "moscow_partner"], "default": "spb"}; required=True — Изолированный источник сопоставления; для основного кейса spb

Связи:
- {"field": "driverId", "target_entity": "Account", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-importbatch"></a>
### ImportBatch
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- city: {"type": "string", "minLength": 1, "maxLength": 80}; required=True — city
- sha256: {"type": "string", "pattern": "^[a-f0-9]{64}$"}; required=True — sha256
- createdAt: {"type": "string", "format": "date-time"}; required=True — createdAt
- status: {"type": "string", "enum": ["pending", "completed", "failed"]}; required=True — status
- accepted: {"type": "integer", "minimum": 0}; required=True — accepted
- quarantined: {"type": "integer", "minimum": 0}; required=True — quarantined
- issues: {"type": "array", "items": {"type": "object", "properties": {"row": {"type": "integer", "minimum": 0}, "externalZoneId": {"type": ["string", "null"]}, "code": {"type": "string", "minLength": 1, "maxLength": 100}, "description": {"type": "string", "minLength": 1, "maxLength": 2000}}, "required": ["row", "externalZoneId", "code", "description"], "additionalProperties": false}}; required=True — issues

Связи:
Не задано / неприменимо.

<a id="doc-parkingobject"></a>
### ParkingObject
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- city: {"type": "string", "minLength": 1, "maxLength": 80}; required=True — city
- externalZoneId: {"type": "string", "minLength": 1, "maxLength": 120}; required=True — Исходное поле источника без пересчёта
- displayName: {"type": "string", "minLength": 1, "maxLength": 500}; required=True — Исходное поле источника без пересчёта
- geometry: {"type": "string", "minLength": 1, "maxLength": 200000}; required=True — Исходное поле источника без пересчёта
- price: {"type": "integer"}; required=True — Исходное поле источника без пересчёта
- priceDescription: {"type": "string", "minLength": 1, "maxLength": 2000}; required=True — Исходное поле источника без пересчёта
- minTime: {"type": "integer", "minimum": 0}; required=True — Исходное поле источника без пересчёта
- timeStep: {"type": "integer", "minimum": 0}; required=True — Исходное поле источника без пересчёта
- tariff: {"type": "object", "properties": {"hasHolidays": {"type": "boolean"}, "periods": {"type": "array", "items": {"type": "object", "properties": {"from": {"type": ["integer", "null"], "minimum": 0}, "to": {"type": ["integer", "null"], "minimum": 0}, "duration": {"type": ["integer", "null"], "minimum": 0}, "price": {"type": "integer"}, "type": {"type": "string", "minLength": 1, "maxLength": 40}}, "required": ["from", "to", "duration", "price", "type"], "additionalProperties": false}}}, "required": ["hasHolidays", "periods"], "additionalProperties": false}; required=True — Исходное поле источника без пересчёта
- entityState: {"type": "string", "minLength": 1, "maxLength": 50}; required=True — Исходное поле источника без пересчёта
- initDate: {"type": "string", "format": "date-time"}; required=True — Исходное поле источника без пересчёта
- lastSyncedAt: {"type": "string", "format": "date-time"}; required=True — Исходное поле источника без пересчёта
- importBatchId: {"type": "string", "format": "uuid"}; required=True — importBatchId
- geometryGeoJson: {"anyOf": [{"$ref": "#/components/schemas/Geometry"}, {"type": "null"}], "x-db-type": "geometry(Geometry,4326)", "x-derived-from": "original geometry WKT; null for quarantine"}; required=False — geometryGeoJson
- geometryState: {"type": "string", "enum": ["valid", "quarantined"]}; required=True — geometryState

Связи:
- {"field": "importBatchId", "target_entity": "ImportBatch", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-route"></a>
### Route
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- vehicleId: {"type": "string", "format": "uuid"}; required=True — vehicleId
- startedAt: {"type": "string", "format": "date-time"}; required=True — startedAt
- endedAt: {"type": ["string", "null"], "format": "date-time"}; required=False — endedAt

Связи:
- {"field": "vehicleId", "target_entity": "Vehicle", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-positionobservation"></a>
### PositionObservation
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- vehicleId: {"type": "string", "format": "uuid"}; required=True — vehicleId
- routeId: {"type": ["string", "null"], "format": "uuid"}; required=False — routeId
- sourceObservationId: {"type": "string", "minLength": 1, "maxLength": 120}; required=True — sourceObservationId
- observedAt: {"type": "string", "format": "date-time"}; required=True — observedAt
- receivedAt: {"type": "string", "format": "date-time"}; required=True — receivedAt
- longitude: {"type": ["number", "null"], "minimum": -180, "maximum": 180}; required=False — longitude
- latitude: {"type": ["number", "null"], "minimum": -90, "maximum": 90}; required=False — latitude
- accuracyMeters: {"type": ["number", "null"], "minimum": 0}; required=False — accuracyMeters
- locationState: {"type": "string", "enum": ["available", "no_coordinates", "technical_error"]}; required=True — locationState
- errorCode: {"type": ["string", "null"], "minLength": 1, "maxLength": 100}; required=False — errorCode

Связи:
- {"field": "vehicleId", "target_entity": "Vehicle", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "routeId", "target_entity": "Route", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-parkingsession"></a>
### ParkingSession
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- vehicleId: {"type": "string", "format": "uuid"}; required=True — vehicleId
- objectId: {"type": "string", "format": "uuid"}; required=True — objectId
- routeId: {"type": ["string", "null"], "format": "uuid"}; required=False — routeId
- startedAt: {"type": "string", "format": "date-time"}; required=True — startedAt
- endAt: {"type": "string", "format": "date-time"}; required=True — endAt
- status: {"type": "string", "enum": ["active", "expired"]}; required=True — status
- paymentConfirmed: {"type": "boolean", "const": false}; required=True — paymentConfirmed
- revision: {"type": "integer", "minimum": 1}; required=True — revision

Связи:
- {"field": "vehicleId", "target_entity": "Vehicle", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "objectId", "target_entity": "ParkingObject", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "routeId", "target_entity": "Route", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-parkingevent"></a>
### ParkingEvent
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- type: {"type": "string", "enum": ["entry", "exit", "object_changed", "session_started", "session_confirmed", "warning_10_minutes", "session_expired", "location_error"]}; required=True — type
- occurredAt: {"type": "string", "format": "date-time"}; required=True — occurredAt
- vehicleId: {"type": "string", "format": "uuid"}; required=True — vehicleId
- observationId: {"type": ["string", "null"], "format": "uuid"}; required=False — observationId
- objectId: {"type": ["string", "null"], "format": "uuid"}; required=False — objectId
- previousObjectId: {"type": ["string", "null"], "format": "uuid"}; required=False — previousObjectId
- sessionId: {"type": ["string", "null"], "format": "uuid"}; required=False — sessionId
- dedupKey: {"type": "string", "minLength": 1, "maxLength": 500}; required=True — dedupKey
- details: {"type": "object", "properties": {"code": {"type": ["string", "null"], "minLength": 1, "maxLength": 100}}, "required": [], "additionalProperties": false}; required=True — details

Связи:
- {"field": "vehicleId", "target_entity": "Vehicle", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "observationId", "target_entity": "PositionObservation", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "objectId", "target_entity": "ParkingObject", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "previousObjectId", "target_entity": "ParkingObject", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "sessionId", "target_entity": "ParkingSession", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-notification"></a>
### Notification
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- vehicleId: {"type": "string", "format": "uuid"}; required=True — vehicleId
- eventId: {"type": "string", "format": "uuid"}; required=True — eventId
- message: {"type": "string", "minLength": 1, "maxLength": 1000}; required=True — message
- createdAt: {"type": "string", "format": "date-time"}; required=True — createdAt
- kind: {"type": "string", "enum": ["warning", "check_payment", "location_error"]}; required=True — kind

Связи:
- {"field": "vehicleId", "target_entity": "Vehicle", "target_field": "id", "on_delete": "RESTRICT"}
- {"field": "eventId", "target_entity": "ParkingEvent", "target_field": "id", "on_delete": "RESTRICT"}

<a id="doc-matchconfiguration"></a>
### MatchConfiguration
- id: {"type": "string", "format": "uuid"}; required=True — Внутренний UUID
- enterMeters: {"type": "number", "exclusiveMinimum": 0, "maximum": 1000, "default": 25}; required=True — Проектный конфигурируемый порог; не требование заказчика
- exitMeters: {"type": "number", "exclusiveMinimum": 0, "maximum": 2000, "default": 40}; required=True — Проектный конфигурируемый порог; не требование заказчика
- confirmSamples: {"type": "integer", "minimum": 1, "maximum": 20, "default": 3}; required=True — Проектный конфигурируемый порог; не требование заказчика
- holdSeconds: {"type": "integer", "minimum": 0, "maximum": 300, "default": 15}; required=True — Проектный конфигурируемый порог; не требование заказчика
- maxAccuracyMeters: {"type": "number", "exclusiveMinimum": 0, "maximum": 1000, "default": 50}; required=True — Проектный конфигурируемый порог; не требование заказчика
- tieMeters: {"type": "number", "minimum": 0, "maximum": 100, "default": 5}; required=True — Проектный конфигурируемый порог; не требование заказчика
- city: {"type": "string", "minLength": 1, "maxLength": 80}; required=True — city
- maxObservationAgeSeconds: {"type": "integer", "minimum": 1, "maximum": 600, "default": 30}; required=True — Проектный конфигурируемый порог времени, не подтверждённый норматив
- futureToleranceSeconds: {"type": "integer", "minimum": 0, "maximum": 60, "default": 5}; required=True — Проектный конфигурируемый порог времени, не подтверждённый норматив

Связи:
Не задано / неприменимо.

<a id="doc-проект-api-контрактов"></a>
## Проект API-контрактов
Машинная спецификация: [openapi.json](openapi.json); проверка структуры не является испытанием приложения.

<a id="doc-get-api-vehicles"></a>
### GET /api/vehicles
Свои автомобили водителя; все автомобили администратора

Запрос: {"parameters": [{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/VehiclePage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-014, FR-015

<a id="doc-get-api-parking-objects"></a>
### GET /api/parking-objects
Объекты источника с исходной геометрией и тарифами

Запрос: {"parameters": [{"name": "city", "in": "query", "schema": {"type": "string", "enum": ["spb", "moscow_partner"]}, "required": true, "description": "city"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingObjectPage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-001, FR-008, FR-014

<a id="doc-get-api-parking-objects-objectid"></a>
### GET /api/parking-objects/{objectId}
Подробности объекта; не обещает тарифный номер или полигональные границы

Запрос: {"parameters": [{"name": "objectId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "objectId"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingObject"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-001, FR-008

<a id="doc-post-api-vehicles-vehicleid-positions"></a>
### POST /api/vehicles/{vehicleId}/positions
Координаты или явная ошибка; сопоставление с устойчивостью

Запрос: {"parameters": [{"name": "vehicleId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "vehicleId"}], "body": {"required": true, "schema": {"$ref": "#/components/schemas/PositionInput"}}}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/MatchResult"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver

Требования: FR-001, FR-004, FR-007, FR-009, FR-010

<a id="doc-get-api-vehicles-vehicleid-match"></a>
### GET /api/vehicles/{vehicleId}/match
Текущий результат определения без изменения сессии

Запрос: {"parameters": [{"name": "vehicleId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "vehicleId"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/MatchResult"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-001, FR-004, FR-007, FR-015

<a id="doc-post-api-vehicles-vehicleid-sessions"></a>
### POST /api/vehicles/{vehicleId}/sessions
Явный запуск сессии без подтверждения оплаты

Запрос: {"parameters": [{"name": "vehicleId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "vehicleId"}], "body": {"required": true, "schema": {"$ref": "#/components/schemas/SessionInput"}}}

Ответ: [{"status": "201", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingSession"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver

Требования: FR-002, FR-011

<a id="doc-get-api-vehicles-vehicleid-sessions"></a>
### GET /api/vehicles/{vehicleId}/sessions
История и активная сессия своего автомобиля

Запрос: {"parameters": [{"name": "vehicleId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "vehicleId"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingSessionPage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-002, FR-011, FR-013

<a id="doc-get-api-sessions-sessionid"></a>
### GET /api/sessions/{sessionId}
Состояние и время окончания сессии своего автомобиля

Запрос: {"parameters": [{"name": "sessionId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "sessionId"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingSession"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-002, FR-011, FR-015

<a id="doc-post-api-sessions-sessionid-confirm"></a>
### POST /api/sessions/{sessionId}/confirm
Явное подтверждение времени без автоматической смены объекта или оплаты

Запрос: {"parameters": [{"name": "sessionId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "sessionId"}], "body": {"required": true, "schema": {"$ref": "#/components/schemas/SessionConfirmation"}}}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingSession"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver

Требования: FR-002, FR-011

<a id="doc-post-api-sessions-sessionid-payment-link"></a>
### POST /api/sessions/{sessionId}/payment-link
Демо-адаптер выдаёт разрешённую официальную ссылку либо unavailable, без оплаты

Запрос: {"parameters": [{"name": "sessionId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "sessionId"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/PaymentLink"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver

Требования: FR-006, FR-012, FR-015

<a id="doc-get-api-vehicles-vehicleid-routes"></a>
### GET /api/vehicles/{vehicleId}/routes
Маршруты своего автомобиля

Запрос: {"parameters": [{"name": "vehicleId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "vehicleId"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/RoutePage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-009, FR-013

<a id="doc-get-api-routes-routeid-positions"></a>
### GET /api/routes/{routeId}/positions
Точки маршрута своего автомобиля в observedAt порядке

Запрос: {"parameters": [{"name": "routeId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "routeId"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/PositionObservationPage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-009, FR-013

<a id="doc-get-api-vehicles-vehicleid-notifications"></a>
### GET /api/vehicles/{vehicleId}/notifications
Предупреждение за 10 минут и необходимость проверки оплаты

Запрос: {"parameters": [{"name": "vehicleId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "vehicleId"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/NotificationPage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: driver, admin

Требования: FR-003, FR-004, FR-010, FR-015

<a id="doc-get-api-admin-events"></a>
### GET /api/admin/events
История всех обязательных типов событий

Запрос: {"parameters": [{"name": "vehicleId", "in": "query", "schema": {"type": "string", "format": "uuid"}, "required": false, "description": "vehicleId"}, {"name": "from", "in": "query", "schema": {"type": "string", "format": "date-time"}, "required": false, "description": "from"}, {"name": "to", "in": "query", "schema": {"type": "string", "format": "date-time"}, "required": false, "description": "to"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingEventPage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-005, FR-014

<a id="doc-get-api-admin-sessions"></a>
### GET /api/admin/sessions
Все сессии с фильтрацией

Запрос: {"parameters": [{"name": "vehicleId", "in": "query", "schema": {"type": "string", "format": "uuid"}, "required": false, "description": "vehicleId"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ParkingSessionPage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-005, FR-014

<a id="doc-get-api-admin-routes"></a>
### GET /api/admin/routes
Все маршруты с фильтрацией

Запрос: {"parameters": [{"name": "vehicleId", "in": "query", "schema": {"type": "string", "format": "uuid"}, "required": false, "description": "vehicleId"}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}, "required": false, "description": "page"}, {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}, "required": false, "description": "pageSize"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/RoutePage"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-014

<a id="doc-get-api-admin-matching"></a>
### GET /api/admin/matching
Просмотр проектных порогов

Запрос: {"parameters": [{"name": "city", "in": "query", "required": true, "description": "Источник, для которого применяются пороги", "schema": {"type": "string", "enum": ["spb", "moscow_partner"], "default": "spb"}}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/MatchConfiguration"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-001, FR-004, FR-010

<a id="doc-put-api-admin-matching"></a>
### PUT /api/admin/matching
Изменение порогов; exitMeters больше enterMeters

Запрос: {"parameters": [{"name": "city", "in": "query", "required": true, "description": "Источник, для которого применяются пороги", "schema": {"type": "string", "enum": ["spb", "moscow_partner"], "default": "spb"}}], "body": {"required": true, "schema": {"$ref": "#/components/schemas/MatchConfigurationInput"}}}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/MatchConfiguration"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-001, FR-004, FR-010

<a id="doc-post-api-admin-imports"></a>
### POST /api/admin/imports
Идемпотентный импорт и карантин невалидной геометрии без слияния объектов

Запрос: {"parameters": [], "body": {"required": true, "schema": {"$ref": "#/components/schemas/ImportInput"}}}

Ответ: [{"status": "202", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ImportBatch"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-001, FR-008, FR-014

<a id="doc-get-api-admin-imports-batchid"></a>
### GET /api/admin/imports/{batchId}
Отчёт импорта и проблемных строк

Запрос: {"parameters": [{"name": "batchId", "in": "path", "schema": {"type": "string", "format": "uuid"}, "required": true, "description": "batchId"}], "body": null}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ImportBatch"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-008, FR-014

<a id="doc-post-api-admin-clock-advance"></a>
### POST /api/admin/clock/advance
Управляемое время только в demo-окружении

Запрос: {"parameters": [], "body": {"required": true, "schema": {"$ref": "#/components/schemas/ClockAdvance"}}}

Ответ: [{"status": "200", "description": "Описанный успешный результат", "schema": {"$ref": "#/components/schemas/ClockState"}}, {"status": "400", "description": "Неверный запрос", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "401", "description": "Нет удостоверенной личности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "403", "description": "Недостаточно прав или чужой автомобиль", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "404", "description": "Объект не найден", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "409", "description": "Конфликт состояния/идемпотентности", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "422", "description": "Нарушение предметной валидации", "schema": {"$ref": "#/components/schemas/Problem"}}, {"status": "503", "description": "Техническая недоступность", "schema": {"$ref": "#/components/schemas/Problem"}}]

Доступ: admin

Требования: FR-003, FR-011

<a id="doc-события-и-интеграции"></a>
## События и интеграции
- ParkingEvent: {"type": "object", "additionalProperties": false, "properties": {"id": {"type": "string", "format": "uuid"}, "type": {"type": "string", "enum": ["entry", "exit", "object_changed", "session_started", "session_confirmed", "warning_10_minutes", "session_expired", "location_error"]}, "occurredAt": {"type": "string", "format": "date-time"}, "vehicleId": {"type": "string", "format": "uuid"}, "observationId": {"type": ["string", "null"], "format": "uuid"}, "objectId": {"type": ["string", "null"], "format": "uuid"}, "previousObjectId": {"type": ["string", "null"], "format": "uuid"}, "sessionId": {"type": ["string", "null"], "format": "uuid"}, "dedupKey": {"type": "string", "minLength": 1, "maxLength": 500}, "details": {"type": "object", "properties": {"code": {"type": ["string", "null"], "minLength": 1, "maxLength": 100}}, "required": [], "additionalProperties": false}}, "required": ["id", "type", "occurredAt", "vehicleId", "dedupKey", "details"], "allOf": [{"if": {"properties": {"type": {"enum": ["session_started", "session_confirmed", "warning_10_minutes", "session_expired"]}}}, "then": {"required": ["sessionId"], "properties": {"sessionId": {"type": "string", "format": "uuid"}}}}, {"if": {"properties": {"type": {"enum": ["entry", "object_changed"]}}}, "then": {"required": ["objectId"], "properties": {"objectId": {"type": "string", "format": "uuid"}}}}, {"if": {"properties": {"type": {"enum": ["exit", "object_changed"]}}}, "then": {"required": ["previousObjectId"], "properties": {"previousObjectId": {"type": "string", "format": "uuid"}}}}]}. Доставка: at_least_once; dedup=dedupKey

<a id="doc-валидация-и-обработка-ошибок"></a>
## Валидация и обработка ошибок
- PostGIS хранит geometry(Geometry,4326); расстояния линий/точек рассчитываются в метрах через geography по компонентам; полигоны через покрытие. Геометрия не исправляется молча.
- Вход 25м, выход 40м, >=3 точек за >=15с, accuracy<=50м; текущий объект удерживается до порога выхода; новый подтверждается при пороге входа; разница кандидатов<5м даёт ambiguous. Это конфигурируемые допущения, не подтверждённые нормативы.
- Гистерезис хранится на автомобиль; при неточных/устаревших/отсутствующих координатах не фиксировать выезд. NO_MATCH после устойчивых валидных точек фиксирует выезд; сессия сохраняется.
- Для available обязательны longitude/latitude/accuracyMeters; no_coordinates и technical_error не сохраняют выдуманные координаты. Храним исходное наблюдение для аудита.
- Время UTC; endAt > Clock.now; одна active сессия на автомобиль; expectedRevision защищает конкуренцию. Если сессия создана меньше чем за10мин до конца, предупреждение формируется сразу однократно (проектное допущение).
- Импорт ограничен 20МБ и20000 объектов за пакет (проектное ограничение), ключ city+externalZoneId; совпадение цены/названия не объединяет записи; city+sha256 предотвращает повтор импорта.
- События: въезд, выезд, смена объекта, начало/подтверждение,10мин,окончание,ошибки позиции. Ссылки objectId/previousObjectId/sessionId заполняются по типу и известному состоянию.
- Переключение/потеря совпадения никогда не создаёт платёж, не завершает и не создаёт сессию. Истечение endAt — отдельный переход с событием.
- Ошибки API:400 синтаксис,401 нет идентификации,403 права/чужие данные/demo-Clock запрещён,404 неизвестный ID,409 конфликт/повтор с другим телом,422 предметная валидация,503 техническая ошибка.
- listObjects возвращает исходный WKT и производный GeoJSON. corridor в MatchResult всегда расчётный и не авторитетная граница. Карантин виден администратору, не используется для определения платной области.
- routeId в PositionInput необязателен; сервер назначает маршрут валидной точке. Наблюдение no_coordinates/technical_error сохраняется без фиктивных координат и при необходимости без маршрута.
- Временная устойчивость: observedAt<=lastAcceptedAt или Clock.now-observedAt>maxObservationAgeSeconds => stale; observedAt-Clock.now>futureToleranceSeconds =>422. По stale не фиксировать выезд и не менять объект или сессию.
- Источник matching определяется Vehicle.sourceCity (по умолчанию spb); используется соответствующая MatchConfiguration.city. Moscow_partner не смешивается с spb. Сессия может ссылаться только на объект того же источника, что и автомобиль.

<a id="doc-рекомендации-по-безопасности"></a>
## Рекомендации по безопасности
Сканирование кода и проверка CVE не выполнялись.

- Проверять владельца автомобиля/сессии/маршрута на сервере при каждой операции; роль из доверенного контекста.
- Идентификаторы/время/расстояния валидируются; maxPageSize100, параметризованные запросы.
- Платёжный адаптер только allowlist; неизвестный URL unavailable. Нет секретов в событиях и API.
- Управляемый Clock и демонстрационные координаты только demo-режим, закрыты в production.
- Геоданные — чувствительная история перемещений: доступ по роли, согласовать срок хранения и удаление.

<a id="doc-риски"></a>
## Риски
- Неточные координаты или границы зон могут привести к ложному определению зоны или перехода. → Использовать порог/буфер для смены зоны и фиксировать исходные координаты в событии.
- Уведомление за 10 минут может не быть замечено водителем. → Показывать статус сессии и оставшееся время в интерфейсе.
- Mock-адаптер может скрыть ошибки реального интеграционного контракта. → Логировать запросы и ответы mock-адаптера и использовать фиксированный контракт.

<a id="doc-ограничения-и-открытые-вопросы"></a>
## Ограничения и открытые вопросы
- Все сценарии — описания приёмки; приложение, SQL, сборка, UI-тесты, CVE-сканирование не выполнялись.
- Линейные данные не задают границ тарифных зон; нельзя рисовать коридор как официальную зону или трактовать отсутствие объекта как бесплатность.
- EPSG4326/координатный порядок — допущение; преобразование иных CRS только после подтверждения.
- Пороговые числа, диапазоны валидации, примерные лимиты пакетов и правила неоднозначности — проектные допущения для последующей проверки.
- Исходный PDF недоступен; полнота проверена относительно перечня пользователя.
- Импорт geometry513420 помещается в карантин; точка в GEOMETRYCOLLECTION не превращается в отдельную тарифную зону.
- Единицы и расчёт цены не подтверждены. price и tariff сохраняются как исходные данные.
- paymentConfirmed всегда false: подтверждение сессии и ссылка не являются подтверждением оплаты.
- Версия Angular Material, провайдер карты/тайлов и модель идентификации фиксируются до реализации; карта не обязана работать без сети.
<a id="doc-допущения-проектирования"></a>
## Допущения проектирования
- A-001: Координаты водителя поступают от мобильного устройства или приложения. (Исходный текст не указывает источник координат.)
- A-003: Время окончания сессии задается водителем при подтверждении. (Текст говорит, что водитель подтверждает сессию и время ее окончания.)
- A-004: Предупреждение и предложение отображаются в интерфейсе приложения водителя. (Канал уведомления не указан.)
- A-006: История сессий и событий хранится в системе и доступна администратору. (Администратор просматривает историю.)
- A-007: Исходные WKT интерпретируются как EPSG:4326 с порядком longitude,latitude. (Диапазоны согласуются с Санкт-Петербургом и Москвой; SRID в WKT отсутствует.)
- A-008: Начальные проектные пороги: вход 25 м, выход 40 м, 3 последовательных точки на протяжении не менее 15 с, точность не хуже 50 м; все параметры конфигурируемые. (Численные значения не заданы пользователем; требуют полевой проверки.)
- A-009: При нескольких кандидатах сохраняется текущий объект в пределах выхода; иначе выбирается минимальная дистанция; при разнице менее 5 м результат ambiguous и переключение откладывается. (Защита от неоднозначности и дрожания; порог 5 м — проектное допущение.)
- A-010: Для импортированных точечных компонентов применяется тот же конфигурируемый допуск, полигон сопоставляется по покрытию, коллекция — по объединению подходящих компонентов без переименования объекта. (В коллекциях источника присутствуют POINT; требуется явное правило до реализации.)
- A-011: В demo маршрут создаётся сервером при первой валидной точке автомобиля за день UTC; отсутствие координат не требует выдуманного routeId. (Границы поездки в исходных данных не заданы. Это проектный вариант, подлежащий согласованию.)
- A-012: Наблюдение stale, если observedAt не новее последнего принятого либо старше Clock.now на 30 с; timestamp более чем на 5 с в будущем отклоняется. Пороги конфигурируемые. (Пользователь требует устойчивость к погрешностям; временные численные пороги не заданы и являются проектными допущениями.)

<a id="doc-открытые-вопросы"></a>
## Открытые вопросы
- Подтвердить SRID и порядок координат у источника; диапазоны подтверждают лишь правдоподобие longitude,latitude.
- externalZoneId — объект; где источник авторитетного номера и полигональных границ тарифной зоны?
- Подтвердить единицы price/minTime/timeStep и period.from/to/duration/price, правила календаря/праздников и выбора периодов.
- Подтвердить официальный URL/адаптер оплаты и доверенный механизм идентификации пользователей.
- Уточнить серверную версию PostGIS: postgis-jdbc2.5.0 — Java-библиотека.
- Согласовать сроки хранения и разрешения на геолокацию, в том числе работу PWA в фоне.

<a id="doc-экраны-и-состояния"></a>
## Экраны и состояния
<a id="doc-мобильная-pwa-карта-позиция-объект-сессия-предупреждение-оплата-driver"></a>
### Мобильная PWA: карта, позиция, объект, сессия, предупреждение, оплата (/driver)
Роли: driver
- loading: Индикатор загрузки; действия изменения состояния отключены.
- error: Сообщение с кодом; техническая ошибка не означает отсутствие зоны или оплату.
- empty: Нет данных или зоны; сессия сохраняется; бесплатность не утверждается.
- forbidden: Доступ запрещён; чужие данные не показываются.
- ready: Данные показаны с временем обновления; устаревшее состояние помечено.

<a id="doc-состояние-подтверждение-сессии-и-переход-к-оплате-driver-sessions-id"></a>
### Состояние, подтверждение сессии и переход к оплате (/driver/sessions/:id)
Роли: driver
- loading: Индикатор загрузки; действия изменения состояния отключены.
- error: Сообщение с кодом; техническая ошибка не означает отсутствие зоны или оплату.
- empty: Нет данных или зоны; сессия сохраняется; бесплатность не утверждается.
- forbidden: Доступ запрещён; чужие данные не показываются.
- ready: Данные показаны с временем обновления; устаревшее состояние помечено.

<a id="doc-сессии-и-маршруты-водителя-driver-history"></a>
### Сессии и маршруты водителя (/driver/history)
Роли: driver
- loading: Индикатор загрузки; действия изменения состояния отключены.
- error: Сообщение с кодом; техническая ошибка не означает отсутствие зоны или оплату.
- empty: Нет данных или зоны; сессия сохраняется; бесплатность не утверждается.
- forbidden: Доступ запрещён; чужие данные не показываются.
- ready: Данные показаны с временем обновления; устаревшее состояние помечено.

<a id="doc-автомобили-объекты-сессии-маршруты-события-и-история-admin"></a>
### Автомобили, объекты, сессии, маршруты, события и история (/admin)
Роли: admin
- loading: Индикатор загрузки; действия изменения состояния отключены.
- error: Сообщение с кодом; техническая ошибка не означает отсутствие зоны или оплату.
- empty: Нет данных или зоны; сессия сохраняется; бесплатность не утверждается.
- forbidden: Доступ запрещён; чужие данные не показываются.
- ready: Данные показаны с временем обновления; устаревшее состояние помечено.

<a id="doc-импорт-карантин-параметры-сопоставления-и-demo-время-admin-import"></a>
### Импорт, карантин, параметры сопоставления и demo-время (/admin/import)
Роли: admin
- loading: Индикатор загрузки; действия изменения состояния отключены.
- error: Сообщение с кодом; техническая ошибка не означает отсутствие зоны или оплату.
- empty: Нет данных или зоны; сессия сохраняется; бесплатность не утверждается.
- forbidden: Доступ запрещён; чужие данные не показываются.
- ready: Данные показаны с временем обновления; устаревшее состояние помечено.

<a id="doc-права-операций"></a>
## Права операций
- driver: listVehicles [own]; listObjects [all]; getObject [all]; ingestPosition [own]; getMatch [own]; createSession [own]; listVehicleSessions [own]; getSession [own]; confirmSession [own]; getPaymentLink [own]; listVehicleRoutes [own]; listRoutePositions [own]; listNotifications [own]
- admin: listVehicles [all]; listObjects [all]; getObject [all]; getMatch [all]; listVehicleSessions [all]; getSession [all]; listVehicleRoutes [all]; listRoutePositions [all]; listNotifications [all]; listEvents [all]; listAllSessions [all]; listAllRoutes [all]; getMatchConfiguration [all]; updateMatchConfiguration [all]; importSource [all]; getImport [all]; advanceDemoClock [all]
