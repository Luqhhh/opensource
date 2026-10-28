"""Semantic-v3 regressions: simulated inference, with explicit sandbox controls."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.context import SourceContextCache, merge_source_contexts, source_api_headers
from exampleproof.guard import validate_candidate
from exampleproof.models import Example, Execution, Proposal, RepairAttempt
from exampleproof.pipeline import evaluate_example, run_project
from exampleproof.providers import (AdaptiveOllamaProvider, OllamaProvider, SemanticOllamaProvider,
                                    public_callable_requirements, validate_public_bindings)


def response(code, rationale="simulated candidate"):
    return io.BytesIO(json.dumps({"done": True, "response": json.dumps({"code": code, "rationale": rationale}),
                                 "prompt_eval_count": 20, "eval_count": 10}).encode())


class SequenceRunner:
    backend = "test_double"

    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def run(self, code, spec):
        self.calls.append(code)
        return next(self.outcomes)


class AdapterGuardTests(unittest.TestCase):
    original = "convert = old_converter\nassert convert(3) == '3'\n"
    candidate = "def convert(value):\n    return value if isinstance(value, str) else str(value)\nassert convert(3) == '3'\n"

    def test_adapters_are_opt_in_and_original_assertions_stay_at_top_level(self):
        self.assertIsNotNone(validate_candidate(self.original, self.candidate))
        self.assertIsNone(validate_candidate(self.original, self.candidate, allow_helpers=True))
        for code in ("def convert(value):\n    assert convert(3) == '3'\n    return str(value)\n",
                     self.candidate.replace("assert convert(3) == '3'", "assert True")):
            with self.subTest(code=code):
                self.assertIsNotNone(validate_candidate(self.original, code, allow_helpers=True))

    def test_decorators_effectful_defaults_control_flow_and_mutation_stay_rejected(self):
        for function in ("@wrapper\ndef convert(value):\n    return str(value)\n",
                         "def convert(value=setup()):\n    return str(value)\n",
                         "def convert(value: str):\n    return value\n",
                         "def convert(value):\n    if value:\n        return str(value)\n    return ''\n",
                         "def convert(value):\n    value[0] = 1\n    return value\n",
                         "def convert(value):\n    return eval(value)\n",
                         "def convert(value):\n    return value.__class__\n",
                         "def __adapter(value):\n    return str(value)\n"):
            with self.subTest(function=function):
                self.assertIsNotNone(validate_candidate("pass\n", function, allow_helpers=True))

    def test_constant_defaults_varargs_and_docstrings_are_supported(self):
        candidate = 'def convert(value=None, *args, reverse=False, count=-1, **kwargs):\n    """Public adapter."""\n    result = str(value)\n    return result\n'
        self.assertIsNone(validate_candidate("pass\n", candidate, allow_helpers=True))


class PublicContractTests(unittest.TestCase):
    def test_explicit_names_before_callable_and_signatures_are_supported(self):
        for context in ("Keep a reusable zero-argument reset callable bound to the store.",
                        "Keep a reusable reset(item) callable bound to the store."):
            with self.subTest(context=context):
                example = self.example(code="reset = missing\n", context=context)
                self.assertEqual(public_callable_requirements(example), ("reset",))
                self.assertIsNotNone(validate_public_bindings(example, "other = missing\n"))

    def example(self, code="from library import collate\nprint(list(collate([1], [2])))\n", context="Preserve a reusable callable named collate."):
        return Example("a.md#1", "a.md", 2, 3, code, context)

    def test_only_explicit_public_callable_names_bound_in_original_are_required(self):
        self.assertEqual(public_callable_requirements(self.example()), ("collate",))
        self.assertEqual(public_callable_requirements(self.example(context="Use the library to merge iterables.")), ())
        self.assertEqual(public_callable_requirements(self.example(context="Keep a callable named secret_check.")), ())
        self.assertEqual(public_callable_requirements(self.example(context="保留名为 collate 的函数。")), ("collate",))
        self.assertEqual(public_callable_requirements(self.example(code="obj.attribute = 1\n", context="Keep a callable named obj.")), ())

    def test_missing_noncallable_and_overwritten_bindings_are_rejected(self):
        for code in ("from heapq import merge\nprint(list(merge([1], [2])))\n", "collate = None\n",
                     "def collate(items):\n    return items\ncollate = []\n", "other = 1\ncollate = other\n"):
            with self.subTest(code=code):
                self.assertIsNotNone(validate_public_bindings(self.example(), code))

    def test_aliases_and_adapters_preserve_bindings_without_claiming_semantics(self):
        for code in ("from heapq import merge as collate\n", "from heapq import merge\ncollate = merge\n",
                     "collate = lambda *items: items\n", "def collate(items):\n    return items\n",
                     "from heapq import merge\ncollate, other = merge, None\n"):
            with self.subTest(code=code):
                self.assertIsNone(validate_public_bindings(self.example(), code))


class AdaptiveProviderTests(unittest.TestCase):
    example = Example("a.md#1", "a.md", 2, 3, "convert = missing\nassert convert(3) == '3'\n",
                      "Keep a reusable callable named convert. Convert non-strings, preserve strings.")
    before = Execution("failed", 21, stderr="NameError: missing", oracle="configured_behavior_checks", failure_kind="example_exception")
    fixed = "def convert(value):\n    return value if isinstance(value, str) else str(value)\nassert convert(3) == '3'\n"

    def test_unchanged_original_is_rejected_before_execution_with_specific_feedback(self):
        runner = SequenceRunner(self.before, Execution("passed", 0))
        with patch("exampleproof.providers.urlopen", side_effect=[response(self.example.code + "# unchanged\n"),
                                                                 response(self.fixed)]) as opened:
            result = evaluate_example(self.example, {}, {}, runner, AdaptiveOllamaProvider("simulated"), max_attempts=2)
        self.assertEqual([attempt.status for attempt in result.attempts], ["rejected", "verified_repair"])
        self.assertEqual(runner.calls, [self.example.code, self.fixed])
        history = json.loads(json.loads(opened.call_args.args[0].data)["prompt"])["previous_attempts"]
        self.assertIn("unchanged from the known-failing original", history[0]["rejection"])

    def test_comments_and_quote_changes_do_not_repeat_a_failed_sandbox_run(self):
        failed = "convert = str\nassert convert(3) == '3'\n"
        equivalent = '# formatting only\nconvert=str\nassert convert(3)=="3"\n'
        runner = SequenceRunner(self.before, Execution("failed", 22), Execution("passed", 0))
        with patch("exampleproof.providers.urlopen", side_effect=[response(failed), response(equivalent), response(self.fixed)]):
            result = evaluate_example(self.example, {}, {}, runner, AdaptiveOllamaProvider("simulated"), max_attempts=3)
        self.assertEqual([attempt.status for attempt in result.attempts], ["repair_failed", "repeated_candidate", "verified_repair"])
        self.assertEqual(runner.calls, [self.example.code, failed, self.fixed])

    def test_schema_is_v3_only_and_recorded_in_each_request(self):
        for provider in (OllamaProvider("simulated"), SemanticOllamaProvider("simulated"),
                         AdaptiveOllamaProvider("simulated")):
            with self.subTest(provider=type(provider).__name__), \
                    patch("exampleproof.providers.urlopen", return_value=response(self.fixed)) as opened:
                proposal = provider.propose(self.example, self.before, {})
                payload = json.loads(opened.call_args.args[0].data)
                self.assertEqual(payload, proposal.inference_evidence.request)
                if isinstance(provider, AdaptiveOllamaProvider):
                    self.assertEqual(payload["format"]["required"], ["code", "rationale"])
                    self.assertEqual(payload["format"]["properties"],
                                     {"code": {"type": "string"}, "rationale": {"type": "string"}})
                    self.assertFalse(payload["format"]["additionalProperties"])
                else:
                    self.assertEqual(payload["format"], "json")

    def test_invalid_schema_response_still_uses_validation_and_finite_retry_budget(self):
        malformed = io.BytesIO(json.dumps({"done": True, "response": json.dumps({"rationale": "missing code"}),
                                          "prompt_eval_count": 20, "eval_count": 10}).encode())
        runner = SequenceRunner(self.before, Execution("passed", 0))
        with patch("exampleproof.providers.urlopen", side_effect=[malformed, response(self.fixed)]) as opened:
            result = evaluate_example(self.example, {}, {}, runner, AdaptiveOllamaProvider("simulated"), max_attempts=2)
        self.assertEqual([attempt.status for attempt in result.attempts], ["candidate_format_error", "verified_repair"])
        self.assertEqual(runner.calls, [self.example.code, self.fixed])
        first = result.attempts[0]
        self.assertEqual(json.loads(first.inference_evidence.response["response"]), {"rationale": "missing code"})
        payload = json.loads(opened.call_args.args[0].data)
        self.assertEqual(payload["options"]["seed"], 18)
        self.assertIn("string fields code and rationale", json.loads(payload["prompt"])["previous_attempts"][0]["rejection"])

    def test_contract_rejection_is_feedback_and_does_not_execute_candidate(self):
        runner = SequenceRunner(self.before, Execution("passed", 0))
        with patch("exampleproof.providers.urlopen", side_effect=[
                response("convert = 3\nassert convert(3) == '3'\n"), response(self.fixed)]) as opened:
            result = evaluate_example(self.example, {"checks": "assert False, 'PRIVATE_CHECK'"}, {}, runner,
                                      AdaptiveOllamaProvider("simulated"), max_attempts=2)
        self.assertEqual(result.status, "verified_repair")
        self.assertEqual([attempt.status for attempt in result.attempts], ["rejected", "verified_repair"])
        self.assertEqual(runner.calls, [self.example.code, self.fixed])
        payload = json.loads(opened.call_args.args[0].data)
        prompt = json.loads(payload["prompt"])
        self.assertEqual(prompt["public_requirements"]["callable_bindings"], ["convert"])
        self.assertIn("non-callable", prompt["previous_attempts"][0]["rejection"])
        self.assertNotIn("PRIVATE_CHECK", payload["prompt"])

    def test_repeat_spends_budget_but_is_not_executed_and_can_be_followed_by_success(self):
        failed = "convert = str\nassert convert(3) == '3'\n"
        runner = SequenceRunner(self.before, Execution("failed", 22, oracle="configured_behavior_checks"), Execution("passed", 0))
        with patch("exampleproof.providers.urlopen", side_effect=[response(failed), response(failed), response(self.fixed)]) as opened:
            result = evaluate_example(self.example, {}, {}, runner, AdaptiveOllamaProvider("simulated"), max_attempts=3)
        self.assertEqual([attempt.status for attempt in result.attempts], ["repair_failed", "repeated_candidate", "verified_repair"])
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual([json.loads(call.args[0].data)["options"]["seed"] for call in opened.call_args_list], [17, 18, 19])
        self.assertEqual(result.stop_reason, "verified_repair")

    def test_all_repeats_preserve_failure_and_exhaust_finite_budget(self):
        candidate = "convert = str\nassert convert(3) == '3'\n"
        runner = SequenceRunner(self.before, Execution("failed", 22))
        with patch("exampleproof.providers.urlopen", side_effect=[response(candidate) for _ in range(3)]):
            result = evaluate_example(self.example, {}, {}, runner, AdaptiveOllamaProvider("simulated"), max_attempts=3)
        self.assertEqual(result.status, "repair_failed")
        self.assertEqual(result.stop_reason, "max_attempts")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(len(result.attempts), 3)

    def test_latest_public_exception_guides_retrieval_but_private_failure_does_not(self):
        for returncode, expected_calls in ((21, 2), (22, 1)):
            after = Execution("failed", returncode, stderr="PRIVATE_OR_PUBLIC_ERROR", oracle="configured_behavior_checks")
            history = (RepairAttempt(1, "repair_failed", Proposal("convert = new_api\n", "old candidate", "test"), after),)
            with self.subTest(returncode=returncode), patch("exampleproof.context.source_context", return_value={}) as retrieved, \
                    patch("exampleproof.providers.urlopen", return_value=response(self.fixed)) as opened:
                AdaptiveOllamaProvider("simulated").propose(self.example, self.before, {}, history=history)
                self.assertEqual(retrieved.call_count, expected_calls)
                if returncode == 21:
                    self.assertEqual(retrieved.call_args_list[0].args[0].code, history[-1].proposal.code)
                    self.assertIs(retrieved.call_args_list[0].args[1], after)
                else:
                    self.assertNotIn("PRIVATE_OR_PUBLIC_ERROR", json.loads(opened.call_args.args[0].data)["prompt"])

    def test_bounded_request_history_keeps_full_budget_counter(self):
        history = tuple(RepairAttempt(i, "rejected", Proposal(f"candidate_{i}()", "simulated", "test")) for i in range(1, 5))
        with patch("exampleproof.providers.urlopen", return_value=response(self.fixed)) as opened:
            provider = AdaptiveOllamaProvider("simulated")
            before_options = dict(provider.options)
            provider.propose(self.example, self.before, {}, history=history)
        payload = json.loads(opened.call_args.args[0].data)
        prior = json.loads(payload["prompt"])["previous_attempts"]
        self.assertEqual([item["number"] for item in prior], [3, 4])
        self.assertEqual(payload["options"]["seed"], 21)
        self.assertEqual(provider.options, before_options)

    def test_legacy_and_v2_keep_strict_guard_and_repeat_stop(self):
        for provider in (OllamaProvider("simulated"), SemanticOllamaProvider("simulated")):
            with patch("exampleproof.providers.urlopen", return_value=response(self.fixed)):
                result = evaluate_example(self.example, {}, {}, SequenceRunner(self.before), provider)
            self.assertEqual(result.status, "rejected")
            self.assertNotIn("allow_helpers", vars(provider))

    def test_cli_selects_v3_and_replay_cannot_enable_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_bytes(b"```python\nassert True\n```\n")
            report = {"summary": {"total": 1, "counts": {"checked": 1}}}
            with patch("exampleproof.cli.AdaptiveOllamaProvider") as provider, \
                    patch("exampleproof.cli.run_project", return_value=(report, "")), patch("exampleproof.cli.write_report"), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["repair", str(root), "--model", "local", "--output", str(root / "output"),
                                       "--repair-policy", "semantic-v3"]), 0)
            provider.assert_called_once_with("local", "http://127.0.0.1:11434", timeout=60)
        with contextlib.redirect_stderr(io.StringIO()), patch("exampleproof.cli.read_project") as read:
            self.assertEqual(main(["repair", "unused", "--proposals", "unused.json", "--output", "unused",
                                   "--repair-policy", "semantic-v3"]), 2)
            read.assert_not_called()


class ContextMergeTests(unittest.TestCase):
    def test_api_owner_labels_only_describe_headers_actually_in_selected_source(self):
        source = ("class Store:\n    def reset(self, name=None):\n        return name\n"
                  "class Other:\n    def reset(self):\n        return None\n")
        units = SourceContextCache().project_units({"sdk.py": source})
        excerpt = {"sdk.py:2-3": "    def reset(self, name=None):\n        return name\n"}
        headers = source_api_headers(excerpt, units)
        self.assertEqual(headers, {"sdk.py:2-2": {"qualified_name": "Store.reset",
                                                 "signature": "    def reset(self, name=None):\n"}})
        self.assertEqual(source_api_headers({"sdk.py:3-3": "        return name\n"}, units), {})
        self.assertEqual(source_api_headers({"sdk.py:2-3": "    def unrelated():\n        pass\n"}, units), {})
        self.assertEqual(source_api_headers(excerpt, units, limit=10), {})

    def test_exact_lines_are_deduplicated_with_precise_labels(self):
        source = "def fetch():\n    value = 1\n    return value\n"
        merged = merge_source_contexts(({"sdk.py:2-2": "    value = 1\n"}, {"sdk.py:1-3": source}))
        self.assertEqual(merged, {"sdk.py:2-2": "    value = 1\n", "sdk.py:1-1": "def fetch():\n", "sdk.py:3-3": "    return value\n"})
        for limit in (0, 1, 40, 80):
            result = merge_source_contexts((merged,), limit=limit)
            self.assertLessEqual(sum(len(key) + len(value) for key, value in result.items()), limit)

    def test_invalid_limits_and_incorrect_labels_are_rejected(self):
        for limit in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                merge_source_contexts(({},), limit=limit)
        with self.assertRaises(ValueError):
            merge_source_contexts(({"sdk.py:1-3": "only one line\n"},))


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Set EXAMPLEPROOF_SANDBOX_TESTS=1")
class AdaptiveSandboxTests(unittest.TestCase):
    def test_adapter_is_executed_with_original_assertions_and_independent_checks(self):
        from exampleproof.runner import SandboxRunner
        example = AdaptiveProviderTests.example
        spec = {"checks": "class Text(str): pass\ntext = Text('hello')\nassert convert(text) is text\nassert convert(None) == 'None'\nassert convert(False) == 'False'\nassert convert('<tag>') == '<tag>'"}
        with patch("exampleproof.providers.urlopen", return_value=response(AdaptiveProviderTests.fixed)):
            result = evaluate_example(example, spec, {}, SandboxRunner({}), AdaptiveOllamaProvider("simulated"))
        self.assertEqual(result.status, "verified_repair", result.to_dict())

    def test_semantically_wrong_adapter_is_rejected_by_unchanged_checks(self):
        from exampleproof.runner import SandboxRunner
        wrong = "def convert(value):\n    return str(value)\nassert convert(3) == '3'\n"
        spec = {"checks": "class Text(str): pass\ntext = Text('hello')\nassert convert(text) is text"}
        with patch("exampleproof.providers.urlopen", return_value=response(wrong)):
            result = evaluate_example(AdaptiveProviderTests.example, spec, {}, SandboxRunner({}), AdaptiveOllamaProvider("simulated"))
        self.assertEqual(result.status, "repair_failed")
        self.assertEqual(result.after.failure_kind, "behavior_check")

    def test_generated_adapter_patch_applies_and_rechecks_without_changing_inputs(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            original = ("```python\n" + AdaptiveProviderTests.example.code + "```\n").encode()
            (root / "README.md").write_bytes(original)
            with patch("exampleproof.providers.urlopen", return_value=response(AdaptiveProviderTests.fixed)):
                report, patch_text = run_project(root, AdaptiveOllamaProvider("simulated"))
            self.assertEqual(report["summary"]["counts"], {"verified_repair": 1})
            copied = Path(directory) / "copy"
            shutil.copytree(root, copied)
            subprocess.run(["git", "apply", "-"], input=patch_text, text=True, encoding="utf-8", cwd=copied, check=True)
            rechecked, remaining = run_project(copied)
            self.assertEqual(rechecked["summary"]["counts"], {"checked": 1})
            self.assertEqual(remaining, "")
            self.assertEqual((root / "README.md").read_bytes(), original)


class ComparisonDriverTests(unittest.TestCase):
    def driver(self):
        import importlib.util
        filename = Path(__file__).resolve().parents[1] / "scripts" / "compare_repair_policies.py"
        spec = importlib.util.spec_from_file_location("policy_comparison_test", filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def project(self, directory):
        root = Path(directory) / "synthetic"
        root.mkdir()
        (root / "README.md").write_bytes(b"```python\nmissing()\n```\n")
        (root / "exampleproof.json").write_text(json.dumps({"examples": {"README.md#1": {"checks": "assert True"}}}), encoding="utf-8")
        (root / "metadata.json").write_text(json.dumps({"schema_version": 1, "suite_id": "synthetic-comparison",
                                                       "cases": [{"id": "README.md#1", "expected_before": "failed"}]}), encoding="utf-8")
        return root

    def test_frozen_inputs_matched_budgets_and_paired_seed_schedule(self):
        driver = self.driver()
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            output = Path(directory) / "comparison"
            def measured(project, destination, provider, max_attempts):
                protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
                self.assertEqual(protocol["status"], "frozen_before_inference")
                self.assertEqual(project.parent, output / "inputs")
                self.assertEqual(max_attempts, 3)
                calls.append((type(provider).__name__, provider.options["seed"], provider.generation_options((None,))["seed"]))
                self.assertEqual(provider.options["num_predict"], 2048)
                self.assertEqual(provider.options["repeat_penalty"], 1.1)
                self.assertEqual(protocol["options"]["repeat_penalty"], 1.1)
                return {"metrics": {"evaluation_complete": True, "expected_failures": 1,
                                    "patch_confirmed_repairs": 0, "healthy_preserved": 0},
                        "repair": {"inference_requests": 1, "input_tokens": 10, "output_tokens": 5,
                                   "inference_duration_seconds": 0.1}}, 1
            with patch.object(driver, "local_metadata", return_value={"model": {"digest": "simulated-digest"}}), \
                    patch.object(driver, "run_benchmark", side_effect=measured):
                result, code = driver.compare([root], output, "simulated", seeds=(17, 29))
            self.assertEqual(code, 0)
            self.assertTrue(result["complete"])
            self.assertEqual(result["independent_failure_cases"], 1)
            self.assertEqual([item[1:] for item in calls], [(17, 18), (17, 18), (29, 30), (29, 30)])
            self.assertEqual([item[0] for item in calls], ["PairedV2Provider", "AdaptiveOllamaProvider", "AdaptiveOllamaProvider", "PairedV2Provider"])
            self.assertEqual(result["groups"]["semantic-v3"]["case_runs"], 2)
            self.assertEqual(result["groups"]["semantic-v3"]["repair_rate"], 0)

    def test_unavailable_service_keeps_frozen_preparation_and_unknown_rates(self):
        driver = self.driver()
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            output = Path(directory) / "comparison"
            with patch.object(driver, "local_metadata", side_effect=OSError("offline")), \
                    patch.object(driver, "run_benchmark") as inferred:
                result, code = driver.compare([root], output, "simulated")
            self.assertEqual(code, 2)
            self.assertFalse(result["complete"])
            self.assertEqual(result["cells"], [])
            self.assertIsNone(result["groups"]["semantic-v3"]["repair_rate"])
            self.assertTrue((output / "protocol.json").is_file())
            self.assertTrue((output / "summary.json").is_file())
            inferred.assert_not_called()

    def test_frozen_inputs_preserve_attribution_and_exclude_reference_candidates(self):
        driver = self.driver()
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            (root / "upstream").mkdir()
            (root / "upstream" / "LICENSE.txt").write_bytes(b"Synthetic upstream attribution\n")
            (root / "upstream" / "PYTHON-RECIPES-NOTICE.md").write_bytes(b"Synthetic recipe notice\n")
            (root / "provenance.json").write_bytes(b'{"source":"synthetic fixture"}\n')
            (root / "proposals.json").write_bytes(b'{"do_not_copy":"REFERENCE_CANDIDATE"}')
            output = Path(directory) / "comparison"
            with patch.object(driver, "local_metadata", side_effect=OSError("offline")):
                _, code = driver.compare([root], output, "simulated")
            self.assertEqual(code, 2)
            frozen = output / "inputs" / root.name
            for name in ("upstream/LICENSE.txt", "upstream/PYTHON-RECIPES-NOTICE.md", "provenance.json"):
                self.assertEqual((frozen / name).read_bytes(), (root / name).read_bytes())
            self.assertFalse((frozen / "proposals.json").exists())
            package = Path(__file__).resolve().parents[1] / "exampleproof"
            for original in (package / "licenses").glob("*.txt"):
                self.assertEqual((output / "implementation" / "licenses" / original.name).read_bytes(), original.read_bytes())

    def test_progress_preserves_cell_identity_and_forwards_execution_events(self):
        driver = self.driver()
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            def measured(project, destination, provider, max_attempts, progress):
                progress({"stage": "attempt_start", "example_id": "README.md#1", "attempt": 1})
                return {"metrics": {"evaluation_complete": True, "expected_failures": 1,
                                    "patch_confirmed_repairs": 0, "healthy_preserved": 0}}, 1
            with patch.object(driver, "local_metadata", return_value={"model": {"digest": "simulated-digest"}}), \
                    patch.object(driver, "run_benchmark", side_effect=measured):
                result, code = driver.compare([root], Path(directory) / "comparison", "simulated", progress=events.append)
            self.assertEqual(code, 0)
            self.assertTrue(result["complete"])
            for policy in ("semantic-v2", "semantic-v3"):
                selected = [event for event in events if event["policy"] == policy]
                self.assertEqual([event["stage"] for event in selected],
                                 ["comparison_cell_start", "attempt_start", "comparison_cell_complete"])
                self.assertTrue(all(event["seed"] == 17 and event["project"] == root.name for event in selected))

    def test_frozen_input_tampering_stops_remaining_requests(self):
        driver = self.driver()
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            original = (root / "README.md").read_bytes()
            output = Path(directory) / "comparison"
            def tampered(project, destination, provider, max_attempts):
                (project / "README.md").write_bytes(b"changed frozen input\n")
                return {"metrics": {"evaluation_complete": True, "expected_failures": 1,
                                    "patch_confirmed_repairs": 0, "healthy_preserved": 0}}, 1
            with patch.object(driver, "local_metadata", return_value={"model": {"digest": "simulated-digest"}}), \
                    patch.object(driver, "run_benchmark", side_effect=tampered) as inferred:
                result, code = driver.compare([root], output, "simulated")
            self.assertEqual(code, 2)
            self.assertFalse(result["complete"])
            self.assertEqual(inferred.call_count, 1)
            self.assertIsNone(result["groups"]["semantic-v2"]["repair_rate"])
            self.assertEqual((root / "README.md").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
