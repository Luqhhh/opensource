import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from exampleproof.pipeline import run_project
from exampleproof.providers import FileProvider
from exampleproof.runner import SandboxRunner


@unittest.skipUnless(os.environ.get('EXAMPLEPROOF_SANDBOX_TESTS') == '1', 'Set EXAMPLEPROOF_SANDBOX_TESTS=1 to test actual Bubblewrap execution')
class SandboxTests(unittest.TestCase):
    def test_host_home_and_network_are_unavailable(self):
        code = '''from pathlib import Path
import socket
assert not Path('/home/lux1').exists()
try:
    socket.create_connection(('1.1.1.1', 443), timeout=0.2)
except OSError:
    print('network unavailable')
else:
    raise AssertionError('unexpected network access')
'''
        result = SandboxRunner({}).run(code, {'expected_stdout': 'network unavailable\n'})
        self.assertEqual(result.status, 'passed', result.stderr)

    def test_source_is_read_only(self):
        result = SandboxRunner({'sample.py': 'value = 3'}).run("open('/workspace/sample.py', 'w').write('bad')", {})
        self.assertEqual(result.status, 'failed', result.stderr)
        self.assertIn('Read-only file system', result.stderr)

    def test_child_processes_are_denied(self):
        code = '''import subprocess
try:
    subprocess.run(['/usr/bin/python3', '-c', 'print(1)'], check=True)
except OSError:
    print('process creation denied')
else:
    raise AssertionError('unexpected child process')
'''
        result = SandboxRunner({}).run(code, {'expected_stdout': 'process creation denied\n'})
        self.assertEqual(result.status, 'passed', result.stderr)

    def test_timeout_is_enforced(self):
        result = SandboxRunner({}, timeout=0.3).run('while True: pass', {})
        self.assertEqual(result.status, 'timeout', result.stderr)
        self.assertLess(result.duration_seconds, 3)

    def test_output_is_bounded(self):
        result = SandboxRunner({}).run("print('x' * 1000000)", {})
        self.assertLessEqual(len(result.stdout.encode()), 64000)
        self.assertEqual(result.status, 'failed')

    def test_sys_exit_zero_cannot_bypass_external_checks(self):
        result = SandboxRunner({}).run('import sys\nsys.exit(0)', {'checks': 'assert False'})
        self.assertEqual(result.status, 'failed')
        self.assertNotEqual(result.returncode, 0)

    def test_wrong_output_fails_despite_normal_exit(self):
        result = SandboxRunner({}).run('print(3)', {'expected_stdout': '4\n'})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.status, 'failed')

    def test_demo_end_to_end(self):
        root = Path(__file__).resolve().parents[1] / 'examples/tutorial'
        report, diff = run_project(root, FileProvider(root / 'proposals.json'))
        self.assertEqual(report['summary']['counts'], {'verified_repair': 3, 'checked': 1, 'skipped': 1, 'runnable_unverified': 1}, report)
        self.assertIn('+from collections.abc import Mapping', diff)
        self.assertNotIn('+assert True', diff)
        self.assertTrue(all(r['proposal']['provider'] == 'candidate_file' for r in report['results'] if r['proposal']))
        original = (root / 'README.md').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / 'tutorial'
            shutil.copytree(root, copied)
            subprocess.run(['git', 'apply', '-'], input=diff, text=True,
                           cwd=copied, check=True, capture_output=True)
            checked, remaining_patch = run_project(copied)
            self.assertEqual(checked['summary']['counts'], {'checked': 4, 'skipped': 1, 'runnable_unverified': 1}, checked)
            self.assertEqual(remaining_patch, '')
        self.assertEqual((root / 'README.md').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
