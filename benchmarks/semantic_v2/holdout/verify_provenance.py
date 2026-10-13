"""Verify provenance and optionally repeat old/new controls only in Bubblewrap.

Usage from the repository root:
  python3 benchmarks/semantic_v2/holdout/verify_provenance.py
  python3 benchmarks/semantic_v2/holdout/verify_provenance.py --runtime --output /tmp/new-evidence-directory
"""
import argparse
import ast
import doctest
import hashlib
import json
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_project(root):
    provenance = json.loads((root / 'provenance.json').read_text())
    config = json.loads((root / 'exampleproof.json').read_text())
    metadata = json.loads((root / 'metadata.json').read_text())
    for item in provenance['files']:
        assert sha((root / item['local_path']).read_bytes()) == item['sha256'], item['local_path']
        assert item['commit'] in item['url']
    for item in provenance['extractions']:
        source = (root / item['source']).read_bytes()
        first, last = item['line_range']
        raw = b''.join(source.splitlines(keepends=True)[first-1:last])
        assert raw == (root / item['raw_snippet']).read_bytes()
        assert sha(raw) == item['raw_sha256']
        document = (root / item['derived_document']).read_bytes()
        assert sha(document) == item['document_sha256']
        extracted = document.decode().split('```python\n', 1)[1].split('```', 1)[0]
        assert sha(extracted.encode()) == item['code_sha256']
        imports = item['normalization']['imports_added']
        if item['normalization']['kind'] == 'dedent_code_block':
            derived = textwrap.dedent(raw.decode())
        else:
            node = next(n for n in ast.parse(source.decode()).body
                        if isinstance(n, ast.FunctionDef) and n.name == item['function'])
            assert [node.body[0].lineno, node.body[0].end_lineno] == item['line_range']
            code, output = [], []
            for example in doctest.DocTestParser().get_examples(ast.get_docstring(node)):
                if example.want:
                    statements = ast.parse(example.source).body
                    assert len(statements) == 1 and isinstance(statements[0], ast.Expr)
                    code.append('print(repr(' + example.source.strip() + '))\n')
                    output.append(example.want)
                else:
                    code.append(example.source)
            derived = ''.join(line+'\n' for line in imports) + ''.join(code)
            assert ''.join(output) == config['examples'][item['case_id']]['expected_stdout']
        assert derived == extracted, item['case_id']
    target = provenance['source_mappings'][metadata['runtime_version']]
    assert set(target) == set(config['source_files'])
    total = 0
    for name, raw_name in target.items():
        data = (root / name).read_bytes()
        assert data == (root / raw_name).read_bytes()
        assert len(data) <= 256_000
        total += len(data)
    assert total <= 2_000_000
    return {'project': root.name, 'files': len(provenance['files']),
            'extractions': len(provenance['extractions']), 'selected_source_files': len(target),
            'selected_source_bytes': total, 'verified': True}


def runtime_project(root, output):
    # Only ExampleProof control code is imported on host. Every upstream import
    # and execution is sent to SandboxRunner, with no host fallback.
    sys.path.insert(0, str(ROOT.parents[2]))
    from exampleproof.benchmark import run_benchmark
    from exampleproof.pipeline import run_project
    from exampleproof.providers import FileProvider
    from exampleproof.report import write_report
    from exampleproof.runner import SandboxRunner

    if output.exists():
        raise ValueError('Output directory must be new')
    output.mkdir(parents=True)
    provenance = json.loads((root / 'provenance.json').read_text())
    metadata = json.loads((root / 'metadata.json').read_text())
    old = metadata['documentation_version']
    sources = {name: (root / path).read_text()
               for name, path in provenance['source_mappings'][old].items()}
    report, _ = run_project(root, runner=SandboxRunner(sources))
    write_report(output / 'old-control', report, '')
    assert all(row['status'] == 'checked' for row in report['results'])
    reference, code = run_benchmark(root, output / 'reference', FileProvider(root / 'proposals.json'))
    assert code == 0 and reference['metrics']['all_passed']
    negative, code = run_benchmark(root, output / 'negative', FileProvider(root / 'negative_proposals.json'))
    assert code == 1 and negative['metrics']['evaluation_complete']
    assert negative['metrics']['verified_repairs'] == 0
    assert negative['metrics']['healthy_preserved'] == negative['metrics']['healthy_controls']
    summary = {'mode': 'evaluator_reference_replay_only_no_model', 'old_control': report['summary'],
               'reference': reference['metrics'], 'negative': negative['metrics']}
    (output / 'validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.runtime and args.output is None:
        parser.error('--runtime requires a new --output directory')
    result = []
    for name in ['mistune', 'werkzeug']:
        value = verify_project(ROOT / name)
        if args.runtime:
            value['runtime'] = runtime_project(ROOT / name, args.output / name)
        result.append(value)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
