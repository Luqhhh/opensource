"""Verify copied bytes and re-extract official doctests without executing them."""

import ast
import doctest
import hashlib
import json
from pathlib import Path


def verify():
    root = Path(__file__).resolve().parent
    provenance = json.loads((root / 'provenance.json').read_text())
    config = json.loads((root / 'exampleproof.json').read_text())
    for item in provenance['files']:
        data = (root / item['local_path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item['sha256'], item['local_path']
        assert item['line_range'] == [1, len(data.splitlines())], item['local_path']
    old_source = (root / 'upstream/1.1.1/src/markupsafe/_native.py').read_text()
    functions = {node.name: node for node in ast.parse(old_source).body
                 if isinstance(node, ast.FunctionDef)}
    names = {'cases/safe_string.md#1': 'soft_unicode',
             'cases/optional_values.md#1': 'escape_silent'}
    for item in provenance['extractions']:
        function = functions[names[item['case_id']]]
        docstring = function.body[0]
        start, end = item['upstream_line_range']
        assert (start, end) == (docstring.lineno, docstring.end_lineno)
        raw = ''.join(old_source.splitlines(keepends=True)[start - 1:end]).encode()
        assert raw == (root / item['raw_snippet']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['raw_snippet_sha256']
        document = (root / item['derived_document']).read_bytes()
        assert hashlib.sha256(document).hexdigest() == item['derived_document_sha256']
        code, output = [], []
        for example in doctest.DocTestParser().get_examples(ast.get_docstring(function)):
            statements = ast.parse(example.source).body
            if example.want:
                assert len(statements) == 1 and isinstance(statements[0], ast.Expr)
                code.append(f'print(repr({example.source.strip()}))\n')
                output.append(example.want)
            else:
                code.append(example.source)
        extracted = document.decode().split('```python\n', 1)[1].split('```', 1)[0]
        assert ''.join(code) == extracted, item['case_id']
        assert ''.join(output) == config['examples'][item['case_id']]['expected_stdout']
    for selected in config['source_files']:
        assert (root / selected).read_bytes() == (root / 'upstream/2.1.5/src' / selected).read_bytes()
    print(json.dumps({'verified_files': len(provenance['files']),
                      'verified_extractions': len(provenance['extractions']),
                      'selected_source_bytes_unchanged': True}))


if __name__ == '__main__':
    verify()
