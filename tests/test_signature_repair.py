"""Signature migration engineering tests; all model answers here are simulated."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.context import SourceContextCache, call_repair_context
from exampleproof.models import Example, Execution
from exampleproof.pipeline import evaluate_example, run_project
from exampleproof.providers import SignatureOllamaProvider, apply_call_binding, binding_repair_choices, rank_source_choices, source_choice_summaries


SOURCE = 'def arrange(items, count, option="keep", fill=None):\n    """Arrange the items into groups of count, with an optional fill."""\n    return [items] * count\n'


def model_binding(binding):
    """Simulate choosing the source plan requested by this synthetic test."""
    def answer(request, *, timeout):
        prompt = json.loads(json.loads(request.data)["prompt"])
        names = [next(name for name, index in binding.items() if index == identifier)
                 for identifier in range(1, len(binding) + 1)]
        selected = next(choice for choice in prompt["binding_choices"] if choice["parameters"] == names)
        return io.BytesIO(json.dumps({"done": True, "response": json.dumps({"choice": selected["id"],
            "rationale": "Simulated parameter-plan choice, not a live-model result"}),
            "prompt_eval_count": 10, "eval_count": 8}).encode())
    return answer


def plan_for(code="from sdk import arrange\nresult = arrange(2, 'AB', 'x')\n", source=SOURCE, error=None):
    example = Example("synthetic.md#1", "synthetic.md", 1, 3, code, "Preserve original inputs and documented behavior.")
    before = Execution("failed", 21, stderr=error or 'File "/work/example.py", line 2, in <module>\nTypeError: invalid argument type',
                       oracle="configured_behavior_checks", failure_kind="example_exception")
    sources = {"sdk.py": source}
    context = {f"sdk.py:1-{len(source.splitlines())}": source}
    return example, before, context, SourceContextCache().project_units(sources)


class CallBindingTests(unittest.TestCase):
    def test_source_usage_clues_rank_compatible_literal_roles_first(self):
        source = ("def arrange(items, count, option='strict', fill=None):\n"
                  "    groups = [iter(items)] * count\n"
                  "    if option == 'strict':\n        return groups\n"
                  "    if option == 'ignore':\n        return groups\n"
                  "    return groups\n")
        example, before, context, units = plan_for(source=source)
        plan = call_repair_context(example, before, context, units)
        self.assertIn("iterable", plan["usage_hints"]["items"])
        self.assertIn("integer_index", plan["usage_hints"]["count"])
        self.assertEqual(binding_repair_choices(example.code, plan)[0]["parameters"], ["count", "items", "fill"])

    def test_complete_choices_preserve_required_parameters_and_fit_the_budget(self):
        example, before, context, units = plan_for()
        plan = call_repair_context(example, before, context, units)
        choices = binding_repair_choices(example.code, plan)
        self.assertTrue(any(choice["parameters"] == ["count", "items", "fill"] for choice in choices))
        self.assertLessEqual(len(json.dumps({"call_repair": plan, "binding_choices": choices}, ensure_ascii=False)), 1200)
        self.assertLessEqual(len(choices), 8)
        for choice in choices:
            self.assertEqual(len(set(choice["parameters"])), 3)
            self.assertTrue({"items", "count"} <= set(choice["parameters"]))
            self.assertNotEqual(choice["parameters"], ["items", "count", "option"])

    def test_keyword_only_migration_keeps_a_valid_formerly_positional_plan(self):
        example, before, context, units = plan_for("from sdk import arrange\nresult = arrange('AB', 2)\n",
                                                  "def arrange(items, *, count):\n    return [items] * count\n")
        plan = call_repair_context(example, before, context, units)
        self.assertFalse(plan["original_binding_valid"])
        self.assertTrue(any(choice["parameters"] == ["items", "count"] for choice in binding_repair_choices(example.code, plan)))

    def test_named_expression_remains_one_input_during_static_ranking(self):
        example, before, context, units = plan_for("from sdk import arrange\nresult = arrange((size := 2), 'AB')\n")
        plan = call_repair_context(example, before, context, units)
        self.assertTrue(any(choice["parameters"] == ["count", "items"] for choice in binding_repair_choices(example.code, plan)))

    def test_mapping_preserves_input_order_defaults_and_unicode_prefix(self):
        example, before, context, units = plan_for("from sdk import arrange\n结果 = arrange(2, '中文', 'x')\n")
        plan = call_repair_context(example, before, context, units)
        result = apply_call_binding(example.code, plan, {"binding": {"items": 2, "count": 1, "fill": 3}, "rationale": "simulated"})
        self.assertEqual(result["code"], "from sdk import arrange\n结果 = arrange(count=(2), items=('中文'), fill=('x'))\n")
        self.assertEqual(plan["parameters"][2], {"name": "option", "kind": "keyword", "default": "'keep'"})

    def test_invalid_mapping_cannot_drop_duplicate_or_invent_an_expression(self):
        example, before, context, units = plan_for()
        plan = call_repair_context(example, before, context, units)
        for binding in ({"items": 1, "count": 1, "fill": 3}, {"items": 2, "count": 1},
                        {"items": 2, "count": 1, "unknown": 3}, {"items": 2, "count": True, "fill": 3},
                        {"items": 2, "count": 1, "fill": 99}, {"items": 2, "option": 1, "fill": 3}):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                apply_call_binding(example.code, plan, {"binding": binding, "rationale": "simulated"})

    def test_positional_only_slots_cannot_reorder_evaluation(self):
        example, before, context, units = plan_for("from sdk import arrange\nresult = arrange(2, 'AB')\n",
                                                  "def arrange(count, /, items):\n    return [items] * count\n")
        plan = call_repair_context(example, before, context, units)
        with self.assertRaisesRegex(ValueError, "evaluation order"):
            apply_call_binding(example.code, plan, {"binding": {"count": 2, "items": 1}, "rationale": "simulated"})
        code = apply_call_binding(example.code, plan, {"binding": {"count": 1, "items": 2}, "rationale": "simulated"})["code"]
        self.assertIn("arrange((2), items=('AB'))", code)

    def test_multiline_keyword_inputs_and_lambda_stay_single_expressions(self):
        code = "from sdk import arrange\nresult = arrange(\n    2,\n    lambda x: x + 1,\n    fill='x',\n)\n"
        example, before, context, units = plan_for(code)
        plan = call_repair_context(example, before, context, units)
        code = apply_call_binding(example.code, plan, {"binding": {"count": 1, "items": 2, "fill": 3}, "rationale": "simulated"})["code"]
        self.assertEqual(code, "from sdk import arrange\nresult = arrange(count=(2), items=(lambda x: x + 1), fill=('x'))\n")


class SignatureEvidenceTests(unittest.TestCase):
    def test_source_ranking_uses_runtime_receiver_and_retains_other_owners(self):
        choices = [{"id": 1, "api": "Manager.clear", "source": "sdk.py:1-1"},
                   {"id": 2, "api": "Collection.reset", "source": "sdk.py:2-2"}]
        before = Execution("failed", 21, stderr="AttributeError: 'Collection' object has no attribute 'obsolete'", oracle="configured_behavior_checks")
        ranked = rank_source_choices(choices, before)
        self.assertEqual([choice["api"] for choice in ranked], ["Collection.reset", "Manager.clear"])
        self.assertEqual([choice["id"] for choice in ranked], [1, 2])
        self.assertEqual(choices[0]["api"], "Manager.clear")
        before.stderr = "AttributeError: 'Collection' object has no attribute 'old_rows'"
        choices[0]["api"] = "Manager.drop_rows"
        self.assertEqual(rank_source_choices(choices, before)[0]["api"], "Manager.drop_rows")

    def test_api_summaries_are_verbatim_selected_evidence_and_do_not_mutate_choices(self):
        source = 'def fresh(value):\n    """Preserve text and convert other values."""\n    return str(value)\n'
        units = SourceContextCache().project_units({"sdk.py": source})
        choices = [{"id": 1, "api": "sdk.fresh", "source": "sdk.py:1-1", "edit": {"edits": [], "rationale": ""}}]
        enriched = source_choice_summaries(choices, {"sdk.py:1-3": source}, units)
        self.assertEqual(enriched[0]["source_summary"], "Preserve text and convert other values.")
        self.assertNotIn("source_summary", choices[0])
        self.assertEqual(source_choice_summaries(choices, {"sdk.py:1-1": "def fresh(value):\n"}, units), choices)
        self.assertEqual(source_choice_summaries(choices, {"sdk.py:1-3": source}, units,
                                               limit=len(json.dumps(choices, ensure_ascii=False))), choices)

    def test_api_must_have_a_complete_unmodified_selected_header(self):
        example, before, context, units = plan_for()
        self.assertIsNotNone(call_repair_context(example, before, context, units))
        self.assertIsNone(call_repair_context(example, before, {}, units))
        forged = {name: text.replace("def arrange", "def invented") for name, text in context.items()}
        self.assertIsNone(call_repair_context(example, before, forged, units))

    def test_assertions_unpacking_and_ambiguous_definitions_stay_outside_mapping(self):
        for code in ("from sdk import arrange\nassert arrange(2, 'AB')\n",
                     "from sdk import arrange\nresult = arrange(*data)\n",
                     "from sdk import arrange\nresult = arrange(2, **data)\n"):
            example, before, context, units = plan_for(code)
            self.assertIsNone(call_repair_context(example, before, context, units), code)
        example, before, context, units = plan_for()
        sources = {"sdk/a.py": SOURCE, "sdk/b.py": SOURCE}
        context = {f"{name}:1-3": text for name, text in sources.items()}
        self.assertIsNone(call_repair_context(example, before, context, SourceContextCache().project_units(sources)))

    def test_private_errors_and_tracebacks_without_an_example_location_are_not_used(self):
        example, before, context, units = plan_for()
        for failure in (Execution("failed", 22, stderr=before.stderr, oracle="configured_behavior_checks"),
                        Execution("failed", 21, stderr="TypeError: PRIVATE", oracle="configured_behavior_checks")):
            self.assertIsNone(call_repair_context(example, failure, context, units))

    def test_module_alias_and_bound_method_are_resolved_without_importing_sources(self):
        example, before, context, units = plan_for("import sdk as helpers\nresult = helpers.arrange(2, 'AB')\n")
        self.assertIsNotNone(call_repair_context(example, before, context, units))
        source = "class Tool:\n    def arrange(self, items, count):\n        return [items] * count\n"
        example, before, context, units = plan_for("tool = Tool()\nresult = tool.arrange(2, 'AB')\n", source)
        plan = call_repair_context(example, before, context, units)
        self.assertEqual([item["name"] for item in plan["parameters"]], ["items", "count"])


class SignatureProviderTests(unittest.TestCase):
    def test_request_constrains_binding_and_retains_raw_response_without_private_checks(self):
        example, before, _, _ = plan_for()
        provider = SignatureOllamaProvider("simulated")
        with patch("exampleproof.providers.urlopen", side_effect=model_binding({"items": 2, "count": 1, "fill": 3})) as opened:
            proposal = provider.propose(example, before, {"sdk.py": SOURCE})
        request = json.loads(opened.call_args.args[0].data)
        prompt = json.loads(request["prompt"])
        self.assertEqual(request["format"]["required"], ["choice", "rationale"])
        self.assertEqual(prompt["call_repair"]["arguments"][0]["expression"], "2")
        self.assertNotIn("repair_choices", prompt)
        self.assertIn("choice", json.loads(proposal.inference_evidence.response["response"]))
        self.assertIn("count=(2), items=('AB'), fill=('x')", proposal.code)

    def test_cli_exposes_signature_policy_and_replay_stays_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\nassert True\n```\n")
            with patch("exampleproof.cli.SignatureOllamaProvider") as provider, \
                    patch("exampleproof.cli.run_project", return_value=({"summary": {"total": 1, "counts": {"checked": 1}}}, "")), \
                    patch("exampleproof.cli.write_report"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["repair", str(root), "--model", "simulated", "--output", str(root / "out"),
                                       "--repair-policy", "semantic-v5"]), 0)
            provider.assert_called_once()
        with contextlib.redirect_stderr(io.StringIO()), patch("exampleproof.cli.read_project") as read:
            self.assertEqual(main(["repair", "unused", "--proposals", "unused", "--output", "unused",
                                   "--repair-policy", "semantic-v5"]), 2)
            read.assert_not_called()


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Set EXAMPLEPROOF_SANDBOX_TESTS=1")
class SignatureSandboxTests(unittest.TestCase):
    source = 'def arrange(items, count, fill=None):\n    """Arrange items by count."""\n    return "".join([items] * count)\n'

    def project(self, directory, code):
        root = Path(directory) / "original"
        root.mkdir()
        (root / "sdk.py").write_text(self.source)
        (root / "README.md").write_text("```python\n" + code + "```\n")
        (root / "exampleproof.json").write_text(json.dumps({"source_files": ["sdk.py"]}))
        return root

    def test_real_execution_preserves_expression_order_and_original_assertions(self):
        code = ("from sdk import arrange\nevents = []\n"
                "result = arrange(events.append('size') or 2, events.append('items') or 'AB')\n"
                "assert events == ['size', 'items']\nassert result == 'ABAB'\n")
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory, code)
            original = (root / "README.md").read_bytes()
            with patch("exampleproof.providers.urlopen", side_effect=model_binding({"count": 1, "items": 2})):
                report, patch_text = run_project(root, SignatureOllamaProvider("simulated"))
            self.assertEqual(report["summary"]["counts"], {"verified_repair": 1}, report)
            copied = Path(directory) / "patched"
            shutil.copytree(root, copied)
            subprocess.run(["git", "apply", "-"], input=patch_text, text=True, cwd=copied, check=True)
            rechecked, remaining = run_project(copied)
            self.assertEqual(rechecked["summary"]["counts"], {"checked": 1})
            self.assertEqual(remaining, "")
            self.assertEqual((root / "README.md").read_bytes(), original)

    def test_two_failing_calls_are_repaired_cumulatively_with_the_same_budget(self):
        code = "from sdk import arrange\na = arrange(2, 'AB')\nb = arrange(3, 'X')\nassert a == 'ABAB'\nassert b == 'XXX'\n"
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory, code)
            with patch("exampleproof.providers.urlopen", side_effect=model_binding({"count": 1, "items": 2})) as opened:
                report, _ = run_project(root, SignatureOllamaProvider("simulated"), max_attempts=2)
            self.assertEqual(report["summary"]["counts"], {"verified_repair": 1}, report)
            second = json.loads(json.loads(opened.call_args.args[0].data)["prompt"])
            self.assertIn("a = arrange(count=(2), items=('AB'))", second["repair_base_code"])
            self.assertEqual(second["call_repair"]["span"][0], 3)


if __name__ == "__main__":
    unittest.main()
