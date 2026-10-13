from dataclasses import asdict
from datetime import datetime
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from exampleproof.models import Example, Execution, Proposal, RepairAttempt, Result
from exampleproof.providers import MAX_RESPONSE_BYTES, OllamaProvider, parse_proposal


class InferenceEvidenceTests(unittest.TestCase):
    example = Example('README.md#1', 'README.md', 2, 3, 'old()', 'API example')
    before = Execution('failed', returncode=21, stderr='NameError: old')

    def propose(self, body):
        with patch('exampleproof.providers.urlopen', return_value=io.BytesIO(body)) as opened:
            proposal = OllamaProvider('local-alias', timeout=180).propose(
                self.example, self.before, {'sdk.py': 'def fixed(): pass'})
        return proposal, opened.call_args.args[0]

    def test_report_retains_actual_request_and_complete_server_envelope(self):
        response = {
            'model': 'local-model:1b', 'created_at': '2026-10-13T00:00:00Z',
            'done': True, 'done_reason': 'stop',
            'response': '{"code":"fixed()","rationale":"Use the available API"}',
            'prompt_eval_count': 153, 'eval_count': 22,
            'total_duration': 1230000000, 'load_duration': 210000000,
            'prompt_eval_duration': 780000000, 'eval_duration': 240000000,
        }
        proposal, request = self.propose(json.dumps(response).encode())
        result = Result(self.example, self.before, 'verified_repair', proposal=proposal,
                        attempts=[RepairAttempt(1, 'verified_repair', proposal=proposal)])
        report = json.loads(json.dumps(result.to_dict()))
        evidence = report['attempts'][0]['proposal']['inference_evidence']
        self.assertEqual(evidence['request'], json.loads(request.data))
        self.assertEqual(evidence['response'], response)
        self.assertIsNone(evidence['response_body'])
        self.assertFalse(evidence['response_truncated'])
        self.assertEqual(evidence['timeout_seconds'], 180)
        self.assertIsNotNone(datetime.fromisoformat(evidence['started_at']).tzinfo)
        self.assertGreaterEqual(evidence['duration_seconds'], 0)
        self.assertEqual(evidence['duration_seconds'], proposal.duration_seconds)
        self.assertEqual(proposal.model, 'local-alias')
        self.assertNotIn('headers', evidence)
        self.assertNotIn('endpoint', evidence)

    def test_timeout_keeps_request_context_and_original_exception(self):
        error = TimeoutError('timed out')
        with patch('exampleproof.providers.urlopen', side_effect=error), \
                patch('exampleproof.providers.time.monotonic', side_effect=[10.0, 12.5]):
            with self.assertRaises(TimeoutError) as caught:
                OllamaProvider('local-model', timeout=2).propose(self.example, self.before, {})
        self.assertIs(caught.exception, error)
        evidence = asdict(caught.exception.inference_evidence)
        self.assertEqual(evidence['timeout_seconds'], 2)
        self.assertEqual(evidence['duration_seconds'], 2.5)
        self.assertEqual(evidence['request']['model'], 'local-model')
        self.assertIsNone(evidence['response'])
        self.assertIsNone(evidence['response_body'])

    def test_malformed_response_is_retained_without_losing_parse_error(self):
        for body in (b'{unfinished', b'[]', b'\xff'):
            with self.subTest(body=body), self.assertRaises(ValueError) as caught:
                self.propose(body)
            evidence = caught.exception.inference_evidence
            self.assertIsNone(evidence.response)
            self.assertEqual(evidence.response_body, body.decode('utf-8', errors='replace'))
            self.assertFalse(evidence.response_truncated)

    def test_invalid_model_json_retains_the_server_envelope(self):
        response = {'done': True, 'response': '{unfinished', 'eval_count': 5}
        with self.assertRaises(json.JSONDecodeError) as caught:
            self.propose(json.dumps(response).encode())
        self.assertEqual(caught.exception.inference_evidence.response, response)
        self.assertIsNone(caught.exception.inference_evidence.response_body)

    def test_oversized_response_evidence_is_bounded_and_marked_truncated(self):
        with self.assertRaisesRegex(ValueError, '256 KB') as caught:
            self.propose(b'x' * (MAX_RESPONSE_BYTES + 100))
        evidence = caught.exception.inference_evidence
        self.assertIsNone(evidence.response)
        self.assertTrue(evidence.response_truncated)
        self.assertEqual(evidence.response_body, 'x' * MAX_RESPONSE_BYTES)

    def test_evaluator_feedback_remains_withheld_in_saved_request(self):
        before = Execution('failed', returncode=22, stderr='private evaluator assertion',
                           oracle='configured_behavior_checks')
        body = json.dumps({'done': True, 'response': '{"code":"","rationale":"Unsure"}'}).encode()
        with patch('exampleproof.providers.urlopen', return_value=io.BytesIO(body)):
            proposal = OllamaProvider('local-model').propose(self.example, before, {})
        prompt = proposal.inference_evidence.request['prompt']
        self.assertNotIn('private evaluator assertion', prompt)
        self.assertIn('withheld', prompt)

    def test_old_proposals_and_attempts_have_no_invented_live_evidence(self):
        proposal = Proposal('fixed()', 'Recorded candidate', 'candidate_file')
        self.assertIsNone(asdict(proposal)['inference_evidence'])
        attempt = RepairAttempt(1, 'verified_repair', proposal)
        self.assertIsNone(asdict(attempt)['inference_evidence'])

    def test_invalid_unicode_is_rejected_before_code_or_rationale_are_used(self):
        for key in ('code', 'rationale'):
            candidate = {'code': 'fixed()', 'rationale': 'Use the available API', key: '\ud800'}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, f'{key} must contain valid UTF-8'):
                parse_proposal(candidate, provider='candidate_file')
            response = {'done': True, 'response': json.dumps(candidate)}
            with self.assertRaisesRegex(ValueError, f'{key} must contain valid UTF-8') as caught:
                self.propose(json.dumps(response).encode())
            self.assertEqual(caught.exception.inference_evidence.response, response)
            str(caught.exception).encode('ascii')

    def test_http_error_retains_server_reason_and_evidence(self):
        response = {'error': "model 'missing-model' not found"}
        error = HTTPError('http://127.0.0.1:11434/api/generate', 404, 'Not Found', {},
                          io.BytesIO(json.dumps(response).encode()))
        with patch('exampleproof.providers.urlopen', side_effect=error):
            with self.assertRaisesRegex(ValueError, 'HTTP 404.*missing-model.*not found') as caught:
                OllamaProvider('missing-model').propose(self.example, self.before, {})
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(caught.exception.inference_evidence.response, response)
        self.assertEqual(caught.exception.inference_evidence.request['model'], 'missing-model')

    def test_non_json_http_error_keeps_status_and_bounded_body(self):
        for body in (b'not JSON', b'x' * (MAX_RESPONSE_BYTES + 100)):
            error = HTTPError('http://127.0.0.1:11434/api/generate', 500, 'Server Error', {}, io.BytesIO(body))
            with self.subTest(size=len(body)), patch('exampleproof.providers.urlopen', side_effect=error):
                with self.assertRaises(HTTPError) as caught:
                    OllamaProvider('local-model').propose(self.example, self.before, {})
            self.assertIs(caught.exception, error)
            evidence = caught.exception.inference_evidence
            self.assertEqual(evidence.response_body, body[:MAX_RESPONSE_BYTES].decode())
            self.assertEqual(evidence.response_truncated, len(body) > MAX_RESPONSE_BYTES)


if __name__ == '__main__':
    unittest.main()
