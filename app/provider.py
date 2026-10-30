"""OpenAI-compatible transport. No retries or raw provider errors in reports."""
import http.client
import json
import math
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


class ProviderError(Exception):
    def __init__(self, message, code="provider_error"):
        super().__init__(message)
        self.code = code


def _number(value, name, integer=False):
    try:
        if isinstance(value, bool):
            raise ValueError
        result = int(str(value)) if integer else float(value)
        if not math.isfinite(result) or result <= 0:
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{name}: требуется положительное " + ("целое число" if integer else "число секунд")) from None


def normalize_config(data):
    base = str(data.get("base_url", os.environ.get("QWEN_BASE_URL", ""))).strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(base)
        valid = (parsed.scheme in ("http", "https") and parsed.hostname and not
                 (parsed.username or parsed.password or parsed.query or parsed.fragment)
                 and parsed.port != 0 and not any(c.isspace() or ord(c) < 32 for c in base))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Укажите QWEN_BASE_URL вида http://адрес:порт/v1, без пароля и параметров в URL")
    model = data.get("model", os.environ.get("QWEN_MODEL", ""))
    if not isinstance(model, str):
        raise ValueError("Укажите QWEN_MODEL: точное имя модели из инструкции организаторов")
    model = model.strip()
    if not model or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise ValueError("Укажите QWEN_MODEL: точное имя модели из инструкции организаторов")
    raw_key = str(data.get("api_key", ""))
    key = raw_key if raw_key.strip() else os.environ.get("QWEN_API_KEY", "")
    if any(ord(c) < 32 or ord(c) > 126 for c in raw_key + key):
        raise ValueError("Ключ содержит недопустимые символы")
    key = key.strip()
    endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
    return {"endpoint": endpoint, "model": model, "api_key": key,
            "timeout": _number(data.get("timeout", os.environ.get("QWEN_TIMEOUT", "180")), "QWEN_TIMEOUT"),
            "max_tokens": _number(data.get("max_tokens", os.environ.get("QWEN_MAX_TOKENS", "6500")), "QWEN_MAX_TOKENS", True)}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials/prompts to a different address.


class Client:
    def __init__(self, config, timeout=None):
        self.config = dict(config)
        self.timeout = _number(timeout if timeout is not None else config.get("timeout", os.environ.get("QWEN_TIMEOUT", "180")), "QWEN_TIMEOUT")
        self.max_tokens = _number(config.get("max_tokens", os.environ.get("QWEN_MAX_TOKENS", "6500")), "QWEN_MAX_TOKENS", True)
        self.calls = []

    def complete(self, messages, stage, attempt):
        try:
            return self._complete(messages, stage, attempt)
        except ProviderError as exc:
            self.calls[-1].update(error_code=exc.code, error=str(exc))
            raise

    def _complete(self, messages, stage, attempt):
        limit = self.max_tokens
        payload = {"model": self.config["model"], "messages": messages, "temperature": 0.2, "max_tokens": limit, "stream": False}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.get("api_key"):
            headers["Authorization"] = "Bearer " + self.config["api_key"]
        record = {"stage": stage, "attempt": attempt, "status": "started", "input_tokens": None, "output_tokens": None,
                  "model": self.config["model"], "max_tokens": limit}
        self.calls.append(record)
        start = time.monotonic()
        try:
            req = urllib.request.Request(self.config["endpoint"], data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError("Ответ модели слишком большой", "response_too_large")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise TypeError
            usage = body.get("usage")
            if isinstance(usage, dict):
                for target, source in [("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")]:
                    value = usage.get(source)
                    record[target] = value if type(value) is int and value >= 0 else None
            choice = body["choices"][0]
            reason = choice.get("finish_reason")
            record["finish_reason"] = reason if reason in (None, "stop", "length", "content_filter", "tool_calls", "function_call") else "unknown"
            if reason == "length":
                raise ProviderError("Ответ обрезан лимитом токенов. Увеличьте QWEN_MAX_TOKENS или сократите требования", "truncated")
            if reason not in (None, "stop"):
                raise ProviderError("API не завершил текстовый ответ обычным образом", "finish_reason")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            if not content.strip():
                raise ProviderError("Модель вернула пустой ответ", "empty_content")
            record["status"] = "ok"
            return content
        except urllib.error.HTTPError as exc:
            record["http_status"] = exc.code
            meanings = {401: ("unauthorized", "Проверьте ключ"), 403: ("forbidden", "Нет доступа"),
                        404: ("not_found", "Проверьте адрес API и имя модели"),
                        429: ("rate_limit", "Лимит запросов; попробуйте позже")}
            code, message = meanings.get(exc.code, ("server_error" if exc.code >= 500 else "http_error", "Проверьте состояние сервера модели и маршрут API"))
            exc.close()
            raise ProviderError(f"API вернул HTTP {exc.code}. {message}", code) from None
        except (TimeoutError, socket.timeout):
            raise ProviderError("Истекло время ожидания API. Проверьте QWEN_TIMEOUT", "timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError("Истекло время ожидания API. Проверьте QWEN_TIMEOUT", "timeout") from None
            raise ProviderError("API недоступен. Проверьте адрес и сеть; возможно, доступ есть только с ВМ организаторов", "network") from None
        except (OSError, http.client.HTTPException):
            raise ProviderError("Ошибка сетевого обмена с API", "network") from None
        except (KeyError, IndexError, TypeError, AttributeError, ValueError, UnicodeError, RecursionError):
            raise ProviderError("API вернул неожиданный формат. Нужен совместимый маршрут /chat/completions", "invalid_response") from None
        finally:
            record["seconds"] = round(time.monotonic() - start, 3)
            if record["status"] == "started":
                record["status"] = "error"
