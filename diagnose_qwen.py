"""One small Qwen request through the production client, with a safe report."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

from app.config import ROOT, load_env
from app.contracts import parse_json
from app.provider import Client, ProviderError, normalize_config


def diagnose(config):
    client = Client(config)
    started = time.monotonic()
    report = {"status": "failed", "model": config["model"]}
    try:
        content = client.complete([
            {"role": "user", "content": 'Return only this JSON object, without explanation: {"ok": true}'}
        ], "diagnostic", 1)
        try:
            data = parse_json(content)
            valid = isinstance(data, dict) and set(data) == {"ok"} and data["ok"] is True
        except (ValueError, AttributeError, RecursionError):
            valid = False
        if not valid:
            client.calls[-1].update(status="error", error_code="diagnostic_format",
                                    error="Диагностика ожидает JSON-объект с единственным полем ok: true")
            raise ProviderError("Диагностика ожидает JSON-объект с единственным полем ok: true", "diagnostic_format")
        report["status"] = "ok"
    except ProviderError as exc:
        report.update(error_code=exc.code, error=str(exc))
    report["metrics"] = {"seconds": round(time.monotonic() - started, 3), "model_calls": len(client.calls),
                         "input_tokens": client.calls[0]["input_tokens"], "output_tokens": client.calls[0]["output_tokens"],
                         "calls": client.calls, "token_note": "null означает неизвестный расход; повторных запросов нет"}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Проверка подключения Qwen: один запрос, без повторов")
    parser.add_argument("--report", type=Path, help="Путь JSON-отчёта (по умолчанию runs/diagnostic-<id>.json)")
    args = parser.parse_args(argv)
    load_env()
    try:
        report = diagnose(normalize_config({}))
    except ValueError as exc:
        report = {"status": "configuration_error", "error": str(exc),
                  "metrics": {"model_calls": 0, "input_tokens": None, "output_tokens": None}}
    destination = args.report or ROOT / "runs" / ("diagnostic-" + uuid.uuid4().hex + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    destination.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
