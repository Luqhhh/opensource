import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.models import Execution
from exampleproof.pipeline import run_project
from exampleproof.providers import OllamaProvider
from exampleproof.report import write_report


class FailedRunner:
    backend = 'test_double'

    def run(self, code, spec):
        return Execution('failed', returncode=21, stderr='NameError: old')


class InferenceReportingTests(unittest.TestCase):
    def run_with_response(self, response):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'README.md').write_text('```python\nold()\n```\n')
        with patch('exampleproof.providers.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            report, diff = run_project(root, OllamaProvider('local-model'), FailedRunner())
        return root, report, diff

    def test_failed_parsing_still_reports_request_response_and_consumed_tokens(self):
        response = {'model': 'local-model', 'done': True, 'response': '{broken',
                    'prompt_eval_count': 25, 'eval_count': 8}
        root, report, diff = self.run_with_response(response)
        self.assertEqual(report['summary']['counts'], {'provider_error': 1})
        attempt = report['results'][0]['attempts'][0]
        self.assertIsNone(attempt['proposal'])
        self.assertEqual(attempt['inference_evidence']['response'], response)
        self.assertEqual(report['repair']['inference_requests'], 1)
        self.assertEqual(report['repair']['input_tokens'], 25)
        self.assertEqual(report['repair']['output_tokens'], 8)
        write_report(root / 'reports', report, diff)
        self.assertEqual(json.loads((root / 'reports/report.json').read_text()), report)

    def test_malformed_unicode_server_error_can_still_be_written(self):
        response = {'error': 'invalid server message: \ud800'}
        root, report, diff = self.run_with_response(response)
        write_report(root / 'reports', report, diff)
        persisted = json.loads((root / 'reports/report.json').read_text())
        self.assertEqual(persisted['results'][0]['attempts'][0]['inference_evidence']['response'], response)
        self.assertIn('invalid server message', (root / 'reports/report.html').read_text())
        self.assertIsNone(report['repair']['input_tokens'])

    def test_timeout_preserves_evidence_in_final_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\nold()\n```\n')
            with patch('exampleproof.providers.urlopen', side_effect=TimeoutError('timed out')):
                report, diff = run_project(root, OllamaProvider('local-model', timeout=180), FailedRunner())
        attempt = report['results'][0]['attempts'][0]
        self.assertEqual(attempt['inference_evidence']['timeout_seconds'], 180)
        self.assertIsNone(attempt['inference_evidence']['response'])
        self.assertEqual(report['repair']['inference_requests'], 1)
        self.assertIsNone(report['repair']['input_tokens'])
        self.assertEqual(diff, '')
