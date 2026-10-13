"""Safe diagnostic categories and paired first-call policy regressions."""

import io
import json
import os
import unittest
from unittest.mock import patch

from exampleproof.models import Example, Execution, Proposal, RepairAttempt
from exampleproof.providers import (OllamaProvider, SYSTEM, SYSTEM_V2, WITHHELD_CHECK_ERROR,
                                    categorized_feedback)
from exampleproof.runner import SandboxRunner
from exampleproof.semantic_study import study_design


class FeedbackTests(unittest.TestCase):
    def test_private_checks_never_enter_category_or_guidance(self):
        for kind, code in (("stdout_mismatch", 0), ("behavior_check", 22), ("timeout", -9)):
            value = Execution("failed", code, "PRIVATE_OUTPUT", "PRIVATE_ASSERTION",
                              oracle="configured_behavior_checks", failure_kind=kind)
            result = categorized_feedback(value)
            self.assertEqual(result["category"], kind)
            self.assertEqual(result["error"], WITHHELD_CHECK_ERROR)
            self.assertNotIn("PRIVATE", json.dumps(result))

    def test_category_is_allowlisted_and_not_derived_from_stderr(self):
        result = categorized_feedback(Execution("failed", 22, stderr="stdout_mismatch PRIVATE",
                                                  failure_kind="PRIVATE_FIELD"))
        self.assertEqual(result["category"], "unknown")
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertIsNone(categorized_feedback(None))

    def test_feedback_policy_changes_history_only(self):
        example = Example("doc.md#1", "doc.md", 2, 2, "value = old()\n", "Preserve the value")
        before = Execution("failed", 21, stderr="NameError: old", failure_kind="example_exception")
        previous = RepairAttempt(1, "repair_failed", Proposal("print(new())\n", "candidate", "test"),
                                 Execution("failed", 0, stderr="PRIVATE_EXPECTATION", oracle="configured_behavior_checks",
                                           failure_kind="stdout_mismatch"))
        payloads = {}
        for mode in ("legacy", "categorized"):
            for history in ((), (previous,)):
                response = io.BytesIO(json.dumps({"done": True, "response": '{"code":"value = new()","rationale":"fixed"}'}).encode())
                with patch("exampleproof.providers.urlopen", return_value=response) as opened:
                    OllamaProvider("model", system_prompt=SYSTEM_V2, feedback_mode=mode).propose(
                        example, before, {"sdk.py:1-2": "def new(): return 1"}, history=history)
                payloads[mode, bool(history)] = json.loads(opened.call_args.args[0].data)
        self.assertEqual(payloads["legacy", False], payloads["categorized", False])
        history = json.loads(payloads["categorized", True]["prompt"])["previous_attempts"][0]
        self.assertEqual(history["execution"]["category"], "stdout_mismatch")
        self.assertIn("avoid adding prints", history["execution"]["guidance"])
        self.assertNotIn("PRIVATE", json.dumps(list(payloads.values())))
        self.assertEqual(payloads["legacy", False]["system"], SYSTEM_V2)

    def test_default_remains_original_policy_and_invalid_options_reject(self):
        self.assertEqual(OllamaProvider("model").system_prompt, SYSTEM)
        for kwargs in ({"feedback_mode": "untrusted"}, {"system_prompt": ""}, {"system_prompt": 2}):
            with self.assertRaises(ValueError):
                OllamaProvider("model", **kwargs)

    def test_design_separates_development_and_holdout_and_paired_ablations(self):
        development, holdout = study_design("development"), study_design("holdout")
        self.assertEqual(development["seeds"], [17])
        self.assertEqual(holdout["seeds"], [17, 29, 43])
        self.assertEqual(len(holdout["arms"]), 5)
        generic = dict(holdout["arms"]["generic_feedback_v2"])
        category = dict(holdout["arms"]["feedback_v2"])
        self.assertNotEqual(generic.pop("feedback"), category.pop("feedback"))
        self.assertEqual(generic, category)
        with self.assertRaises(ValueError):
            study_design("unknown")


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Set EXAMPLEPROOF_SANDBOX_TESTS=1")
class FeedbackSandboxTests(unittest.TestCase):
    def test_categories_follow_real_execution_stage(self):
        runner = SandboxRunner({})
        cases = [
            ("value = 1\n", {"checks": "assert value == 2"}, "behavior_check"),
            ("value = 1\nprint(value)\n", {"checks": "assert value == 1", "expected_stdout": ""}, "stdout_mismatch"),
            ("value = missing\n", {"checks": "assert value == 1"}, "example_exception"),
            ("import os\nos._exit(0)\n", {"checks": "assert False"}, "incomplete_execution"),
            ("value = 1\n", {"checks": "assert value == 1"}, "none"),
        ]
        for code, spec, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(runner.run(code, spec).failure_kind, expected)


if __name__ == "__main__":
    unittest.main()
