"""Semantic experiment protocol tests; model HTTP responses are always mocked.

The integration tests use only self-authored fixtures in Bubblewrap. They never
read development/holdout case packs or their reference answers.
"""

from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exampleproof import study
from exampleproof.models import Example, Execution
from exampleproof.providers import SYSTEM, SYSTEM_V2, WITHHELD_CHECK_ERROR
from exampleproof.semantic_study import study_design, validate_project_splits


class SequenceRunner:
    backend = "test_double"

    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def run(self, code, spec):
        self.calls.append((code, spec))
        return next(self.outcomes)


def response(code="value = 3\n", **fields):
    payload = {"done": True, "response": json.dumps({"code": code, "rationale": "Repair the public task"}),
               "prompt_eval_count": 100, "eval_count": 20, **fields}
    return io.BytesIO(json.dumps(payload).encode())


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts/run_semantic_study.py"
    spec = importlib.util.spec_from_file_location("semantic_study_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SemanticStudyTests(unittest.TestCase):
    example = Example("README.md#1", "README.md", 2, 2, "value = removed()\n", "Produce value 3 without printing")
    before = Execution("failed", 21, stderr="NameError: removed", oracle="configured_behavior_checks",
                       failure_kind="example_exception")
    spec = {"checks": "assert value == 3, 'PRIVATE_CHECK_SENTINEL'", "expected_stdout": ""}
    context = {"legacy": {"sdk.py:1-2 (body excerpt)": "def replacement():\n    return 3\n"},
               "v2": {"sdk.py:1-2": "def replacement():\n    return 3\n"}}

    def plan(self):
        return {"model": "test-model", "timeout_seconds": 10, "calls_per_failure_max": 3,
                "generation_options": {"temperature": 0.2, "num_predict": 1024, "num_ctx": 8192},
                "design": study_design("development")}

    def evaluate(self, arm, runner, responses=None):
        requests = []
        responses = iter(responses or ["value = 3\n"] * 3)

        def open_response(request, **kwargs):
            requests.append(json.loads(request.data))
            return response(next(responses))

        with patch("exampleproof.providers.urlopen", side_effect=open_response):
            outcome, attempts = study.evaluate_study_case(
                self.example, self.spec, {"unselected.py": "REFERENCE_ANSWER_SENTINEL"}, self.before,
                self.context, self.plan(), arm, 17, "http://127.0.0.1:11434", runner=runner)
        return outcome, attempts, requests

    def test_five_actual_first_payloads_form_declared_pairs(self):
        payloads = {}
        for arm in self.plan()["design"]["arms"]:
            outcome, attempts, requests = self.evaluate(arm, SequenceRunner(Execution("passed", 0)))
            self.assertEqual(outcome["success_attempt"], 1)
            self.assertEqual(len(attempts), 1)
            payloads[arm] = requests[0]
        self.assertEqual(payloads["legacy_source"], payloads["legacy_feedback"])
        self.assertEqual(payloads["source_v2"], payloads["generic_feedback_v2"])
        self.assertEqual(payloads["source_v2"], payloads["feedback_v2"])
        for arm, payload in payloads.items():
            legacy = arm.startswith("legacy_")
            prompt = json.loads(payload["prompt"])
            self.assertEqual(payload["system"], SYSTEM if legacy else SYSTEM_V2)
            self.assertEqual(prompt["sources"], self.context["legacy" if legacy else "v2"])
            self.assertEqual(payload["options"], {"seed": 17, **self.plan()["generation_options"]})
            self.assertNotIn("previous_attempts", prompt)
            self.assertNotIn("category", prompt["execution"])
            self.assertNotIn("PRIVATE_CHECK_SENTINEL", json.dumps(payload))
            self.assertNotIn("REFERENCE_ANSWER_SENTINEL", json.dumps(payload))

    def test_second_payload_routes_only_declared_history_and_categories(self):
        payloads = {}
        for arm in self.plan()["design"]["arms"]:
            failed = Execution("failed", 0, stdout="PRIVATE_STDOUT", stderr="PRIVATE_EXPECTED",
                               oracle="configured_behavior_checks", failure_kind="stdout_mismatch")
            outcome, attempts, requests = self.evaluate(arm, SequenceRunner(failed, Execution("passed", 0)))
            self.assertEqual(outcome["success_attempt"], 2)
            self.assertEqual([attempt.number for attempt in attempts], [1, 2])
            self.assertEqual([request["options"]["seed"] for request in requests], [17, 18])
            self.assertNotIn("PRIVATE", json.dumps(requests))
            payloads[arm] = requests[1]
            prompt = json.loads(requests[1]["prompt"])
            if arm in {"legacy_source", "source_v2"}:
                self.assertNotIn("previous_attempts", prompt)
                neutral_first, neutral_second = deepcopy(requests[0]), deepcopy(requests[1])
                neutral_first["options"].pop("seed")
                neutral_second["options"].pop("seed")
                self.assertEqual(neutral_first, neutral_second)
            else:
                self.assertEqual(len(prompt["previous_attempts"]), 1)
                feedback = prompt["previous_attempts"][0]["execution"]
                self.assertEqual(feedback["error"], WITHHELD_CHECK_ERROR)
                if arm == "feedback_v2":
                    self.assertEqual(feedback["category"], "stdout_mismatch")
                else:
                    self.assertNotIn("category", feedback)
        generic, categorized = deepcopy(payloads["generic_feedback_v2"]), deepcopy(payloads["feedback_v2"])
        prompt = json.loads(categorized["prompt"])
        del prompt["previous_attempts"][0]["execution"]["category"]
        del prompt["previous_attempts"][0]["execution"]["guidance"]
        categorized["prompt"] = json.dumps(prompt, ensure_ascii=False)
        self.assertEqual(generic, categorized)

    def test_declines_and_structural_rejections_consume_same_budget(self):
        for arm in self.plan()["design"]["arms"]:
            runner = SequenceRunner()
            outcome, attempts, requests = self.evaluate(arm, runner, ["", "if False:\n    value = 3\n", ""])
            self.assertEqual(outcome["status"], "not_repaired")
            self.assertEqual([a.status for a in attempts], ["declined", "rejected", "declined"])
            self.assertEqual([request["options"]["seed"] for request in requests], [17, 18, 19])
            self.assertEqual(runner.calls, [])

    def test_malformed_generation_is_retained_then_feedback_can_continue(self):
        for arm in ("legacy_feedback", "generic_feedback_v2", "feedback_v2"):
            with patch("exampleproof.providers.urlopen", side_effect=[response(response="{unfinished"), response()]):
                outcome, attempts = study.evaluate_study_case(
                    self.example, self.spec, {}, self.before, self.context, self.plan(), arm, 17,
                    "http://127.0.0.1:11434", runner=SequenceRunner(Execution("passed", 0)))
            self.assertEqual(outcome["success_attempt"], 2)
            self.assertEqual([a.status for a in attempts], ["candidate_format_error", "verified_repair"])
            second = json.loads(attempts[1].proposal.inference_evidence.request["prompt"])
            prior = second["previous_attempts"][0]
            self.assertIsNone(prior["candidate"])
            self.assertIsNone(prior["execution"])
            self.assertEqual(prior["status"], "candidate_format_error")

    def test_infrastructure_error_stops_each_arm_without_success_claim(self):
        for arm in self.plan()["design"]["arms"]:
            with patch("exampleproof.providers.urlopen", side_effect=TimeoutError("offline")) as opened:
                outcome, attempts = study.evaluate_study_case(
                    self.example, self.spec, {}, self.before, self.context, self.plan(), arm, 17,
                    "http://127.0.0.1:11434", runner=SequenceRunner())
            self.assertEqual(outcome["status"], "incomplete")
            self.assertEqual(len(attempts), 1)
            self.assertEqual(opened.call_count, 1)

    def test_split_validation_rejects_seen_or_mislabeled_holdout_before_model_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'fixture'
            root.mkdir()
            valid = {'split': 'holdout_v2', 'selection': {'held_out_from_method_optimization': True},
                     'provenance': {'held_out': True, 'live_model_evaluation': False}}
            study.write_json(root / 'metadata.json', valid)
            validate_project_splits([root], study_design('holdout'))
            changes = [
                {'split': 'development_v2'},
                {'selection': {'held_out_from_method_optimization': False}},
                {'provenance': {'held_out': False}},
                {'provenance': {'previous_cases_and_live_results_seen': True}},
                {'provenance': {'live_model_evaluation': True}},
            ]
            for index, fields in enumerate(changes):
                study.write_json(root / 'metadata.json', {**valid, **fields})
                with self.subTest(fields=fields), patch('exampleproof.study.local_metadata') as metadata, \
                        self.assertRaises(ValueError):
                    study.freeze_study([root], root.parent / f'rejected-{index}', design=study_design('holdout'))
                metadata.assert_not_called()
                self.assertFalse((root.parent / f'rejected-{index}').exists())
            study.write_json(root / 'metadata.json', {'split': 'development_v2'})
            validate_project_splits([root], study_design('development'))
            with self.assertRaises(ValueError):
                validate_project_splits([root], {'split': 'ambiguous'})

    def test_method_lock_refuses_missing_stale_or_development_lock(self):
        script = load_script()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            lock_path = base / "lock.json"
            with patch.object(script, "freeze_study") as freeze:
                for argv in (["freeze", str(base / 'project'), '--output', str(base / 'out'), '--split', 'holdout'],
                             ["freeze", str(base / 'project'), '--output', str(base / 'out'), '--split', 'development', '--method-lock', str(lock_path)]):
                    with self.subTest(argv=argv), patch('sys.argv', ['semantic-study', *argv]), self.assertRaises(ValueError):
                        script.main()
                freeze.assert_not_called()
            with patch('sys.argv', ['semantic-study', 'lock-method', str(lock_path)]), redirect_stdout(io.StringIO()):
                self.assertEqual(script.main(), 0)
            with patch('sys.argv', ['semantic-study', 'lock-method', str(lock_path)]), self.assertRaises(ValueError):
                script.main()
            with patch.object(script, 'implementation_hashes', return_value={'changed.py': 'changed'}), \
                    patch.object(script, 'freeze_study') as freeze, \
                    patch('sys.argv', ['semantic-study', 'freeze', str(base / 'project'), '--output', str(base / 'out'), '--split', 'holdout', '--method-lock', str(lock_path)]), \
                    self.assertRaisesRegex(ValueError, 'changed'):
                script.main()
            freeze.assert_not_called()

    def test_modified_method_lock_fails_its_seal_before_freeze(self):
        script = load_script()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            lock_path = base / 'lock.json'
            with patch('sys.argv', ['semantic-study', 'lock-method', str(lock_path)]), redirect_stdout(io.StringIO()):
                script.main()
            locked = json.loads(lock_path.read_text())
            locked['locked_at'] = 'rewritten timestamp'
            study.write_json(lock_path, locked)
            with patch.object(script, 'freeze_study') as freeze, \
                    patch('sys.argv', ['semantic-study', 'freeze', str(base / 'project'), '--output', str(base / 'out'), '--split', 'holdout', '--method-lock', str(lock_path)]), \
                    self.assertRaisesRegex(ValueError, 'seal'):
                script.main()
            freeze.assert_not_called()

    def test_valid_lock_is_embedded_in_frozen_design_before_any_live_calls(self):
        script = load_script()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            lock_path = base / 'lock.json'
            with patch('sys.argv', ['semantic-study', 'lock-method', str(lock_path)]), redirect_stdout(io.StringIO()):
                script.main()
            with patch.object(script, 'freeze_study', return_value={'status': 'frozen_before_live_inference', 'schedule': []}) as freeze, \
                    patch('sys.argv', ['semantic-study', 'freeze', str(base / 'project'), '--output', str(base / 'out'), '--split', 'holdout', '--method-lock', str(lock_path)]), redirect_stdout(io.StringIO()):
                self.assertEqual(script.main(), 0)
            design = freeze.call_args.kwargs['design']
            self.assertEqual(design['split'], 'holdout')
            self.assertEqual(design['method_lock']['sha256'], study.digest(lock_path))
            self.assertEqual(design['method_lock']['implementation_sha256'], study.implementation_hashes())


@unittest.skipUnless(os.environ.get('EXAMPLEPROOF_SANDBOX_TESTS') == '1', 'Set EXAMPLEPROOF_SANDBOX_TESTS=1')
class SemanticStudySandboxTests(unittest.TestCase):
    metadata = {'model': {'digest': 'test-pinned-model'}, 'server': {'version': 'test'}}

    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        project = base / 'self_authored_fixture'
        project.mkdir()
        (project / 'README.md').write_text('# Fix removed API\n\nProduce value 3 without printing.\n```python\nfrom sdk import removed\nvalue = removed()\n```\n\n# Healthy control\n\nKeep value 3 without printing.\n```python\nfrom sdk import replacement\nvalue = replacement()\n```\n')
        (project / 'sdk.py').write_text('def replacement():\n    """Produce the supported value."""\n    return 3\n')
        study.write_json(project / 'exampleproof.json', {'documents': ['README.md'], 'source_files': ['sdk.py'], 'timeout_seconds': 5,
                                                       'examples': {f'README.md#{i}': {'checks': "assert value == 3, 'PRIVATE_CHECK_SENTINEL'", 'expected_stdout': ''} for i in (1, 2)}})
        study.write_json(project / 'metadata.json', {'schema_version': 1, 'suite_id': 'self-authored-semantic-test', 'split': 'development_v2',
                                                   'provenance': {'held_out': False, 'previous_cases_and_live_results_seen': True},
                                                   'cases': [{'id': 'README.md#1', 'expected_before': 'failed'}, {'id': 'README.md#2', 'expected_before': 'checked'}]})
        study.write_json(project / 'provenance.json', {'classification': 'self_authored_test_fixture'})
        return base, project

    def freeze(self, project, output):
        with patch('exampleproof.study.local_metadata', return_value=self.metadata):
            return study.freeze_study([project], output, 'test-model', design=study_design('development'))

    def test_full_five_arm_lifecycle_keeps_pairs_costs_checks_patches_and_healthy_controls(self):
        base, project = self.fixture()
        original = study.inventory(project)
        output = base / 'experiment'
        plan = self.freeze(project, output)
        requests = []

        def respond(request, **kwargs):
            payload = json.loads(request.data)
            requests.append(payload)
            # Each arm's first candidate computes the right value but prints an
            # extra line. Its second candidate repairs this output behavior.
            code = 'from sdk import replacement\nvalue = replacement()\n'
            if payload['options']['seed'] == 17:
                code += 'print(value)\n'
            return response(code)

        with patch('exampleproof.study.local_metadata', return_value=self.metadata), \
                patch('exampleproof.providers.urlopen', side_effect=respond), redirect_stdout(io.StringIO()):
            summary, exit_code = study.run_study(output)
        self.assertEqual(exit_code, 0)
        self.assertTrue(summary['complete'])
        self.assertEqual(study.inventory(project), original)
        self.assertEqual(len(requests), 10)
        self.assertNotIn('PRIVATE_CHECK_SENTINEL', json.dumps(requests))
        first_by_arm = {}
        for cell in plan['schedule']:
            arm = cell['arm']
            group = summary['groups'][arm]
            self.assertEqual((group['case_runs'], group['first_try_passed'], group['budget_passed']), (1, 0, 1))
            self.assertEqual((group['healthy_case_runs'], group['healthy_preserved']), (1, 1))
            self.assertEqual((group['requests'], group['input_tokens'], group['output_tokens']), (2, 200, 40))
            location = output / 'runs' / '17' / arm / project.name
            inference = json.loads((location / 'inference.json').read_text())
            failed_case = inference['cases'][0]
            self.assertEqual(failed_case['attempts'][0]['after']['failure_kind'], 'stdout_mismatch')
            self.assertEqual(failed_case['success_attempt'], 2)
            self.assertEqual(inference['cases'][1]['attempts'], [])
            first_by_arm[arm] = failed_case['attempts'][0]['proposal']['inference_evidence']['request']
            replay = json.loads((location / 'patch_validation/benchmark.json').read_text())
            self.assertEqual(replay['mode'], 'recorded_candidates')
            self.assertEqual(replay['patch_application'], 'passed')
            self.assertEqual(replay['repair']['inference_requests'], 0)
            self.assertTrue(replay['metrics']['all_passed'])
            if arm == 'feedback_v2':
                payload = failed_case['attempts'][1]['proposal']['inference_evidence']['request']
                self.assertEqual(json.loads(payload['prompt'])['previous_attempts'][0]['execution']['category'], 'stdout_mismatch')
        self.assertEqual(first_by_arm['legacy_source'], first_by_arm['legacy_feedback'])
        self.assertEqual(first_by_arm['source_v2'], first_by_arm['generic_feedback_v2'])
        self.assertEqual(first_by_arm['source_v2'], first_by_arm['feedback_v2'])
        self.assertEqual(json.loads((output / 'finished.json').read_text())['status'], 'complete')
        with self.assertRaisesRegex(ValueError, 'already exist'):
            study.run_study(output)

    def test_context_and_private_check_tampering_blocks_before_model_request(self):
        for relative in ('contexts/self_authored_fixture.json', 'inputs/self_authored_fixture/exampleproof.json'):
            base, project = self.fixture()
            output = base / 'experiment'
            self.freeze(project, output)
            with (output / relative).open('a') as target:
                target.write('\n ')
            with patch('exampleproof.providers.urlopen') as opened, self.assertRaises(ValueError):
                study.run_study(output)
            opened.assert_not_called()
            self.assertFalse((output / 'started.json').exists())


if __name__ == '__main__':
    unittest.main()
