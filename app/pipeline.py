import copy
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import render_documents, write_files
from .contracts import SYSTEM_PROMPT, analysis_prompt, design_prompt, parse_json, validate_analysis, validate_design
from .demo import REQUIREMENTS, fixture
from .provider import Client


class Engine:
    def __init__(self, root, client_factory=Client, design_schema_version="2.0"):
        if design_schema_version not in ("1.0", "2.0"):
            raise ValueError("Unsupported design schema version")
        self.design_schema_version = design_schema_version
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.client_factory = client_factory
        self.jobs = {}
        self.lock = threading.RLock()

    def _set(self, job, **values):
        with self.lock:
            job.update(values)

    def _event(self, job, text):
        with self.lock:
            job["events"].append({"time": datetime.now(timezone.utc).isoformat(), "text": text})

    def create(self, requirements, config=None, demo=False):
        if not demo and self.design_schema_version == "2.0":
            from .specifications import require_validation_tools
            require_validation_tools()
        with self.lock:
            if any(j["_busy"] or j["status"] == "awaiting_answers" for j in self.jobs.values()):
                raise ValueError("Уже есть незавершенный запуск. Завершите его или отмените")
            if len(self.jobs) >= 20:
                finished = next((key for key, j in self.jobs.items() if j["status"] in ("complete", "failed", "cancelled")), None)
                if finished:
                    del self.jobs[finished]
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "status": "running", "stage": "analysis", "demo": demo,
                   "created_at": datetime.now(timezone.utc).isoformat(), "events": [], "error": None,
                   "requirements": REQUIREMENTS if demo else requirements, "analysis": None, "design": None,
                   "answers": {}, "_answers_submitted": False, "files": [], "report": None, "_started": time.monotonic(), "_active_seconds": 0.0,
                   "_client": None if demo else self.client_factory(config), "_busy": True, "_cancelled": False}
            self.jobs[job_id] = job
        threading.Thread(target=self._initial, args=(job,), daemon=True).start()
        return job_id

    def snapshot(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            return copy.deepcopy({key: value for key, value in job.items() if not key.startswith("_")})

    def _ensure_active(self, job):
        if job["_cancelled"]:
            raise ValueError("Запуск отменен")

    def _structured(self, job, prompt, stage, validator):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        for attempt in (1, 2):
            self._ensure_active(job)
            self._event(job, f"{stage}: обращение к Qwen, попытка {attempt}/2")
            content = job["_client"].complete(messages, stage, attempt)
            self._ensure_active(job)
            try:
                data = parse_json(content)
                issues = validator(data)
            except (ValueError, TypeError, RecursionError):
                issues = ["Ответ не является корректным JSON-объектом"]
            calls = job["_client"].calls
            if calls:
                calls[-1]["validation_status"] = "error" if issues else "ok"
                calls[-1]["validation_issues"] = len(issues)
            if not issues:
                return data
            self._event(job, f"Проверка структуры: обнаружено проблем — {len(issues)}")
            if attempt == 2:
                raise ValueError("Модель не исправила структуру: " + "; ".join(issues[:8]))
            messages.extend([{"role": "assistant", "content": content}, {"role": "user", "content": "Исправь только перечисленные ошибки, сохрани смысл. Верни полный JSON. Ошибки:\n" + "\n".join(issues[:20])}])

    def _initial(self, job):
        start = time.monotonic()
        try:
            self._event(job, "Учебный пример: загружаем заранее подготовленные данные, без вызова модели" if job["demo"] else "Начинаем анализ исходных требований")
            if job["demo"]:
                analysis, design = fixture()
                issues = validate_analysis(analysis, job["requirements"]) + validate_design(design, analysis)
                if issues:
                    raise ValueError("Ошибка учебного примера: " + "; ".join(issues))
                self._set(job, analysis=analysis, design=design)
                self._finish(job, start)
            else:
                analysis = self._structured(job, analysis_prompt(job["requirements"]), "Анализ", lambda data: validate_analysis(data, job["requirements"]))
                self._set(job, analysis=analysis)
                self._ensure_active(job)
                if analysis["questions"]:
                    self._event(job, "Нужны уточнения. Можно ответить или явно продолжить с допущениями")
                    with self.lock:
                        if job["_cancelled"]:
                            self._save_cancelled(job, start)
                            return
                        report = {"status":"awaiting_answers", "metrics":self._metrics(job, start), "limitations":["Analysis only; design and application tests not executed"]}
                        files = {"analysis.json":json.dumps(analysis,ensure_ascii=False,indent=2), "pending-report.json":json.dumps(report,ensure_ascii=False,indent=2)}
                        write_files(self.root / job["id"], files)
                        job["_active_seconds"] += time.monotonic() - start
                        job.update(status="awaiting_answers", stage="questions", _busy=False, report=report, files=sorted(files))
                else:
                    self._design(job, start)
        except Exception as exc:
            self._fail(job, exc, start)

    def continue_run(self, job_id, answers, accept_assumptions=False):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] != "awaiting_answers" or job["_busy"]:
                raise ValueError("Сейчас запуск не ожидает ответов")
            if not isinstance(answers, dict) or any(not isinstance(v, str) or len(v) > 5000 for v in answers.values()):
                raise ValueError("Ответы должны быть текстом длиной до 5000 символов")
            expected = {q["id"] for q in job["analysis"]["questions"]}
            if set(answers) - expected:
                raise ValueError("Неизвестный идентификатор вопроса")
            missing = [q for q in expected if not answers.get(q, "").strip()]
            if missing and not accept_assumptions:
                raise ValueError("Ответьте на вопросы или подтвердите продолжение с допущениями")
            job.update(answers={k: v.strip() for k, v in answers.items()}, _answers_submitted=True, status="running", stage="design", _busy=True)
        self._event(job, "Пользователь продолжил с допущениями" if missing else "Получены ответы пользователя")
        threading.Thread(target=self._resume, args=(job,), daemon=True).start()

    def _resume(self, job):
        start = time.monotonic()
        try:
            self._design(job, start)
        except Exception as exc:
            self._fail(job, exc, start)

    def _design(self, job, start):
        self._set(job, stage="design")
        self._event(job, "Подготавливаем системный анализ и сценарии приемки")
        def validate_generated(data):
            issues = validate_design(data, job["analysis"])
            if self.design_schema_version == "2.0" and data.get("schema_version") != "2.0":
                issues.append("New generations require schema_version=2.0; legacy remains readable")
            return issues
        design = self._structured(job, design_prompt(job["requirements"], job["analysis"], job["answers"], self.design_schema_version), "Проектирование", validate_generated)
        self._set(job, design=design)
        self._finish(job, start)

    def _metrics(self, job, start):
        calls = [] if job["_client"] is None else copy.deepcopy(job["_client"].calls)
        def tokens(field):
            return sum(c[field] for c in calls) if calls and all(c[field] is not None for c in calls) else None
        return {"wall_seconds": round(time.monotonic() - job["_started"], 3),
                "processing_seconds": round(job["_active_seconds"] + time.monotonic() - start, 3),
                "model_calls": len(calls), "repair_attempts": sum(c["attempt"] > 1 for c in calls),
                "input_tokens": tokens("input_tokens"), "output_tokens": tokens("output_tokens"), "calls": calls,
                "token_note": "Только usage от API; отсутствие данных не считается нулевым расходом",
                "manual_actions": [{"type": "answer" if job["answers"].get(q["id"]) else "assumption", "question_id": q["id"]} for q in (job["analysis"] or {}).get("questions", [])] if job["_answers_submitted"] else []}

    def _finish(self, job, start):
        self._ensure_active(job)
        self._set(job, stage="validation")
        self._event(job, "Проверяем структуру, цитаты, ссылки и покрытие требований сценариями")
        issues = validate_analysis(job["analysis"], job["requirements"]) + validate_design(job["design"], job["analysis"])
        if issues:
            raise ValueError("Ошибка проверки: " + "; ".join(issues[:8]))
        report = {"mode": "prepared_example" if job["demo"] else "qwen_generation", "status": "structural_checks_passed",
                  "checks": ["Формат обязательных полей", "Уникальные FR-ID и TC-ID", "Цитаты найдены в исходном тексте", "Нет неизвестных FR-ссылок", "Каждое FR связано хотя бы с одним сценарием проверки"],
                  "requirements_count": len(job["analysis"]["functional_requirements"]), "test_scenarios_count": len(job["design"]["test_scenarios"]),
                  "scenario_coverage_percent": 100, "issues": [],
                  "limitations": ["Покрытие означает наличие ссылок, а не качество или выполнение тестов", "Смысловую полноту и корректность должен проверить человек", "Код приложения, сборка, UI-тесты и CVE-сканирование не выполнялись"],
                  "metrics": self._metrics(job, start)}
        documents = render_documents(job["requirements"], job["analysis"], job["design"], job["answers"], report, job["demo"])
        self._ensure_active(job)
        write_files(self.root / job["id"], documents)
        self._event(job, "Готово. Документы сохранены; сценарии тестирования описаны, но не выполнялись")
        with self.lock:
            if job["_cancelled"]:
                self._save_cancelled(job, start)
                return
            job.update(status="complete", stage="complete", report=report, files=sorted(documents), _busy=False, _client=None)

    def _fail(self, job, exc, start):
        # Raw unexpected exception details are not exposed to the browser.
        message = str(exc) if isinstance(exc, ValueError) else "Внутренняя ошибка обработки. Проверьте настройки и повторите запуск"
        from .provider import ProviderError
        if isinstance(exc, ProviderError):
            message = str(exc)
        with self.lock:
            if job["_cancelled"]:
                self._save_cancelled(job, start)
                return
            report = {"status": "failed", "error": message, "metrics": self._metrics(job, start)}
            self._event(job, message)
        files = {"failure-report.json": json.dumps(report, ensure_ascii=False, indent=2)}
        if job["analysis"]:
            files["analysis.json"] = json.dumps(job["analysis"], ensure_ascii=False, indent=2)
        write_files(self.root / job["id"], files)
        with self.lock:
            if job["_cancelled"]:
                self._save_cancelled(job, start)
            else:
                job.update(status="failed", error=message, report=report, files=sorted(files), _busy=False, _client=None)

    def _save_cancelled(self, job, start):
        report = {"status": "cancelled", "metrics": self._metrics(job, start)}
        name = "cancellation-report.json"
        write_files(self.root / job["id"], {name: json.dumps(report, ensure_ascii=False, indent=2)})
        job.update(report=report, files=[name], _client=None, _busy=False)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] not in ("running", "awaiting_answers"):
                raise ValueError("Этот запуск уже завершен")
            job.update(_cancelled=True, status="cancelled", stage="cancelled")
            # A request already sent to the provider may still finish and consume tokens.
            if not job["_busy"]:
                self._save_cancelled(job, time.monotonic())
        self._event(job, "Отменено локально. Уже отправленный запрос к API может завершиться и расходовать токены")
