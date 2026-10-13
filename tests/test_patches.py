import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from exampleproof.extract import extract_markdown
from exampleproof.models import Execution, Proposal
from exampleproof.pipeline import run_project


class SequenceRunner:
    backend = 'test_double'

    def __init__(self, count):
        self.executions = iter(
            execution
            for _ in range(count)
            for execution in (Execution('failed', oracle='original_top_level_assertions'),
                              Execution('passed'))
        )

    def run(self, code, spec):
        return next(self.executions)


class RecordedProvider:
    def __init__(self, candidates):
        self.candidates = candidates

    def propose(self, example, before, sources):
        return Proposal(self.candidates[example.id], 'Synthetic patch fixture', 'test_double')


@unittest.skipUnless(shutil.which('git'), 'Git is required to verify exported patches')
class PatchRoundTripTests(unittest.TestCase):
    def assert_patch_round_trip(self, documents, candidates):
        """Apply only to a disposable copy; never execute the example code."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / 'original'
            project.mkdir()
            for name, text in documents.items():
                target = project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(text.encode('utf-8'))
            (project / 'exampleproof.json').write_text(json.dumps({
                'documents': list(documents),
            }), encoding='utf-8')
            snapshot = {path.relative_to(project): path.read_bytes()
                        for path in project.rglob('*') if path.is_file()}
            report, patch = run_project(project, RecordedProvider(candidates),
                                        SequenceRunner(len(candidates)))
            self.assertEqual(report['summary']['counts'], {'verified_repair': len(candidates)})
            self.assertTrue(patch)
            self.assertEqual(snapshot, {path.relative_to(project): path.read_bytes()
                                        for path in project.rglob('*') if path.is_file()})

            destination = base / 'review-copy'
            shutil.copytree(project, destination)
            for command in (['git', 'apply', '--check'], ['git', 'apply', '--whitespace=nowarn']):
                completed = subprocess.run(command, cwd=destination, input=patch.encode('utf-8'),
                                           capture_output=True, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr.decode('utf-8') + '\n' + patch)

            for name, original in documents.items():
                repaired = (destination / name).read_bytes().decode('utf-8')
                self.assertEqual(repaired.endswith('\n'), original.endswith('\n'))
                examples = extract_markdown(repaired, name)
                self.assertEqual([example.id for example in examples],
                                 [key for key in candidates if key.startswith(name + '#')])
                for example in examples:
                    expected = candidates[example.id]
                    if not expected.endswith('\n'):
                        expected += '\n'
                    if '\r\n' in original:
                        expected = expected.replace('\r\n', '\n').replace('\n', '\r\n')
                    self.assertEqual(example.code, expected)
            self.assertEqual(snapshot, {path.relative_to(project): path.read_bytes()
                                        for path in project.rglob('*') if path.is_file()})
            return patch

    def test_one_to_three_space_fences_preserve_code_and_document_newlines(self):
        for width in range(1, 4):
            for newline in ('\n', '\r\n'):
                with self.subTest(width=width, newline=repr(newline)):
                    indent = ' ' * width
                    original = ('# Example\n' + indent + '```python\n' + indent + 'old()\n'
                                + indent + 'assert True\n' + indent + '```\n')
                    original = original.replace('\n', newline)
                    candidate = 'values = [\n    1,\n    2,\n]\nassert True\n'
                    self.assert_patch_round_trip({'README.md': original}, {'README.md#1': candidate})

    def test_document_without_final_newline_exports_git_marker(self):
        original = '# Example\n```python\nold()\nassert True\n```'
        candidate = 'result = fixed()\nprint(result)\nassert True'
        patch = self.assert_patch_round_trip({'README.md': original}, {'README.md#1': candidate})
        self.assertIn('\\ No newline at end of file\n', patch)

    def test_filenames_with_spaces_and_unicode_round_trip(self):
        names = ('docs/getting started.md', '文档/示例 教程.md')
        original = '# Example\n```python\nold()\nassert True\n```\n'
        self.assert_patch_round_trip({name: original for name in names},
                                     {name + '#1': 'fixed()\nassert True\n' for name in names})

    def test_multiple_blocks_can_grow_and_shrink_in_one_document(self):
        original = ('# First\n```python\nold()\nassert True\n```\n\n'
                    '# Second\n~~~python\nfirst = old()\nsecond = old()\n'
                    'print(first, second)\nassert True\n~~~\n')
        candidates = {
            'README.md#1': 'first = fixed()\nsecond = fixed()\nprint(first, second)\nassert True\n',
            'README.md#2': 'fixed()\nassert True\n',
        }
        patch = self.assert_patch_round_trip({'README.md': original}, candidates)
        self.assertEqual(patch.count('--- a/README.md'), 1)

    def test_multiline_strings_containing_closing_fences_keep_one_code_block(self):
        for delimiter in ('```', '~~~~'):
            for indent in ('', '  '):
                with self.subTest(delimiter=delimiter, indent=indent):
                    original = (indent + delimiter + 'python\n' + indent + 'old()\n'
                                + indent + 'assert True\n' + indent + delimiter + '\n')
                    candidate = 'value = """\n' + delimiter + '\n' + delimiter * 2 + '\n"""\nassert True\n'
                    self.assert_patch_round_trip({'README.md': original}, {'README.md#1': candidate})

    def test_crlf_candidate_with_fence_in_multiline_string_round_trips(self):
        original = '```python\r\nold()\r\nassert True\r\n```\r\n'
        candidate = 'value = """\r\n```\r\n"""\r\nassert True\r\n'
        self.assert_patch_round_trip({'README.md': original}, {'README.md#1': candidate})


if __name__ == '__main__':
    unittest.main()
