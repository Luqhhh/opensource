import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.report import write_report


class ReportFileTests(unittest.TestCase):
    report = {'project_name': 'demo', 'generated_at': 'now',
              'summary': {'counts': {}}, 'results': []}

    def test_existing_hardlinks_do_not_modify_project_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'README.md'
            original.write_text('original document')
            output = root / 'report'
            output.mkdir()
            for name in ('report.json', 'report.html', 'verified.patch'):
                os.link(original, output / name)
            write_report(output, self.report, 'patch\r\n')
            self.assertEqual(original.read_text(), 'original document')
            self.assertEqual(json.loads((output / 'report.json').read_text()), self.report)
            self.assertEqual((output / 'verified.patch').read_bytes(), b'patch\r\n')
            self.assertEqual(len(list(output.iterdir())), 3)

    def test_write_failure_cleans_up_staged_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            existing = output / 'report.json'
            existing.write_text('previous report')
            with patch('exampleproof.report.os.replace', side_effect=OSError('disk error')):
                with self.assertRaisesRegex(OSError, 'disk error'):
                    write_report(output, self.report, '')
            self.assertEqual(existing.read_text(), 'previous report')
            self.assertEqual(list(output.iterdir()), [existing])

    def test_cli_refuses_to_overwrite_candidate_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('```python\nmissing()\n```\n')
            proposals = root / 'report.json'
            proposals.write_text('{}')
            with contextlib.redirect_stderr(io.StringIO()), patch('exampleproof.cli.run_project') as run:
                code = main(['repair', str(root), '--proposals', str(proposals), '--output', str(root)])
            self.assertEqual(code, 2)
            self.assertEqual(proposals.read_text(), '{}')
            run.assert_not_called()
