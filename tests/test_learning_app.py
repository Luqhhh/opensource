"""Synthetic functional/security checks, not reader or live-model evaluation."""
from dataclasses import dataclass
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile
from unittest.mock import patch

from exampleproof.learn_server import LearningApp, Handler, ThreadingHTTPServer, unpack_upload
from exampleproof.learning import local_guide, model_guide, model_payload
from exampleproof.model_api import JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.tutorial import prepare_project


def archive(files):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as z:
        for name, text in files.items():
            z.writestr(name, text)
    return result.getvalue()


FILES = {'README.md': '# Example\n\nA small synthetic project for functional tests only.\n\n## Install\n\npip install example\n\n## Usage\n\n```python\nfrom example import run\nrun()\n```\n',
         'example.py': 'raise RuntimeError("Project code must never run")\ndef run():\n    return 1\n',
         'pyproject.toml': '[project]\nrequires-python = ">=3.10"\n'}


def wait_ready(app, identifier):
    for _ in range(150):
        record = app.read(identifier)
        if record['status'] not in {'importing', 'analyzing'}:
            return record
        time.sleep(.02)
    raise AssertionError('Background work did not finish')


class FakeClient:
    evidence_kind = 'synthetic_test'
    provider = 'ollama'
    model = 'fixture'
    calls = 0

    def complete(self, system, payload):
        self.calls += 1
        eid = payload['evidence'][0]['id']
        value = {'overview': '合成响应，用于测试。', 'overview_evidence_ids': [eid],
                 'steps': [{'title': '查看原文', 'action': '阅读引用', 'checkpoint': '记录理解', 'evidence_ids': [eid]} for _ in range(3)],
                 'prerequisites': [], 'findings': []}
        return JSONReply(value, InferenceEvidence({}, 'synthetic', 1, duration_seconds=.01), 11, 22)


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_upload_flat_and_wrapped_never_executes(self):
        for wrapper in ('', 'project/'):
            target = self.root / ('wrapped' if wrapper else 'flat')
            target.mkdir()
            meta = unpack_upload(archive({wrapper+k: v for k, v in FILES.items()}), target)
            self.assertEqual(meta['copied_files'], 3)
            self.assertEqual((target/'example.py').read_text(), FILES['example.py'])
            snapshot = prepare_project(target, {'kind': 'test'})
            guide = local_guide(snapshot, 'Example', '学习用法', 'beginner')
            self.assertFalse(guide['executed_project_code'])
            self.assertGreaterEqual(len(guide['steps']), 3)

    def test_upload_rejects_all_paths_before_writing(self):
        for name in ('../escape.py', '/tmp/escape.py', 'C:/escape.py', 'project/../../escape.py', 'a\\b.py'):
            target = self.root / str(abs(hash(name)))
            target.mkdir()
            with self.assertRaises(ValueError):
                unpack_upload(archive({'README.md': 'safe', name: 'bad'}), target)
            self.assertEqual(list(target.rglob('*')), [])

    def test_upload_omits_sensitive_and_dependencies(self):
        unpack_upload(archive(FILES | {'.env': 'secret', 'api_token.txt': 'secret', 'node_modules/x.js': 'bad', 'bin.dat': b'\0', 'Dockerfile': 'FROM python:3.10'}), self.root)
        self.assertEqual({p.name for p in self.root.iterdir()}, set(FILES) | {'Dockerfile'})

    def test_symlink_is_not_materialized(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as z:
            z.writestr('project/README.md', 'safe')
            link = zipfile.ZipInfo('project/link.py')
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, '/etc/passwd')
        unpack_upload(raw.getvalue(), self.root)
        self.assertFalse((self.root/'link.py').exists())

    def test_model_cannot_cite_unseen_sources(self):
        unpack_upload(archive(FILES), self.root)
        snapshot = prepare_project(self.root, {'kind': 'test'})
        payload = model_payload(snapshot, 'Example', '学习用法', 'beginner')
        reply = FakeClient().complete('', payload)
        reply.value['steps'][0]['evidence_ids'] = ['not-provided']
        with self.assertRaises(ValueError):
            model_guide(snapshot, local_guide(snapshot, 'E', '学习', 'beginner'), payload, reply)

    def test_missing_claim_gets_countersearch(self):
        unpack_upload(archive(FILES), self.root)
        snapshot = prepare_project(self.root, {'kind': 'test'})
        payload = model_payload(snapshot, 'E', '学习', 'beginner')
        reply = FakeClient().complete('', payload)
        reply.value['findings'] = [{'title': '缺少 run 说明', 'category': 'explanation', 'impact': '可能难以使用', 'suggestion': '补充 run 解释', 'evidence_ids': [payload['evidence'][0]['id']]}]
        guide = model_guide(snapshot, local_guide(snapshot, 'E', '学习', 'beginner'), payload, reply)
        self.assertFalse(guide['findings'][0]['source_search']['absence_established'])
        self.assertEqual(guide['findings'][0]['status'], 'needs_confirmation')

    def test_multiline_secret_redacted_before_chunking(self):
        text = '# Example\n' + '\n'.join(['text']*75) + '\n-----BEGIN PRIVATE KEY-----\n' + '\n'.join(['VERY_PRIVATE']*20) + '\n-----END PRIVATE KEY-----\n'
        unpack_upload(archive({'README.md': text}), self.root)
        payload = model_payload(prepare_project(self.root, {'kind': 'test'}), 'E', '学习', 'beginner')
        self.assertNotIn('VERY_PRIVATE', json.dumps(payload))

    def test_progress_persists_and_ai_requires_matching_consent(self):
        client = FakeClient()
        app = LearningApp(self.root/'data', 'ollama', 'fixture', lambda: client)
        try:
            created = app.create(name='Example', goal='学习调用', level='beginner', upload=archive(FILES))
            record = wait_ready(app, created['id'])
            self.assertEqual(record['status'], 'ready')
            self.assertEqual(client.calls, 0)
            with self.assertRaises(ValueError):
                app.analyze(record['id'], 'wrong')
            self.assertEqual(client.calls, 0)
            app.progress(record['id'], ['step-1'])
            self.assertEqual(app.read(record['id'])['completed_steps'], ['step-1'])
            app.analyze(record['id'], record['ai_preview']['approval'])
            final = wait_ready(app, record['id'])
            self.assertEqual(final['guide']['mode'], 'ai')
            self.assertEqual(final['guide']['usage']['input_tokens'], 11)
            self.assertEqual(final['completed_steps'], [])
            with self.assertRaises(ValueError):
                app.analyze(record['id'], record['ai_preview']['approval'])
            self.assertEqual(client.calls, 1)
        finally:
            app.pool.shutdown()

    def test_failed_model_preserves_local_guide(self):
        client = FakeClient()
        client.complete = lambda *args: (_ for _ in ()).throw(ValueError('synthetic failure'))
        app = LearningApp(self.root/'data', 'ollama', 'fixture', lambda: client)
        try:
            r = wait_ready(app, app.create(name='Example', goal='学习', level='beginner', upload=archive(FILES))['id'])
            app.analyze(r['id'], r['ai_preview']['approval'])
            failed = wait_ready(app, r['id'])
            self.assertEqual(failed['guide']['mode'], 'local')
            self.assertIn('synthetic failure', failed['error'])
            self.assertTrue(list(app.folder(r['id']).glob('failure-*.json')))
        finally:
            app.pool.shutdown()

    def test_http_host_csrf_upload_source_and_export(self):
        app = LearningApp(self.root/'data', 'none')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.app = app
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url+'/api/config') as response:
                self.assertFalse(json.load(response)['ai_available'])
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url+'/api/projects', data=b'{}', method='POST'))
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError):
                urlopen(Request(url+'/api/config', headers={'Host': 'evil.test'}))
            request = Request(url+'/api/projects/upload?name=Example&goal=learn&level=beginner', data=archive(FILES), headers={'X-ExampleProof-Token': app.csrf}, method='POST')
            with urlopen(request) as response:
                r = wait_ready(app, json.load(response)['id'])
            with urlopen(url+f'/api/projects/{r["id"]}/source?path=README.md') as response:
                self.assertIn('synthetic', json.load(response)['text'])
            with self.assertRaises(HTTPError):
                urlopen(url+f'/api/projects/{r["id"]}/source?path=../../etc/passwd')
            with urlopen(url+f'/api/projects/{r["id"]}/export') as response:
                self.assertIn('入门指南', response.read().decode())
        finally:
            server.shutdown()
            server.server_close()
            app.pool.shutdown()


if __name__ == '__main__':
    unittest.main()
