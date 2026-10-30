"""HTTP integration checks. All model responses here are local fixtures."""
import contextlib
import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app.config import load_env
from app.contracts import parse_json
from app.demo import REQUIREMENTS, fixture
from app.pipeline import Engine
from app.provider import Client, ProviderError, normalize_config
from diagnose_qwen import diagnose, main
from server import make_server

SECRET = "test-private-key"


def response(content='{"ok":true}', **extra):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], **extra}


@contextlib.contextmanager
def api(replies):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, self.headers.get("Authorization"),
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            status, body = replies[len(received) - 1]
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/redirected")
            self.end_headers()
            if callable(body):
                body = body()
            try:
                self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())
            except OSError:
                pass  # The timeout test intentionally closes the client first.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def wait_for(engine, job_id, predicate=lambda j: j["status"] != "running"):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        job = engine.snapshot(job_id)
        if predicate(job):
            return job
        time.sleep(0.01)
    raise AssertionError("Pipeline did not reach expected state")


class OrganizerFormatTests(unittest.TestCase):
    def test_reasoning_and_gateway_escaped_json(self):
        variants = [
            '<think>internal text</think>\n\n{"ok": true}',
            'internal text</think>\n\n{"ok": true}',
            r'internal text\n</think>\n\n{\"ok\": true}',
            '<think>internal text</think>\n```json\n{"ok": true}\n```',
        ]
        for content in variants:
            with self.subTest(content=content):
                self.assertEqual(parse_json(content), {"ok": True})
        self.assertEqual(parse_json('{"value":"</think>"}'), {"value": "</think>"})
        for content in ('preface {"ok": true}', '<think>{"ok": true}', 'text</think>invalid'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_json(content)

    def test_diagnostic_uses_same_parser_as_pipeline(self):
        content = r'internal text\n</think>\n\n{\"ok\": true}'
        with api([(200, response(content))]) as (url, received):
            report = diagnose(normalize_config({"base_url": url, "model": "q"}))
            self.assertEqual(report["status"], "ok")
            self.assertEqual(len(received), 1)


class ConfigurationTests(unittest.TestCase):
    def test_env_precedence_and_optional_key(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            env = Path(temp) / ".env"
            env.write_text('QWEN_BASE_URL=http://localhost/v1\nQWEN_MODEL="from-file"\nQWEN_TIMEOUT=12.5\nQWEN_MAX_TOKENS=345\nQWEN_API_KEY=\nOTHER=value', encoding="utf-8-sig")
            os.environ["QWEN_MODEL"] = "from-process"
            load_env(env)
            config = normalize_config({})
            self.assertEqual(config["model"], "from-process")
            self.assertEqual(config["timeout"], 12.5)
            self.assertEqual(config["max_tokens"], 345)
            self.assertEqual(config["api_key"], "")
            self.assertNotIn("OTHER", os.environ)
            self.assertEqual(normalize_config({"model": "from-ui"})["model"], "from-ui")

    def test_invalid_settings_and_no_invented_model(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                normalize_config({"base_url": "http://localhost/v1"})
            for field in ("timeout", "max_tokens"):
                for value in (0, -1, True, "nan", "inf", "bad", None):
                    with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                        normalize_config({"base_url": "http://localhost/v1", "model": "q", field: value})
            for value in (1.5, "2.5"):
                with self.assertRaises(ValueError):
                    normalize_config({"base_url": "http://localhost/v1", "model": "q", "max_tokens": value})
            for url in ("http://localhost:bad/v1", "http://localhost:0/v1", "http://local host/v1", "http://localhost/v1#secret"):
                with self.assertRaises(ValueError):
                    normalize_config({"base_url": url, "model": "q"})
            with self.assertRaises(ValueError):
                normalize_config({"base_url": "http://localhost/v1", "model": "q", "api_key": SECRET + "\n"})

    def test_config_endpoint_has_no_key_or_default_model(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"QWEN_API_KEY": SECRET}, clear=True):
            server = make_server(port=0, runs_root=temp)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/config") as r:
                    body = json.load(r)
                self.assertTrue(body["has_key"])
                self.assertEqual(body["model"], "")
                self.assertNotIn(SECRET, json.dumps(body))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


class TransportTests(unittest.TestCase):
    def test_routes_limits_no_key_and_legacy_constructor(self):
        for suffix in ("", "/chat/completions", "/chat/completions/"):
            with self.subTest(suffix=suffix), api([(200, response())]) as (url, received):
                config = normalize_config({"base_url": url + suffix, "model": "organizer-model", "timeout": 7, "max_tokens": 321})
                client = Client(config, timeout=9)
                self.assertEqual(client.timeout, 9)
                self.assertEqual(client.complete([], "test", 1), '{"ok":true}')
                self.assertEqual(received[0][0], "/v1/chat/completions")
                self.assertIsNone(received[0][1])
                self.assertEqual(received[0][2]["max_tokens"], 321)
                self.assertIsNone(client.calls[0]["input_tokens"])

    def test_http_errors_are_recorded_without_bodies_or_retries(self):
        for status, code in ((401, "unauthorized"), (403, "forbidden"), (404, "not_found"),
                             (429, "rate_limit"), (500, "server_error"), (503, "server_error"), (302, "http_error")):
            with self.subTest(status=status), api([(status, SECRET.encode())]) as (url, received):
                client = Client(normalize_config({"base_url": url, "model": "q", "api_key": SECRET}))
                with self.assertRaises(ProviderError) as caught:
                    client.complete([], "test", 1)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(len(received), 1)
                self.assertEqual(client.calls[0]["http_status"], status)
                self.assertEqual(client.calls[0]["error_code"], code)
                self.assertNotIn(SECRET, str(caught.exception) + json.dumps(client.calls))
                self.assertNotIn("Authorization", json.dumps(client.calls))

    def test_malformed_empty_and_truncated_responses(self):
        truncated = response("partial", usage={"prompt_tokens": 4, "completion_tokens": 8})
        truncated["choices"][0]["finish_reason"] = "length"
        for body, code in ((b'not-json ' + SECRET.encode(), "invalid_response"), ([], "invalid_response"),
                           ({"choices": []}, "invalid_response"), ({"choices": [None]}, "invalid_response"),
                           (response(None), "invalid_response"), (response("  "), "empty_content"),
                           (truncated, "truncated")):
            with self.subTest(code=code, body=type(body)), api([(200, body)]) as (url, received):
                client = Client(normalize_config({"base_url": url, "model": "q"}))
                with self.assertRaises(ProviderError) as caught:
                    client.complete([], "test", 1)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(client.calls[0]["status"], "error")
                self.assertEqual(len(received), 1)
                self.assertNotIn(SECRET, json.dumps(client.calls))
                if code == "truncated":
                    self.assertEqual(client.calls[0]["output_tokens"], 8)

    def test_network_timeout_and_timeout_forwarding(self):
        for exc, code in ((socket.timeout(), "timeout"), (urllib.error.URLError(socket.timeout()), "timeout"),
                          (urllib.error.URLError(SECRET), "network"), (OSError(SECRET), "network")):
            with self.subTest(code=code), patch("urllib.request.OpenerDirector.open", side_effect=exc) as opened:
                client = Client({"endpoint": "http://localhost/v1/chat/completions", "model": "q", "api_key": "", "timeout": 0.1})
                with self.assertRaises(ProviderError) as caught:
                    client.complete([], "test", 1)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(opened.call_count, 1)
                self.assertEqual(opened.call_args.kwargs["timeout"], 0.1)
                self.assertNotIn(SECRET, json.dumps(client.calls))

    def test_real_socket_read_timeout(self):
        def delayed():
            time.sleep(0.15)
            return response()
        with api([(200, delayed)]) as (url, received):
            client = Client(normalize_config({"base_url": url, "model": "q", "timeout": 0.03}))
            with self.assertRaises(ProviderError) as caught:
                client.complete([], "test", 1)
            self.assertEqual(caught.exception.code, "timeout")
            self.assertEqual(len(received), 1)
            self.assertEqual(client.calls[0]["error_code"], "timeout")

    def test_bad_usage_is_unknown(self):
        with api([(200, response(usage={"prompt_tokens": True, "completion_tokens": -1}))]) as (url, _):
            client = Client(normalize_config({"base_url": url, "model": "q"}))
            client.complete([], "test", 1)
            self.assertIsNone(client.calls[0]["input_tokens"])
            self.assertIsNone(client.calls[0]["output_tokens"])


class DiagnosticAndPipelineTests(unittest.TestCase):
    def test_diagnostic_and_cli_saved_metrics(self):
        with api([(200, response(usage={"prompt_tokens": 3, "completion_tokens": 5}))]) as (url, received), tempfile.TemporaryDirectory() as temp:
            report_path = Path(temp) / "report.json"
            with patch.dict(os.environ, {"QWEN_BASE_URL": url, "QWEN_MODEL": "local-fixture", "QWEN_API_KEY": SECRET, "QWEN_MAX_TOKENS": "321", "QWEN_TIMEOUT": "2"}, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--report", str(report_path)]), 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["metrics"]["model_calls"], 1)
            self.assertEqual(report["metrics"]["input_tokens"], 3)
            self.assertIn("seconds", report["metrics"])
            self.assertEqual(received[0][2]["max_tokens"], 321)
            self.assertNotIn(SECRET, output.getvalue() + report_path.read_text(encoding="utf-8"))

    def test_diagnostic_rejects_wrong_format_without_retry(self):
        for content in ('hello', '{"ok":1}', '{"ok":false}', '{"ok":true,"extra":1}', '[]'):
            with self.subTest(content=content), api([(200, response(content))]) as (url, received):
                report = diagnose(normalize_config({"base_url": url, "model": "q"}))
                self.assertEqual(report["error_code"], "diagnostic_format")
                self.assertEqual(report["metrics"]["calls"][0]["status"], "error")
                self.assertEqual(len(received), 1)

    def test_diagnostic_provider_error_has_safe_metrics(self):
        with api([(401, SECRET.encode())]) as (url, received):
            report = diagnose(normalize_config({"base_url": url, "model": "q", "api_key": SECRET}))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["error_code"], "unauthorized")
            self.assertEqual(report["metrics"]["model_calls"], 1)
            self.assertNotIn(SECRET, json.dumps(report))
            self.assertEqual(len(received), 1)

    def test_diagnostic_configuration_error_without_request(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True), patch("diagnose_qwen.load_env"), contextlib.redirect_stdout(io.StringIO()):
            dest = Path(temp) / "report.json"
            self.assertEqual(main(["--report", str(dest)]), 1)
            report = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "configuration_error")
            self.assertEqual(report["metrics"]["model_calls"], 0)

    def test_full_http_analysis_with_question_gate_and_artifacts(self):
        analysis, design = fixture()
        replies = [(200, response(json.dumps(obj), usage={"prompt_tokens": 10, "completion_tokens": 20})) for obj in (analysis, design)]
        with api(replies) as (url, received), tempfile.TemporaryDirectory() as temp:
            engine = Engine(temp, design_schema_version="1.0")
            job_id = engine.create(REQUIREMENTS, normalize_config({"base_url": url, "model": "local-fixture", "api_key": SECRET}))
            job = wait_for(engine, job_id)
            self.assertEqual(job["status"], "awaiting_answers")
            engine.continue_run(job_id, {"Q-001": "Только открытое приложение"})
            job = wait_for(engine, job_id)
            self.assertEqual(job["status"], "complete", job["error"])
            expected = {"analysis.json", "design.json", "system-analysis.md", "acceptance-tests.md", "quality-report.json"}
            self.assertTrue(expected <= set(job["files"]))
            for name in job["files"]:
                content = (Path(temp) / job_id / name).read_text(encoding="utf-8")
                self.assertTrue(content)
                self.assertNotIn(SECRET, content)
            self.assertEqual(len(received), 2)
            self.assertEqual(job["report"]["metrics"]["input_tokens"], 20)
            self.assertEqual(job["report"]["metrics"]["output_tokens"], 40)

    def test_provider_failure_saved_in_pipeline_report(self):
        with api([(429, SECRET.encode())]) as (url, received), tempfile.TemporaryDirectory() as temp:
            engine = Engine(temp)
            job_id = engine.create(REQUIREMENTS, normalize_config({"base_url": url, "model": "q"}))
            job = wait_for(engine, job_id)
            self.assertEqual(job["status"], "failed")
            report = json.loads((Path(temp) / job_id / "failure-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["metrics"]["calls"][0]["error_code"], "rate_limit")
            self.assertEqual(len(received), 1)
            self.assertNotIn(SECRET, json.dumps(report))

    def test_cancellation_keeps_actual_call_metrics(self):
        started, release = threading.Event(), threading.Event()
        class BlockingClient:
            def __init__(self, config):
                self.calls = []
            def complete(self, messages, stage, attempt):
                started.set()
                release.wait(3)
                self.calls.append({"stage": stage, "attempt": attempt, "status": "ok", "seconds": 0.1, "input_tokens": 5, "output_tokens": 7})
                return json.dumps(fixture()[0])
        with tempfile.TemporaryDirectory() as temp:
            engine = Engine(temp, BlockingClient)
            job_id = engine.create(REQUIREMENTS, {})
            self.assertTrue(started.wait(2))
            engine.cancel(job_id)
            with self.assertRaises(ValueError):
                engine.create(REQUIREMENTS, {})
            release.set()
            job = wait_for(engine, job_id, lambda j: bool(j["files"]))
            self.assertEqual(job["status"], "cancelled")
            self.assertEqual(job["report"]["metrics"]["model_calls"], 1)
            self.assertEqual(job["report"]["metrics"]["output_tokens"], 7)
            self.assertTrue((Path(temp) / job_id / "cancellation-report.json").exists())


if __name__ == "__main__":
    unittest.main()
