"""Check v2 provenance, old-runtime controls and reference/negative replays.

Only repository-owned code executes in this host interpreter. Every upstream
snippet and every external semantic check executes through SandboxRunner.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[2]
sys.path.insert(0, str(REPOSITORY))

from exampleproof.benchmark import run_benchmark
from exampleproof.guard import validate_candidate
from exampleproof.pipeline import read_project, run_project
from exampleproof.providers import FileProvider
from exampleproof.report import write_report


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def inventory(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}


def validate(output):
    output.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": 1, "split": "development_v2", "mode": "historical_and_recorded_candidate_validation", "live_model_requests": 0, "projects": {}, "complete": False}
    original_hashes = inventory(REPOSITORY / 'benchmarks/real_projects')
    frozen_hashes = inventory(REPOSITORY / 'docs/evidence/real-projects-20261013')
    try:
        for name in ('tinydb', 'more_itertools', 'markupsafe'):
            root = ROOT / name
            destination = output / name
            destination.mkdir()
            provenance = json.loads((root / 'provenance.json').read_text())
            for copied in provenance['copied_files']:
                assert hashlib.sha256((root / copied['path']).read_bytes()).hexdigest() == copied['sha256'], copied
                assert (root / copied['path']).read_bytes() == (REPOSITORY / copied['origin']).read_bytes(), copied
            config, documents, sources, examples = read_project(root)
            for spec in config['examples'].values():
                ast.parse(spec.get('setup', ''))
                ast.parse(spec['checks'])
            historical_inputs = destination / 'historical/inputs'
            historical_inputs.mkdir(parents=True)
            for selected, contents in documents.items():
                target = historical_inputs / selected
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents)
            for selected, upstream in provenance['historical_source_mapping'].items():
                target = historical_inputs / selected
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / upstream, target)
            historical_config = dict(config, source_files=list(provenance['historical_source_mapping']))
            dump(historical_inputs / 'exampleproof.json', historical_config)
            historical, patch = run_project(historical_inputs)
            write_report(destination / 'historical/check', historical, patch)
            assert historical['summary']['counts'] == {'checked': len(examples)}, historical['summary']
            assert historical['repair']['inference_requests'] == 0
            reference, code = run_benchmark(root, destination / 'reference', FileProvider(root / 'proposals.json'))
            assert code == 0 and reference['metrics']['all_passed'], reference['metrics']
            negatives = json.loads((root / 'negative_proposals.json').read_text())
            references = json.loads((root / 'proposals.json').read_text())
            by_id = {example.id: example for example in examples}
            negative_results = []
            for variant, replacements in negatives.items():
                for key, candidate in replacements.items():
                    assert validate_candidate(by_id[key].code, candidate['code']) is None, (variant, key)
                # Other failing cases use their reference, so failures isolate
                # the declared negative candidate and not missing proposals.
                candidates = dict(references, **replacements)
                path = destination / (variant + '-proposals.json')
                dump(path, candidates)
                negative, code = run_benchmark(root, destination / ('negative-' + variant), FileProvider(path))
                assert code == 1 and negative['metrics']['evaluation_complete'], negative['metrics']
                report = json.loads((destination / ('negative-' + variant) / 'repair/report.json').read_text())
                for result in report['results']:
                    key = result['example']['id']
                    if key not in replacements:
                        continue
                    assert result['status'] == 'repair_failed', (variant, key, result['status'])
                    assert result['rejection'] is None, result
                    assert result['after']['returncode'] == 22, result
                    assert 'AssertionError' in result['after']['stderr'], result
                    negative_results.append({"variant": variant, "id": key, "guard_passed": True, "candidate_execution_completed": True, "external_checks_rejected": True, "returncode": result['after']['returncode'], "displayed_stdout_matches": result['after']['stdout'] == config['examples'][key].get('expected_stdout'), "failure": result['after']['stderr'], "report": str((destination / ('negative-' + variant) / 'repair/report.json').relative_to(output))})
            summary['projects'][name] = {"historical_version": provenance['historical_versions'], "target_version": provenance['target_versions'], "historical_same_checks_passed": len(examples), "target_expected_failures": reference['metrics']['expected_failures'], "healthy_controls": reference['metrics']['healthy_controls'], "reference_repairs_patch_confirmed": reference['metrics']['patch_confirmed_repairs'], "reference_healthy_preserved": reference['metrics']['healthy_preserved'], "negative_controls": negative_results, "copied_files_verified": len(provenance['copied_files']), "input_sha256": {**{path: hashlib.sha256(content.encode()).hexdigest() for path, content in {**documents, **sources}.items()}, 'exampleproof.json': hashlib.sha256((root / 'exampleproof.json').read_bytes()).hexdigest(), 'metadata.json': hashlib.sha256((root / 'metadata.json').read_bytes()).hexdigest()}}
            print(json.dumps({"project": name, "historical_passed": len(examples), "reference_passed": reference['metrics']['all_passed'], "semantic_negatives_rejected": len(negative_results)}), flush=True)
        assert inventory(REPOSITORY / 'benchmarks/real_projects') == original_hashes
        assert inventory(REPOSITORY / 'docs/evidence/real-projects-20261013') == frozen_hashes
        summary['v1_projects_and_frozen_evidence_unchanged'] = True
        summary['complete'] = True
    finally:
        dump(output / 'validation.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory; existing outputs are never overwritten')
    args = parser.parse_args()
    validate(args.output.resolve())


if __name__ == '__main__':
    main()
