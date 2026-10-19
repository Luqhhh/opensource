"""Synthetic fixtures and mocked API contracts, not live-model effectiveness."""

import contextlib
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zipfile

from exampleproof.cli import main
from exampleproof.model_api import JSONClient, JSONReply
from exampleproof.models import Example, Execution, InferenceEvidence
from exampleproof.pipeline import run_project
from exampleproof.project_input import github_repository, project_input, unpack_snapshot
from exampleproof.providers import DeepSeekProvider
from exampleproof.tutorial import analyze_project, discover, write_analysis


def completion(value, **updates):
    result = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
              "usage": {"prompt_tokens": 20, "completion_tokens": 5}}
    result.update(updates)
    return io.BytesIO(json.dumps(result).encode())


class ModelAPIContractTests(unittest.TestCase):
    def client(self):
        return JSONClient("deepseek", "deepseek-flash", api_key="synthetic-test-key")

    def test_auth_is_sent_only_to_official_https_and_not_retained(self):
        with patch("exampleproof.model_api.urlopen", return_value=completion({"findings": []})) as send:
            reply = self.client().complete("Return JSON", {"evidence": []})
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-test-key")
        self.assertNotIn("synthetic-test-key", json.dumps(asdict(reply)))
        self.assertEqual((reply.input_tokens, reply.output_tokens), (20, 5))
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_credentials_are_redacted_from_malformed_and_http_errors(self):
        responses = [io.BytesIO(b'synthetic-test-key {broken'),
                     HTTPError("https://api.deepseek.com", 401, "unauthorized", {},
                               io.BytesIO(b'synthetic-test-key'))]
        for response in responses:
            with self.subTest(response=type(response).__name__):
                options = {"side_effect": response} if isinstance(response, HTTPError) else {"return_value": response}
                with patch("exampleproof.model_api.urlopen", **options), self.assertRaises(ValueError) as caught:
                    self.client().complete("Return JSON", {})
                self.assertNotIn("synthetic-test-key", str(caught.exception))
                evidence = asdict(caught.exception.inference_evidence)
                self.assertNotIn("synthetic-test-key", json.dumps(evidence))
                self.assertIn("[REDACTED]", evidence["response_body"])

    def test_transport_errors_do_not_expose_credentials_or_retry(self):
        with patch("exampleproof.model_api.urlopen", side_effect=TimeoutError("synthetic-test-key")) as send:
            with self.assertRaises(ValueError) as caught:
                self.client().complete("Return JSON", {})
        self.assertEqual(send.call_count, 1)
        self.assertEqual(str(caught.exception), "[REDACTED]")
        self.assertIsNotNone(caught.exception.inference_evidence)

    def test_http_error_envelope_preserves_available_usage(self):
        body = json.dumps({"error": "synthetic-test-key", "usage": {"prompt_tokens": 7, "completion_tokens": 1}}).encode()
        error = HTTPError("https://api.deepseek.com", 503, "unavailable", {}, io.BytesIO(body))
        with patch("exampleproof.model_api.urlopen", side_effect=error), self.assertRaises(ValueError) as caught:
            self.client().complete("Return JSON", {})
        from exampleproof.providers import response_token_count
        evidence = caught.exception.inference_evidence
        self.assertEqual(response_token_count(evidence.response, "input_tokens"), 7)
        self.assertNotIn("synthetic-test-key", json.dumps(asdict(evidence)))

    def test_invalid_config_fails_before_network(self):
        with patch("exampleproof.model_api.urlopen") as send:
            for endpoint in ("http://api.deepseek.com", "https://evil.invalid", "https://api.deepseek.com@evil.invalid",
                             "https://api.deepseek.com/?x=1", "https://api.deepseek.com:443"):
                with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                    JSONClient("deepseek", "model", endpoint=endpoint, api_key="synthetic")
            for timeout in (True, 0, -1, float("nan"), float("inf")):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    JSONClient("deepseek", "model", timeout=timeout, api_key="synthetic")
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                JSONClient("deepseek", "model")
            send.assert_not_called()

    def test_incomplete_empty_malformed_and_invalid_usage_fail_closed(self):
        envelopes = [
            {"choices": []},
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
             "usage": {"prompt_tokens": True}},
            {"error": {"message": "unavailable"}}, [],
        ]
        for envelope in envelopes:
            with self.subTest(envelope=envelope), patch("exampleproof.model_api.urlopen", return_value=io.BytesIO(json.dumps(envelope).encode())):
                with self.assertRaises(ValueError) as caught:
                    self.client().complete("Return JSON", {})
                evidence = caught.exception.inference_evidence
                self.assertTrue(evidence.response is not None or evidence.response_body is not None)
        with patch("exampleproof.model_api.urlopen", return_value=io.BytesIO(b"x" * 256_001)):
            with self.assertRaises(ValueError) as caught:
                self.client().complete("Return JSON", {})
        self.assertTrue(caught.exception.inference_evidence.response_truncated)

    def test_ollama_analysis_keeps_loopback_policy_and_usage(self):
        with self.assertRaises(ValueError):
            JSONClient("ollama", "local", endpoint="https://remote.invalid")
        envelope = {"done": True, "response": '{"findings": []}', "prompt_eval_count": 8, "eval_count": 3}
        with patch("exampleproof.model_api.urlopen", return_value=io.BytesIO(json.dumps(envelope).encode())) as send:
            reply = JSONClient("ollama", "local").complete("Return JSON", {})
        self.assertEqual(send.call_args.args[0].full_url, "http://127.0.0.1:11434/api/generate")
        self.assertIsNone(send.call_args.args[0].get_header("Authorization"))
        self.assertEqual((reply.input_tokens, reply.output_tokens), (8, 3))

    def test_explicit_local_generation_settings_are_validated_and_sent(self):
        envelope = {"done": True, "response": '{}'}
        with patch("exampleproof.model_api.urlopen", return_value=io.BytesIO(json.dumps(envelope).encode())) as send:
            JSONClient("ollama", "local", ollama_options={"num_ctx": 8192, "seed": 17}).complete("Return JSON", {})
        options = json.loads(send.call_args.args[0].data)["options"]
        self.assertEqual(options, {"temperature": 0, "num_predict": 2048, "num_ctx": 8192, "seed": 17})
        with self.assertRaises(ValueError):
            JSONClient("ollama", "local", ollama_options={"num_ctx": -1})
        with self.assertRaises(ValueError):
            JSONClient("deepseek", "deepseek-flash", api_key="synthetic", ollama_options={"seed": 17})

    def test_cloud_transport_refuses_auth_redirects(self):
        from exampleproof.model_api import urlopen
        from urllib.request import HTTPRedirectHandler, Request
        request = Request("https://api.deepseek.com/chat/completions", headers={"Authorization": "Bearer synthetic"})
        with patch("exampleproof.model_api.build_opener") as build:
            urlopen(request, timeout=2)
        handler = next(h for h in build.call_args.args if isinstance(h, HTTPRedirectHandler))
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code), self.assertRaises(ValueError):
                handler.redirect_request(request, None, code, "", {}, "https://other.invalid")

    def test_repair_withholds_evaluator_details_and_records_parse_failure_usage(self):
        example = Example("a.md#1", "a.md", 1, 1, "old()", "Public contract")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-test-key"}):
            provider = DeepSeekProvider()
        before = Execution("failed", 22, stderr="private-oracle", oracle="configured_behavior_checks")
        with patch("exampleproof.model_api.urlopen", return_value=completion({"code": "fixed()", "rationale": "API"})) as send:
            result = provider.propose(example, before, {})
        self.assertEqual(result.provider, "deepseek")
        self.assertNotIn("private-oracle", send.call_args.args[0].data.decode())
        class FailedRunner:
            def run(self, code, spec):
                return Execution("failed", 21, stderr="old is missing")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("```python\nold()\n```\n")
            with patch("exampleproof.model_api.urlopen", return_value=completion({"code": 1})):
                report, diff = run_project(root, provider, FailedRunner())
        self.assertEqual(report["repair"]["input_tokens"], 20)
        self.assertEqual(report["repair"]["output_tokens"], 5)
        self.assertEqual(report["summary"]["counts"], {"provider_error": 1})
        self.assertEqual(diff, "")


class ProjectInputTests(unittest.TestCase):
    def archive(self, entries):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in entries:
                archive.writestr(name, content)
        return output.getvalue()

    def test_github_urls_are_validated_without_network(self):
        for value in ("owner/project", "https://github.com/owner/project.git"):
            self.assertEqual(github_repository(value), "owner/project")
        for value in ("https://github.com@evil.invalid/o/p", "http://github.com/o/p", "git@github.com:o/p",
                      "https://github.com/o/p/tree/main", "o/../p", "-o/p", "https://github.com/o/p?q=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                github_repository(value)

    def test_snapshot_is_pinned_to_commit_and_cleans_up(self):
        sha = "a" * 40
        data = self.archive([("project-sha/README.md", "# Tutorial"), ("project-sha/docs/setup.md", "Setup")])
        with patch("exampleproof.project_input.fetch", side_effect=[json.dumps({"sha": sha}).encode(), data]) as fetch:
            with project_input("owner/project", ref="feature/setup") as (root, metadata):
                self.assertEqual((root / "docs/setup.md").read_text(), "Setup")
                self.assertEqual(metadata["commit"], sha)
                self.assertEqual(fetch.call_args_list[0].args[0],
                                 "https://api.github.com/repos/owner/project/commits/feature%2Fsetup")
                self.assertIn(sha, fetch.call_args_list[1].args[0])
            self.assertFalse(root.exists())

    def test_archive_traversal_and_mixed_roots_rejected_before_writes(self):
        cases = [[("root/README.md", "safe"), ("root/../../escape.md", "unsafe")],
                 [("/root/file.md", "unsafe")], [("root/file.md", "a"), ("other/file.md", "b")],
                 [("root/a\\b.md", "unsafe")]]
        for entries in cases:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.assertRaises(ValueError):
                    unpack_snapshot(self.archive(entries), root)
                self.assertEqual(list(root.iterdir()), [])

    def test_archive_symlinks_secrets_and_evaluator_inputs_are_excluded(self):
        link = zipfile.ZipInfo("root/link.py")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        data = self.archive([("root/README.md", "# Tutorial"), ("root/.env", "secret"),
                             ("root/tests/checks.py", "private-oracle"),
                             ("root/exampleproof.json", "private-oracle"), (link, "/outside.py")])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unpack_snapshot(data, root)
            self.assertEqual([p.name for p in root.iterdir()], ["README.md"])

    def test_missing_local_directory_does_not_trigger_fetch(self):
        with patch("exampleproof.project_input.fetch") as fetch, self.assertRaises(ValueError):
            with project_input("/no/such/project"):
                pass
        fetch.assert_not_called()

    def test_github_download_and_expansion_limits_fail_before_copying(self):
        data = self.archive([("root/README.md", "a" * 100)])
        for option in ("MAX_ARCHIVE_BYTES", "MAX_EXPANDED_BYTES", "MAX_ENTRIES"):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as temporary:
                with patch("exampleproof.project_input." + option, 0), self.assertRaises(ValueError):
                    unpack_snapshot(data, Path(temporary))
                self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_missing_commit_metadata_never_downloads_archive(self):
        with patch("exampleproof.project_input.fetch", return_value=b'{"sha": "not-a-sha"}') as fetch:
            with self.assertRaises(ValueError):
                with project_input("owner/project"):
                    pass
        self.assertEqual(fetch.call_count, 1)


class FixtureClient:
    """Only synthetic responses; never calls a model service."""
    evidence_kind = "synthetic_fixture"
    provider = "synthetic_fixture"
    model = "fixture"

    def __init__(self, values):
        self.values = iter(values)
        self.requests = []

    def complete(self, system, evidence):
        self.requests.append(evidence)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return JSONReply(value, InferenceEvidence({"system": system, "evidence": evidence}, "fixture", 1), 10, 2)


class TutorialAnalysisTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "README.md").write_text("# Start\n[Setup](docs/setup.md)\n[Missing](docs/missing.md)\n"
                                       "```python\nraise RuntimeError('never execute')\n```\n", encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs/setup.md").write_text("# Setup\nConfigure settings before using the library.\n")
        (root / "library.py").write_text("raise RuntimeError('must not import')\ndef configure(settings):\n    return settings\n")
        (root / "pyproject.toml").write_text('[project]\nname = "fixture"\n')
        (root / "tests").mkdir()
        (root / "tests/oracle.py").write_text('assert "private-oracle"\n')
        (root / "exampleproof.json").write_text('{"examples": {"checks": "private-oracle"}}')
        (root / ".env").write_text("PRIVATE_SECRET=fixture\n")
        (root / "credentials.json").write_text('{"key": "PRIVATE_SECRET"}')
        (root / "linked.py").symlink_to(root / "library.py")
        return root

    def test_static_analysis_covers_multiple_files_without_writes_or_execution(self):
        root = self.fixture()
        original = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob("*") if p.is_file()}
        with patch("subprocess.run", side_effect=AssertionError("execution forbidden")):
            report = analyze_project(root, {"kind": "local"})
        self.assertEqual(report["mode"], "static_analysis")
        self.assertEqual(report["coverage"]["indexed_files"], 4)
        self.assertFalse(report["execution"]["performed"])
        self.assertEqual(report["usage"]["requests"], 0)
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["findings"][0]["target"], "docs/missing.md")
        self.assertNotIn("private-oracle", json.dumps(report))
        self.assertNotIn("PRIVATE_SECRET", json.dumps(report))
        after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in root.rglob("*") if p.is_file()}
        self.assertEqual(original, after)

    def test_ai_selection_and_analysis_use_only_original_bounded_evidence(self):
        root = self.fixture()
        baseline = analyze_project(root, {"kind": "local"})
        doc = next(c for c in baseline["context"]["selected"] if c["path"] == "docs/setup.md")
        finding = {"title": "解释配置来源", "category": "explanation", "impact": "读者不清楚配置从何获得",
                   "suggestion": "增加配置示例", "evidence_ids": [doc["id"]]}
        client = FixtureClient([{"selected_ids": [doc["id"]]}, {"findings": [finding]}])
        report = analyze_project(root, {"kind": "local"}, client=client, strategy="ai", context_chars=2000)
        self.assertEqual(report["context"]["actual"], "ai")
        self.assertEqual(report["usage"]["requests"], 2)
        self.assertEqual(report["usage"]["input_tokens"], 20)
        self.assertLessEqual(len(json.dumps(client.requests[0]["candidates"], ensure_ascii=False)), 2000)
        self.assertLessEqual(report["context"]["used_chars"], 2000)
        self.assertEqual(report["context"]["used_chars"], len(json.dumps(report["context"]["selected"], ensure_ascii=False)))
        self.assertEqual(report["findings"][-1]["status"], "ai_suggestion_unverified")
        for chunk in client.requests[1]["evidence"]:
            lines = (root / chunk["path"]).read_text().splitlines(keepends=True)
            self.assertEqual(chunk["text"], "".join(lines[chunk["start_line"] - 1:chunk["end_line"]]))

    def test_invalid_selection_falls_back_explicitly_and_invalid_citations_are_rejected(self):
        for selection in ({"selected_ids": ["../../private"]}, {"selected_ids": [{}]},
                          {"selected_ids": []}, ValueError("selection unavailable")):
            with self.subTest(selection=selection):
                client = FixtureClient([selection, {"findings": [
                    {"title": "invented", "impact": "x", "suggestion": "x", "category": "sequence",
                     "evidence_ids": ["not-supplied"]},
                    {"title": "malformed", "impact": "x", "suggestion": "x", "category": [], "evidence_ids": []}]}])
                report = analyze_project(self.fixture(), {"kind": "local"}, client=client, strategy="ai")
                self.assertEqual(report["context"]["actual"], "lexical")
                self.assertTrue(report["context"]["fallback_reason"])
                self.assertEqual(len(report["findings"]), 1)
                self.assertNotIn("private-oracle", json.dumps(client.requests))
                self.assertEqual(len(report["calls"]), 2)

    def test_failed_analysis_keeps_static_results_and_unknown_usage(self):
        client = FixtureClient([ValueError("API unavailable")])
        report = analyze_project(self.fixture(), {"kind": "local"}, client=client)
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["calls"][0]["status"], "error")
        self.assertIsNone(report["usage"]["input_tokens"])

    def test_no_automatic_ai_calls_and_output_is_fresh_escaped_and_separate(self):
        root = self.fixture()
        report = analyze_project(root, {"kind": "local"})
        report["findings"][0]["title"] = '<script>alert("x")</script>'
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            write_analysis(output, report)
            self.assertNotIn('<script>', (output / "analysis.html").read_text())
            self.assertIn("script-src 'none'", (output / "analysis.html").read_text())
            self.assertEqual(json.loads((output / "analysis.json").read_text()), report)
            with self.assertRaises(FileExistsError):
                write_analysis(output, report)
        with patch("exampleproof.model_api.urlopen") as send, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["analyze", str(root), "--static", "--output", str(root / "report")]), 2)
        self.assertFalse((root / "report").exists())
        send.assert_not_called()

    def test_cli_local_analysis_and_provider_validation(self):
        root = self.fixture()
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary) / "report"
            with patch("exampleproof.model_api.JSONClient") as constructor:
                self.assertEqual(main(["analyze", str(root), "--static", "--output", str(output)]), 0)
            constructor.assert_not_called()
            self.assertTrue((output / "analysis.html").is_file())
            self.assertEqual(json.loads((output / "analysis.json").read_text())["calls"], [])
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stderr(io.StringIO()):
            output = Path(temporary) / "report"
            self.assertEqual(main(["analyze", str(root), "--static", "--output", str(output), "--context-strategy", "ai"]), 2)
            self.assertFalse(output.exists())

    def test_cli_defaults_to_flash_and_one_rule_context_analysis_call(self):
        root = self.fixture()
        client = FixtureClient([{"findings": []}])
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary) / "report"
            with patch("exampleproof.model_api.JSONClient", return_value=client) as constructor:
                self.assertEqual(main(["analyze", str(root), "--output", str(output)]), 0)
            constructor.assert_called_once_with("deepseek", "deepseek-flash", endpoint=None, timeout=60)
            report = json.loads((output / "analysis.json").read_text())
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(report["context"]["requested"], "lexical")
        self.assertEqual(report["context"]["actual"], "lexical")
        self.assertEqual(len(report["calls"]), 1)
        self.assertEqual(report["calls"][0]["stage"], "analysis")

    def test_cli_missing_key_fails_without_network_or_static_fallback(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True), \
                patch("exampleproof.project_input.fetch") as fetch, \
                patch("exampleproof.model_api.urlopen") as send, \
                contextlib.redirect_stderr(io.StringIO()) as error:
            output = Path(temporary) / "report"
            self.assertEqual(main(["analyze", "owner/project", "--output", str(output)]), 2)
            self.assertIn("DEEPSEEK_API_KEY", error.getvalue())
            self.assertFalse(output.exists())
        fetch.assert_not_called()
        send.assert_not_called()

    def test_cli_keeps_explicit_model_provider_and_ai_context_options(self):
        root = self.fixture()
        for options, provider, model, strategy in [
                (["--model", "configured-model"], "deepseek", "configured-model", "lexical"),
                (["--provider", "ollama", "--model", "local-model"], "ollama", "local-model", "lexical"),
                (["--context-strategy", "ai"], "deepseek", "deepseek-flash", "ai")]:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary, \
                    patch("exampleproof.model_api.JSONClient") as constructor, \
                    patch("exampleproof.tutorial.analyze_project", return_value={"findings": [], "calls": [], "warnings": []}) as analyze, \
                    patch("exampleproof.tutorial.write_analysis"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["analyze", str(root), "--output", str(Path(temporary) / "report"), *options]), 0)
                constructor.assert_called_once_with(provider, model, endpoint=None, timeout=60)
                self.assertEqual(analyze.call_args.kwargs["strategy"], strategy)

    def test_cli_static_rejects_model_options_before_reading_project(self):
        for options in (["--model", "unused"], ["--endpoint", "https://api.deepseek.com"],
                        ["--context-strategy", "ai"]):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary, \
                    patch("exampleproof.project_input.project_input") as read, \
                    patch("exampleproof.model_api.JSONClient") as constructor, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["analyze", "owner/project", "--static", "--output",
                                       str(Path(temporary) / "report"), *options]), 2)
                read.assert_not_called()
                constructor.assert_not_called()

    def test_cli_deepseek_repair_selects_provider_without_local_model(self):
        root = self.fixture()
        # Existing repair config schema is intentionally separate from discovery.
        (root / "exampleproof.json").unlink()
        report = {"summary": {"total": 1, "counts": {"checked": 1}}}
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            with patch("exampleproof.cli.DeepSeekProvider") as provider, \
                    patch("exampleproof.cli.run_project", return_value=(report, "")), \
                    patch("exampleproof.cli.write_report"):
                status = main(["repair", str(root), "--provider", "deepseek", "--repair-policy", "semantic-v2",
                               "--output", str(Path(temporary) / "report")])
        self.assertEqual(status, 0)
        provider.assert_called_once_with("deepseek-flash", "https://api.deepseek.com", timeout=60, semantic=True)

    def test_input_and_context_limits_are_reported(self):
        root = self.fixture()
        with patch("exampleproof.tutorial.MAX_FILES", 1):
            files, skipped = discover(root)
        self.assertEqual(len(files), 1)
        self.assertGreater(skipped["file_limit"], 0)
        with self.assertRaises(ValueError):
            analyze_project(root, {}, context_chars=0)

    def test_oversized_github_target_is_not_reported_as_a_broken_link(self):
        root = self.fixture()
        report = analyze_project(root, {"kind": "github", "snapshot": {"omitted_eligible_paths": ["docs/missing.md"]}})
        self.assertEqual(report["findings"], [])


if __name__ == "__main__":
    unittest.main()
