import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.benchmark import _write_json, load_manifest, run_benchmark, score_benchmark
from exampleproof.cli import main
from exampleproof.pipeline import read_project
from exampleproof.providers import FileProvider


def fixture(root):
    (root / "README.md").write_text("```python\nresult = missing_api(3)\n```\n\n```python\nresult = 6\n```\n")
    config = {"examples": {"README.md#1": {"checks": "assert result == 6"},
                            "README.md#2": {"checks": "assert result == 6"}}}
    (root / "exampleproof.json").write_text(json.dumps(config))
    manifest = {"schema_version": 1, "suite_id": "synthetic-test", "cases": [
        {"id": "README.md#1", "expected_before": "failed"},
        {"id": "README.md#2", "expected_before": "checked"}]}
    (root / "metadata.json").write_text(json.dumps(manifest))
    (root / "proposals.json").write_text(json.dumps({"README.md#1": {
        "code": "result = 3 * 2", "rationale": "Synthetic regression fixture"}}))
    return manifest


def report(*statuses):
    return {"repair": {}, "results": [{"example": {"id": f"README.md#{i}"}, "status": status,
                          "attempts": [{}] if status == "verified_repair" else []}
                         for i, status in enumerate(statuses, 1)]}


class BenchmarkTests(unittest.TestCase):
    def test_manifest_requires_exact_case_coverage_and_valid_expectations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = fixture(root)
            examples = read_project(root)[3]
            for cases in ([], original["cases"][:1], original["cases"] * 2,
                          [{"id": "README.md#1", "expected_before": []}],
                          [{"id": "README.md#1", "expected_before": "skipped"}]):
                with self.subTest(cases=cases):
                    (root / "metadata.json").write_text(json.dumps({**original, "cases": cases}))
                    with self.assertRaises(ValueError):
                        load_manifest(root, examples)

    def test_patch_recheck_and_healthy_controls_are_required_for_success(self):
        manifest = {"cases": [{"id": "README.md#1", "expected_before": "failed"},
                               {"id": "README.md#2", "expected_before": "checked"}]}
        baseline, repaired = report("failed", "checked"), report("verified_repair", "checked")
        missing = score_benchmark(manifest, baseline, repaired)
        self.assertIsNone(missing["repair_rate"])
        self.assertFalse(missing["all_passed"])
        regressed = score_benchmark(manifest, baseline, repaired, report("checked", "failed"))
        self.assertEqual(regressed["patch_confirmed_repairs"], 1)
        self.assertEqual(regressed["healthy_preserved"], 0)
        self.assertFalse(regressed["all_passed"])
        mismatch = score_benchmark(manifest, report("checked", "checked"), repaired, report("checked", "checked"))
        self.assertFalse(mismatch["baseline_valid"])
        self.assertIsNone(mismatch["repair_rate"])
        valid = score_benchmark(manifest, baseline, repaired, report("checked", "checked"))
        self.assertTrue(valid["all_passed"])
        self.assertEqual(valid["repair_rate"], 1)
        self.assertTrue(valid["evaluation_complete"])

    def test_unavailable_evidence_is_not_a_zero_rate_or_false_alarm(self):
        manifest = {"cases": [{"id": "README.md#1", "expected_before": "failed"},
                               {"id": "README.md#2", "expected_before": "checked"}]}
        baseline, repaired = report("failed", "checked"), report("verified_repair", "checked")
        blocked = score_benchmark(manifest, report("blocked", "blocked"))
        self.assertEqual(blocked["healthy_false_alarms"], 0)
        self.assertEqual(len(blocked["infrastructure_errors"]), 2)
        self.assertFalse(blocked["evaluation_complete"])
        self.assertIsNone(blocked["repair_rate"])
        for repair, patched in (
            (report("blocked", "checked"), report("checked", "checked")),
            (report("provider_error", "checked"), report("failed", "checked")),
            (repaired, report("blocked", "checked")),
            (repaired, report("checked")),
            (report("verified_repair"), report("checked", "checked")),
        ):
            with self.subTest(repair=repair, patched=patched):
                scored = score_benchmark(manifest, baseline, repair, patched)
                self.assertFalse(scored["evaluation_complete"])
                self.assertFalse(scored["all_passed"])
                self.assertIsNone(scored["repair_rate"])
                self.assertTrue(scored["infrastructure_errors"])
        false_alarm = score_benchmark(manifest, report("failed", "failed"))
        self.assertEqual(false_alarm["healthy_false_alarms"], 1)

    def test_stage_exceptions_preserve_failure_summary(self):
        baseline, repaired, patched = report("failed", "checked"), report("verified_repair", "checked"), report("checked", "checked")
        stages = (
            ("baseline", [OSError("baseline failed")], None),
            ("repair", [(baseline, ""), ValueError("repair failed")], None),
            ("patched", [(baseline, ""), (repaired, ""), SyntaxError("recheck failed")], None),
            ("baseline_report", [(baseline, "")], [OSError("report failed")]),
            ("repair_report", [(baseline, ""), (repaired, "")], [None, OSError("report failed")]),
            ("patched_report", [(baseline, ""), (repaired, ""), (patched, "")], [None, None, OSError("report failed")]),
        )
        for stage, executions, writes in stages:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture(root)
                originals = {p.name: p.read_bytes() for p in root.iterdir()}
                output = root / "evidence"
                with patch("exampleproof.benchmark.run_project", side_effect=executions), \
                        patch("exampleproof.benchmark.write_report", side_effect=writes):
                    summary, code = run_benchmark(root, output, FileProvider(root / "proposals.json"))
                self.assertEqual(code, 2)
                self.assertEqual(summary["error"]["stage"], stage)
                self.assertEqual(summary["stage"], stage)
                self.assertFalse(summary["metrics"]["evaluation_complete"])
                self.assertIsNone(summary["metrics"]["repair_rate"])
                self.assertFalse(summary["metrics"]["all_passed"])
                self.assertGreaterEqual(summary["duration_seconds"], 0)
                self.assertEqual(json.loads((output / "benchmark.json").read_text()), summary)
                self.assertEqual({name: (root / name).read_bytes() for name in originals}, originals)

    def test_failure_to_write_final_summary_propagates(self):
        def write(path, value):
            if path.name == "benchmark.json":
                raise OSError("summary disk failure")
            return _write_json(path, value)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            with patch("exampleproof.benchmark.run_project", side_effect=ValueError("execution failed")), \
                    patch("exampleproof.benchmark._write_json", side_effect=write):
                with self.assertRaisesRegex(OSError, "summary disk failure"):
                    run_benchmark(root, root / "evidence", FileProvider(root / "proposals.json"))

    def test_invalid_baseline_stops_before_model_call_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            provider = FileProvider(root / "proposals.json")
            output = root / "evidence"
            with patch("exampleproof.benchmark.run_project", return_value=(report("blocked", "blocked"), "")) as run:
                with patch("exampleproof.benchmark.write_report"):
                    summary, code = run_benchmark(root, output, provider)
            self.assertEqual(code, 2)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(summary["patch_application"], "not_attempted")
            self.assertIsNone(summary["metrics"]["verified_repairs"])
            self.assertTrue((output / "benchmark.json").exists())
            with self.assertRaisesRegex(ValueError, "new directory"):
                run_benchmark(root, output, provider)

    def test_missing_behavior_checks_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            (root / "exampleproof.json").write_text("{}")
            with contextlib.redirect_stderr(io.StringIO()), patch("exampleproof.benchmark.run_project") as run:
                code = main(["benchmark", str(root), "--proposals", str(root / "proposals.json"),
                             "--output", str(root / "evidence")])
            self.assertEqual(code, 2)
            run.assert_not_called()
            self.assertFalse((root / "evidence").exists())


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Set EXAMPLEPROOF_SANDBOX_TESTS=1")
class BenchmarkSandboxTests(unittest.TestCase):
    def test_cli_runs_frozen_inputs_applies_patch_rechecks_and_can_replay_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            fixture(root)
            originals = {p.name: p.read_bytes() for p in root.iterdir()}
            output = root / "evidence"
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["benchmark", str(root), "--proposals", str(root / "proposals.json"),
                             "--output", str(output)])
            self.assertEqual(code, 0)
            summary = json.loads((output / "benchmark.json").read_text())
            self.assertEqual(summary["mode"], "recorded_candidates")
            self.assertEqual(summary["repair"]["inference_requests"], 0)
            self.assertTrue(summary["metrics"]["all_passed"])
            self.assertEqual(summary["patch_application"], "passed")
            self.assertEqual(summary["metrics"]["healthy_preserved"], 1)
            self.assertEqual(json.loads((output / "patched/report.json").read_text())["summary"]["counts"], {"checked": 2})
            self.assertEqual({name: (root / name).read_bytes() for name in originals}, originals)
            replay, code = run_benchmark(output / "inputs", root / "replay",
                                         FileProvider(output / "inputs/proposals.json"))
            self.assertEqual(code, 0)
            self.assertTrue(replay["metrics"]["all_passed"])


if __name__ == "__main__":
    unittest.main()
