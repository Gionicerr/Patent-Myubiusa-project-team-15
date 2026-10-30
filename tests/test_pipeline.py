import copy
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app.contracts import parse_json, validate_analysis, validate_design
from app.demo import REQUIREMENTS, fixture
from app.pipeline import Engine
from app.provider import Client, ProviderError, normalize_config
from server import make_server


def wait(engine, job_id):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        state = engine.snapshot(job_id)
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("Pipeline did not finish")


class ContractsTests(unittest.TestCase):
    def setUp(self):
        self.a, self.d = fixture()

    def test_fixture_valid(self):
        self.assertEqual(validate_analysis(self.a, REQUIREMENTS), [])
        self.assertEqual(validate_design(self.d, self.a), [])

    def test_invented_source_quote_rejected(self):
        self.a["functional_requirements"][0]["source_quote"] = "Система должна отправлять деньги"
        self.assertTrue(any("source_quote" in issue for issue in validate_analysis(self.a, REQUIREMENTS)))

    def test_duplicate_ids_rejected(self):
        self.a["functional_requirements"][1]["id"] = "FR-001"
        self.assertTrue(validate_analysis(self.a, REQUIREMENTS))

    def test_uncovered_and_unknown_requirements_rejected(self):
        self.d["test_scenarios"][0]["requirement_ids"] = ["FR-999"]
        issues = validate_design(self.d, self.a)
        self.assertTrue(any("FR-999" in s for s in issues))
        self.assertTrue(any("FR-001" in s for s in issues))

    def test_malformed_shape_handled_without_crash(self):
        self.d["api"] = "not a list"
        self.assertTrue(validate_design(self.d, self.a))

    def test_json_wrappers_and_nonobjects(self):
        self.assertEqual(parse_json('```json\n{"ok":1}\n```'), {"ok": 1})
        with self.assertRaises(ValueError):
            parse_json("[]")


class FakeClient:
    def __init__(self, config):
        self.calls = []

    def complete(self, messages, stage, attempt):
        self.calls.append({"stage": stage, "attempt": attempt, "status": "ok", "input_tokens": 10, "output_tokens": 20, "seconds": 0.01})
        return json.dumps(fixture()[0 if stage == "Анализ" else 1], ensure_ascii=False)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine(self.temp.name, FakeClient)

    def test_demo_exports_without_model_and_marks_example(self):
        job_id = self.engine.create("different input", demo=True)
        job = wait(self.engine, job_id)
        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["requirements"], REQUIREMENTS)
        self.assertEqual(job["report"]["metrics"]["model_calls"], 0)
        self.assertIsNone(job["report"]["metrics"]["input_tokens"])
        text = (Path(self.temp.name) / job_id / "system-analysis.md").read_text(encoding="utf-8")
        self.assertIn("УЧЕБНЫЙ ПРИМЕР", text)
        self.assertIn("Сканирование кода и проверка CVE не выполнялись", text)

    def test_question_gate_then_complete_and_usage(self):
        job_id = self.engine.create(REQUIREMENTS, {})
        job = wait(self.engine, job_id)
        self.assertEqual(job["status"], "awaiting_answers")
        with self.assertRaises(ValueError):
            self.engine.continue_run(job_id, {})
        self.engine.continue_run(job_id, {"Q-001": "Только открытое приложение"})
        job = wait(self.engine, job_id)
        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["report"]["metrics"]["input_tokens"], 20)
        self.assertEqual(job["report"]["metrics"]["output_tokens"], 40)
        self.assertEqual(job["report"]["metrics"]["manual_actions"][0]["type"], "answer")

    def test_explicit_assumptions_accepted(self):
        job_id = self.engine.create(REQUIREMENTS, {})
        wait(self.engine, job_id)
        self.engine.continue_run(job_id, {}, True)
        job = wait(self.engine, job_id)
        self.assertEqual(job["status"], "complete")
        self.assertEqual(job["report"]["metrics"]["manual_actions"][0]["type"], "assumption")

    def test_unknown_answer_and_concurrent_run_rejected(self):
        job_id = self.engine.create(REQUIREMENTS, {})
        wait(self.engine, job_id)
        with self.assertRaises(ValueError):
            self.engine.continue_run(job_id, {"Q-999": "bad"}, True)
        with self.assertRaises(ValueError):
            self.engine.create(REQUIREMENTS, {})
        self.engine.cancel(job_id)
        self.assertEqual(self.engine.snapshot(job_id)["status"], "cancelled")

    def test_one_repair_and_failure_report(self):
        class Broken(FakeClient):
            def complete(self, messages, stage, attempt):
                super().complete(messages, stage, attempt)
                return "invalid JSON"
        self.engine.client_factory = Broken
        job_id = self.engine.create(REQUIREMENTS, {})
        job = wait(self.engine, job_id)
        # Wait until the failure artifact is saved too.
        for _ in range(100):
            if self.engine.snapshot(job_id)["files"]:
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["report"]["metrics"]["model_calls"], 2)
        self.assertEqual(job["report"]["metrics"]["repair_attempts"], 1)
        self.assertTrue((Path(self.temp.name) / job_id / "failure-report.json").exists())


class ProviderTests(unittest.TestCase):
    def test_provider_transport_usage_and_key_redaction(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path, self.headers.get("Authorization"), body))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"choices": [{"message": {"content": "{\"ok\":true}"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 7, "completion_tokens": 9}}).encode())
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            config = normalize_config({"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "test-qwen", "api_key": "secret-for-test"})
            client = Client(config)
            self.assertEqual(client.complete([{"role": "user", "content": "test"}], "test", 1), '{"ok":true}')
            self.assertEqual(received[0][0], "/v1/chat/completions")
            self.assertEqual(received[0][1], "Bearer secret-for-test")
            self.assertEqual(client.calls[0]["input_tokens"], 7)
            self.assertNotIn("secret-for-test", json.dumps(client.calls))
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_missing_usage_stays_unknown_and_http_body_not_exposed(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 401, "secret-for-test", {}, None)):
            client = Client({"endpoint": "http://localhost/v1/chat/completions", "model": "q", "api_key": "secret-for-test"})
            with self.assertRaises(ProviderError) as caught:
                client.complete([], "test", 1)
            self.assertNotIn("secret-for-test", str(caught.exception))
            self.assertEqual(client.calls[0]["status"], "error")
            self.assertIsNone(client.calls[0]["input_tokens"])

    def test_invalid_urls_rejected(self):
        for base in ["file:///tmp/x", "http://key:secret@host/v1", "http://host/v1?key=secret", "invalid"]:
            with self.assertRaises(ValueError):
                normalize_config({"base_url": base, "model": "q"})


class ServerTests(unittest.TestCase):
    def test_http_demo_download_preview_and_csrf(self):
        with tempfile.TemporaryDirectory() as temp:
            server = make_server(port=0, runs_root=temp, client_factory=FakeClient)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def get(path):
                with urllib.request.urlopen(base + path) as r:
                    return r.read()
            def post(path, body, token):
                req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Pipeline-Token": token})
                return json.loads(urllib.request.urlopen(req).read())
            try:
                self.assertIn("ИИ-аналитик", get("/").decode())
                config = json.loads(get("/api/config"))
                self.assertNotIn("api_key", config)
                bad_host = urllib.request.Request(base + "/api/config", headers={"Host": "untrusted.example"})
                with self.assertRaises(urllib.error.HTTPError) as host_error:
                    urllib.request.urlopen(bad_host)
                self.assertEqual(host_error.exception.code, 403)
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    post("/api/demo", {}, "bad-token")
                self.assertEqual(caught.exception.code, 403)
                job_id = post("/api/demo", {}, config["csrf_token"])["id"]
                job = wait(server.engine, job_id)
                self.assertEqual(job["status"], "complete")
                archive = zipfile.ZipFile(io.BytesIO(get(f"/api/runs/{job_id}/archive")))
                self.assertEqual(set(archive.namelist()), set(job["files"]))
                preview = json.loads(get(f"/api/runs/{job_id}/files/system-analysis.md?preview=1"))
                self.assertIn("УЧЕБНЫЙ ПРИМЕР", preview["content"])
                with self.assertRaises(urllib.error.HTTPError):
                    get(f"/api/runs/{job_id}/files/.env")
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
