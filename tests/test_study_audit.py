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


if __name__ == "__main__":
    unittest.main()
