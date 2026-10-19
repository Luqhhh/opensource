"""Synthetic multi-round candidates and mocked cloud transport, not quality results."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.model_api import JSONClient, JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.tutorial import analyze_snapshot, prepare_project, write_analysis
from exampleproof.tutorial_privacy import review_cloud
from exampleproof.tutorial_retrieval import search_index, validate_requests
from exampleproof.tutorial_scope import EvidenceScope


def response(requests=(), retained=(), findings=()):
    return {"findings": list(findings), "edits": [], "evidence_requests": list(requests), "retain_ids": list(retained)}


def gap(kind, query, **extra):
    return {"kind": kind, "query": query, "reason": "Need the behavior evidence for this task"} | extra


class IterativeFixtureClient:
    provider = "synthetic_fixture"
    model = "iterative-fixture"
    evidence_kind = "synthetic_fixture"

    def __init__(self, values, before=None):
        self.values, self.requests, self.before = iter(values), [], before

    def complete(self, system, evidence):
        if self.before:
            self.before(len(self.requests), evidence)
        self.requests.append(evidence)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(evidence)
        return JSONReply(value, InferenceEvidence({"system": system, "evidence": evidence}, "synthetic", 1), 10, 2)


class IterativeRetrievalTests(unittest.TestCase):
    def fixture(self, count=55):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "README.md").write_text("# Getting started\n\nRead the API reference before using the application.\n")
        for i in range(count):
            (root / f"source{i:02}.py").write_text("value = 1\n")
        (root / "zzz.py").write_text("def resolve_endpoint(value):\n    return value + '/v1'\n")
        (root / "zzzz.py").write_text("def load_profile(name):\n    return {'profile': name}\n")
        return root

    def snapshot(self, **kwargs):
        return prepare_project(self.fixture(), {}, **kwargs)

    def test_two_gap_rounds_find_symbols_and_paths_outside_initial_candidates(self):
        snapshot = self.snapshot()
        target = next(c for c in snapshot.chunks if c.path == "zzz.py")
        self.assertNotIn(target, snapshot.candidates)
        def second(payload):
            self.assertTrue(any(c["path"] == "zzz.py" for c in payload["evidence"]))
            return response([gap("path", "zzzz.py")], [target.id])
        def final(payload):
            paths = {c["path"] for c in payload["evidence"]}
            self.assertTrue({"README.md", "zzz.py", "zzzz.py"} <= paths)
            refs = [c["id"] for c in payload["evidence"] if c["path"] in {"zzz.py", "zzzz.py"}]
            return response(findings=[{"title": "解释配置来源", "category": "explanation", "impact": "配置关系需要说明",
                                       "suggestion": "说明 profile 和 endpoint 的关系", "evidence_ids": refs}])
        client = IterativeFixtureClient([response([gap("symbol", "resolve_endpoint")]), second, final])
        requirements = {"schema_version": "tutorial-evidence-requirements-1", "snapshot_id": snapshot.snapshot_id,
                        "evidence_kind": "synthetic_fixture", "annotator": "synthetic task fixture",
                        "cases": [{"id": "configuration", "required": [{"path": "zzz.py", "start_line": 1, "end_line": 2}]}]}
        with patch("subprocess.run", side_effect=AssertionError("No host commands")), \
                patch.object(Path, "read_text", side_effect=AssertionError("Frozen index only")):
            report = analyze_snapshot(snapshot, client=client, strategy="iterative", evidence_requirements=requirements)
        self.assertEqual(report["retrieval"]["stop_reason"], "model_finished")
        self.assertEqual(len(report["retrieval"]["rounds"]), 3)
        self.assertEqual(report["usage"]["requests"], 3)
        self.assertEqual(report["usage"]["input_tokens"], 30)
        self.assertEqual(report["necessary_evidence_coverage"]["stages"]["candidates"]["covered_spans"], 0)
        self.assertEqual(report["necessary_evidence_coverage"]["stages"]["selected"]["covered_spans"], 1)
        self.assertEqual(report["findings"][0]["origin"], "synthetic_fixture")
        self.assertEqual(len(report["findings"][0]["evidence"]), 2)
        self.assertFalse(report["execution"]["performed"])
        self.assertEqual(report["warnings"], [])

    def test_task_affects_initial_query_and_is_sent_each_round(self):
        root = self.fixture()
        generic = prepare_project(root, {})
        task = "resolve endpoint"
        snapshot = prepare_project(root, {}, task=task)
        self.assertNotIn("zzz.py", {c.path for c in generic.candidates})
        self.assertIn("zzz.py", {c.path for c in snapshot.candidates})
        client = IterativeFixtureClient([response()])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(client.requests[0]["task"], task)
        self.assertTrue(report["context"]["task_conditioned"])
        with self.assertRaisesRegex(ValueError, "requires the iterative"):
            analyze_snapshot(snapshot, client=client, strategy="ai")

    def test_search_text_path_line_and_qualified_method_return_exact_source(self):
        root = self.fixture(count=0)
        (root / "object.py").write_text("class Service:\n    def connect(self):\n        return 'unique-behavior-marker'\n")
        snapshot = prepare_project(root, {})
        for request in (gap("symbol", "Service.connect"), gap("text", "unique-behavior-marker"),
                        gap("path", "object.py", start_line=3)):
            with self.subTest(request=request):
                validate_requests(response([request]), set())
                found, receipt = search_index(snapshot, request)
                self.assertEqual(receipt["status"], "matches")
                self.assertIn("object.py", {c.path for c in found})
                for chunk in found:
                    self.assertEqual(chunk.text, "".join(snapshot.files[chunk.path]["text"].splitlines(keepends=True)[chunk.start_line - 1:chunk.end_line]))
        found, _ = search_index(snapshot, gap("symbol", "object.py"))
        self.assertEqual(found, [])

    def test_round_limit_stops_before_an_extra_search_or_model_call(self):
        snapshot = self.snapshot()
        client = IterativeFixtureClient([response([gap("path", "zzz.py")]), response([gap("path", "zzzz.py")])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative", max_retrieval_rounds=1)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(report["retrieval"]["stop_reason"], "round_limit")
        self.assertEqual(report["retrieval"]["unresolved_requests"][0]["query"], "zzzz.py")
        self.assertEqual(report["retrieval"]["rounds"][-1]["searches"], [])
        self.assertTrue(report["warnings"])

    def test_repeated_queries_and_unmatched_queries_do_not_spin(self):
        snapshot = self.snapshot()
        client = IterativeFixtureClient([response([gap("path", "zzz.py")]), response([gap("path", "zzz.py")])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(report["retrieval"]["stop_reason"], "no_new_evidence")
        self.assertEqual(report["retrieval"]["rounds"][-1]["searches"][0]["status"], "repeated_request")
        self.assertEqual(len(client.requests), 2)
        client = IterativeFixtureClient([response([gap("symbol", "not_indexed_anywhere")])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(report["retrieval"]["rounds"][0]["searches"][0]["status"], "no_indexed_match")
        self.assertEqual(report["retrieval"]["unresolved_requests"][0]["query"], "not_indexed_anywhere")

    def test_same_text_query_can_page_to_unseen_matches_within_round_limit(self):
        snapshot = self.snapshot()
        client = IterativeFixtureClient([response([gap("text", "value")]), response([gap("text", "value")]), response()])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative", max_retrieval_rounds=2)
        self.assertEqual(report["retrieval"]["stop_reason"], "model_finished")
        first, second = [set(r["searches"][0]["returned_ids"]) for r in report["retrieval"]["rounds"][:2]]
        self.assertEqual(len(first), 6)
        self.assertEqual(len(second), 6)
        self.assertFalse(first & second)
        self.assertTrue(first | second <= report["retrieval"]["evidence"].keys())

    def test_files_changed_after_freeze_do_not_change_later_search_evidence(self):
        root = self.fixture()
        snapshot = prepare_project(root, {})
        original = snapshot.files["zzz.py"]["text"]
        def before(number, payload):
            if number == 0:
                (root / "zzz.py").write_text("CHANGED AFTER FREEZE\n")
        client = IterativeFixtureClient([response([gap("path", "zzz.py")]), response()], before)
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        evidence = next(c for c in client.requests[1]["evidence"] if c["path"] == "zzz.py")
        self.assertEqual(evidence["text"], original)
        self.assertNotIn("CHANGED AFTER FREEZE", json.dumps(report))

    def test_invalid_request_batch_is_rejected_before_any_search(self):
        snapshot = self.snapshot()
        invalid = [gap("path", "../private.py"), gap("path", "/etc/passwd"), gap("path", "a\\b.py"),
                   gap("shell", "cat /etc/passwd"), gap("symbol", "__import__('os')"),
                   gap("text", "needle", command="id"), gap("path", "zzz.py", start_line=True)]
        for request in invalid:
            with self.subTest(request=request), patch("exampleproof.tutorial_retrieval.search_index") as search:
                client = IterativeFixtureClient([response([gap("path", "zzz.py"), request])])
                report = analyze_snapshot(snapshot, client=client, strategy="iterative")
                self.assertEqual(report["retrieval"]["stop_reason"], "invalid_evidence_request")
                search.assert_not_called()

    def test_budget_exhaustion_does_not_send_an_oversized_chunk(self):
        root = self.fixture()
        (root / "zzz.py").write_text('value = "' + "x" * 3000 + '"\n')
        snapshot = prepare_project(root, {})
        client = IterativeFixtureClient([response([gap("path", "zzz.py")])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative", context_chars=2000)
        self.assertEqual(report["retrieval"]["stop_reason"], "context_budget_exhausted")
        self.assertEqual(len(client.requests), 1)
        self.assertLessEqual(report["context"]["used_chars"], 2000)
        self.assertNotIn("zzz.py", {c["path"] for c in report["context"]["selected"]})

    def test_new_evidence_can_replace_old_context_without_losing_anchor(self):
        snapshot = self.snapshot()
        client = IterativeFixtureClient([response([gap("path", "zzz.py")]), response()])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative", context_chars=2000)
        self.assertEqual(report["retrieval"]["stop_reason"], "model_finished")
        paths = {c["path"] for c in report["context"]["selected"]}
        self.assertTrue({"README.md", "zzz.py"} <= paths)
        for payload in client.requests:
            self.assertLessEqual(len(json.dumps(payload["evidence"], ensure_ascii=False)), 2000)
        self.assertNotEqual(client.requests[0]["evidence"], client.requests[1]["evidence"])

    def test_later_provider_error_preserves_previous_findings_and_matching_context(self):
        snapshot = self.snapshot()
        def first(payload):
            evidence = payload["evidence"][0]
            return response([gap("path", "zzz.py")], findings=[{"title": "补充前提说明", "category": "prerequisites",
                "impact": "读者需要前提说明", "suggestion": "说明相关前提", "evidence_ids": [evidence["id"]]}])
        client = IterativeFixtureClient([first, TimeoutError("synthetic timeout")])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(report["retrieval"]["stop_reason"], "model_error")
        self.assertEqual(report["context"]["selected"], client.requests[0]["evidence"])
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(len(client.requests), 2)
        self.assertIsNone(report["usage"]["input_tokens"])

    def test_freeze_filters_tests_and_finding_ids_remain_enforced(self):
        root = self.fixture()
        (root / "tests").mkdir()
        (root / "tests/test_api.py").write_text("assert 1 == 1\n")
        (root / "symlink.py").symlink_to(root / "zzz.py")
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        snapshot = prepare_project(root, {})
        client = IterativeFixtureClient([response([gap("path", "tests/test_api.py")])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(report["retrieval"]["rounds"][0]["searches"][0]["status"], "no_indexed_match")
        self.assertNotIn("symlink.py", snapshot.files)
        self.assertEqual({str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}, before)
        snapshot = prepare_project(root, {}, scope=EvidenceScope(include_tests=True))
        found, _ = search_index(snapshot, gap("path", "tests/test_api.py"))
        self.assertTrue(found)
        client = IterativeFixtureClient([response(findings=[{"title": "无效引用", "category": "explanation", "impact": "影响",
            "suggestion": "建议", "evidence_ids": ["unknown-id"]}])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["warnings"])

    def test_configuration_and_retention_fail_closed_and_report_exports_trace(self):
        snapshot = self.snapshot()
        for limit in (True, 0, 6, 1.2):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "round limit"):
                analyze_snapshot(snapshot, client=IterativeFixtureClient([]), strategy="iterative", max_retrieval_rounds=limit)
        client = IterativeFixtureClient([response([gap("path", "zzz.py")], retained=["not-current"])])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative")
        self.assertEqual(report["retrieval"]["stop_reason"], "invalid_evidence_request")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            write_analysis(output, report)
            self.assertEqual(json.loads((output / "retrieval.json").read_text()), report["retrieval"])
            self.assertFalse((output / "verified.patch").exists())

    def test_cli_iterative_task_and_limit_use_the_same_loop(self):
        root = self.fixture()
        client = IterativeFixtureClient([response([gap("path", "zzz.py")]), response()])
        with tempfile.TemporaryDirectory() as temporary, patch("exampleproof.model_api.JSONClient", return_value=client), \
                contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary) / "report"
            self.assertEqual(main(["analyze", str(root), "--provider", "ollama", "--model", "synthetic",
                "--context-strategy", "iterative", "--task", "configure a service", "--max-retrieval-rounds", "1", "--output", str(output)]), 0)
            report = json.loads((output / "analysis.json").read_text())
            self.assertEqual(report["retrieval"]["max_rounds"], 1)
            self.assertEqual(client.requests[0]["task"], "configure a service")
        with tempfile.TemporaryDirectory() as temporary, patch("exampleproof.model_api.JSONClient") as constructor, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["analyze", str(root), "--static", "--context-strategy", "iterative",
                                   "--output", str(Path(temporary) / "static")]), 2)
            constructor.assert_not_called()


class IterativeCloudTests(unittest.TestCase):
    fixture = IterativeRetrievalTests.fixture

    def cloud_response(self, request, **kwargs):
        payload = json.loads(json.loads(request.data)["messages"][1]["content"])
        value = response([gap("path", "zzz.py")]) if payload["retrieval"]["round"] == 0 else response()
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode())

    def test_cloud_preflight_covers_the_entire_index_and_every_round_is_redacted(self):
        root = self.fixture()
        (root / "zzz.py").write_text('def resolve_endpoint(value):\n    api_key = "prjkey198765"\n    return value\n')
        snapshot = prepare_project(root, {}, task='configure service password="tskkey983542"')
        target = next(c for c in snapshot.chunks if c.path == "zzz.py")
        self.assertNotIn(target, snapshot.candidates)
        client = JSONClient("deepseek", "synthetic", api_key="synthetic-api-key")
        client.evidence_kind = "synthetic_fixture"
        with tempfile.TemporaryDirectory() as temporary, patch("exampleproof.model_api.urlopen", side_effect=self.cloud_response) as send:
            review_path = Path(temporary) / "review.json"
            with self.assertRaisesRegex(ValueError, "No model request was sent"):
                review_cloud(snapshot, client, review_path, strategies=("iterative",), max_retrieval_rounds=2)
            send.assert_not_called()
            record = json.loads(review_path.read_text())
            self.assertEqual(len(record["review"]["permitted_evidence"]), len(snapshot.chunks))
            self.assertNotIn("prjkey198765", review_path.read_text())
            self.assertNotIn("tskkey983542", review_path.read_text())
            reviewed = review_cloud(snapshot, client, review_path, record["sha256"], strategies=("iterative",), max_retrieval_rounds=2)
            with self.assertRaisesRegex(ValueError, "round limit"):
                analyze_snapshot(snapshot, client=reviewed, strategy="iterative", max_retrieval_rounds=3)
            report = analyze_snapshot(snapshot, client=reviewed, strategy="iterative", max_retrieval_rounds=2)
            self.assertEqual(report["retrieval"]["stop_reason"], "model_finished")
            self.assertEqual(send.call_count, 2)
            for call in send.call_args_list:
                raw = call.args[0].data.decode()
                self.assertNotIn("prjkey198765", raw)
                self.assertNotIn("tskkey983542", raw)
                self.assertNotIn("synthetic-api-key", raw)
            sent = json.loads(json.loads(send.call_args_list[-1].args[0].data)["messages"][1]["content"])
            self.assertIn("zzz.py", {c["path"] for c in sent["evidence"]})
            self.assertIn("[REDACTED]", json.dumps(sent))
            self.assertEqual(report["mode"], "synthetic_fixture")
            from exampleproof.tutorial_retrieval import ITERATIVE_SYSTEM
            fake_metadata = {"round": 2, "max_rounds": 2, "last_search": [{
                "request": gap("path", "unreviewed.py"), "status": "matches", "matched_chunks": 1,
                "returned_ids": [target.id]}]}
            with self.assertRaisesRegex(ValueError, "Unreviewed cloud iteration"):
                reviewed.complete(ITERATIVE_SYSTEM, {"coverage": sent["coverage"], "task": snapshot.task,
                    "evidence": report["context"]["selected"], "retrieval": fake_metadata})
            self.assertEqual(send.call_count, 2)

    def test_cli_cloud_approval_binds_rounds_before_any_paid_request(self):
        root = self.fixture()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-api-key"}), \
                patch.object(JSONClient, "evidence_kind", "synthetic_fixture"), \
                patch("exampleproof.model_api.urlopen", side_effect=self.cloud_response) as send, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            output = Path(temporary) / "report"
            args = ["analyze", str(root), "--context-strategy", "iterative", "--task", "configure service",
                    "--max-retrieval-rounds", "1", "--output", str(output)]
            self.assertEqual(main(args), 2)
            send.assert_not_called()
            self.assertFalse(output.exists())
            record = json.loads(Path(str(output) + "-cloud-review.json").read_text())
            self.assertEqual(record["review"]["retrieval"]["max_rounds"], 1)
            approved = args + ["--approve-cloud", record["sha256"]]
            self.assertEqual(main(approved + ["--max-retrieval-rounds", "2"]), 2)
            send.assert_not_called()
            self.assertEqual(main(approved), 0)
            self.assertEqual(send.call_count, 2)
            report = json.loads((output / "retrieval.json").read_text())
            self.assertEqual(report["stop_reason"], "model_finished")


if __name__ == "__main__":
    unittest.main()
