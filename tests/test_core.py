import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.config import load_config, safe_path
from exampleproof.extract import extract_markdown
from exampleproof.guard import validate_candidate
from exampleproof.models import Example, Execution, Proposal
from exampleproof.pipeline import evaluate_example, exit_code, run_project
from exampleproof.providers import OllamaProvider
from exampleproof.report import render_html


class ExtractionTests(unittest.TestCase):
    def test_positions_and_non_python_fences(self):
        text = '# Title\n```text\n```python\n```\n\n~~~python\nprint(2)\n~~~\n'
        examples = extract_markdown(text, 'README.md')
        self.assertEqual(len(examples), 1)
        self.assertEqual((examples[0].id, examples[0].start_line, examples[0].end_line), ('README.md#1', 7, 7))
        self.assertEqual(examples[0].code, 'print(2)\n')

    def test_long_fence_does_not_close_early(self):
        examples = extract_markdown('````python\nx = """\n```\n"""\n````\n', 'a.md')
        self.assertEqual(len(examples), 1)
        self.assertIn('```', examples[0].code)

    def test_unclosed_fence_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'unclosed'):
            extract_markdown('```python\nprint(1)', 'a.md')


class ConfigTests(unittest.TestCase):
    def test_traversal_hidden_files_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('hi')
            (root / 'alias.md').symlink_to(root / 'README.md')
            for value in ('../secret', '/etc/passwd', '.env', 'alias.md'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    safe_path(root, value)

    def test_setup_is_explicit_and_configuration_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\nprint(1)\n```\n')
            (root / 'exampleproof.json').write_text(json.dumps({'examples': {'README.md#1': {'setup': 'x = 1'}}}))
            self.assertEqual(load_config(root)['examples']['README.md#1']['setup'], 'x = 1')
            (root / 'exampleproof.json').write_text(json.dumps({'timeout_seconds': -1}))
            with self.assertRaisesRegex(ValueError, 'timeout'):
                load_config(root)


class GuardTests(unittest.TestCase):
    original = 'result = old_api(1)\nassert result == 2\nprint(result)\n'

    def test_api_change_preserves_oracle(self):
        self.assertIsNone(validate_candidate(self.original, self.original.replace('old_api', 'new_api')))

    def test_assertion_removal_and_weakening_rejected(self):
        for candidate in ('print(2)\n', 'result = 2\nassert True\nprint(result)\n',
                          'result = 2\nif False:\n    assert result == 2\n'):
            with self.subTest(candidate=candidate):
                self.assertIsNotNone(validate_candidate(self.original, candidate))

    def test_error_swallowing_and_process_exit_rejected(self):
        for candidate in ('try:\n    result = old_api(1)\nexcept Exception:\n    pass\nassert result == 2\n',
                          'import sys\nsys.exit(0)\nassert result == 2\n',
                          'exec("pass")\nassert result == 2\n'):
            with self.subTest(candidate=candidate):
                self.assertIsNotNone(validate_candidate(self.original, candidate))


class SequenceRunner:
    backend = 'test_double'

    def __init__(self, *results):
        self.results = iter(results)

    def run(self, code, spec):
        return next(self.results)


class ConstantProvider:
    def __init__(self, code):
        self.code = code
        self.calls = 0

    def propose(self, example, before, sources):
        self.calls += 1
        return Proposal(self.code, 'test proposal', 'test_double')


class PipelineTests(unittest.TestCase):
    def example(self, code='result = broken(1)\nassert result == 2\n'):
        return Example('README.md#1', 'README.md', 2, 3, code, 'Example')

    def test_healthy_examples_do_not_call_model(self):
        provider = ConstantProvider('raise RuntimeError')
        result = evaluate_example(self.example(), {}, {}, SequenceRunner(Execution('passed', oracle='original_top_level_assertions')), provider)
        self.assertEqual(result.status, 'checked')
        self.assertEqual(provider.calls, 0)

    def test_failed_behavior_check_is_not_a_repair(self):
        runner = SequenceRunner(Execution('failed', oracle='configured_behavior_checks'), Execution('failed', stderr='AssertionError'))
        result = evaluate_example(self.example(), {}, {}, runner, ConstantProvider('result = fixed(1)\nassert result == 2\n'))
        self.assertEqual(result.status, 'repair_failed')

    def test_model_added_assertion_cannot_supply_its_own_oracle(self):
        runner = SequenceRunner(Execution('failed'), Execution('passed', oracle='original_top_level_assertions'))
        result = evaluate_example(self.example('print(broken())\n'), {}, {}, runner,
                                  ConstantProvider('print(2)\nassert True\n'))
        self.assertEqual(result.status, 'candidate_unverified')
        self.assertEqual(result.after.oracle, 'none')

    def test_multiple_repairs_make_a_single_document_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = '# A\r\n```python\r\nold()\r\nassert True\r\n```\r\n# B\r\n```python\r\nold()\r\nassert True\r\n```\r\n'
            (root / 'README.md').write_bytes(original.encode())
            runner = SequenceRunner(Execution('failed', oracle='original_top_level_assertions'), Execution('passed'),
                                    Execution('failed', oracle='original_top_level_assertions'), Execution('passed'))
            report, diff = run_project(root, ConstantProvider('new()\nassert True\n'), runner)
            self.assertEqual(report['summary']['counts']['verified_repair'], 2)
            self.assertEqual(diff.count('--- a/README.md'), 1)
            self.assertEqual(diff.count('+new()\r\n'), 2)
            self.assertEqual((root / 'README.md').read_bytes(), original.encode())

    def test_provider_failure_is_visible(self):
        class BrokenProvider:
            def propose(self, *args):
                raise ValueError('malformed response')
        result = evaluate_example(self.example(), {}, {}, SequenceRunner(Execution('failed')), BrokenProvider())
        self.assertEqual(result.status, 'provider_error')
        self.assertIn('malformed response', result.rejection)

    def test_no_tests_and_all_skipped_are_not_success(self):
        for summary in ({'total': 0, 'counts': {}}, {'total': 2, 'counts': {'skipped': 2}}, {'total': 1, 'counts': {'blocked': 1}}):
            self.assertEqual(exit_code({'summary': summary}), 2)

    def test_html_escapes_untrusted_document_content(self):
        result = evaluate_example(self.example('<script>alert(1)</script>'), {'skip': 'demo'}, {}, None)
        html = render_html({'project_name': '<img src=x>', 'generated_at': 'now',
                            'summary': {'counts': {'skipped': 1}}, 'results': [result.to_dict()]})
        self.assertNotIn('<script>alert', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn("script-src 'none'", html)


class ProviderTests(unittest.TestCase):
    def test_remote_endpoints_rejected(self):
        for address in ('https://example.com', 'http://user:pw@localhost:11434', 'file:///tmp/a'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                OllamaProvider('model', address)

    def test_ollama_protocol_is_mocked_not_live(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({'done': True, 'response': json.dumps({'code': 'x = 1', 'rationale': 'reason'}),
                                   'prompt_eval_count': 5, 'eval_count': 6}).encode()
        example = Example('a.md#1', 'a.md', 1, 1, 'x = old()', 'context')
        with patch('exampleproof.providers.urlopen', return_value=Response()) as request:
            proposal = OllamaProvider('test-model').propose(example, Execution('failed', stderr='NameError'), {'a.py': 'x = 1'})
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload['stream'], False)
        self.assertEqual(proposal.input_tokens, 5)
        self.assertEqual(proposal.provider, 'ollama')
        self.assertNotIn('expected_stdout', json.loads(payload['prompt']))


if __name__ == '__main__':
    unittest.main()
