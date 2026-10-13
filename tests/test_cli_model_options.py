import contextlib
import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from exampleproof.cli import main


class ModelTimeoutTests(unittest.TestCase):
    def test_semantic_policy_selects_versioned_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\nprint(1)\n```\n')
            report = {'summary': {'total': 1, 'counts': {'checked': 1}}}
            with patch('exampleproof.cli.SemanticOllamaProvider') as provider, \
                    patch('exampleproof.cli.run_project', return_value=(report, '')), \
                    patch('exampleproof.cli.write_report'), contextlib.redirect_stdout(io.StringIO()):
                code = main(['repair', str(root), '--model', 'local-model', '--output', str(root / 'reports'),
                             '--repair-policy', 'semantic-v2'])
            self.assertEqual(code, 0)
            provider.assert_called_once_with('local-model', 'http://127.0.0.1:11434', timeout=60)

    def test_semantic_policy_does_not_label_recorded_candidates_as_live(self):
        with patch('exampleproof.cli.read_project') as read, contextlib.redirect_stderr(io.StringIO()):
            code = main(['repair', 'unused', '--proposals', 'unused.json', '--output', 'unused',
                         '--repair-policy', 'semantic-v2'])
        self.assertEqual(code, 2)
        read.assert_not_called()

    def test_invalid_timeouts_fail_before_reading_inputs(self):
        for value in ('0', '-1', 'nan', 'inf', 'text'):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error, patch('exampleproof.cli.read_project') as read:
                    main(['repair', 'unused', '--model', 'local', '--output', 'unused', '--model-timeout', value])
                self.assertEqual(error.exception.code, 2)
                read.assert_not_called()

    def test_timeout_is_forwarded_to_model_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\nprint(1)\n```\n')
            report = {'summary': {'total': 1, 'counts': {'checked': 1}}}
            with patch('exampleproof.cli.OllamaProvider') as provider, \
                    patch('exampleproof.cli.run_project', return_value=(report, '')), \
                    patch('exampleproof.cli.write_report'), contextlib.redirect_stdout(io.StringIO()):
                code = main(['repair', str(root), '--model', 'local-model', '--output', str(root / 'reports'),
                             '--model-timeout', '180.5'])
            self.assertEqual(code, 0)
            provider.assert_called_once_with('local-model', 'http://127.0.0.1:11434', timeout=180.5)
