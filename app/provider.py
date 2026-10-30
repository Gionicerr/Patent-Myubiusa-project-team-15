"""OpenAI-compatible HTTP transport. Keys are never included in logs/errors."""
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


class ProviderError(Exception):
    pass


def normalize_config(data):
    base = str(data.get("base_url", "")).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Укажите адрес API вида http://адрес:порт/v1, без пароля и параметров в URL")
    model = str(data.get("model", "")).strip()
    if not model or len(model) > 200:
        raise ValueError("Укажите точное имя модели из инструкции организаторов")
    key = str(data.get("api_key", "")).strip() or os.environ.get("QWEN_API_KEY", "")
    if "\n" in key or "\r" in key:
        raise ValueError("Ключ содержит недопустимый перенос строки")
    endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
    return {"endpoint": endpoint, "model": model, "api_key": key}


class Client:
    def __init__(self, config, timeout=180):
        self.config = config
        self.timeout = timeout
        self.calls = []

    def complete(self, messages, stage, attempt):
        payload = {"model": self.config["model"], "messages": messages, "temperature": 0.2, "max_tokens": 6500, "stream": False}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config["api_key"]:
            headers["Authorization"] = "Bearer " + self.config["api_key"]
        req = urllib.request.Request(self.config["endpoint"], data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        record = {"stage": stage, "attempt": attempt, "status": "started", "input_tokens": None, "output_tokens": None}
        self.calls.append(record)
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError("Ответ модели слишком большой")
            body = json.loads(raw)
            usage = body.get("usage") or {}
            for target, source in [("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")]:
                value = usage.get(source)
                record[target] = value if isinstance(value, int) and value >= 0 else None
            choice = body["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ProviderError("Ответ обрезан лимитом токенов. Сократите требования или увеличьте max_tokens в app/provider.py")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("Модель вернула пустой ответ")
            record["status"] = "ok"
            return content
        except urllib.error.HTTPError as exc:
            # Do not echo provider bodies: they can contain credentials or proxy details.
            meanings = {401: "Проверьте ключ", 403: "Нет доступа", 404: "Проверьте адрес API и имя модели", 429: "Лимит запросов; попробуйте позже"}
            raise ProviderError(f"API вернул HTTP {exc.code}. " + meanings.get(exc.code, "Проверьте состояние сервера модели")) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            raise ProviderError("API недоступен или истекло время ожидания. Проверьте сеть; возможно, доступ есть только с VM организаторов") from None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeError):
            raise ProviderError("API вернул неожиданный формат. Нужен совместимый маршрут /v1/chat/completions") from None
        finally:
            record["seconds"] = round(time.monotonic() - start, 3)
            if record["status"] == "started":
                record["status"] = "error"
