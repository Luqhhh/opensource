"""Study protocol regressions; all model responses and execution are test doubles."""

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from exampleproof import study
from exampleproof.models import Example, Execution, InferenceEvidence, Proposal, RepairAttempt
from exampleproof.pipeline import run_project
from exampleproof.providers import OllamaProvider, SYSTEM, WITHHELD_CHECK_ERROR


class RecordingRunner:
    backend = "test_double"

    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def run(self, code, spec):
        self.calls.append((code, spec))
        return next(self.outcomes)


class StudyTests(unittest.TestCase):
    example = Example("README.md#1", "README.md", 2, 2, "value = old()\n", "Use the documented API")
    before = Execution("failed", 21, stderr="AttributeError: old", oracle="configured_behavior_checks")
    source = {"sdk.py:1-2 (body excerpt)": "def new():\n    return 2\n"}
    spec = {"checks": "assert value == 2  # PRIVATE_CHECK_SENTINEL", "expected_stdout": ""}
    plan = {"model": "test-model", "timeout_seconds": 10, "calls_per_failure_max": 3,
            "generation_options": {"temperature": 0.2, "num_predict": 1024, "num_ctx": 8192}}

    @staticmethod
    def response(code="value = new()\n", **extra):
        value = {"done": True, "response": json.dumps({"code": code, "rationale": "API migration"}),
                 "prompt_eval_count": 100, "eval_count": 20, **extra}
        return io.BytesIO(json.dumps(value).encode())

    def evaluate(self, arm, runner, **kwargs):
        return study.evaluate_study_case(self.example, self.spec, {"sdk.py": "def new(): return 2\n"},
                                         self.before, self.source, self.plan, arm, 17,
                                         "http://127.0.0.1:11434", runner=runner, **kwargs)

    def test_actual_arm_payloads_differ_only_in_source_and_feedback(self):
        prior = RepairAttempt(1, "repair_failed", Proposal("value = partial()\n", "Prior candidate", "ollama"),
                              Execution("failed", 22, stderr="PRIVATE_CHECK_SENTINEL", oracle="configured_behavior_checks"))
        payloads = {}
        options = {**self.plan["generation_options"], "seed": 18}
        for arm in study.ARMS:
            with patch("exampleproof.providers.urlopen", return_value=self.response()) as opened:
                provider = study.StudyProvider("test-model", "http://127.0.0.1:11434", 10,
                                               options=options, arm=arm, context=self.source, history=(prior,))
                provider.propose(self.example, self.before, {"gold.py": "REFERENCE_ANSWER_SENTINEL"})
            payloads[arm] = json.loads(opened.call_args.args[0].data)
        prompts = {arm: json.loads(value["prompt"]) for arm, value in payloads.items()}
        self.assertEqual(prompts["direct"]["sources"], {})
        self.assertEqual(prompts["source"]["sources"], self.source)
        self.assertEqual(prompts["source_feedback"]["sources"], self.source)
        self.assertNotIn("previous_attempts", prompts["direct"])
        self.assertNotIn("previous_attempts", prompts["source"])
        history = prompts["source_feedback"]["previous_attempts"]
        self.assertEqual(history[0]["execution"]["error"], WITHHELD_CHECK_ERROR)
        self.assertEqual(history[0]["candidate"]["code"], "value = partial()\n")
        for arm, payload in payloads.items():
            self.assertEqual(payload["options"], options)
            self.assertEqual(payload["system"], SYSTEM)
            self.assertNotIn("PRIVATE_CHECK_SENTINEL", json.dumps(payload))
            self.assertNotIn("REFERENCE_ANSWER_SENTINEL", json.dumps(payload))
            neutral = {k: v for k, v in prompts[arm].items() if k not in {"sources", "previous_attempts"}}
            self.assertEqual(neutral, {k: v for k, v in prompts["direct"].items() if k != "sources"})

    def test_all_arms_pair_seeds_budget_and_stop_at_first_verified_candidate(self):
        for arm in study.ARMS:
            requests = []
            def respond(request, **kwargs):
                requests.append(json.loads(request.data))
                return self.response("value = partial()\n" if len(requests) == 1 else "value = new()\n")
            runner = RecordingRunner(Execution("failed", 21, stderr="first candidate runtime error"), Execution("passed", 0))
            with self.subTest(arm=arm), patch("exampleproof.providers.urlopen", side_effect=respond):
                outcome, attempts = self.evaluate(arm, runner)
            self.assertEqual(outcome["status"], "verified_repair")
            self.assertEqual(outcome["success_attempt"], 2)
            self.assertEqual([r["options"]["seed"] for r in requests], [17, 18])
            self.assertEqual([r["options"]["num_predict"] for r in requests], [1024, 1024])
            self.assertEqual([a.number for a in attempts], [1, 2])
            self.assertEqual(len(runner.calls), 2)
            second = json.loads(requests[1]["prompt"])
            self.assertEqual("previous_attempts" in second, arm == "source_feedback")
            if arm == "source_feedback":
                self.assertEqual(second["previous_attempts"][0]["execution"]["error"], "first candidate runtime error")
            self.assertNotIn("PRIVATE_CHECK_SENTINEL", json.dumps(requests))

    def test_declines_consume_equal_budget_and_do_not_execute_candidates(self):
        for arm in study.ARMS:
            requests = []
            def respond(request, **kwargs):
                requests.append(json.loads(request.data))
                return self.response("")
            runner = RecordingRunner()
            with self.subTest(arm=arm), patch("exampleproof.providers.urlopen", side_effect=respond):
                outcome, attempts = self.evaluate(arm, runner)
            self.assertEqual(outcome["status"], "not_repaired")
            self.assertEqual([r["options"]["seed"] for r in requests], [17, 18, 19])
            self.assertEqual([a.status for a in attempts], ["declined"] * 3)
            self.assertEqual(runner.calls, [])

    def test_invalid_generated_json_consumes_budget_and_can_be_followed_by_success(self):
        bad = self.response(response="{unfinished")
        runner = RecordingRunner(Execution("passed", 0))
        with patch("exampleproof.providers.urlopen", side_effect=[bad, self.response()]):
            outcome, attempts = self.evaluate("source_feedback", runner)
        self.assertEqual(outcome["status"], "verified_repair")
        self.assertEqual([a.status for a in attempts], ["provider_error", "verified_repair"])
        self.assertFalse(study.infrastructure_failure(attempts[0]))
        self.assertEqual(attempts[0].inference_evidence.response["response"], "{unfinished")

    def test_transport_failure_stops_cell_as_incomplete(self):
        for arm in study.ARMS:
            with self.subTest(arm=arm), patch("exampleproof.providers.urlopen", side_effect=TimeoutError("offline")) as opened:
                outcome, attempts = self.evaluate(arm, RecordingRunner())
            self.assertEqual(outcome["status"], "incomplete")
            self.assertTrue(study.infrastructure_failure(attempts[0]))
            self.assertEqual(opened.call_count, 1)

    def test_sandbox_unavailability_is_incomplete_and_stops_retries(self):
        with patch("exampleproof.providers.urlopen", return_value=self.response()) as opened:
            outcome, attempts = self.evaluate("source", RecordingRunner(Execution("blocked", stderr="bwrap unavailable")))
        self.assertEqual(outcome["status"], "incomplete")
        self.assertEqual(attempts[0].status, "blocked")
        self.assertEqual(opened.call_count, 1)

    def test_completed_server_envelope_without_valid_candidate_is_not_transport_failure(self):
        for response in ({"done": True, "response": "[]"}, {"done": True, "response": "{}"},
                         {"done": True, "response": "{unfinished"}):
            evidence = InferenceEvidence({}, "2026-10-13T00:00:00Z", 10, response=response)
            attempt = RepairAttempt(1, "provider_error", inference_evidence=evidence)
            self.assertFalse(study.infrastructure_failure(attempt))
        for response in (None, {"error": "model unavailable"}, {"done": False}, {"done": True, "error": "server failure"}):
            evidence = InferenceEvidence({}, "2026-10-13T00:00:00Z", 10, response=response)
            self.assertTrue(study.infrastructure_failure(RepairAttempt(1, "provider_error", inference_evidence=evidence)))

    def test_invalid_server_response_fields_are_incomplete_not_model_failures(self):
        valid = {"done": True, "response": json.dumps({"code": "value = new()\n", "rationale": "Migration"})}
        responses = [
            {"done": True},
            {"done": True, "response": 123},
            {**valid, "prompt_eval_count": -1},
            {**valid, "prompt_eval_count": True},
            {**valid, "eval_count": "20"},
        ]
        for response in responses:
            body = json.dumps(response).encode()
            with self.subTest(response=response), patch("exampleproof.providers.urlopen", side_effect=lambda *a, **k: io.BytesIO(body)) as opened:
                outcome, attempts = self.evaluate("source_feedback", RecordingRunner())
            self.assertEqual(outcome["status"], "incomplete")
            self.assertTrue(study.infrastructure_failure(attempts[0]))
            self.assertEqual(opened.call_count, 1)

    def test_source_excerpts_are_real_line_slices_deterministic_and_bounded(self):
        sources = {
            "sdk.py": "class API:\n    def old(self):\n        return 1\n\n    def new(self):\n        return 2\n",
            "other.py": "def unrelated():\n    return 10\n",
            "bad.py": "def syntax_error(\n",
        }
        first = study.source_context(self.example, self.before, sources, limit=240)
        second = study.source_context(self.example, self.before, dict(reversed(list(sources.items()))), limit=240)
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertLessEqual(sum(len(label) + len(text) for label, text in first.items()), 240)
        for label, text in first.items():
            match = re.fullmatch(r"(.+):(\d+)-(\d+) \((?:signature|body excerpt)\)", label)
            self.assertIsNotNone(match)
            filename, start, end = match.group(1), int(match.group(2)), int(match.group(3))
            self.assertGreaterEqual(end, start)
            self.assertEqual(text, "".join(sources[filename].splitlines(keepends=True)[start - 1:end]))
        self.assertEqual(study.source_context(self.example, self.before, sources, limit=1), {})

    def test_single_line_source_definitions_have_nonempty_valid_signature_ranges(self):
        sources = {"sdk.py": "def old(): return 1\nclass API: pass\n"}
        contexts = study.source_context(self.example, self.before, sources)
        signatures = {label: text for label, text in contexts.items() if label.endswith("(signature)")}
        self.assertTrue(signatures)
        for label, text in signatures.items():
            self.assertTrue(text, label)
            start, end = map(int, re.search(r":(\d+)-(\d+) ", label).groups())
            self.assertGreaterEqual(end, start)

    def frozen_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        project = base / "fixture"
        project.mkdir()
        (project / "README.md").write_text("```python\nvalue = old()\n```\n")
        (project / "sdk.py").write_text("def new():\n    return 2\n")
        (project / "exampleproof.json").write_text(json.dumps({
            "documents": ["README.md"], "source_files": ["sdk.py"], "examples": {self.example.id: self.spec}}))
        (project / "metadata.json").write_text(json.dumps({"schema_version": 1, "suite_id": "test-study-v1",
                                                          "cases": [{"id": self.example.id, "expected_before": "failed"}]}))
        (project / "provenance.json").write_text("{}\n")
        (project / "proposals.json").write_text(json.dumps({self.example.id: {"code": "REFERENCE_ANSWER_SENTINEL"}}))
        baseline, _ = run_project(project, runner=RecordingRunner(self.before))
        frozen = base / "frozen"
        with patch("exampleproof.study.local_metadata", return_value={"model": {"digest": "test-digest"}, "server": {"version": "test"}}), \
                patch("exampleproof.study.subprocess.check_output", return_value="test version\n"), \
                patch("exampleproof.study.run_project", return_value=(baseline, "")):
            plan = study.freeze_study([project], frozen, model="test-model")
        return frozen, plan

    def test_freeze_snapshot_contains_checks_but_generated_source_context_does_not(self):
        root, plan = self.frozen_fixture()
        study.verify_freeze(root, plan)
        self.assertIn("PRIVATE_CHECK_SENTINEL", (root / "inputs/fixture/exampleproof.json").read_text())
        text = (root / "contexts/fixture.json").read_text()
        self.assertNotIn("PRIVATE_CHECK_SENTINEL", text)
        self.assertNotIn("REFERENCE_ANSWER_SENTINEL", text)
        self.assertEqual(len(plan["schedule"]), len(study.ARMS) * len(study.SEEDS))

    def test_freeze_rejects_case_check_reference_and_context_tampering(self):
        for relative in ("inputs/fixture/README.md", "inputs/fixture/exampleproof.json",
                         "inputs/fixture/proposals.json", "contexts/fixture.json"):
            with self.subTest(relative=relative):
                root, plan = self.frozen_fixture()
                with (root / relative).open("a") as target:
                    target.write("\n ")
                with self.assertRaises(ValueError):
                    study.verify_freeze(root, plan)

    def test_freeze_rejects_baseline_error_or_healthy_state_tampering(self):
        root, plan = self.frozen_fixture()
        path = root / "baseline/fixture/report.json"
        report = json.loads(path.read_text())
        report["results"][0]["before"]["stderr"] = "different model-visible error"
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            study.verify_freeze(root, plan)

    def test_freeze_rejects_protocol_budget_seed_or_schedule_tampering(self):
        for field, replacement in (("calls_per_failure_max", 5), ("replicate_seeds", [99]), ("schedule", [])):
            with self.subTest(field=field):
                root, plan = self.frozen_fixture()
                changed = deepcopy(plan)
                changed[field] = replacement
                (root / "protocol.json").write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    study.verify_freeze(root, changed)

    def test_freeze_rejects_prompt_and_implementation_changes(self):
        root, plan = self.frozen_fixture()
        with patch("exampleproof.providers.SYSTEM", SYSTEM + "\nchanged"):
            with self.assertRaises(ValueError):
                study.verify_freeze(root, plan)
        with patch("exampleproof.study.implementation_hashes", return_value={"study.py": "changed"}):
            with self.assertRaises(ValueError):
                study.verify_freeze(root, plan)

    def write_cell(self, root, cell, status="complete", *, tokens=True):
        inference = {"duration_seconds": 1.5, "response": {"prompt_eval_count": 100, "eval_count": 20} if tokens else {}}
        attempt = {"status": "verified_repair", "proposal": {"inference_evidence": inference}}
        evidence = {"status": status, "duration_seconds": 2.0,
                    "cases": [{"example": {"id": self.example.id}, "status": "verified_repair", "success_attempt": 1, "attempts": [attempt]}],
                    "patch_validation": {"cases": [{"id": self.example.id, "patched_status": "checked"}]}}
        path = root / "runs" / str(cell["seed"]) / cell["arm"] / cell["project"] / "inference.json"
        study.write_json(path, evidence)

    def test_missing_or_incomplete_cells_never_report_success_rates(self):
        root, plan = self.frozen_fixture()
        self.write_cell(root, plan["schedule"][0])
        summary = study.summarize_study(root)
        self.assertFalse(summary["complete"])
        for group in summary["groups"].values():
            self.assertIsNone(group["budget_rate"])
            self.assertIsNone(group["first_try_rate"])
        for cell in plan["schedule"]:
            self.write_cell(root, cell, status="incomplete" if cell == plan["schedule"][-1] else "complete")
        summary = study.summarize_study(root)
        self.assertFalse(summary["complete"])
        self.assertTrue(all(group["budget_rate"] is None for group in summary["groups"].values()))

    def test_complete_summary_counts_only_paired_repeats_and_records_cost(self):
        root, plan = self.frozen_fixture()
        for cell in plan["schedule"]:
            self.write_cell(root, cell)
        summary = study.summarize_study(root)
        self.assertTrue(summary["complete"])
        for group in summary["groups"].values():
            self.assertEqual(group["case_runs"], 3)
            self.assertEqual(group["budget_passed"], 3)
            self.assertEqual(group["budget_rate"], 1)
            self.assertEqual(group["requests"], 3)
            self.assertEqual(group["input_tokens"], 300)
            self.assertEqual(group["output_tokens"], 60)
            self.assertEqual(group["inference_seconds"], 4.5)
        self.write_cell(root, plan["schedule"][0], tokens=False)
        summary = study.summarize_study(root)
        arm = plan["schedule"][0]["arm"]
        self.assertIsNone(summary["groups"][arm]["input_tokens"])
        self.assertIsNone(summary["groups"][arm]["output_tokens"])

    def test_started_run_requires_successful_final_verification_before_reporting_rates(self):
        root, plan = self.frozen_fixture()
        for cell in plan["schedule"]:
            self.write_cell(root, cell)
        study.write_json(root / "started.json", {"started_at": "2026-10-13T00:00:00Z"})
        summary = study.summarize_study(root)
        self.assertFalse(summary["complete"])
        self.assertEqual(summary["run_status"]["status"], "running_or_interrupted")
        self.assertTrue(all(group["budget_rate"] is None for group in summary["groups"].values()))
        study.write_json(root / "finished.json", {"status": "incomplete", "reason": "Final verification failed"})
        summary = study.summarize_study(root)
        self.assertFalse(summary["complete"])
        self.assertTrue(all(group["first_try_rate"] is None for group in summary["groups"].values()))
        study.write_json(root / "finished.json", {"status": "complete"})
        self.assertTrue(study.summarize_study(root)["complete"])

    def completed_mock_cell(self, root, plan, cell, endpoint):
        self.write_cell(root, cell)
        return {"status": "complete", "patch_validation": {"patch_confirmed_repairs": 1}}

    def test_run_verifies_final_metadata_and_records_successful_completion(self):
        root, plan = self.frozen_fixture()
        with patch("exampleproof.study.local_metadata", return_value=plan["model_metadata"]) as metadata, \
                patch("exampleproof.study.run_cell", side_effect=self.completed_mock_cell) as cells, \
                redirect_stdout(io.StringIO()):
            summary, code = study.run_study(root)
        self.assertEqual(code, 0)
        self.assertTrue(summary["complete"])
        self.assertEqual(metadata.call_count, 2)
        self.assertEqual(cells.call_count, len(plan["schedule"]))
        finished = json.loads((root / "finished.json").read_text())
        self.assertEqual(finished["status"], "complete")
        self.assertEqual(finished["metadata"], plan["model_metadata"])
        self.assertIn("finished_at", finished)

    def test_changed_model_at_final_verification_preserves_results_but_withholds_rates(self):
        root, plan = self.frozen_fixture()
        changed_metadata = deepcopy(plan["model_metadata"])
        changed_metadata["model"]["digest"] = "changed-after-generations"
        with patch("exampleproof.study.local_metadata", side_effect=[plan["model_metadata"], changed_metadata]), \
                patch("exampleproof.study.run_cell", side_effect=self.completed_mock_cell), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "changed during"):
            study.run_study(root)
        finished = json.loads((root / "finished.json").read_text())
        summary = json.loads((root / "summary.json").read_text())
        self.assertEqual(finished["status"], "incomplete")
        self.assertIn("changed during", finished["reason"])
        self.assertFalse(summary["complete"])
        self.assertEqual(summary["missing_or_incomplete"], [])
        self.assertTrue(all(group["case_runs"] == 3 for group in summary["groups"].values()))
        self.assertTrue(all(group["budget_rate"] is None for group in summary["groups"].values()))

    def test_final_frozen_input_check_detects_change_during_run(self):
        root, plan = self.frozen_fixture()
        def run_cell(run_root, run_plan, cell, endpoint):
            result = self.completed_mock_cell(run_root, run_plan, cell, endpoint)
            if cell == run_plan["schedule"][-1]:
                with (run_root / "inputs/fixture/exampleproof.json").open("a") as target:
                    target.write("\n ")
            return result
        with patch("exampleproof.study.local_metadata", return_value=plan["model_metadata"]), \
                patch("exampleproof.study.run_cell", side_effect=run_cell), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "Frozen project changed"):
            study.run_study(root)
        self.assertEqual(json.loads((root / "finished.json").read_text())["status"], "incomplete")
        summary = json.loads((root / "summary.json").read_text())
        self.assertFalse(summary["complete"])
        self.assertTrue(all(group["budget_rate"] is None for group in summary["groups"].values()))

    def test_run_exception_is_recorded_and_partial_summary_never_reports_rates(self):
        root, plan = self.frozen_fixture()
        with patch("exampleproof.study.local_metadata", return_value=plan["model_metadata"]), \
                patch("exampleproof.study.run_cell", side_effect=RuntimeError("test interruption")), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "test interruption"):
            study.run_study(root)
        finished = json.loads((root / "finished.json").read_text())
        self.assertEqual(finished["status"], "incomplete")
        self.assertIn("RuntimeError: test interruption", finished["reason"])
        summary = json.loads((root / "summary.json").read_text())
        self.assertFalse(summary["complete"])
        self.assertEqual(len(summary["missing_or_incomplete"]), len(plan["schedule"]))
        self.assertTrue(all(group["budget_rate"] is None for group in summary["groups"].values()))

    def test_generation_options_validate_copy_and_preserve_default(self):
        options = {"seed": 17, "temperature": 0.2, "num_ctx": 8192, "num_predict": 1024}
        provider = OllamaProvider("test-model", options=options)
        options["seed"] = 999
        self.assertEqual(provider.options["seed"], 17)
        self.assertEqual(OllamaProvider("test-model").options, {"temperature": 0})
        for options in ({"seed": True}, {"seed": -1}, {"seed": 2**31}, {"temperature": float("nan")},
                        {"temperature": True}, {"num_ctx": 0}, {"num_predict": 32769}, {"unknown": 1}, []):
            with self.subTest(options=options), self.assertRaises(ValueError):
                OllamaProvider("test-model", options=options)


if __name__ == "__main__":
    unittest.main()
