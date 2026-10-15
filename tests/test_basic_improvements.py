"""Usability regressions; model responses and ordinary runner calls are simulated."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from exampleproof import context, runner
from exampleproof.benchmark import score_benchmark
from exampleproof.cli import main
from exampleproof.models import Example, Execution, Proposal, Result
from exampleproof.pipeline import evaluate_example, exit_code, run_project
from exampleproof.providers import OllamaProvider
from exampleproof.report import render_html


class SequenceRunner:
    backend = "test_double"

    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def run(self, code, spec):
        self.calls.append(code)
        return next(self.outcomes)


def response(content, **metadata):
    return io.BytesIO(json.dumps({"done": True, "response": content,
                                 "prompt_eval_count": 10, "eval_count": 5, **metadata}).encode())


class EnvironmentTests(unittest.TestCase):
    def test_help_and_scan_load_without_unix_resource_module(self):
        # Simulate a Windows import environment in a fresh interpreter. The
        # document is only parsed; the example is never executed.
        program = '''import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "resource":
        raise ImportError("resource unavailable")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from exampleproof.cli import main
sys.exit(main(sys.argv[1:]))
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\nraise RuntimeError('never execute')\n```\n", encoding="utf-8")
            for args in (["--help"], ["scan", str(root)]):
                result = subprocess.run([sys.executable, "-c", program, *args],
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                if args[0] == "scan":
                    self.assertEqual(json.loads(result.stdout)[0]["id"], "README.md#1")

    def test_unsupported_platform_reports_requirements_without_spawning(self):
        with patch.object(runner.sys, "platform", "win32"), patch.object(runner, "resource", None), \
                patch.object(runner.shutil, "which", return_value=None), \
                patch.object(runner.subprocess, "Popen") as started:
            report = runner.environment_report()
            result = runner.SandboxRunner({}).run("pass", {})
        self.assertFalse(report["ready"])
        self.assertFalse(report["probe_performed"])
        self.assertEqual(result.status, "blocked")
        self.assertIn("doctor", result.stderr)
        started.assert_not_called()

    def test_doctor_uses_real_runner_for_namespace_probe(self):
        for status in ("passed", "blocked"):
            with self.subTest(status=status), patch.object(runner.sys, "platform", "linux"), \
                    patch.object(runner, "resource", object()), \
                    patch.object(runner.shutil, "which", return_value="/usr/bin/bwrap"), \
                    patch.object(runner.Path, "is_file", return_value=True), \
                    patch.object(runner.SandboxRunner, "run", return_value=Execution(status, stderr="probe")) as probe:
                report = runner.environment_report()
                self.assertEqual(report["ready"], status == "passed")
                self.assertTrue(report["probe_performed"])
                probe.assert_called_once_with("pass", {})

    def test_doctor_json_has_failure_exit_and_does_not_read_project(self):
        report = {"ready": False, "checks": [], "probe_performed": False}
        output = io.StringIO()
        with patch("exampleproof.cli.environment_report", return_value=report), \
                patch("exampleproof.cli.read_project") as read, contextlib.redirect_stdout(output):
            code = main(["doctor", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue()), report)
        read.assert_not_called()


class CandidateRetryTests(unittest.TestCase):
    original = "result = old_api()\nassert result == 2\n"
    fixed = "result = new_api()\nassert result == 2\n"

    def example(self):
        return Example("README.md#1", "README.md", 2, 3, self.original, "Keep the task behavior")

    def failure(self):
        return Execution("failed", 21, stderr="NameError: old_api", oracle="configured_behavior_checks")

    def test_malformed_candidate_retries_and_keeps_evidence_and_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_bytes(("```python\n" + self.original + "```\n").encode("utf-8"))
            (root / "exampleproof.json").write_text(json.dumps({"examples": {
                "README.md#1": {"checks": "assert result == 2, 'PRIVATE_CHECK'"}}}), encoding="utf-8")
            simulated = SequenceRunner(self.failure(), Execution("passed", 0))
            with patch("exampleproof.providers.urlopen", side_effect=[
                response("{unfinished"), response(json.dumps({"code": self.fixed, "rationale": "API change"}))
            ]) as opened:
                report, diff = run_project(root, OllamaProvider("simulated"), simulated, max_attempts=3)
            result = report["results"][0]
            self.assertEqual([a["status"] for a in result["attempts"]], ["candidate_format_error", "verified_repair"])
            self.assertEqual(result["attempts"][0]["inference_evidence"]["response"]["response"], "{unfinished")
            self.assertEqual(report["repair"]["inference_requests"], 2)
            self.assertEqual((report["repair"]["input_tokens"], report["repair"]["output_tokens"]), (20, 10))
            self.assertEqual(simulated.calls, [self.original, self.fixed])
            self.assertIn("+result = new_api()", diff)
            self.assertEqual(exit_code(report), 0)
            prompt = json.loads(opened.call_args.args[0].data)["prompt"]
            self.assertIn("candidate_format_error", prompt)
            self.assertNotIn("PRIVATE_CHECK", prompt)

    def test_invalid_candidate_schema_exhausts_existing_budget_without_execution(self):
        simulated = SequenceRunner(self.failure())
        with patch("exampleproof.providers.urlopen", side_effect=[response("[]"), response("{}")]) as opened:
            result = evaluate_example(self.example(), {}, {}, simulated, OllamaProvider("simulated"), max_attempts=2)
        self.assertEqual(result.status, "candidate_format_error")
        self.assertEqual(result.stop_reason, "max_attempts")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(len(simulated.calls), 1)

    def test_service_and_protocol_errors_stop_without_spending_more_budget(self):
        for body in ({"done": False, "response": "{}"}, {"done": True, "response": "{}", "eval_count": -1},
                     {"error": "model unavailable"}, []):
            with self.subTest(body=body), patch("exampleproof.providers.urlopen",
                    return_value=io.BytesIO(json.dumps(body).encode())) as opened:
                result = evaluate_example(self.example(), {}, {}, SequenceRunner(self.failure()),
                                          OllamaProvider("simulated"), max_attempts=3)
                self.assertEqual(result.status, "provider_error")
                self.assertEqual(opened.call_count, 1)
        with patch("exampleproof.providers.urlopen", side_effect=TimeoutError("offline")) as opened:
            result = evaluate_example(self.example(), {}, {}, SequenceRunner(self.failure()),
                                      OllamaProvider("simulated"), max_attempts=3)
        self.assertEqual(result.status, "provider_error")
        self.assertEqual(opened.call_count, 1)

    def test_benchmark_counts_format_failure_but_withholds_service_failure_rate(self):
        example = self.example()
        manifest = {"cases": [{"id": example.id, "expected_before": "failed"}]}
        baseline = {"results": [Result(example, self.failure(), "failed").to_dict()]}
        for status, complete in (("candidate_format_error", True), ("provider_error", False)):
            repaired = {"results": [Result(example, self.failure(), status).to_dict()]}
            metrics = score_benchmark(manifest, baseline, repaired, baseline)
            self.assertEqual(metrics["evaluation_complete"], complete)
            self.assertEqual(metrics["repair_rate"], 0 if complete else None)


class ProgressTests(unittest.TestCase):
    def test_events_follow_execution_and_library_is_silent_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\nassert True\n```\n", encoding="utf-8")
            events = []
            output, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                run_project(root, runner=SequenceRunner(Execution("passed", oracle="original_top_level_assertions")),
                            progress=events.append)
                run_project(root, runner=SequenceRunner(Execution("passed", oracle="original_top_level_assertions")))
            self.assertEqual([event["stage"] for event in events],
                             ["project_start", "example_start", "example_complete"])
            self.assertEqual(events[1]["index"], 1)
            self.assertEqual(events[1]["total"], 1)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(errors.getvalue(), "")

    def test_cli_progress_uses_stderr_and_quiet_removes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\nassert True\n```\n", encoding="utf-8")
            for quiet in (False, True):
                output, errors = io.StringIO(), io.StringIO()
                with patch("exampleproof.pipeline.SandboxRunner", return_value=SequenceRunner(
                        Execution("passed", oracle="original_top_level_assertions"))), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = main(["check", str(root), "--output", str(root / "reports"), *(["--quiet"] if quiet else [])])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue().splitlines()[0])["counts"], {"checked": 1})
                self.assertEqual(bool(errors.getvalue()), not quiet)
                if not quiet:
                    self.assertIn("[1/1]", errors.getvalue())

    def test_candidate_events_include_rejection_before_next_attempt(self):
        class Provider:
            def propose(self, example, before, sources, *, history=()):
                code = "result = 2\n" if not history else "result = 2\nassert result == 2\n"
                return Proposal(code, "simulated", "test_double")
        events = []
        example = Example("a.md#1", "a.md", 2, 3, "old()\nassert result == 2\n", "")
        result = evaluate_example(example, {}, {}, SequenceRunner(
            Execution("failed", oracle="original_top_level_assertions"), Execution("passed")),
            Provider(), max_attempts=2, progress=events.append)
        self.assertEqual(result.status, "verified_repair")
        self.assertEqual([event["stage"] for event in events],
                         ["attempt_start", "attempt_complete", "attempt_start", "attempt_complete"])
        self.assertEqual(events[1]["status"], "rejected")


class ContextCacheTests(unittest.TestCase):
    def example(self, code="fetch()"):
        return Example("a.md#1", "a.md", 2, 2, code, "Find records by key")

    def before(self):
        return Execution("failed", 21, stderr="TypeError: missing key")

    def test_reuses_parse_and_invalidates_changed_content(self):
        sources = {"api.py": "def fetch(key): return key\n"}
        cache = context.SourceContextCache()
        with patch.object(context, "_units", wraps=context._units) as parsed:
            first = context.source_context(self.example(), self.before(), sources, cache=cache)
            self.assertEqual(context.source_context(self.example(), self.before(), dict(sources), cache=cache), first)
            self.assertEqual(parsed.call_count, 1)
            sources["api.py"] = "def fetch(key): return key + 1\n"
            changed = context.source_context(self.example(), self.before(), sources, cache=cache)
            self.assertEqual(parsed.call_count, 2)
            self.assertNotEqual(changed, first)
        self.assertEqual(changed, context.source_context(self.example(), self.before(), sources))

    def test_cached_rankings_are_task_independent_and_do_not_mutate_units(self):
        sources = {"api.py": "def fetch(key): return key\ndef select(key): return key + 1\n"}
        cache = context.SourceContextCache()
        for code in ("fetch()", "select()", "fetch()"):
            example = self.example(code)
            self.assertEqual(context.source_context(example, self.before(), sources, cache=cache),
                             context.source_context(example, self.before(), sources))
        self.assertTrue(all("score" not in unit for unit in cache.project_units(sources)))

    def test_standard_index_terms_are_reused_and_cache_is_not_global(self):
        example = self.example("from library import removed\nremoved()")
        before = Execution("failed", 21, stderr="ImportError: cannot import name 'removed' from 'library'")
        sources = {"library.py": ""}
        cache = context.SourceContextCache()
        with patch.object(context, "_index_terms", wraps=context._index_terms) as indexed:
            first = context.source_context(example, before, sources, cache=cache)
            self.assertEqual(context.source_context(example, before, sources, cache=cache), first)
            self.assertEqual(indexed.call_count, 1)
            context.source_context(example, before, sources, cache=context.SourceContextCache())
            self.assertEqual(indexed.call_count, 2)


class ReportUsabilityTests(unittest.TestCase):
    def test_action_items_precede_success_and_errors_open_without_script(self):
        results = []
        for index, status in enumerate(("checked", "runnable_unverified", "failed")):
            example = Example(f"README.md#{index + 1}", "README.md", 2, 2, "<script>untrusted</script>", "")
            execution = Execution("failed" if status == "failed" else "passed", oracle="none")
            results.append(Result(example, execution, status).to_dict())
        report = {"project_name": "Demo", "generated_at": "now", "results": results,
                  "summary": {"total": 3, "counts": {r["status"]: 1 for r in results}},
                  "repair": {"attempts": 0, "max_attempts": 1, "input_tokens": None, "output_tokens": None}}
        html = render_html(report)
        self.assertLess(html.index('data-status="failed"'), html.index('data-status="checked"'))
        self.assertIn("<details open>", html)
        self.assertIn("下一步：", html)
        self.assertIn("2 项需要处理", html)
        self.assertIn("未提供", html)
        self.assertIn("&lt;script&gt;untrusted", html)
        self.assertNotIn("<script>untrusted", html)
        self.assertIn("script-src 'none'", html)
        self.assertEqual(report["results"][0]["status"], "checked")

    def test_behavior_and_stdout_failures_have_specific_guidance(self):
        from exampleproof.report import next_step
        for kind, text in (("behavior_check", "副作用"), ("stdout_mismatch", "换行")):
            example = Example("a.md#1", "a.md", 2, 2, "old()", "")
            result = Result(example, Execution("failed", failure_kind=kind), "failed").to_dict()
            self.assertIn(text, next_step(result))


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Set EXAMPLEPROOF_SANDBOX_TESTS=1")
class EnvironmentSandboxTests(unittest.TestCase):
    def test_doctor_success_in_real_sandbox(self):
        report = runner.environment_report()
        self.assertTrue(report["ready"], report)
        self.assertTrue(report["probe_performed"])

    def test_benchmark_progress_includes_all_three_phases(self):
        from exampleproof.benchmark import run_benchmark
        from exampleproof.providers import FileProvider
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            original = "```python\nresult = missing()\n```\n"
            (root / "README.md").write_text(original, encoding="utf-8")
            (root / "exampleproof.json").write_text(json.dumps({"examples": {"README.md#1": {
                "checks": "assert result == 2"}}}), encoding="utf-8")
            (root / "metadata.json").write_text(json.dumps({"schema_version": 1, "suite_id": "synthetic-progress",
                "cases": [{"id": "README.md#1", "expected_before": "failed"}]}), encoding="utf-8")
            candidates = root / "candidates.json"
            candidates.write_text(json.dumps({"README.md#1": {"code": "result = 2\n", "rationale": "recorded fixture"}}), encoding="utf-8")
            events = []
            summary, code = run_benchmark(root, Path(directory) / "evidence", FileProvider(candidates), progress=events.append)
            self.assertEqual(code, 0, summary)
            self.assertEqual([event["phase"] for event in events if event["stage"] == "phase_start"],
                             ["baseline", "repair", "patched"])
            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
