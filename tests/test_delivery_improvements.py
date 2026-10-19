"""Synthetic regression evidence; no independent human or live-model results."""
import contextlib
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof import tutorial_eval
from exampleproof.model_api import JSONClient, JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.tutorial import analyze_snapshot, prepare_project
from exampleproof.tutorial_budget import AnalysisDeadline, deadline
from exampleproof.tutorial_improve import improve, prepare_improvement, SYSTEM
from exampleproof.tutorial_privacy import review_cloud, review_payload


class Client:
    provider = "synthetic_fixture"
    model = "fixture"
    evidence_kind = "synthetic_fixture"
    def __init__(self, values, tokens=(10, 2), delay=0):
        self.values = iter(values)
        self.tokens, self.delay, self.payloads = tokens, delay, []
    def complete(self, system, payload):
        self.payloads.append(payload)
        if self.delay:
            time.sleep(self.delay)
        value = next(self.values)
        if callable(value):
            value = value(payload)
        return JSONReply(value, InferenceEvidence({"system": system, "payload": payload}, "synthetic", 1), *self.tokens)


def gap():
    return {"findings": [], "edits": [], "evidence_requests": [{"kind": "symbol", "query": "configure", "reason": "Need configuration behavior"}], "retain_ids": []}


class BudgetTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "README.md").write_text("# Setup\n\nRead the tutorial.\n")
        for i in range(50):
            (root / f"source{i:02}.py").write_text("value = 1\n")
        (root / "zzz.py").write_text("def configure():\n    return 3\n")
        return root, prepare_project(root, {})

    def test_budget_stops_before_next_request_and_preserves_exact_usage(self):
        root, snapshot = self.fixture()
        client = Client([gap(), {"findings": []}])
        report = analyze_snapshot(snapshot, client=client, strategy="iterative", max_total_tokens=12)
        self.assertEqual(len(client.payloads), 1)
        self.assertEqual(report["retrieval"]["stop_reason"], "token_budget")
        self.assertEqual(report["retrieval"]["budget"]["observed_total_tokens"], 12)
        self.assertEqual(report["usage"]["input_tokens"], 10)
        self.assertTrue(report["retrieval"]["unresolved_requests"])

    def test_unknown_usage_stops_additional_calls_without_zero_cost(self):
        root, snapshot = self.fixture()
        client = Client([gap()], tokens=(None, 2))
        report = analyze_snapshot(snapshot, client=client, strategy="iterative", max_total_tokens=100)
        self.assertEqual(report["retrieval"]["stop_reason"], "usage_unknown")
        self.assertIsNone(report["retrieval"]["budget"]["observed_total_tokens"])

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX hard deadline")
    def test_deadline_interrupts_blocking_provider_and_restores_signal(self):
        root, snapshot = self.fixture()
        handler = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        report = analyze_snapshot(snapshot, client=Client([gap()], delay=2), strategy="iterative", deadline_seconds=0.03)
        self.assertLess(time.monotonic() - started, 0.8)
        self.assertEqual(report["retrieval"]["stop_reason"], "deadline")
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX hard deadline")
    def test_cli_deadline_covers_input_preparation(self):
        root, _ = self.fixture()
        with patch("exampleproof.tutorial.discover", side_effect=lambda *a, **k: time.sleep(2)), contextlib.redirect_stderr(io.StringIO()):
            started = time.monotonic()
            self.assertEqual(main(["analyze", str(root), "--static", "--deadline-seconds", "0.03", "--output", str(root.parent / "unused")]), 2)
            self.assertLess(time.monotonic() - started, 0.8)

    def test_rounds_measure_new_required_evidence_only_with_annotations(self):
        root, snapshot = self.fixture()
        annotation = {"schema_version": "tutorial-evidence-requirements-1", "snapshot_id": snapshot.snapshot_id,
                      "evidence_kind": "synthetic_fixture", "annotator": "fixture",
                      "cases": [{"id": "task", "required": [{"path": "zzz.py", "start_line": 1, "end_line": 2}]}]}
        report = analyze_snapshot(snapshot, client=Client([gap(), {"findings": [], "evidence_requests": []}]),
                                  strategy="iterative", evidence_requirements=annotation)
        self.assertEqual([r["necessary_evidence"]["newly_covered_spans"] for r in report["retrieval"]["rounds"]], [0, 1])

    def test_cloud_approval_binds_token_threshold_and_deadline(self):
        root, snapshot = self.fixture()
        path = root.parent / (root.name + "-review.json")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        client = JSONClient("deepseek", "deepseek-flash", api_key="fixture")
        with self.assertRaises(ValueError):
            review_cloud(snapshot, client, path, strategies=("iterative",), max_total_tokens=100, deadline_seconds=10)
        approval = json.loads(path.read_text())["sha256"]
        reviewed = review_cloud(snapshot, client, path, approval, strategies=("iterative",), max_total_tokens=100, deadline_seconds=10)
        with patch.object(client, "complete") as call, self.assertRaisesRegex(ValueError, "budget"):
            analyze_snapshot(snapshot, client=reviewed, strategy="iterative", max_total_tokens=200, deadline_seconds=10)
        call.assert_not_called()


class EvaluationTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        root = base / "project"
        root.mkdir()
        (root / "README.md").write_text("# Setup\n\nInitialize the service.\n")
        spec = {"schema_version": "tutorial-task-evaluation-1", "projects": {"demo": {"root": str(root), "provenance": {}}},
                "model": {"provider": "synthetic_fixture", "name": "fixture"},
                "cases": [{"id": "initialization", "project": "demo", "task": "Initialize service", "acceptance": "Service returns expected result",
                           "required_evidence": [{"path": "README.md", "start_line": 1, "end_line": 3}],
                           "gold_issues": [{"id": "missing-api", "description": "Synthetic gold sentinel never sent to model"}]}]}
        frozen = base / "frozen"
        result = tutorial_eval.freeze(spec, frozen)
        review = {"seal": result["seal"], "reviewer": "synthetic human-record fixture; not a real review", "approved": True,
                  "independent_human": True, "authored_candidates_or_annotations": False, "complete_gold_inventory": True}
        return base, frozen, review

    def test_pending_review_prevents_all_model_creation(self):
        base, frozen, review = self.fixture()
        with patch("exampleproof.model_api.JSONClient") as client, self.assertRaisesRegex(ValueError, "Independent human"):
            tutorial_eval.run(frozen, base / "run", review | {"approved": False}, client)
        client.assert_not_called()
        self.assertFalse((base / "run").exists())

    def test_tampered_tasks_or_inputs_fail_before_calls(self):
        base, frozen, review = self.fixture()
        (frozen / "inputs/demo/README.md").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "changed"):
            tutorial_eval.verify(frozen)

    def test_strategies_share_task_scope_initial_context_and_keep_quality_unknown(self):
        base, frozen, review = self.fixture()
        clients = []
        def factory(*args):
            client = Client([{"findings": [], "evidence_requests": []}])
            clients.append(client)
            return client
        tutorial_eval.run(frozen, base / "run", review, factory)
        first, second = [c.payloads[0] for c in clients]
        self.assertEqual(first["task"], second["task"])
        self.assertEqual(first["evidence"], second["evidence"])
        self.assertNotIn("Synthetic gold sentinel", json.dumps([first, second]))
        summary = tutorial_eval.summarize(frozen, base / "run")
        self.assertIsNone(summary["support_rate"])
        self.assertIsNone(summary["reader_task_completion_rate"])
        results = json.loads((base / "run/results.json").read_text())
        self.assertEqual([r["usage"]["input_tokens"] for r in results["rows"]], [10, 10])
        quality = json.loads((base / "run/quality-review-template.json").read_text())
        quality.update(reviewer="synthetic review fixture", independent_human=True)
        summary = tutorial_eval.summarize(frozen, base / "run", quality)
        self.assertEqual(summary["metrics"]["lexical"]["issue_recall"], 0)
        self.assertIsNone(summary["metrics"]["lexical"]["reader_task_completion_rate"])
        quality["rows"].pop()
        with self.assertRaisesRegex(ValueError, "every run"):
            tutorial_eval.summarize(frozen, base / "run", quality)


class ImprovementTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        root = base / "project"
        root.mkdir()
        (root / "README.rst").write_text("Task\n====\n\n.. code-block:: python\n\n    >>> from pathlib import Path\n    >>> Path('/missing-directory/result.txt').write_text('stored')\n")
        snapshot = prepare_project(root, {})
        chunk = next(c for c in snapshot.chunks if c.path == "README.rst")
        report = analyze_snapshot(snapshot)
        report["findings"] = [{"title": "Use a writable local path", "category": "prerequisites", "impact": "Copying fails", "suggestion": "Use a relative path", "evidence": [asdict(chunk)]}]
        analysis = base / "analysis.json"
        analysis.write_text(json.dumps(report))
        contract = base / "contract.json"
        contract.write_text(json.dumps({"schema_version": "tutorial-task-1", "task": "Write result.txt", "document": "README.rst", "block": 1,
                                       "source_files": [], "checks": "assert Path('result.txt').read_text() == 'stored' # PRIVATE_ORACLE\n"}))
        proposal = base / "proposal.json"
        proposal.write_text(json.dumps({"original": "'/missing-directory/result.txt'", "replacement": "'result.txt'", "rationale": "Use local path"}))
        return base, root, analysis, contract, proposal

    def test_diagnosis_hash_and_exact_source_are_checked_before_provider(self):
        base, root, analysis, contract, proposal = self.fixture()
        prepared = prepare_improvement(root, analysis, contract, 0)
        self.assertNotIn("PRIVATE_ORACLE", json.dumps(prepared["payload"]))
        self.assertNotIn("checks", prepared["payload"])
        (root / "README.rst").write_text((root / "README.rst").read_text() + "\nChanged prose.\n")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            prepare_improvement(root, analysis, contract, 0)

    def test_exact_cloud_review_hides_oracle_and_binds_payload(self):
        base, root, analysis, contract, proposal = self.fixture()
        task = prepare_improvement(root, analysis, contract, 0)
        client = JSONClient("deepseek", "deepseek-flash", api_key="fixture")
        review_path = base / "review.json"
        with self.assertRaises(ValueError):
            review_payload(client, SYSTEM, task["payload"], task["binding"], review_path)
        self.assertNotIn("PRIVATE_ORACLE", review_path.read_text())
        approval = json.loads(review_path.read_text())["sha256"]
        reviewed = review_payload(client, SYSTEM, task["payload"], task["binding"], review_path, approval)
        with patch.object(client, "complete") as call, self.assertRaises(ValueError):
            reviewed.complete(SYSTEM, task["payload"] | {"checks": "private"})
        call.assert_not_called()

    @unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Requires real isolated execution")
    def test_recorded_finding_to_patch_keeps_oracle_and_rst_original(self):
        base, root, analysis, contract, proposal = self.fixture()
        before = (root / "README.rst").read_bytes()
        oracle = contract.read_bytes()
        result = improve(root, analysis, contract, 0, base / "result", proposal_path=proposal)
        self.assertEqual(result["status"], "task_validation_passed")
        self.assertEqual(result["candidate_origin"], "recorded_candidate")
        self.assertEqual(result["model_requests"], 0)
        self.assertEqual(result["task_validated_patches"], 1)
        self.assertEqual((base / "result/validation/contract.json").read_bytes(), oracle)
        self.assertEqual((root / "README.rst").read_bytes(), before)
        self.assertTrue((base / "result/adoptable.patch").is_file())

    @unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Requires real isolated execution")
    def test_running_but_wrong_task_does_not_export_adoptable_patch(self):
        base, root, analysis, contract, proposal = self.fixture()
        proposal.write_text(json.dumps({"original": "'/missing-directory/result.txt'", "replacement": "'wrong.txt'", "rationale": "Synthetic negative"}))
        result = improve(root, analysis, contract, 0, base / "result", proposal_path=proposal)
        self.assertEqual(result["status"], "task_validation_failed")
        self.assertFalse((base / "result/adoptable.patch").exists())


class ArchiveTests(unittest.TestCase):
    def test_archive_round_trip_and_tamper_detection(self):
        import importlib.util
        path = Path(__file__).resolve().parents[1] / "scripts/archive_tutorial_evidence.py"
        spec = importlib.util.spec_from_file_location("evidence_archive", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            (source / "record.json").write_text('{"mode":"synthetic_fixture"}\n')
            output = base / "evidence.tar.gz"
            result = module.archive(source, output, "recorded_candidate_replay")
            self.assertEqual(result["files"], 1)
            index = output.with_name(output.name + ".index.json")
            record = json.loads(index.read_text())
            record["files"][0]["sha256"] = "tampered"
            index.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                module.audit(output, index)


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Requires real isolated execution")
class GeneratedCandidateTests(unittest.TestCase):
    def fixture(self):
        helper = ImprovementTests()
        values = helper.fixture()
        self.addCleanup(helper.doCleanups)
        return values

    def test_synthetic_model_candidate_is_not_counted_as_live_evidence(self):
        base, root, analysis, contract, proposal = self.fixture()
        client = Client([json.loads(proposal.read_text())])
        result = improve(root, analysis, contract, 0, base / "generated", client=client)
        self.assertEqual(result["status"], "task_validation_passed")
        self.assertEqual(result["candidate_origin"], "synthetic_candidate")
        self.assertEqual(result["model_requests"], 1)
        self.assertNotIn("PRIVATE_ORACLE", json.dumps(client.payloads))
        self.assertTrue((base / "generated/inference.json").is_file())

    def test_model_cannot_supply_replacement_checks(self):
        base, root, analysis, contract, proposal = self.fixture()
        value = json.loads(proposal.read_text()) | {"checks": "assert True"}
        result = improve(root, analysis, contract, 0, base / "rejected", client=Client([value]))
        self.assertEqual(result["status"], "proposal_or_validation_failed")
        self.assertFalse((base / "rejected/adoptable.patch").exists())
        self.assertFalse((base / "rejected/validation").exists())


class EvaluationFailureTests(unittest.TestCase):
    def test_service_failure_is_unknown_recall_not_a_measured_miss(self):
        helper = EvaluationTests()
        base, frozen, review = helper.fixture()
        self.addCleanup(helper.doCleanups)
        class FailedClient(Client):
            def complete(self, *args):
                raise ValueError("Synthetic transport failure")
        tutorial_eval.run(frozen, base / "run", review, lambda *args: FailedClient([]))
        quality = json.loads((base / "run/quality-review-template.json").read_text())
        quality.update(reviewer="synthetic fixture", independent_human=True)
        summary = tutorial_eval.summarize(frozen, base / "run", quality)
        self.assertIsNone(summary["metrics"]["lexical"]["issue_recall"])
        self.assertEqual(summary["metrics"]["lexical"]["unavailable_runs"], 1)
