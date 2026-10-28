"""Edit protocol regressions; model responses are simulated unless noted elsewhere."""
import contextlib
import importlib.util
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
from exampleproof.context import SourceContextCache, source_repair_choices
from exampleproof.models import Example, Execution
from exampleproof.pipeline import evaluate_example, run_project
from exampleproof.providers import EditOllamaProvider, apply_line_edits


def edits(*changes):
    return {"edits": [{"line": line, "replacement": text} for line, text in changes],
            "rationale": "Simulated edit proposal, not a live-model result"}


def response(value):
    return io.BytesIO(json.dumps({"done": True, "response": json.dumps(value),
                                 "prompt_eval_count": 10, "eval_count": 10}).encode())


class LineEditTests(unittest.TestCase):
    def test_unchanged_line_in_a_real_edit_does_not_discard_the_useful_change(self):
        self.assertEqual(apply_line_edits("x = 1\ny = old(x)\n", edits((1, "x = 1"), (2, "y = new(x)")))["code"],
                         "x = 1\ny = new(x)\n")

    def test_insertion_uses_original_numbers_and_preserves_unedited_setup_bytes(self):
        original = "# 中文\r\nitems = ['α', False, None]\r\nconvert = old\r\nprint(convert(items))\r\n"
        result = apply_line_edits(original, edits((4, "print(convert(items), end='')"),
                                                 (3, "def convert(value):\n    return str(value)")))
        self.assertEqual(result["code"], "# 中文\r\nitems = ['α', False, None]\r\ndef convert(value):\r\n    return str(value)\r\nprint(convert(items), end='')\r\n")

    def test_final_newline_and_unicode_separators_inside_strings_are_preserved(self):
        original = "text = 'a\u2028b'\nresult = old(text)"
        self.assertEqual(apply_line_edits(original, edits((2, "result = new(text)")))["code"],
                         "text = 'a\u2028b'\nresult = new(text)")
        self.assertEqual(apply_line_edits("text = 'a\u2028b'", edits((1, "text = 'c\u2028d'")))["code"], "text = 'c\u2028d'")

    def test_deletion_is_explicit_and_does_not_shift_other_edit_addresses(self):
        self.assertEqual(apply_line_edits("a = 1\nb = 2\nc = 3\n", edits((1, ""), (3, "c = 4")))["code"],
                         "b = 2\nc = 4\n")

    def test_invalid_protocol_is_rejected_without_guessing_or_partial_application(self):
        values = [edits(), edits((0, "new")), edits((3, "new")), edits((True, "new")),
                  edits((1, "new"), (1, "other")), edits((1, "old\n")), edits((1, 3)),
                  edits((1, "x\ry")), edits((1, "\ud800")), {"code": "new", "rationale": "wrong protocol"},
                  {"edits": [{"line": 1, "replacement": "new", "extra": 1}], "rationale": "bad"},
                  {**edits((1, "new")), "extra": 1}]
        for value in values:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                apply_line_edits("old\nlast\n", value)

    def test_edit_count_and_materialized_utf8_size_are_bounded(self):
        with self.assertRaises(ValueError):
            apply_line_edits("x\n" * 9, edits(*((line, "y") for line in range(1, 10))))
        with self.assertRaises(ValueError):
            apply_line_edits("x\n", edits((1, "中" * 11000)))
        with self.assertRaises(ValueError):
            apply_line_edits("x\n" * 8, edits(*((line, "y" * 5000) for line in range(1, 9))))


class EditProviderTests(unittest.TestCase):
    original = "from sdk import old\nitems = [1, False, None]\nconvert = old\nassert convert(3) == '3'\n"
    example = Example("a.md#1", "a.md", 2, 5, original, "Keep a reusable callable named convert.")
    before = Execution("failed", 21, stderr="ImportError: cannot import name 'old' from 'sdk'",
                       oracle="configured_behavior_checks", failure_kind="example_exception")

    def test_raw_edits_remain_auditable_and_candidate_retains_setup(self):
        value = {"choice": 1, "rationale": "Simulated source choice"}
        provider = EditOllamaProvider("simulated")
        with patch("exampleproof.providers.urlopen", return_value=response(value)) as opened:
            proposal = provider.propose(self.example, self.before, {"sdk.py": 'def new(value):\n    """Convert values to text."""\n    return str(value)\n'})
        self.assertEqual(proposal.code, self.original.replace("from sdk import old", "from sdk import new as old"))
        self.assertEqual(json.loads(proposal.inference_evidence.response["response"]), value)
        request = json.loads(opened.call_args.args[0].data)
        self.assertEqual(request["format"]["required"], ["choice", "rationale"])
        self.assertEqual(json.loads(request["prompt"])["repair_choices"][0]["api"], "sdk.new")

    def test_invalid_edit_retries_with_original_addresses_and_hidden_checks_withheld(self):
        class Runner:
            calls = []
            def run(self, code, spec):
                self.calls.append(code)
                return EditProviderTests.before if len(self.calls) == 1 else Execution("passed", 0)
        runner = Runner()
        with patch("exampleproof.providers.urlopen", side_effect=[response(edits((99, "pass"))),
                                                                 response(edits((1, "from sdk import new as old")))]) as opened:
            result = evaluate_example(self.example, {"checks": "PRIVATE_EVALUATOR_TEXT"}, {}, runner,
                                      EditOllamaProvider("simulated"), max_attempts=2)
        self.assertEqual([attempt.status for attempt in result.attempts], ["candidate_format_error", "verified_repair"])
        self.assertEqual(len(runner.calls), 2)
        request = json.loads(opened.call_args.args[0].data)
        self.assertEqual(request["options"]["seed"], 18)
        self.assertNotIn("PRIVATE_EVALUATOR_TEXT", request["prompt"])
        self.assertEqual(json.loads(request["prompt"])["edit_lines"]["1"], "from sdk import old")
        self.assertIn("original line", json.loads(request["prompt"])["previous_attempts"][0]["rejection"])

    def test_deleting_original_assertion_is_rejected_before_execution(self):
        class Runner:
            def run(self, code, spec):
                if code != EditProviderTests.original:
                    raise AssertionError("Rejected assertion removal reached execution")
                return EditProviderTests.before
        with patch("exampleproof.providers.urlopen", return_value=response(edits((4, "")))):
            result = evaluate_example(self.example, {}, {}, Runner(), EditOllamaProvider("simulated"))
        self.assertEqual(result.status, "rejected")

    def test_unknown_choice_retries_without_inventing_or_executing_an_edit(self):
        class Runner:
            calls = []
            def run(self, code, spec):
                self.calls.append(code)
                return EditProviderTests.before if len(self.calls) == 1 else Execution("passed", 0)
        runner = Runner()
        with patch("exampleproof.providers.urlopen", side_effect=[response({"choice": 99, "rationale": "bad id"}),
                response({"choice": 1, "rationale": "available id"})]):
            result = evaluate_example(self.example, {}, {"sdk.py": 'def new(value):\n    """Convert values to text."""\n    return str(value)\n'},
                                      runner, EditOllamaProvider("simulated"), max_attempts=2)
        self.assertEqual([attempt.status for attempt in result.attempts], ["candidate_format_error", "verified_repair"])
        self.assertEqual(len(runner.calls), 2)


class SourceChoiceTests(unittest.TestCase):
    def choices(self, code, error, sources, context=None):
        example = Example("synthetic.md#1", "synthetic.md", 1, 10, code, "Preserve all original inputs and operations.")
        before = Execution("failed", 21, stderr=error, oracle="configured_behavior_checks")
        if context is None:
            context = {f"{name}:1-{len(text.splitlines())}": text for name, text in sources.items()}
        units = SourceContextCache().project_units(sources)
        return source_repair_choices(example, before, sources, context, units)

    def test_import_alias_and_other_imports_survive_source_derived_substitution(self):
        result = self.choices("from library import old as convert, other\nprint(convert(3))\n",
                              "ImportError: cannot import name 'old' from 'library'",
                              {"library.py": "def fresh(value):\n    return str(value)\n"})
        self.assertEqual([choice["api"] for choice in result], ["library.fresh"])
        candidate = apply_line_edits("from library import old as convert, other\nprint(convert(3))\n", result[0]["edit"])["code"]
        self.assertEqual(candidate, "from library import other\nfrom library import fresh as convert\nprint(convert(3))\n")

    def test_static_binding_rejects_duplicate_keyword_and_incompatible_arity(self):
        result = self.choices("from library import old\nold([1], [2], key=int)\n",
                              "ImportError: cannot import name 'old' from 'library'", {"library.py":
                              "def wrong(items, key=None):\n    return items\ndef fresh(*items, key=None):\n    return items\n"})
        self.assertEqual([choice["api"] for choice in result], ["library.fresh"])

    def test_attribute_choices_respect_receiver_scope_and_bound_call_shape(self):
        result = self.choices("db = Store()\nclear = db.obsolete\nclear()\n",
                              "AttributeError: 'Store' object has no attribute 'obsolete'", {"sdk.py":
                              "class Store:\n    def wipe(self):\n        return None\n    def remove(self, name):\n        return name\nclass Other:\n    def wipe(self):\n        return None\n"})
        self.assertEqual([choice["api"] for choice in result], ["Store.wipe"])
        self.assertEqual(result[0]["edit"]["edits"], [{"line": 2, "replacement": "clear = db.wipe"}])

    def test_explicit_reexport_uses_public_module_without_importing_it(self):
        result = self.choices("from library import old\nold(3)\n",
                              "ImportError: cannot import name 'old' from 'library'", {
                              "library/_impl.py": "def fresh(value):\n    return value\n",
                              "library/__init__.py": "try:\n    from ._impl import fresh\nexcept ImportError:\n    pass\n"})
        self.assertEqual([choice["api"] for choice in result], ["library.fresh"])

    def test_stdlib_choice_needs_exact_signature_in_selected_evidence(self):
        from exampleproof.stdlib_index import STDLIB_INDEX
        filename, start, end, name, text = next(entry for entry in STDLIB_INDEX if entry[0] == "stdlib/heapq.py" and entry[3] == "merge")
        code = "from library import old\nold([1], [2], key=int, reverse=True)\n"
        sources = {"library.py": "# Old export removed.\n"}
        context = {f"{filename}:{start}-{end}": text}
        result = self.choices(code, "ImportError: cannot import name 'old' from 'library'", sources, context)
        self.assertEqual([choice["api"] for choice in result], ["heapq.merge"])
        self.assertEqual(self.choices(code, "ImportError: cannot import name 'old' from 'library'", sources,
                                     {f"{filename}:{start}-{end}": text.replace("def merge", "def forged")}), [])

    def test_private_failure_is_not_reinterpreted_as_public_api_evidence(self):
        example = Example("synthetic.md#1", "synthetic.md", 1, 1, "old(3)\n", "Preserve behavior.")
        before = Execution("failed", 22, stderr="NameError: name 'PRIVATE_SYMBOL' is not defined", oracle="configured_behavior_checks")
        self.assertEqual(source_repair_choices(example, before, {}, {}, []), [])

    def test_cli_selects_edit_policy_and_disallows_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("```python\nassert True\n```\n")
            report = {"summary": {"total": 1, "counts": {"checked": 1}}}
            with patch("exampleproof.cli.EditOllamaProvider") as provider, \
                    patch("exampleproof.cli.run_project", return_value=(report, "")), \
                    patch("exampleproof.cli.write_report"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["repair", str(root), "--model", "simulated", "--output", str(root / "out"),
                                       "--repair-policy", "semantic-v4"]), 0)
            provider.assert_called_once()
        with contextlib.redirect_stderr(io.StringIO()), patch("exampleproof.cli.read_project") as read:
            self.assertEqual(main(["repair", "unused", "--proposals", "unused", "--output", "unused",
                                   "--repair-policy", "semantic-v4"]), 2)
            read.assert_not_called()

    def test_comparison_can_freeze_v3_and_v4_with_the_same_budget(self):
        filename = Path(__file__).resolve().parents[1] / "scripts" / "compare_repair_policies.py"
        spec = importlib.util.spec_from_file_location("line_repair_comparison", filename)
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        seen = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            root.mkdir()
            (root / "README.md").write_text("```python\nmissing()\n```\n")
            (root / "metadata.json").write_text(json.dumps({"schema_version": 1, "suite_id": "synthetic",
                "cases": [{"id": "README.md#1", "expected_before": "failed"}]}))
            def measured(project, output, provider, max_attempts):
                seen.append((type(provider).__name__, provider.options, max_attempts))
                return {"metrics": {"evaluation_complete": True, "expected_failures": 1,
                                    "patch_confirmed_repairs": 0, "healthy_preserved": 0}}, 1
            with patch.object(driver, "local_metadata", return_value={"model": {"digest": "simulated"}}), \
                    patch.object(driver, "run_benchmark", side_effect=measured):
                result, code = driver.compare([root], Path(directory) / "out", "simulated",
                                              policies=("semantic-v3", "semantic-v4"))
            self.assertEqual(code, 0)
            self.assertEqual(set(result["groups"]), {"semantic-v3", "semantic-v4"})
            self.assertEqual([item[0] for item in seen], ["AdaptiveOllamaProvider", "EditOllamaProvider"])
            self.assertEqual(seen[0][1:], seen[1][1:])


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Set EXAMPLEPROOF_SANDBOX_TESTS=1")
class EditSandboxTests(unittest.TestCase):
    def test_edit_patch_applies_and_rechecks_with_independent_behavior_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "original"
            root.mkdir()
            original = ("```python\n" + EditProviderTests.original + "```\n").encode()
            (root / "README.md").write_bytes(original)
            (root / "sdk.py").write_text('def new(value):\n    """Convert values to text."""\n    return value if isinstance(value, str) else str(value)\n')
            (root / "exampleproof.json").write_text(json.dumps({"source_files": ["sdk.py"], "examples": {
                "README.md#1": {"checks": "assert items == [1, False, None]\nclass Text(str): pass\ntext = Text('hi')\nassert convert(text) is text\nassert convert(None) == 'None'"}}}))
            with patch("exampleproof.providers.urlopen", return_value=response({"choice": 1, "rationale": "Simulated source choice"})):
                report, patch_text = run_project(root, EditOllamaProvider("simulated"))
            self.assertEqual(report["summary"]["counts"], {"verified_repair": 1}, report)
            copied = Path(directory) / "patched"
            shutil.copytree(root, copied)
            subprocess.run(["git", "apply", "-"], input=patch_text, text=True, cwd=copied, check=True)
            rechecked, remaining = run_project(copied)
            self.assertEqual(rechecked["summary"]["counts"], {"checked": 1})
            self.assertEqual(remaining, "")
            self.assertEqual((root / "README.md").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
