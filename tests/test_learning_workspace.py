"""Assistant-authored synthetic engineering checks, not independent learning evidence."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from test_learning_app import FILES, FakeClient, archive, wait_ready
from exampleproof.learn_server import LearningApp, Handler, ThreadingHTTPServer
from exampleproof.learning_tasks import outline
from exampleproof.learning_workspace import StudyConflict, StudyWorkspace


class Tutor(FakeClient):
    def complete(self, system, payload):
        if 'intent' not in payload:
            return super().complete(system, payload)
        reply = super().complete(system, payload)
        eid = payload['evidence'][0]['id']
        reply.value = {'answer': '合成反馈：请将输入与返回值对应起来。', 'evidence_ids': [eid],
                       'next_actions': [{'text': '查看引用中的函数调用。', 'evidence_ids': [eid]}],
                       'uncertainties': ['没有执行代码。']}
        return reply


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = Tutor()
        self.app = LearningApp(Path(self.temp.name)/'data', 'ollama', 'fixture', lambda: self.client)
        self.record = wait_ready(self.app, self.app.create(name='Synthetic', goal='理解输入与返回', level='beginner', upload=archive(FILES))['id'])
        self.ws = self.app.workspace
        self.view = self.ws.view(self.record['id'])
        self.step = self.view['tasks'][0]
        self.base = {'route_id': self.view['route_id'], 'step_key': self.step['key']}

    def tearDown(self):
        self.app.pool.shutdown()
        self.temp.cleanup()

    def change(self, **values):
        return self.ws.mutate(self.record['id'], self.base | values)

    def prepare(self, **values):
        return self.ws.prepare(self.record['id'], self.base | {'question': '这一步为什么这样做？', 'intent': 'ask'} | values)

    def finished(self, request):
        for _ in range(200):
            value = self.ws.status(self.record['id'], request['id'])
            if value['status'] in {'ready', 'failed'}:
                return value
            time.sleep(.01)
        self.fail('Tutor request did not finish')

    def test_tasks_have_grounded_location_prerequisites_expected_and_optional_exercises(self):
        for task in self.view['tasks']:
            self.assertTrue(task['where'])
            self.assertEqual(task['expected'], task['checkpoint'])
            self.assertEqual(len(task['actions']), 3)
            self.assertEqual(len(task['exercises']), 3)
        statements = [s for s in self.record['guide']['steps'] if s.get('original_code')]
        self.assertEqual([s['original_code'] for s in statements], ['from example import run', 'run()'])
        for step in statements:
            ref = step['evidence'][0]
            self.assertEqual('\n'.join(FILES[ref['path']].splitlines()[ref['start_line']-1:ref['end_line']]), step['original_code'])

    def test_get_does_not_write_legacy_record_or_study_state(self):
        folder = self.app.folder(self.record['id'])
        before = (folder/'record.json').read_bytes()
        self.ws.view(self.record['id'])
        self.assertEqual(before, (folder/'record.json').read_bytes())
        self.assertFalse((folder/'study.json').exists())

    def test_note_position_and_reopen_preserve_each_other(self):
        self.change(action='note', text='我的笔记', version=0)
        self.change(action='position', reader={'path':'README.md','start_line':3,'end_line':3,'scroll':142,'mode':'document'}, history=[])
        reopened = StudyWorkspace(self.app).view(self.record['id'])
        self.assertEqual(reopened['notes'][self.step['key']]['text'], '我的笔记')
        self.assertEqual(reopened['positions'][self.view['route_id']]['reader']['scroll'], 142)

    def test_concurrent_note_versions_cannot_silently_overwrite(self):
        self.change(action='note', text='first', version=0)
        with self.assertRaises(StudyConflict):
            self.change(action='note', text='stale', version=0)
        self.assertEqual(self.ws.view(self.record['id'])['notes'][self.step['key']]['text'], 'first')

    def test_stale_route_and_outside_source_are_rejected(self):
        with self.assertRaises(StudyConflict):
            self.ws.mutate(self.record['id'], self.base | {'route_id':'stale','action':'note','text':'x'})
        with self.assertRaises(ValueError):
            self.change(action='note', text='x', evidence=[{'path':'../../etc/passwd','start_line':1,'end_line':2}])

    def test_adjustment_is_reversible_and_not_completion(self):
        self.change(action='adjust', preference='hard')
        self.change(action='adjust', preference='split')
        self.change(action='subtask', completed=[0, 1])
        after = self.change(action='undo-adjust')
        self.assertEqual(after['adjustments'][self.view['route_id']][self.step['key']]['preference'], 'hard')
        self.assertEqual(self.app.read(self.record['id'])['completed_steps'], [])
        self.change(action='undo-adjust')
        self.assertNotIn(self.step['key'], self.ws.view(self.record['id'])['adjustments'][self.view['route_id']])

    def test_notes_discussions_and_completed_history_survive_regeneration(self):
        self.change(action='note', text='保留旧笔记', version=0)
        self.prepare(use_ai=False)
        self.app.progress(self.record['id'], [self.step['id']])
        self.app.analyze(self.record['id'], self.record['ai_preview']['approval'])
        current = wait_ready(self.app, self.record['id'])
        view = self.ws.view(current['id'])
        self.assertEqual(view['notes'][self.step['key']]['text'], '保留旧笔记')
        self.assertEqual(len(view['discussions']), 1)
        self.assertEqual(view['routes'][self.view['route_id']]['completed_steps'], [self.step['id']])
        self.assertEqual(current['completed_steps'], [])
        preview = self.app.regenerate_preview(current['id'])
        self.app.analyze(current['id'], preview['preview']['approval'], True)
        final = wait_ready(self.app, current['id'])
        self.assertEqual(len(self.ws.view(final['id'])['routes']), 3)
        # Even an identical synthetic route gets new note keys for a new version.
        self.assertNotEqual(view['tasks'][0]['key'], self.ws.view(final['id'])['tasks'][0]['key'])
        self.assertIn('保留旧笔记', self.ws.export(final['id']))

    def test_local_help_does_not_call_model_and_feedback_does_not_complete(self):
        r = self.prepare(use_ai=False, intent='feedback', exercise_id='explain', question='输入用于调用函数')
        self.assertEqual(r['status'], 'ready')
        self.assertEqual(self.client.calls, 0)
        self.assertEqual(r['response']['origin'], 'local_guidance')
        self.assertEqual(self.app.read(self.record['id'])['completed_steps'], [])
        self.assertEqual(self.ws.view(self.record['id'])['actual_run_checks'], [])

    def test_error_help_requires_actual_error_and_stores_fields(self):
        with self.assertRaises(ValueError):
            self.prepare(intent='error', use_ai=False)
        r = self.prepare(intent='error', error='ModuleNotFoundError: no module named example', command='python main.py', environment='Python 3.10 / Linux', use_ai=False)
        self.assertIn('解释器', r['response']['answer'])
        discussion = self.ws.view(self.record['id'])['discussions'][0]
        self.assertEqual(discussion['command'], 'python main.py')

    def test_preview_is_bound_to_exact_request_and_single_use(self):
        request = self.prepare()
        self.assertEqual(self.client.calls, 0)
        with self.assertRaises(ValueError):
            self.ws.send(self.record['id'], request['id'], 'wrong')
        self.ws.send(self.record['id'], request['id'], request['approval'])
        final = self.finished(request)
        self.assertEqual(final['status'], 'ready')
        with self.assertRaises(ValueError):
            self.ws.send(self.record['id'], request['id'], request['approval'])
        self.assertEqual(self.client.calls, 1)
        self.assertNotIn('payload', final)
        self.assertNotIn('attempt', final)

    def test_question_selection_and_recent_discussion_are_in_reviewed_context(self):
        self.prepare(question='上一次的问题', use_ai=False)
        request = self.prepare(question='解释返回值', selection={'path':'example.py','start_line':2,'end_line':3})
        payload = request['preview']
        self.assertEqual(payload['evidence'][0]['path'], 'example.py')
        self.assertIn('def run', payload['evidence'][0]['text'])
        self.assertEqual(payload['conversation'][0]['question'], '上一次的问题')
        self.assertEqual(payload['learner']['goal'], self.record['goal'])

    def test_secret_redaction_covers_question_error_and_whole_file(self):
        request = self.prepare(question='token="VERY_SECRET"', error='password="ERROR_SECRET"')
        rendered = json.dumps(request)
        self.assertNotIn('VERY_SECRET', rendered)
        self.assertNotIn('ERROR_SECRET', rendered)

    def test_unseen_model_citation_is_rejected_with_attempt_preserved(self):
        original = self.client.complete
        def invalid(system, payload):
            reply = original(system, payload)
            reply.value['evidence_ids'] = ['unseen']
            return reply
        self.client.complete = invalid
        r = self.prepare()
        self.ws.send(self.record['id'], r['id'], r['approval'])
        final = self.finished(r)
        self.assertEqual(final['status'], 'failed')
        self.assertEqual(self.ws.view(self.record['id'])['discussions'], [])
        stored = json.loads(self.ws.request_path(self.record['id'], r['id']).read_text())
        self.assertEqual(stored['attempt']['kind'], 'synthetic_provider')

    def test_provider_failure_is_not_faked_as_local_success(self):
        self.client.complete = lambda *a: (_ for _ in ()).throw(ValueError('synthetic failure'))
        r = self.prepare()
        self.ws.send(self.record['id'], r['id'], r['approval'])
        self.assertEqual(self.finished(r)['status'], 'failed')

    def test_restart_marks_interrupted_requests_and_preserves_notes(self):
        self.change(action='note', text='仍在', version=0)
        r = self.prepare()
        path = self.ws.request_path(self.record['id'], r['id'])
        stored = json.loads(path.read_text());stored['status'] = 'running';self.ws.write(path, stored)
        restarted = StudyWorkspace(self.app)
        self.assertEqual(restarted.status(self.record['id'], r['id'])['status'], 'failed')
        self.assertEqual(restarted.view(self.record['id'])['notes'][self.step['key']]['text'], '仍在')

    def test_mark_question_resolved_and_export_sources(self):
        r = self.prepare(use_ai=False)
        self.ws.mutate(self.record['id'], {'action':'resolve','id':r['discussion_id'],'resolved':True})
        export = self.ws.export(self.record['id'])
        self.assertIn('已解决', export)
        self.assertIn('README.md:', export)

    def test_outline_is_static_and_fences_do_not_become_headings(self):
        self.assertEqual([x['title'] for x in outline('a.md','# Real\n```python\n# fake\n```\n## Next')], ['Real','Next'])
        text = 'raise RuntimeError("never execute")\nclass Example:\n    def run(self):\n        return 1\n'
        self.assertEqual([x['title'] for x in outline('a.py',text)], ['Example','run'])

    def test_history_preserves_scroll_mode_and_current_index(self):
        self.change(action='position', history=[{'path':'README.md','start_line':1,'end_line':3,'scroll':155,'mode':'document'}], history_index=0)
        position = self.ws.view(self.record['id'])['positions'][self.view['route_id']]
        self.assertEqual(position['history'][0]['scroll'], 155)
        self.assertEqual(position['history'][0]['mode'], 'document')
        self.assertEqual(position['history_index'], 0)

    def test_example_call_has_static_implementation_link(self):
        usage = next(t for t in self.view['tasks'] if t.get('original_code') == 'run()')
        self.assertEqual(usage['implementations'][0]['evidence'][0]['path'], 'example.py')
        self.assertEqual(usage['implementations'][0]['evidence'][0]['start_line'], 2)

    def test_bad_next_action_schema_is_rejected(self):
        payload = self.prepare()['preview']
        with self.assertRaises(ValueError):
            self.ws.parse_answer({'answer':'a','evidence_ids':['e1'],'next_actions':['invalid'],'uncertainties':[]}, payload)

    def test_unavailable_sandbox_records_block_and_never_falls_back(self):
        with patch('exampleproof.runner.shutil.which', return_value=None), patch('exampleproof.runner.subprocess.Popen') as process:
            result = self.ws.run_check(self.record['id'], self.base | {'code':'raise RuntimeError("must not run on host")'})
        process.assert_not_called()
        self.assertEqual(result['execution']['status'], 'blocked')
        self.assertFalse(result['independent_behavior_check'])
        self.assertEqual(self.app.read(self.record['id'])['completed_steps'], [])
        self.assertEqual(len(self.ws.view(self.record['id'])['run_checks']), 1)

    @unittest.skipUnless(os.environ.get('EXAMPLEPROOF_SANDBOX_TESTS') == '1', 'opt-in actual isolated execution')
    def test_actual_run_stdout_failure_and_read_only_input(self):
        original = self.app.folder(self.record['id'])/'input/example.py'
        before = original.read_bytes()
        result = self.ws.run_check(self.record['id'], self.base | {'code':'print("actual sandbox")'})
        self.assertEqual(result['execution']['status'], 'passed')
        self.assertEqual(result['execution']['stdout'], 'actual sandbox\n')
        self.assertEqual(result['execution']['oracle'], 'none')
        failed = self.ws.run_check(self.record['id'], self.base | {'code':'open("/workspace/example.py", "w").write("changed")'})
        self.assertEqual(failed['execution']['status'], 'failed')
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(self.app.read(self.record['id'])['completed_steps'], [])

    def test_new_http_routes_reject_cross_origin_and_return_conflict(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.app = self.app
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/api/projects/{self.record["id"]}'
        def post(suffix, body, headers=None):
            return urlopen(Request(url+suffix, data=json.dumps(body).encode(), headers=headers or {'X-ExampleProof-Token':self.app.csrf}, method='POST'))
        try:
            with urlopen(url+'/workspace') as response:
                self.assertEqual(json.load(response)['route_id'], self.view['route_id'])
            for suffix in ('/workspace','/help-prepare','/help-send','/regenerate-preview','/run-check'):
                with self.assertRaises(HTTPError) as error:
                    post(suffix, {}, {'Origin':'https://evil.invalid','X-ExampleProof-Token':self.app.csrf})
                self.assertEqual(error.exception.code, 403)
            with post('/workspace', self.base | {'action':'note','text':'HTTP note','version':0}) as response:
                self.assertEqual(json.load(response)['notes'][self.step['key']]['text'], 'HTTP note')
            with self.assertRaises(HTTPError) as conflict:
                post('/workspace', self.base | {'action':'note','text':'stale','version':0})
            self.assertEqual(conflict.exception.code, 409)
            with post('/help-prepare', self.base | {'question':'HTTP question','use_ai':False}) as response:
                self.assertEqual(json.load(response)['response']['origin'], 'local_guidance')
            with urlopen(url+'/journal') as response:
                self.assertIn('HTTP note', response.read().decode())
            with urlopen(url+'/source?path=example.py') as response:
                self.assertEqual(json.load(response)['outline'][0]['title'], 'run')
        finally:
            server.shutdown();server.server_close()


if __name__ == '__main__':
    unittest.main()
