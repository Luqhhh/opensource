import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request

from exampleproof.models import Example, Execution, Proposal
from exampleproof.providers import FileProvider, OllamaProvider, urlopen


class FileProviderTests(unittest.TestCase):
    def provider(self, value):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'proposals.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return FileProvider(path)

    def test_single_candidate_format_remains_supported(self):
        provider = self.provider({'a.md#1': {'code': 'fixed()', 'rationale': 'API change'}})
        example = Example('a.md#1', 'a.md', 1, 1, 'old()', '')
        proposal = provider.propose(example, Execution('failed'), {})
        self.assertEqual(proposal.code, 'fixed()')
        self.assertEqual(proposal.provider, 'candidate_file')
        self.assertIsNone(provider.propose(example, Execution('failed'), {}, history=(object(),)))

    def test_sequence_is_selected_by_example_history_without_shared_cursor(self):
        provider = self.provider({'a.md#1': [
            {'code': 'first()', 'rationale': 'first candidate'},
            {'code': 'second()', 'rationale': 'refined candidate'},
        ], 'b.md#1': []})
        example = Example('a.md#1', 'a.md', 1, 1, 'old()', '')
        self.assertEqual(provider.propose(example, None, {}, history=(object(),)).code, 'second()')
        self.assertEqual(provider.propose(example, None, {}).code, 'first()')
        self.assertIsNone(provider.propose(example, None, {}, history=(object(), object())))
        for example_id in ('b.md#1', 'missing.md#1'):
            self.assertIsNone(provider.propose(Example(example_id, '', 1, 1, '', ''), None, {}))

    def test_all_candidates_are_validated_before_execution(self):
        for value in ([], {'a.md#1': None}, {'a.md#1': [
                {'code': 'valid()', 'rationale': 'valid'}, {'code': 'invalid()'}]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.provider(value)

    def test_candidate_file_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proposals.json'
            path.write_bytes(b' ' * 2_000_001)
            with self.assertRaisesRegex(ValueError, 'exceeds 2 MB'):
                FileProvider(path)


class OllamaProviderTests(unittest.TestCase):
    example = Example('a.md#1', 'a.md', 1, 1, 'old()', 'Original documentation')
    valid_result = {'done': True, 'response': json.dumps({'code': 'fixed()', 'rationale': 'API change'})}

    def propose(self, result=None, *, before=None, history=()):
        payload = json.dumps(self.valid_result if result is None else result).encode()
        with patch('exampleproof.providers.urlopen', return_value=io.BytesIO(payload)) as request:
            proposal = OllamaProvider('test-model').propose(
                self.example, before or Execution('failed', stderr='NameError: old'),
                {'sdk.py': 'def fixed(): pass'}, history=history)
        prompt = json.loads(json.loads(request.call_args.args[0].data)['prompt'])
        return proposal, prompt

    def test_original_evidence_and_each_attempt_are_available_on_retry(self):
        history = (
            SimpleNamespace(number=1, status='rejected',
                            proposal=Proposal('assert True', 'First attempt', 'ollama'),
                            after=None, rejection='Original assertion was removed', diff=None),
            SimpleNamespace(number=2, status='repair_failed',
                            proposal=Proposal('another_api()', 'Second attempt', 'ollama'),
                            after=Execution('failed', returncode=21, stderr='NameError: another_api'),
                            rejection=None, diff='unused'),
        )
        proposal, prompt = self.propose(history=history)
        self.assertEqual(proposal.provider, 'ollama')
        self.assertEqual(prompt['code'], 'old()')
        self.assertEqual(prompt['error'], 'NameError: old')
        self.assertEqual(prompt['sources'], {'sdk.py': 'def fixed(): pass'})
        attempts = prompt['previous_attempts']
        self.assertEqual([attempt['number'] for attempt in attempts], [1, 2])
        self.assertEqual(attempts[0]['rejection'], 'Original assertion was removed')
        self.assertEqual(attempts[1]['candidate']['code'], 'another_api()')
        self.assertEqual(attempts[1]['execution']['error'], 'NameError: another_api')

    def test_first_attempt_does_not_invent_history(self):
        _, prompt = self.propose()
        self.assertNotIn('previous_attempts', prompt)

    def test_original_error_is_not_duplicated_in_the_prompt(self):
        _, prompt = self.propose(before=Execution('failed', returncode=21, stderr='unique traceback marker'))
        self.assertEqual(json.dumps(prompt).count('unique traceback marker'), 1)
        self.assertEqual(prompt['execution']['status'], 'failed')

    def test_external_evaluator_details_are_withheld_from_original_and_retry_errors(self):
        check_error = 'Traceback:\n  File "external-checks", line 2\nassert value == "secret_expected"\nValueError: secret_message'
        before = Execution('failed', returncode=22, stderr=check_error)
        history = (SimpleNamespace(
            number=1, status='repair_failed', proposal=Proposal('fixed()', 'reason', 'ollama'),
            after=Execution('failed', returncode=0, stdout='secret_stdout',
                            stderr='secret_stderr\nExpected stdout did not match the configured oracle.'),
            rejection=None, diff=None),)
        _, prompt = self.propose(before=before, history=history)
        self.assertNotIn('secret_', json.dumps(prompt))
        self.assertIn('withheld', prompt['error'])
        self.assertIn('withheld', prompt['previous_attempts'][0]['execution']['error'])

    def test_external_traceback_is_redacted_before_error_truncation(self):
        error = 'File "external-checks"\n' + ('x' * 9000) + 'secret_message'
        _, prompt = self.propose(before=Execution('failed', stderr=error))
        self.assertNotIn('secret_message', prompt['error'])
        _, prompt = self.propose(before=Execution('failed', returncode=22, stderr='secret_without_traceback'))
        self.assertNotIn('secret_without_traceback', prompt['error'])

    def test_check_output_is_withheld_even_when_checks_timeout_or_exit_early(self):
        for status, returncode in (('timeout', -9), ('failed', 0), ('failed', -11)):
            before = Execution(status, returncode=returncode, stderr='secret_without_traceback',
                               oracle='configured_behavior_checks')
            with self.subTest(status=status, returncode=returncode):
                _, prompt = self.propose(before=before)
                self.assertNotIn('secret_without_traceback', json.dumps(prompt))
                self.assertEqual(prompt['execution']['status'], status)

    def test_original_runtime_errors_remain_available_with_configured_checks(self):
        before = Execution('failed', returncode=21, stderr='NameError: missing_api',
                           oracle='configured_behavior_checks')
        _, prompt = self.propose(before=before)
        self.assertEqual(prompt['error'], 'NameError: missing_api')

    def test_response_envelope_is_validated(self):
        invalid_results = [[], 'text', 42, {'done': False}, {'done': 1},
                           {'done': True}, {'done': True, 'response': {}},
                           {'done': True, 'response': '[]'},
                           {'done': True, 'response': '{'},
                           {'done': True, 'response': '{"code": 1, "rationale": "bad"}'}]
        for result in invalid_results:
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.propose(result)
        for raw in (b'null', b'{'):
            with self.subTest(raw=raw), patch('exampleproof.providers.urlopen', return_value=io.BytesIO(raw)), self.assertRaises(ValueError):
                OllamaProvider('test-model').propose(self.example, Execution('failed'), {})

    def test_token_counts_are_nonnegative_integers(self):
        for key in ('prompt_eval_count', 'eval_count'):
            for invalid in (True, -1, 1.5, '5', {}):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    self.propose({**self.valid_result, key: invalid})
        proposal, _ = self.propose({**self.valid_result, 'prompt_eval_count': 0, 'eval_count': 4})
        self.assertEqual((proposal.input_tokens, proposal.output_tokens), (0, 4))

    def test_service_error_is_clear(self):
        with self.assertRaisesRegex(ValueError, 'model is unavailable'):
            self.propose({'error': 'model is unavailable'})

    def test_response_read_is_bounded(self):
        with patch('exampleproof.providers.urlopen', return_value=io.BytesIO(b'x' * 256_001)), self.assertRaisesRegex(ValueError, '256 KB'):
            OllamaProvider('test-model').propose(self.example, Execution('failed'), {})

    def test_malformed_endpoints_and_timeouts_fail_before_request(self):
        for endpoint in ('http://localhost:bad', 'http://localhost:65536',
                         'http://localhost:\n11434', 'http://[::1]suffix',
                         'http://localhost/#fragment', 'http://localhost/?query',
                         'http://user@localhost', 'http://localhost:'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                OllamaProvider('test-model', endpoint)
        for timeout in (0, -1, True, float('inf'), float('nan'), '60'):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                OllamaProvider('test-model', timeout=timeout)
        for endpoint in ('http://localhost:11434', 'https://127.0.0.1', 'http://[::1]:11434'):
            OllamaProvider('test-model', endpoint)

    def test_transport_ignores_proxies_and_refuses_all_redirects(self):
        request = Request('http://localhost:11434/api/generate', data=b'private source')
        with patch.dict('os.environ', {'http_proxy': 'http://remote.invalid:8080', 'no_proxy': ''}), patch('exampleproof.providers.build_opener') as build:
            urlopen(request, timeout=2)
        handlers = build.call_args.args
        proxy = next(handler for handler in handlers if isinstance(handler, ProxyHandler))
        redirects = next(handler for handler in handlers if isinstance(handler, HTTPRedirectHandler))
        self.assertEqual(proxy.proxies, {})
        build.return_value.open.assert_called_once_with(request, timeout=2)
        for code in (301, 302, 303, 307, 308):
            for destination in ('http://remote.invalid/api/generate', 'http://localhost:11434/elsewhere'):
                with self.subTest(code=code, destination=destination), self.assertRaisesRegex(ValueError, 'redirects are disabled'):
                    redirects.redirect_request(request, None, code, '', {}, destination)


if __name__ == '__main__':
    unittest.main()
