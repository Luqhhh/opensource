import ast
import unittest
from unittest.mock import patch

from exampleproof.guard import validate_candidate
from exampleproof.models import Example, Execution, Proposal
from exampleproof.pipeline import evaluate_example


class CandidateLimitsTests(unittest.TestCase):
    original = "result = missing()\nassert result == 2\n"
    candidate = "result = int('2')\nassert result == 2\n"

    def test_long_addition_assertions_fail_closed_below_byte_limit(self):
        complex_code = "assert " + "+".join(["1"] * 1000) + " == 1000\n"
        self.assertLess(len(complex_code.encode("utf-8")), 32_000)
        for original, candidate in ((self.original, complex_code),
                                    (complex_code, self.candidate)):
            with self.subTest(complex_original=original == complex_code):
                rejection = validate_candidate(original, candidate)
                self.assertIn("recursion limit", rejection)

    def test_deep_unary_assertions_fail_closed_in_original_or_candidate(self):
        complex_code = "assert " + "-" * 4000 + "1 == 1\n"
        self.assertLess(len(complex_code.encode("utf-8")), 32_000)
        for original, candidate in ((self.original, complex_code),
                                    (complex_code, self.candidate)):
            with self.subTest(complex_original=original == complex_code):
                self.assertIn("recursion limit", validate_candidate(original, candidate))

    def test_parser_recursion_error_is_a_rejection(self):
        for parse_call in (1, 2):
            with self.subTest(parse_call=parse_call):
                outcomes = [ast.parse(self.original)] * (parse_call - 1)
                outcomes.append(RecursionError("parser depth"))
                with patch("exampleproof.guard.ast.parse", side_effect=outcomes):
                    self.assertIn("recursion limit", validate_candidate(self.original, self.candidate))

    def test_excessive_parentheses_are_rejected_in_original_or_candidate(self):
        complex_code = "assert " + "(" * 500 + "True" + ")" * 500 + "\n"
        for original, candidate in ((self.original, complex_code),
                                    (complex_code, self.candidate)):
            with self.subTest(complex_original=original == complex_code):
                self.assertIn("Cannot structurally validate code", validate_candidate(original, candidate))

    def test_complex_candidate_is_not_executed_and_can_be_retried(self):
        complex_code = "assert " + "+".join(["1"] * 1000) + " == 1000\n"

        class Runner:
            def __init__(self):
                self.calls = []

            def run(self, code, spec):
                self.calls.append(code)
                return Execution("failed" if len(self.calls) == 1 else "passed",
                                 oracle="original_top_level_assertions")

        class Provider:
            def propose(self, example, before, sources, *, history=()):
                return Proposal(complex_code if not history else CandidateLimitsTests.candidate,
                                "Synthetic candidate; not model inference", "test_double")

        runner = Runner()
        example = Example("README.md#1", "README.md", 2, 3, self.original, "Example")
        result = evaluate_example(example, {}, {}, runner, Provider(), max_attempts=2)
        self.assertEqual(result.status, "verified_repair")
        self.assertEqual([attempt.status for attempt in result.attempts],
                         ["rejected", "verified_repair"])
        self.assertIn("recursion limit", result.attempts[0].rejection)
        self.assertIsNone(result.attempts[0].after)
        self.assertEqual(runner.calls, [self.original, self.candidate])


if __name__ == "__main__":
    unittest.main()
