"""Synthetic import/AI lifecycle checks; no live model or reader evaluation."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from exampleproof.learn_server import Handler, LearningApp, ThreadingHTTPServer
from test_learning_app import FILES, FakeClient, archive, wait_ready


class AutoAILearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = FakeClient()
        self.app = LearningApp(self.root/'data', 'ollama', 'fixture', lambda: self.client)
        self.addCleanup(self.app.pool.shutdown)

    def create(self, **options):
        return self.app.create(name='Example', goal='学习调用', level='beginner',
                               upload=archive(FILES), **options)

    def test_import_choice_generates_once_without_analyze_or_browser(self):
        record = wait_ready(self.app, self.create(auto_ai=True)['id'])
        self.assertEqual(record['status'], 'ready')
        self.assertEqual(record['guide']['mode'], 'ai')
        self.assertEqual(record['guide_revision'], 2)
        self.assertEqual(record['ai_trigger'], 'import_choice')
        self.assertEqual(self.client.calls, 1)
        self.assertIsNone(record['error'])
        folder = self.app.folder(record['id'])
        for name, content in FILES.items():
            self.assertEqual((folder/'input'/name).read_text(), content)
        attempt = json.loads(next(folder.glob('attempt-*.json')).read_text())
        self.assertEqual(attempt['kind'], 'test_provider')
        for _ in range(3):
            self.app.public(self.app.read(record['id']))
            self.app.list()
            self.app.workspace.view(record['id'])
        with self.assertRaises(ValueError):
            self.app.analyze(record['id'], record['ai_preview']['approval'])
        self.assertEqual(self.client.calls, 1)

    def test_import_stays_busy_until_model_finishes(self):
        started, release = threading.Event(), threading.Event()
        original = self.client.complete

        def delayed(system, payload):
            started.set()
            if not release.wait(5):
                raise ValueError('synthetic timeout')
            return original(system, payload)

        self.client.complete = delayed
        record = self.create(auto_ai=True)
        try:
            self.assertTrue(started.wait(3))
            current = self.app.read(record['id'])
            self.assertEqual(current['status'], 'analyzing')
            self.assertEqual(self.app.list()[0]['status'], 'analyzing')
            with self.assertRaises(ValueError):
                self.app.analyze(record['id'], current['ai_preview']['approval'])
            with self.assertRaises(ValueError):
                self.app.progress(record['id'], ['step-1'])
        finally:
            release.set()
        self.assertEqual(wait_ready(self.app, record['id'])['guide']['mode'], 'ai')
        self.assertEqual(self.client.calls, 1)

    def test_opt_out_and_legacy_import_stay_local_after_reopen(self):
        for options in ({'auto_ai': False}, {}):
            record = wait_ready(self.app, self.create(**options)['id'])
            self.assertEqual(record['guide']['mode'], 'local')
            self.assertIn('ai_preview', record)
            self.assertFalse(record['auto_ai'])
        restarted = LearningApp(self.app.data, 'ollama', 'fixture', lambda: self.client)
        try:
            self.assertTrue(all(row['mode'] == 'local' for row in restarted.list()))
            self.assertEqual(self.client.calls, 0)
        finally:
            restarted.pool.shutdown()

    def test_no_model_configuration_preserves_local_route(self):
        self.app.provider = 'none'
        self.app.factory = Mock(side_effect=AssertionError('must not create model client'))
        record = wait_ready(self.app, self.create(auto_ai=True)['id'])
        self.assertEqual(record['status'], 'ready')
        self.assertEqual(record['guide']['mode'], 'local')
        self.assertFalse(record['auto_ai'])
        self.app.factory.assert_not_called()

    def test_failed_auto_generation_preserves_local_route_and_can_retry(self):
        original = self.client.complete
        self.client.complete = Mock(side_effect=ValueError('synthetic unavailable'))
        record = wait_ready(self.app, self.create(auto_ai=True)['id'])
        self.assertEqual(record['status'], 'ready')
        self.assertEqual(record['guide']['mode'], 'local')
        self.assertIn('synthetic unavailable', record['error'])
        self.assertEqual(record['guide_revision'], 1)
        self.assertTrue(list(self.app.folder(record['id']).glob('failure-*.json')))
        self.app.read(record['id'])
        self.app.list()
        self.client.complete.assert_called_once()
        self.client.complete = original
        self.app.analyze(record['id'], record['ai_preview']['approval'])
        retried = wait_ready(self.app, record['id'])
        self.assertEqual(retried['guide']['mode'], 'ai')
        self.assertEqual(retried['ai_trigger'], 'manual_request')
        self.assertIsNone(retried['error'])

    def test_client_setup_failure_does_not_fail_import(self):
        self.app.factory = Mock(side_effect=ValueError('synthetic missing key'))
        record = wait_ready(self.app, self.create(auto_ai=True)['id'])
        self.assertEqual(record['status'], 'ready')
        self.assertEqual(record['guide']['mode'], 'local')
        self.assertIn('synthetic missing key', record['error'])
        self.assertEqual(self.client.calls, 0)

    def test_cloud_auto_generation_retains_redaction_and_request_binding(self):
        self.app.provider = self.client.provider = 'deepseek'
        self.client.endpoint = 'https://api.deepseek.com'
        self.client._key = 'SYNTHETIC_PRIVATE_KEY'
        original = self.client.complete
        self.client.complete = Mock(side_effect=original)
        record = wait_ready(self.app, self.app.create(
            name='Example', goal='学习 SYNTHETIC_PRIVATE_KEY', level='beginner',
            upload=archive(FILES | {'README.md': FILES['README.md'] + '\ntoken="PROJECT_SECRET"\n'}),
            auto_ai=True)['id'])
        self.assertEqual(record['guide']['mode'], 'ai')
        self.client.complete.assert_called_once()
        sent = self.client.complete.call_args.args[1]
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY', json.dumps(sent))
        self.assertNotIn('PROJECT_SECRET', json.dumps(sent))
        manifest = json.loads((self.app.folder(record['id'])/record['review_file']).read_text())
        self.assertEqual(manifest['review']['payload'], sent)
        self.assertEqual(manifest['sha256'], record['ai_preview']['approval'])
        self.assertEqual(manifest['review']['binding']['snapshot_id'], record['snapshot_id'])

    def test_cloud_request_change_is_rejected_before_automatic_send(self):
        self.app.provider = self.client.provider = 'deepseek'
        self.client.endpoint = 'https://api.deepseek.com'
        original = self.app._preview

        def changed(record, snapshot):
            original(record, snapshot)
            record['payload']['learner']['goal'] = 'unapproved replacement'

        with patch.object(self.app, '_preview', side_effect=changed):
            record = wait_ready(self.app, self.create(auto_ai=True)['id'])
        self.assertEqual(record['guide']['mode'], 'local')
        self.assertIn('review changed', record['error'])
        self.assertEqual(self.client.calls, 0)

    def test_import_choice_requires_boolean(self):
        for invalid in ('false', 'true', None, 0, 1, [], {}):
            with self.assertRaises(ValueError):
                self.create(auto_ai=invalid)
        self.assertEqual(self.app.list(), [])

    def test_http_zip_and_github_honor_import_choice(self):
        source = self.root/'github-source'
        source.mkdir()
        for name, text in FILES.items():
            (source/name).write_text(text)

        @contextmanager
        def fake_download(*args, **kwargs):
            yield source, {'kind': 'synthetic_github'}

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.app = self.app
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'

        def request(route, body):
            return urlopen(Request(url+route, data=body, method='POST',
                                   headers={'X-ExampleProof-Token': self.app.csrf}))

        try:
            with patch('exampleproof.learn_server.project_input', fake_download):
                for kind in ('github', 'zip'):
                    for selected in (True, False):
                        with self.subTest(kind=kind, auto_ai=selected):
                            before = self.client.calls
                            if kind == 'github':
                                route = '/api/projects'
                                body = json.dumps({'repository': 'owner/example', 'goal': 'learn',
                                                   'level': 'beginner', 'auto_ai': selected}).encode()
                            else:
                                route = '/api/projects/upload?name=Example&goal=learn&level=beginner&auto_ai=' + str(selected).lower()
                                body = archive(FILES)
                            with request(route, body) as response:
                                self.assertEqual(response.status, 202)
                                identifier = json.load(response)['id']
                            record = wait_ready(self.app, identifier)
                            self.assertEqual(record['guide']['mode'], 'ai' if selected else 'local')
                            self.assertEqual(self.client.calls, before + int(selected))
                for query in ('auto_ai=yes', 'auto_ai=true&auto_ai=false'):
                    with self.assertRaises(HTTPError) as error:
                        request('/api/projects/upload?name=Example&goal=learn&'+query, archive(FILES))
                    self.assertEqual(error.exception.code, 400)
                with self.assertRaises(HTTPError) as error:
                    request('/api/projects', json.dumps({'repository': 'owner/example', 'goal': 'learn',
                                                        'level': 'beginner', 'auto_ai': 'false'}).encode())
                self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
        self.assertEqual(self.client.calls, 2)


if __name__ == '__main__':
    unittest.main()
