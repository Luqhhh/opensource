"""Synthetic evidence-loss cases; these are not independent project findings."""

import json
from pathlib import Path
import tempfile
import unittest

from exampleproof.model_api import JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.tutorial import analyze_snapshot, prepare_project
from exampleproof.tutorial_scope import EvidenceScope
from exampleproof.tutorial_study import audit_comparison, run_comparison


class DiagnosticFixtureClient:
    provider = "synthetic_fixture"
    model = "diagnostic-fixture"
    evidence_kind = "synthetic_fixture"

    def __init__(self, values):
        self.values = iter(values)
        self.requests = []

    def complete(self, system, evidence):
        self.requests.append(evidence)
        value = next(self.values)
        if callable(value):
            value = value(evidence)
        return JSONReply(value, InferenceEvidence({"system": system, "evidence": evidence}, "synthetic", 1), 10, 2)


class EvidenceDiagnosticsTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "README.md").write_text("# Setup\n\nRead the API usage guide.\n")
        (root / "api.py").write_text("value = 1\n")
        return root

    def requirements(self, snapshot, paths):
        return {"schema_version": "tutorial-evidence-requirements-1", "snapshot_id": snapshot.snapshot_id,
                "evidence_kind": "synthetic_fixture", "annotator": "synthetic engineering fixture",
                "cases": [{"id": "task-1", "task": "Complete a specific API usage task",
                           "required": [{"path": p, "start_line": 1, "end_line": 1} for p in paths]}]}

    def diagnostic(self, report, path):
        spans = report["necessary_evidence_coverage"]["cases"][0]["required"]
        return next(s["diagnostic"] for s in spans if s["path"] == path)

    def test_policy_exclusion_unknown_input_and_bad_annotation_remain_distinct(self):
        root = self.fixture()
        (root / "tests").mkdir()
        (root / "tests/test_api.py").write_text("assert value == 1\n")
        snapshot = prepare_project(root, {})
        requirements = self.requirements(snapshot, ["tests/test_api.py", "missing.py", "README.md", "api.py"])
        requirements["cases"][0]["required"][2]["end_line"] = 100
        report = analyze_snapshot(snapshot, evidence_requirements=requirements)
        self.assertEqual(self.diagnostic(report, "tests/test_api.py")["first_gap"], "input_policy_exclusion")
        self.assertEqual(self.diagnostic(report, "missing.py")["first_gap"], "input_not_indexed_unknown")
        self.assertEqual(self.diagnostic(report, "README.md")["status"], "invalid_annotation")
        self.assertEqual(self.diagnostic(report, "api.py")["status"], "covered")
        coverage = report["necessary_evidence_coverage"]
        self.assertEqual(coverage["omissions"]["by_first_gap"], {"input_not_indexed_unknown": 1, "input_policy_exclusion": 1})
        self.assertEqual(coverage["omissions"]["invalid_annotation_spans"], 1)
        self.assertEqual(coverage["stages"]["indexed"]["total_spans"], 3)
        self.assertEqual(coverage["stages"]["indexed"]["total_cases"], 0)
        self.assertEqual(coverage["omissions"]["by_path_role"]["test"]["uncovered_spans"], 1)
        self.assertEqual(coverage["cases"][0]["task"], requirements["cases"][0]["task"])
        self.assertEqual(coverage["evidence_kind"], "synthetic_fixture")
        self.assertEqual(coverage["omissions"]["causal_conclusions"], "not_established")

    def test_recording_tasks_does_not_change_the_query_or_candidate_pool(self):
        snapshot = prepare_project(self.fixture(), {})
        original = analyze_snapshot(snapshot)
        report = analyze_snapshot(snapshot, evidence_requirements=self.requirements(snapshot, ["api.py"]))
        self.assertFalse(report["context"]["task_conditioned"])
        self.assertFalse(report["context"]["outside_candidate_search"])
        self.assertEqual(report["context"]["candidate_ids"], original["context"]["candidate_ids"])
        self.assertEqual(report["context"]["selected"], original["context"]["selected"])
        self.assertIsNone(original["necessary_evidence_coverage"]["omissions"])

    def test_candidate_cutoff_does_not_get_labeled_as_a_task_query_error(self):
        root = self.fixture()
        for i in range(55):
            (root / f"source{i:02}.py").write_text("value = 1\n")
        (root / "zzz.py").write_text("result = 2\n")
        snapshot = prepare_project(root, {})
        report = analyze_snapshot(snapshot, evidence_requirements=self.requirements(snapshot, ["zzz.py"]))
        self.assertEqual(self.diagnostic(report, "zzz.py")["first_gap"], "candidate_pool_omission")
        self.assertEqual(len(snapshot.candidates), 40)
        self.assertEqual(report["necessary_evidence_coverage"]["omissions"]["causal_conclusions"], "not_established")

    def test_visible_but_unchosen_source_is_a_selection_omission(self):
        snapshot = prepare_project(self.fixture(), {})
        client = DiagnosticFixtureClient([
            lambda p: {"selected_ids": [c["id"] for c in p["candidates"] if c["kind"] == "document"]},
            {"findings": []}])
        report = analyze_snapshot(snapshot, client=client, strategy="ai", evidence_requirements=self.requirements(snapshot, ["api.py"]))
        self.assertEqual(self.diagnostic(report, "api.py")["first_gap"], "ai_selection_omission")
        span = report["necessary_evidence_coverage"]["cases"][0]["required"][0]
        self.assertTrue(span["coverage"]["shown_to_selector"])
        self.assertFalse(span["coverage"]["before_budget"])

    def test_chosen_but_over_budget_source_is_a_budget_omission(self):
        root = self.fixture()
        (root / "api.py").write_text('value = "' + "x" * 3000 + '"\n')
        snapshot = prepare_project(root, {})
        client = DiagnosticFixtureClient([lambda p: {"selected_ids": [c["id"] for c in p["candidates"]]}, {"findings": []}])
        report = analyze_snapshot(snapshot, client=client, strategy="ai", context_chars=2000,
                                  evidence_requirements=self.requirements(snapshot, ["api.py"]))
        self.assertEqual(self.diagnostic(report, "api.py")["first_gap"], "context_budget_omission")
        self.assertTrue(report["necessary_evidence_coverage"]["cases"][0]["required"][0]["coverage"]["before_budget"])

    def limited_selector_fixture(self):
        root = self.fixture()
        for i in range(10):
            (root / f"source{i:02}.py").write_text('value = "' + "x" * 700 + '"\n')
        (root / "zzz.py").write_text('value = "' + "x" * 700 + '"\n')
        return prepare_project(root, {})

    def test_unshown_candidate_and_fallback_have_different_explanations(self):
        snapshot = self.limited_selector_fixture()
        for valid, expected in ((True, "selector_visibility_limit"), (False, "context_budget_omission")):
            with self.subTest(valid_selection=valid):
                selection = (lambda p: {"selected_ids": [c["id"] for c in p["candidates"] if c["kind"] == "document"]}) if valid else {"selected_ids": ["unknown-id"]}
                client = DiagnosticFixtureClient([selection, {"findings": []}])
                report = analyze_snapshot(snapshot, client=client, strategy="ai", context_chars=2000,
                                          evidence_requirements=self.requirements(snapshot, ["zzz.py"]))
                self.assertEqual(self.diagnostic(report, "zzz.py")["first_gap"], expected)
                self.assertFalse(report["necessary_evidence_coverage"]["cases"][0]["required"][0]["coverage"]["shown_to_selector"])

    def test_long_line_omitted_from_chunks_is_not_a_ranker_omission(self):
        root = self.fixture()
        (root / "api.py").write_text('value = "' + "x" * 5000 + '"\n')
        snapshot = prepare_project(root, {})
        report = analyze_snapshot(snapshot, evidence_requirements=self.requirements(snapshot, ["api.py"]))
        self.assertEqual(self.diagnostic(report, "api.py")["first_gap"], "chunk_index_omission")

    def test_audit_recomputes_omission_labels_with_the_frozen_scope(self):
        root = self.fixture()
        scope = EvidenceScope(include_tests=True)
        snapshot = prepare_project(root, {}, scope=scope)
        requirements = self.requirements(snapshot, ["tests/not_captured.py"])
        client = DiagnosticFixtureClient([{"findings": []}, lambda p: {"selected_ids": [p["candidates"][0]["id"]]}, {"findings": []}])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            run_comparison(root, {}, output, client, snapshot=snapshot, scope=scope, evidence_requirements=requirements)
            audit = audit_comparison(output)
            self.assertEqual(audit["status"], "passed", audit)
            self.assertIsNone(audit["quality_passed"])
            path = output / "lexical/analysis.json"
            report = json.loads(path.read_text())
            self.assertEqual(self.diagnostic(report, "tests/not_captured.py")["first_gap"], "input_not_indexed_unknown")
            report["necessary_evidence_coverage"]["cases"][0]["required"][0]["diagnostic"]["first_gap"] = "input_policy_exclusion"
            path.write_text(json.dumps(report))
            self.assertEqual(audit_comparison(output)["status"], "failed")

    def test_bad_task_annotations_fail_before_any_model_request(self):
        snapshot = prepare_project(self.fixture(), {})
        for task in (None, "", " ", ["not a string"]):
            requirements = self.requirements(snapshot, ["api.py"])
            requirements["cases"][0]["task"] = task
            client = DiagnosticFixtureClient([])
            with self.subTest(task=task), self.assertRaisesRegex(ValueError, "Annotated tasks"):
                analyze_snapshot(snapshot, client=client, evidence_requirements=requirements)
            self.assertEqual(client.requests, [])


if __name__ == "__main__":
    unittest.main()
