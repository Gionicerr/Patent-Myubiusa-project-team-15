import csv
import io
import json
from pathlib import Path


def _bullets(items):
    return "\n".join("- " + str(item).replace("\n", " ") for item in items) or "Не задано / неприменимо."


def render_documents(requirements, analysis, design, answers, report, demo=False):
    banner = "> УЧЕБНЫЙ ПРИМЕР: заранее подготовленные данные, Qwen не вызывалась.\n\n" if demo else "> Черновик, сформированный ИИ. Требует содержательной проверки человеком.\n\n"
    a, d = analysis, design
    parts = [banner + "# " + a["title"], "## Назначение\n" + a["purpose"], "## Цели\n" + _bullets(a["goals"]), "## Границы\n" + _bullets(a["scope"]) + "\n\n" + d["boundaries"], "## Роли и права"]
    for role in a["roles"]:
        parts.append("### " + role["name"] + "\n" + _bullets(role["permissions"]))
    parts.append("## Функциональные требования")
    for fr in a["functional_requirements"]:
        parts.append(f"### {fr['id']}: {fr['text']}\nОснование: {fr['source_quote']}\n\nКритерии приемки:\n" + _bullets(fr["acceptance_criteria"]))
    parts.append("## Нефункциональные требования\n" + _bullets([n["text"] + " Основание: " + n["source_quote"] for n in a["nonfunctional_requirements"]]))
    parts.append("## Допущения, не подтвержденные заказчиком\n" + _bullets([f"{x['id']}: {x['text']} ({x['reason']})" for x in a["assumptions"]]))
    parts.append("## Уточнения и ответы")
    for q in a["questions"]:
        answer = answers.get(q["id"], "").strip()
        parts.append(f"### {q['id']}: {q['question']}\nВлияние: {q['impact']}\n\n" + ("Ответ пользователя: " + answer if answer else "Ответ не получен. Рабочее допущение: " + q["default_assumption"]))
    parts.append("## Пользовательские сценарии")
    for flow in d["user_flows"]:
        parts.append("### " + flow["role"] + "\nТребования: " + ", ".join(flow["requirement_ids"]) + "\n\n" + _bullets(flow["steps"]))
    parts.append("## Компоненты\n" + _bullets([f"{c['name']} — {c['responsibility']}. Технология: {c['technology']}" for c in d["components"]]))
    parts.append("## Модель данных")
    for entity in d["data_model"]:
        parts.append("### " + entity["entity"] + "\n" + _bullets(entity["fields"]) + "\n\nСвязи:\n" + _bullets(entity["relations"]))
    parts.append("## Проект API-контрактов\nЭто описание, а не валидированная OpenAPI-спецификация.")
    for endpoint in d["api"]:
        parts.append(f"### {endpoint['method']} {endpoint['path']}\n{endpoint['description']}\n\nЗапрос: {endpoint['request']}\n\nОтвет: {endpoint['response']}\n\nДоступ: {endpoint['auth']}\n\nТребования: " + ", ".join(endpoint["requirement_ids"]))
    parts.append("## События и интеграции\n" + _bullets([f"{e['name']}: {e['schema']}. Доставка: {e['delivery']}" for e in d["events"]]))
    parts.append("## Валидация и обработка ошибок\n" + _bullets(d["validation_and_errors"]))
    parts.append("## Рекомендации по безопасности\nСканирование кода и проверка CVE не выполнялись.\n\n" + _bullets(d["security_recommendations"]))
    parts.append("## Риски\n" + _bullets([r["risk"] + " → " + r["mitigation"] for r in a["risks"]]))
    parts.append("## Ограничения и открытые вопросы\n" + _bullets(d["limitations"]))
    tests = [banner + "# План приемочного тестирования", "Это описания сценариев. Тесты приложения не запускались."]
    for test in d["test_scenarios"]:
        tests.append(f"## {test['id']} — {', '.join(test['requirement_ids'])}\nТип: {test['type']}\n\nДано: {test['given']}\n\nКогда: {test['when']}\n\nТогда: {test['then']}")
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["requirement_id", "requirement", "test_scenario_ids", "api_endpoints"])
    for fr in a["functional_requirements"]:
        # Prevent spreadsheet formula execution when the CSV is opened in Excel.
        label = fr["text"]
        if label.lstrip().startswith(("=", "+", "-", "@")):
            label = "'" + label
        writer.writerow([fr["id"], label, "; ".join(t["id"] for t in d["test_scenarios"] if fr["id"] in t["requirement_ids"]), "; ".join(e["method"] + " " + e["path"] for e in d["api"] if fr["id"] in e["requirement_ids"])])
    dump = lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return {"requirements.md": banner + "# Исходные требования\n\n" + requirements,
            "analysis.json": dump(a), "design.json": dump(d), "answers.json": dump(answers),
            "system-analysis.md": "\n\n".join(parts) + "\n", "acceptance-tests.md": "\n\n".join(tests) + "\n",
            "traceability.csv": out.getvalue(), "quality-report.json": dump(report)}


def write_files(directory, documents):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    for name, content in documents.items():
        (root / name).write_text(content, encoding="utf-8-sig" if name.endswith(".csv") else "utf-8")
