import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from exampleproof.cli import main
from exampleproof.models import Example, Execution, Proposal
from exampleproof.pipeline import evaluate_example, exit_code, run_project
from exampleproof.providers import FileProvider
from exampleproof.report import render_html


class RecordingRunner:
    backend = 'test_double'

    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def run(self, code, spec):
        self.calls.append((code, spec))
        return next(self.outcomes)


class RecordingProvider:
    def __init__(self, *codes):
        self.codes = iter(codes)
        self.histories = []

    def propose(self, example, before, sources, *, history=()):
        self.histories.append((example.code, before.stderr, history))
        code = next(self.codes)
        if isinstance(code, Exception):
            raise code
        if code is None:
            return None
        return Proposal(code, '<script>reason</script>', 'test_double',
                        input_tokens=10, output_tokens=5, duration_seconds=0.25)


class RetryTests(unittest.TestCase):
    original = 'result = broken()\nassert result == 2\n'
    first = 'result = incomplete()\nassert result == 2\n'
    fixed = 'result = fixed()\nassert result == 2\n'

    def example(self, code=None):
        return Example('README.md#1', 'README.md', 2, 3, code or self.original, 'Example')

    def failure(self):
        return Execution('failed', stderr='original error', oracle='original_top_level_assertions')

    def test_failed_candidate_supplies_feedback_to_next_round(self):
        runner = RecordingRunner(self.failure(), Execution('failed', stderr='new error'), Execution('passed'))
        provider = RecordingProvider(self.first, self.fixed)
        result = evaluate_example(self.example(), {}, {}, runner, provider, max_attempts=3)
        self.assertEqual(result.status, 'verified_repair')
        self.assertEqual([a.status for a in result.attempts], ['repair_failed', 'verified_repair'])
        self.assertEqual(result.proposal.code, self.fixed)
        self.assertEqual(result.stop_reason, 'verified_repair')
        original, error, history = provider.histories[1]
        self.assertEqual((original, error), (self.original, 'original error'))
        self.assertEqual(history[0].after.stderr, 'new error')
        self.assertEqual(history[0].proposal.code, self.first)
        self.assertEqual(len(runner.calls), 3)

    def test_rejected_assertion_removal_is_not_executed_and_can_be_retried(self):
        runner = RecordingRunner(self.failure(), Execution('passed'))
        provider = RecordingProvider('result = fixed()\n', self.fixed)
        result = evaluate_example(self.example(), {}, {}, runner, provider, max_attempts=2)
        self.assertEqual(result.status, 'verified_repair')
        self.assertEqual(result.attempts[0].status, 'rejected')
        self.assertIn('assertion', provider.histories[1][2][0].rejection)
        self.assertEqual(len(runner.calls), 2)

    def test_original_assertions_remain_required_in_later_rounds(self):
        runner = RecordingRunner(self.failure(), Execution('failed'))
        result = evaluate_example(self.example(), {}, {}, runner,
                                  RecordingProvider(self.first, 'result = fixed()\n'), max_attempts=2)
        self.assertEqual(result.status, 'rejected')
        self.assertEqual(result.stop_reason, 'max_attempts')
        self.assertEqual(len(runner.calls), 2)

    def test_limit_and_default_single_attempt(self):
        for budget in (1, 2):
            with self.subTest(budget=budget):
                runner = RecordingRunner(self.failure(), *[Execution('failed') for _ in range(budget)])
                provider = RecordingProvider(self.first, self.fixed)
                result = evaluate_example(self.example(), {}, {}, runner, provider, max_attempts=budget)
                self.assertEqual(len(result.attempts), budget)
                self.assertEqual(result.stop_reason, 'max_attempts')

    def test_repeated_candidate_stops_without_reexecution(self):
        runner = RecordingRunner(self.failure(), Execution('failed'))
        result = evaluate_example(self.example(), {}, {}, runner,
                                  RecordingProvider(self.first, self.first.replace('\n', '\r\n')), max_attempts=5)
        self.assertEqual(result.status, 'repair_failed')
        self.assertEqual(result.stop_reason, 'repeated_candidate')
        self.assertEqual(result.attempts[-1].status, 'repeated_candidate')
        self.assertIsNone(result.attempts[-1].after)
        self.assertEqual(len(runner.calls), 2)

    def test_fixed_leading_indentation_is_not_a_duplicate(self):
        runner = RecordingRunner(self.failure(), Execution('passed'))
        result = evaluate_example(self.example(), {}, {}, runner,
                                  RecordingProvider(' ' + self.fixed, self.fixed), max_attempts=2)
        self.assertEqual([attempt.status for attempt in result.attempts], ['rejected', 'verified_repair'])
        self.assertEqual(len(runner.calls), 2)

    def test_provider_error_and_decline_keep_previous_attempts(self):
        for candidate, status in ((ValueError('bad response'), 'provider_error'), ('', 'declined')):
            with self.subTest(status=status):
                runner = RecordingRunner(self.failure(), Execution('failed'))
                result = evaluate_example(self.example(), {}, {}, runner,
                                          RecordingProvider(self.first, candidate), max_attempts=3)
                self.assertEqual(result.status, status)
                self.assertEqual(len(result.attempts), 2)
                self.assertEqual(result.attempts[0].proposal.code, self.first)
                self.assertIsNone(result.after)

    def test_exhausted_replay_preserves_last_failed_outcome(self):
        runner = RecordingRunner(self.failure(), Execution('failed'))
        result = evaluate_example(self.example(), {}, {}, runner,
                                  RecordingProvider(self.first, None), max_attempts=3)
        self.assertEqual(result.status, 'repair_failed')
        self.assertEqual(result.stop_reason, 'no_candidate')
        self.assertEqual(len(result.attempts), 1)

    def test_model_assertions_never_become_independent_evidence(self):
        runner = RecordingRunner(Execution('failed'), Execution('failed'), Execution('passed'))
        result = evaluate_example(self.example('broken()\n'), {}, {}, runner,
                                  RecordingProvider('partial()\nassert True\n', 'fixed()\nassert True\n'), max_attempts=3)
        self.assertEqual(result.status, 'candidate_unverified')
        self.assertEqual(result.after.oracle, 'none')
        self.assertEqual(len(result.attempts), 2)

    def test_blocked_runner_stops_retries(self):
        runner = RecordingRunner(self.failure(), Execution('blocked'))
        result = evaluate_example(self.example(), {}, {}, runner, RecordingProvider(self.fixed), max_attempts=5)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(len(result.attempts), 1)

    def test_report_includes_history_usage_and_only_final_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\n' + self.original + '```\n')
            runner = RecordingRunner(self.failure(), Execution('failed'), Execution('passed'))
            report, diff = run_project(root, RecordingProvider(self.first, self.fixed), runner, max_attempts=3)
        self.assertEqual(report['schema_version'], 2)
        self.assertEqual(report['repair']['attempts'], 2)
        self.assertEqual(report['repair']['input_tokens'], 20)
        self.assertEqual(report['repair']['output_tokens'], 10)
        self.assertEqual(report['repair']['proposal_duration_seconds'], 0.5)
        self.assertIn('+result = fixed()', diff)
        self.assertNotIn('incomplete', diff)
        self.assertEqual(exit_code(report), 0)
        html = render_html(report)
        self.assertIn('第 1 轮', html)
        self.assertIn('第 2 轮', html)
        self.assertIn('incomplete()', html)
        self.assertIn('&lt;script&gt;reason', html)
        self.assertNotIn('<script>reason', html)

    def test_invalid_attempt_limits_fail_before_execution(self):
        for value in (0, -1, 6, 1.5, True, '2'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'max_attempts'):
                evaluate_example(self.example(), {}, {}, None, max_attempts=value)

    def test_partial_token_counts_are_reported_as_unknown(self):
        class PartialUsageProvider(RecordingProvider):
            def propose(self, *args, **kwargs):
                proposal = super().propose(*args, **kwargs)
                if kwargs.get('history'):
                    proposal.input_tokens = None
                    proposal.output_tokens = None
                return proposal
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\n' + self.original + '```\n')
            runner = RecordingRunner(self.failure(), Execution('failed'), Execution('passed'))
            report, _ = run_project(root, PartialUsageProvider(self.first, self.fixed), runner, max_attempts=2)
        self.assertIsNone(report['repair']['input_tokens'])
        self.assertIsNone(report['repair']['output_tokens'])
        self.assertEqual(report['results'][0]['attempts'][0]['proposal']['input_tokens'], 10)

    def test_cli_rejects_invalid_limit(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(['repair', '.', '--proposals', 'unused.json', '--output', 'unused', '--max-attempts', '6'])
        self.assertEqual(error.exception.code, 2)


@unittest.skipUnless(os.environ.get('EXAMPLEPROOF_SANDBOX_TESTS') == '1', 'Requires Bubblewrap integration tests')
class RetrySandboxTests(unittest.TestCase):
    def test_failed_replay_then_success_patch_applies_and_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            root.mkdir()
            original = '  ```python\n  result = missing()\n  assert result == 2\n  ```'
            (root / 'README.md').write_text(original)
            (root / 'exampleproof.json').write_text(json.dumps({'examples': {'README.md#1': {'checks': 'assert result == 2'}}}))
            proposals = Path(directory) / 'proposals.json'
            proposals.write_text(json.dumps({'README.md#1': [
                {'code': 'result = int("bad")\nassert result == 2\n', 'rationale': 'recorded failure'},
                {'code': 'result = int("2")\nassert result == 2\n', 'rationale': 'recorded success'},
            ]}))
            output = Path(directory) / 'report'
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(['repair', str(root), '--proposals', str(proposals), '--output', str(output), '--max-attempts', '2'])
            self.assertEqual(code, 0)
            report = json.loads((output / 'report.json').read_text())
            self.assertEqual(report['repair']['attempts'], 2)
            self.assertEqual(report['summary']['counts'], {'verified_repair': 1})
            self.assertEqual((root / 'README.md').read_text(), original)
            copied = Path(directory) / 'copy'
            shutil.copytree(root, copied)
            subprocess.run(['git', 'apply', str(output / 'verified.patch')], cwd=copied, check=True, capture_output=True)
            checked, diff = run_project(copied)
            self.assertEqual(checked['summary']['counts'], {'checked': 1}, checked)
            self.assertEqual(diff, '')
