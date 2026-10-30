"""Run: python server.py. Open http://127.0.0.1:8765."""
import argparse
import io
import json
import os
import secrets
import sys
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.config import load_env
from app.demo import REQUIREMENTS
from app.pipeline import Engine
from app.provider import normalize_config

ROOT = Path(__file__).resolve().parent


def make_server(host="127.0.0.1", port=8765, runs_root=None, client_factory=None):
    engine = Engine(runs_root or ROOT / "runs", **({"client_factory": client_factory} if client_factory else {}))
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def parse_request(self):
            if not super().parse_request():
                return False
            try:
                hostname = urllib.parse.urlsplit("//" + self.headers.get("Host", "")).hostname
            except ValueError:
                hostname = None
            allowed = {"localhost", "127.0.0.1", "::1"}
            if host not in ("0.0.0.0", "::"):
                allowed.add(host)
            if hostname not in allowed:
                self.send_error(403, "Local host only")
                return False
            return True

        def log_message(self, fmt, *args):
            # No request bodies, keys, prompts or provider responses in console logs.
            pass

        def send_bytes(self, data, kind="application/json; charset=utf-8", status=200, attachment=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if attachment:
                self.send_header("Content-Disposition", 'attachment; filename="' + attachment + '"')
            self.end_headers()
            self.wfile.write(data)

        def json(self, data, status=200):
            self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), status=status)

        def do_GET(self):
            try:
                path = urllib.parse.urlsplit(self.path).path
                static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
                if path in static:
                    name, mime = static[path]
                    return self.send_bytes((ROOT / "static" / name).read_bytes(), mime)
                if path == "/api/config":
                    return self.json({"csrf_token": token, "base_url": os.environ.get("QWEN_BASE_URL", ""), "model": os.environ.get("QWEN_MODEL", ""), "has_key": bool(os.environ.get("QWEN_API_KEY")), "example_requirements": REQUIREMENTS})
                parts = path.strip("/").split("/")
                if len(parts) >= 3 and parts[:2] == ["api", "runs"]:
                    job = engine.snapshot(parts[2])
                    if len(parts) == 3:
                        return self.json(job)
                    if len(parts) == 4 and parts[3] == "archive":
                        if not job["files"]:
                            raise ValueError("Файлы пока не готовы")
                        buf = io.BytesIO()
                        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
                            for name in job["files"]:
                                archive.write(engine.root / job["id"] / name, name)
                        return self.send_bytes(buf.getvalue(), "application/zip", attachment="pipeline-result.zip")
                    if len(parts) == 5 and parts[3] == "files" and parts[4] in job["files"]:
                        name = parts[4]
                        data = (engine.root / job["id"] / name).read_bytes()
                        if urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("preview") == ["1"]:
                            return self.json({"content": data.decode("utf-8-sig")})
                        return self.send_bytes(data, "application/octet-stream", attachment=name)
                self.json({"error": "Не найдено"}, 404)
            except KeyError:
                self.json({"error": "Запуск не найден. После перезапуска сервера сохраненные файлы доступны в папке runs"}, 404)
            except ValueError as exc:
                self.json({"error": str(exc)}, 400)

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get("X-Pipeline-Token", ""), token):
                return self.json({"error": "Обновите страницу и повторите действие"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 200_000:
                    raise ValueError("Размер запроса должен быть от 1 до 200000 байт")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Ожидался объект запроса")
                path = urllib.parse.urlsplit(self.path).path
                if path == "/api/demo":
                    return self.json({"id": engine.create(REQUIREMENTS, demo=True)}, 202)
                if path == "/api/runs":
                    requirements = body.get("requirements", "")
                    if not isinstance(requirements, str) or not 30 <= len(requirements.strip()) <= 20000:
                        raise ValueError("Введите от 30 до 20000 символов требований")
                    config_data = body.get("config", {})
                    if not isinstance(config_data, dict):
                        raise ValueError("Некорректные настройки подключения")
                    config = normalize_config(config_data)
                    return self.json({"id": engine.create(requirements.strip(), config, context=body.get('source_summary'))}, 202)
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "runs"]:
                    if parts[3] == "resume-design":
                        config_data = body.get('config', {})
                        if not isinstance(config_data, dict):
                            raise ValueError('Invalid connection settings')
                        return self.json({'id': engine.resume_design(parts[2], normalize_config(config_data))}, 202)
                    if parts[3] == "continue":
                        engine.continue_run(parts[2], body.get("answers", {}), body.get("accept_assumptions") is True)
                        return self.json({"ok": True}, 202)
                    if parts[3] == "cancel":
                        engine.cancel(parts[2])
                        return self.json({"ok": True})
                self.json({"error": "Не найдено"}, 404)
            except (ValueError, TypeError, RecursionError, FileNotFoundError) as exc:
                self.json({"error": str(exc) if isinstance(exc, ValueError) else "Некорректный запрос"}, 400)
            except KeyError:
                self.json({"error": "Запуск не найден"}, 404)

    server = ThreadingHTTPServer((host, port), Handler)
    server.engine = engine
    return server


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    parser = argparse.ArgumentParser(description="Локальный пайплайн системного анализа")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"Откройте http://127.0.0.1:{args.port} — для остановки нажмите Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
