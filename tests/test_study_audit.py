"""Evidence tampering checks for the standalone read-only auditor; no model calls."""

from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


LOCATION = Path(__file__).resolve().parents[1] / "scripts/verify_real_project_study.py"
SPEC = importlib.util.spec_from_file_location("study_auditor", LOCATION)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class StudyAuditTests(unittest.TestCase):
    def fixture(self, arm="direct", previous=()):
        plan = {"model": "test-model", "system_prompt": "fixed system", "timeout_seconds": 10,
                "frozen_at": "2026-01-01T00:00:00+00:00", "generation_options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024}}
        example = {"id": "case.md#1", "context": "original context", "code": "old()\n"}
        before = {"status": "failed", "stderr": "NameError: old", "returncode": 21, "oracle": "configured_behavior_checks"}
        outcome = {"example": example, "before": before}
        project = {"contexts": {example["id"]: {"api.py:1-1 (signature)": "def replacement():\n"}}}
        cell = {"project": "test", "seed": 17, "arm": arm}
        prompt = {"example_id": example["id"], "context": example["context"], "code": example["code"],
                  "error": "NameError: old", "execution": {"status": "failed"},
                  "sources": {} if arm == "direct" else project["contexts"][example["id"]]}
        if previous and arm == "source_feedback":
            prompt["previous_attempts"] = [AUDIT.history_record(x) for x in previous]
        candidate = {"code": "replacement()\n", "rationale": "replace renamed API"}
        event = {"request": {"model": "test-model", "stream": False, "format": "json", "system": "fixed system",
                             "prompt": json.dumps(prompt), "options": {**plan["generation_options"], "seed": 17 + len(previous)}},
                 "timeout_seconds": 10, "started_at": "2026-01-01T00:00:01+00:00", "duration_seconds": 0.5,
                 "response": {"model": "test-model", "done": True, "response": json.dumps(candidate),
                              "prompt_eval_count": 10, "eval_count": 5, "total_duration": 400000000},
                 "response_body": None, "response_truncated": False}
        proposal = {**candidate, "provider": "ollama", "model": "test-model", "input_tokens": 10,
                    "output_tokens": 5, "duration_seconds": 0.5, "inference_evidence": event}
        attempt = {"number": len(previous) + 1, "status": "repair_failed", "proposal": proposal,
                   "after": {"status": "failed", "stderr": "external-checks: secret expected value", "returncode": 22,
                             "oracle": "configured_behavior_checks"}, "rejection": None}
        group = {"requests": 0, "inference_seconds": 0.0, "raw_server_seconds": 0.0,
                 "statuses": Counter(), "input_tokens": 0, "output_tokens": 0}
        return attempt, previous, outcome, project, plan, cell, group

    def test_patch_is_applied_in_memory_and_context_tampering_rejected(self):
        documents = {"a.md": "before\nold()\nafter\n"}
        patch = "--- a/a.md\n+++ b/a.md\n@@ -1,3 +1,3 @@\n before\n-old()\n+new()\n after\n"
        self.assertEqual(AUDIT.apply_saved_patch(documents, patch), {"a.md": "before\nnew()\nafter\n"})
        with self.assertRaisesRegex(ValueError, "context"):
            AUDIT.apply_saved_patch(documents, patch.replace("-old()", "-unrelated()"))
        self.assertEqual(documents["a.md"], "before\nold()\nafter\n")

    def test_actual_raw_cost_is_counted(self):
        fixture = self.fixture()
        AUDIT.inspect_attempt(*fixture)
        self.assertEqual(fixture[-1]["input_tokens"], 10)
        self.assertEqual(fixture[-1]["output_tokens"], 5)
        self.assertEqual(fixture[-1]["raw_server_seconds"], 0.4)

    def test_direct_sources_and_oracle_leaks_rejected(self):
        for extra in ({"sources": {"api.py": "secret source"}}, {"checks": "secret oracle"}, {"previous_attempts": []}):
            fixture = self.fixture()
            request = fixture[0]["proposal"]["inference_evidence"]["request"]
            request["prompt"] = json.dumps({**json.loads(request["prompt"]), **extra})
            with self.assertRaisesRegex(ValueError, "separation"):
                AUDIT.inspect_attempt(*fixture)

    def test_seed_and_token_budget_tampering_rejected(self):
        for key, value in (("seed", 18), ("num_predict", 2048), ("num_ctx", 16000)):
            fixture = self.fixture()
            fixture[0]["proposal"]["inference_evidence"]["request"]["options"][key] = value
            with self.assertRaisesRegex(ValueError, "options"):
                AUDIT.inspect_attempt(*fixture)

    def test_saved_candidate_must_equal_model_response(self):
        fixture = self.fixture()
        fixture[0]["proposal"]["code"] = "manual_fix()\n"
        with self.assertRaisesRegex(ValueError, "actual model response"):
            AUDIT.inspect_attempt(*fixture)

    def test_feedback_hides_external_checks_and_nonfeedback_has_no_history(self):
        previous = self.fixture()[0]
        fixture = self.fixture("source_feedback", (previous,))
        payload = AUDIT.inspect_attempt(*fixture)
        history = json.loads(payload["prompt"])["previous_attempts"]
        self.assertEqual(history[0]["execution"]["error"], AUDIT.WITHHELD)
        fixture = self.fixture("source", (previous,))
        payload = AUDIT.inspect_attempt(*fixture)
        self.assertNotIn("previous_attempts", json.loads(payload["prompt"]))

    def test_v2_request_uses_declared_context_prompt_and_sanitized_category(self):
        previous = self.fixture()[0]
        previous["after"]["failure_kind"] = "behavior_check"
        fixture = self.fixture("source_feedback", (previous,))
        attempt, _, outcome, project, plan, cell, _ = fixture
        cell["arm"] = "feedback_v2"
        plan["design"] = {"arms": {"feedback_v2": {
            "context": "v2", "feedback": "categorized", "system_prompt": "revised system"}}}
        project["contexts"]["case.md#1"] = {
            "legacy": project["contexts"]["case.md#1"], "v2": {"api.py:1-1": "def replacement():\n"}}
        project["config"] = {"examples": {"case.md#1": {"expected_stdout": ""}}}
        outcome["before"]["failure_kind"] = "example_exception"
        attempt["after"]["failure_kind"] = "behavior_check"
        request = attempt["proposal"]["inference_evidence"]["request"]
        request["system"] = "revised system"
        prompt = json.loads(request["prompt"])
        prompt["sources"] = project["contexts"]["case.md#1"]["v2"]
        prompt["previous_attempts"] = [AUDIT.history_record(previous, categorized=True)]
        request["prompt"] = json.dumps(prompt)
        payload = AUDIT.inspect_attempt(*fixture)
        self.assertNotIn("secret expected value", payload["prompt"])
        execution = json.loads(payload["prompt"])["previous_attempts"][0]["execution"]
        self.assertEqual(execution["category"], "behavior_check")
        prompt["previous_attempts"][0]["execution"]["guidance"] = "Use secret oracle answer"
        request["prompt"] = json.dumps(prompt)
        with self.assertRaisesRegex(ValueError, "separation"):
            AUDIT.inspect_attempt(*fixture)

    def test_v2_category_must_match_host_execution_facts(self):
        stdout = {"status": "failed", "returncode": 0, "stdout": "unexpected\n",
                  "stderr": "\nExpected stdout did not match the configured oracle.",
                  "failure_kind": "stdout_mismatch"}
        AUDIT.inspect_failure_kind(stdout, {"expected_stdout": ""})
        with self.assertRaisesRegex(ValueError, "recorded mismatch"):
            AUDIT.inspect_failure_kind(stdout, {"expected_stdout": "unexpected\n"})
        with self.assertRaisesRegex(ValueError, "category"):
            AUDIT.inspect_failure_kind({**stdout, "failure_kind": "behavior_check"}, {"expected_stdout": ""})
        with self.assertRaisesRegex(ValueError, "category"):
            AUDIT.inspect_failure_kind({"status": "failed", "returncode": 22, "failure_kind": "stdout_mismatch"}, {})

    def test_v2_context_rejects_duplicated_or_fabricated_lines_and_over_budget(self):
        sources = {"api.py": "def first():\n    return 1\ndef second(): return 2\n"}
        context = {"api.py:1-2": "def first():\n    return 1\n"}
        AUDIT.inspect_context(context, sources, 100, version="v2")
        for bad, message in (({**context, "api.py:2-2": "    return 1\n"}, "duplicate"),
                             ({"api.py:1-2": "def answer(): return 42\n"}, "original source"),
                             ({"api.py:0-1": "def first():\n"}, "range")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                AUDIT.inspect_context(bad, sources, 200, version="v2")
        with self.assertRaisesRegex(ValueError, "budget"):
            AUDIT.inspect_context(context, sources, 1, version="v2")

    def test_stdlib_excerpts_cannot_include_unindexed_implementation_body(self):
        sources = {"stdlib/demo.py": 'def demo(item):\n    """Process an item."""\n    return item\n'}
        standard = {"sources": sources, "entries": (("stdlib/demo.py", 1, 2, "demo", ""),)}
        context = {"stdlib/demo.py:1-2": 'def demo(item):\n    """Process an item."""\n'}
        AUDIT.inspect_context(context, {}, 200, version="v2", standard=standard)
        with self.assertRaisesRegex(ValueError, "signature/docstring"):
            AUDIT.inspect_context({"stdlib/demo.py:1-3": sources["stdlib/demo.py"]}, {}, 200,
                                  version="v2", standard=standard)

    def test_stdlib_pool_needs_observed_matching_import_and_separate_budget(self):
        design = {"retrieval_policy": {"triggered_character_budget": {"project": 4000, "stdlib": 2000},
                                       "untriggered_project_character_budget": 6000}}
        example = {"code": "from project import removed\nremoved()"}
        before = {"status": "failed", "returncode": 21, "oracle": "configured_behavior_checks",
                  "stderr": "ImportError: cannot import name 'removed' from 'project'"}
        context = {"stdlib/demo.py:1-1": "def demo(): pass\n"}
        AUDIT.inspect_retrieval_pools(context, example, before, {"project.py": ""}, design)
        with self.assertRaisesRegex(ValueError, "trigger"):
            AUDIT.inspect_retrieval_pools(context, {"code": "removed()"}, before, {"project.py": ""}, design)
        with self.assertRaisesRegex(ValueError, "trigger"):
            AUDIT.inspect_retrieval_pools(context, example, {**before, "returncode": 22}, {"project.py": ""}, design)
        with self.assertRaisesRegex(ValueError, "Project retrieval allocation"):
            AUDIT.inspect_retrieval_pools({**context, "project.py:1-1": "x" * 4000}, example, before, {"project.py": ""}, design)
        with self.assertRaisesRegex(ValueError, "Stdlib retrieval budget"):
            AUDIT.inspect_retrieval_pools({"stdlib/demo.py:1-1": "x" * 2000}, example, before, {"project.py": ""}, design)

    def test_archived_prompt_reader_never_executes_python(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "providers.py"
            path.write_text("raise RuntimeError('must not execute')\nSYSTEM = 'fixed'\nSYSTEM_V2 = SYSTEM + ' revision'\n")
            self.assertEqual(AUDIT.static_system_prompts(path), {"SYSTEM": "fixed", "SYSTEM_V2": "fixed revision"})

    def test_holdout_method_lock_detects_drift_and_invalid_chronology(self):
        design = {"split": "holdout", "arms": {"an_arm": {}}, "seeds": [17]}
        plan = {"implementation_sha256": {"core.py": "fixed"}, "frozen_at": "2026-01-02T00:00:00+00:00"}
        locked = {"locked_at": "2026-01-01T00:00:00+00:00", "implementation_sha256": plan["implementation_sha256"], "design": dict(design)}
        digest = AUDIT.text_sha(json.dumps(locked, ensure_ascii=False, indent=2) + "\n")
        design["method_lock"] = {"sha256": digest, **locked}
        AUDIT.inspect_method_lock(design, plan)
        with self.assertRaisesRegex(ValueError, "after input freeze"):
            AUDIT.inspect_method_lock(design, {**plan, "frozen_at": "2025-01-01T00:00:00+00:00"})
        with self.assertRaisesRegex(ValueError, "implementation"):
            AUDIT.inspect_method_lock(design, {**plan, "implementation_sha256": {"core.py": "changed"}})
        design["method_lock"]["locked_at"] = "2025-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "seal"):
            AUDIT.inspect_method_lock(design, plan)

    def test_seen_development_project_cannot_be_declared_holdout(self):
        design = {"split": "holdout"}
        good = {"split": "holdout_v2", "selection": {"held_out_from_method_optimization": True}, "provenance": {}}
        AUDIT.inspect_split(good, design)
        for bad in ({**good, "split": "development_v2"},
                    {**good, "selection": {}},
                    {**good, "provenance": {"previous_cases_and_live_results_seen": True}},
                    {**good, "provenance": {"live_model_evaluation": True}}):
            with self.subTest(metadata=bad), self.assertRaises(ValueError):
                AUDIT.inspect_split(bad, design)

    def test_missing_runs_return_incomplete_not_passed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            study = root / "study"
            core = repo / "exampleproof"
            archive = study / "implementation/exampleproof"
            inputs = study / "inputs/demo"
            for path in (core, archive, inputs, study / "baseline/demo", study / "contexts"):
                path.mkdir(parents=True, exist_ok=True)
            for path in (core, archive):
                (path / "providers.py").write_text("SYSTEM = 'fixed system'\n")
            doc = "# Demo\n\n```python\nbroken()\n```\n"
            config = {"documents": ["case.md"], "source_files": [], "examples": {"case.md#1": {"expected_stdout": ""}}}
            (inputs / "case.md").write_text(doc)
            (inputs / "exampleproof.json").write_text(json.dumps(config))
            baseline = {"runner": "bubblewrap", "provenance": {"documents": {"case.md": AUDIT.text_sha(doc)}, "sources": {},
                        "configuration_sha256": AUDIT.text_sha(json.dumps(config, sort_keys=True))},
                        "results": [{"example": {"id": "case.md#1", "path": "case.md", "start_line": 4, "end_line": 4,
                                                  "code": "broken()\n", "context": "# Demo\n# Demo"}, "status": "failed"}]}
            (study / "baseline/demo/report.json").write_text(json.dumps(baseline))
            (study / "contexts/demo.json").write_text(json.dumps({"case.md#1": {}}))
            plan = {"status": "frozen_before_live_inference", "system_prompt": "fixed system", "system_sha256": AUDIT.text_sha("fixed system"),
                    "implementation_sha256": {"providers.py": AUDIT.sha(core / "providers.py")}, "source_context_character_limit": 12000,
                    "arms": ["direct", "source", "source_feedback"], "replicate_seeds": [17],
                    "schedule": [{"project": "demo", "seed": 17, "arm": arm} for arm in ("direct", "source", "source_feedback")],
                    "projects": [{"name": "demo", "input_sha256": AUDIT.inventory(inputs),
                                  "context_sha256": AUDIT.sha(study / "contexts/demo.json"),
                                  "baseline_sha256": AUDIT.sha(study / "baseline/demo/report.json"), "expected": {"case.md#1": "failed"}}]}
            (study / "protocol.json").write_text(json.dumps(plan))
            (study / "protocol.sha256").write_text(AUDIT.sha(study / "protocol.json"))
            result = AUDIT.audit(study, repo)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["errors"], [])
            self.assertTrue(result["incomplete"])
            # Archived mode is explicit: it permits later core revisions while
            # retaining every check against the frozen implementation itself.
            (core / "providers.py").write_text("SYSTEM = 'a later revision'\n")
            self.assertEqual(AUDIT.audit(study, repo)["status"], "failed")
            archived = AUDIT.audit(study, repo, archived_only=True)
            self.assertEqual(archived["status"], "incomplete")
            self.assertEqual(archived["implementation_check"], "archived_only")
            self.assertEqual(archived["errors"], [])
            (archive / "providers.py").write_text("SYSTEM = 'tampered archive'\n")
            self.assertEqual(AUDIT.audit(study, repo, archived_only=True)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
