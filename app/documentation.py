"""Markdown-only documentation controls; no changes to application contracts."""
import re


def document_controls(typed=False):
    references=[('Бизнес-требования','requirements.md'),('Структурированный анализ','analysis.json'),
                ('Проект решения','design.json'),('Сценарии приёмки','acceptance-tests.md'),
                ('Трассировка','traceability.csv'),('Фактические проверки документов','quality-report.json')]
    if typed: references.append(('Локальный проект OpenAPI (не Swagger UI)','openapi.json'))
    return '''## Общие положения

### Статус и область документа

Проектируемое поведение (TO BE). Реализация целевого приложения этим документом не подтверждается. Настоящее время в исходных требованиях не означает внедрения. Сценарии приёмки описаны, но не исполнены; структурные проверки документов учитываются отдельно.

### История изменений документа

Версия документа не равна версии контракта. История автора/дат/задач в исходных данных не предоставлена; эти сведения не восстанавливаются предположениями.

| Версия документа | Изменение / основание | Автор | Дата | Jira |
|---|---|---|---|---|
| Не задана | Подготовка проектного описания по входным данным | Не назначен | Не задана | Не предоставлена |

### Ответственные

| Роль | Подразделение | ФИО |
|---|---|---|
| Заказчик | Не предоставлено | Не назначен |
| Руководитель проекта | Не предоставлено | Не назначен |
| Аналитик | Не предоставлено | Не назначен |
| Разработчик | Не предоставлено | Не назначен |
| Представитель ИБ | Не предоставлено | Не назначен |

### Лист согласования

Согласование не проводилось. Ответственные, замечания и даты согласования не предоставлены.

| Артефакт | Статус | Ответственный | Дата |
|---|---|---|---|
| Текущее описание | Не проводилось; сведения не предоставлены | Не назначен | Не задана |

### Термины и определения

| Термин | Значение |
|---|---|
| FR-ID | Идентификатор функционального требования |
| TC-ID | Идентификатор описанного приёмочного сценария, не доказательство его выполнения |
| AS IS / TO BE | Фактически реализованное / проектируемое поведение |

Предметный и корпоративный глоссарии не предоставлены; определения по умолчанию не приписываются заказчику.

### Использованные документы

''' + '\n'.join('- ['+title+']('+path+')' for title,path in references)


def with_contents(markdown):
    """Explicit unique anchors, including stable FR anchors; ignore fenced code."""
    lines=markdown.splitlines();entries=[];prepared=[];seen={};fence=None
    for line in lines:
        if line.lstrip().startswith(('```','~~~')):
            mark=line.lstrip()[:3]
            fence=None if fence==mark else (mark if fence is None else fence)
        heading=None if fence else re.match(r'^(#{2,3})\s+(.+)$',line)
        if heading:
            level,title=len(heading[1]),heading[2]
            fr=re.match(r'(FR-\d{3,})\b',title)
            base=fr[1].lower() if fr else 'doc-'+re.sub(r'[^\w-]+','-',title.lower()).strip('-')
            seen[base]=seen.get(base,0)+1;anchor=base if seen[base]==1 else base+'-'+str(seen[base])
            prepared.append('<a id="'+anchor+'"></a>')
            entries.append('  '*(level-2)+'- ['+title.replace('[','').replace(']','')+'](#'+anchor+')')
        prepared.append(line)
    for i,line in enumerate(prepared):
        if line.startswith('# '):
            prepared[i+1:i+1]=['','## Оглавление','']+entries+['']
            break
    return '\n'.join(prepared)+'\n'
