"""Assistant-authored synthetic gateway checks; never call a real model."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from exampleproof.gateway import Gateway, GatewayError, GatewayServer
from exampleproof.gateway_client import GatewayClient, MAX_GATEWAY_BODY, gateway_url
from exampleproof.learn_server import Handler, LearningApp
from exampleproof.model_api import JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.tutorial_privacy import review_payload

INVITE = 'synthetic-invite-token-for-gateway-tests'
UPSTREAM = 'synthetic-private-upstream-api-key'
BODY = {'model':'fixture-model', 'system':'Return JSON.', 'evidence':{'question':'synthetic question'}}


class SyntheticClient:
    _key = UPSTREAM

    def __init__(self):
        self.calls = 0
        self.fail = False

    def complete(self, system, payload):
        self.calls += 1
        if self.fail:
            raise ValueError('Do not expose '+UPSTREAM)
        return JSONReply({'answer':'synthetic answer', 'redaction_probe':UPSTREAM},
                         InferenceEvidence({}, 'synthetic', 60), 10, 12)


class GatewayHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = SyntheticClient()
        self.gateway = Gateway(self.temp.name, model='fixture-model', token=INVITE,
                               client_factory=lambda:self.client)
        self.server = GatewayServer(('127.0.0.1',0), self.gateway)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.endpoint = 'http://127.0.0.1:'+str(self.server.server_port)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, body=BODY, token=INVITE, path='/v1/complete', headers=None):
        data = json.dumps(body).encode()
        all_headers = {'Content-Type':'application/json', 'Authorization':'Bearer '+token}
        all_headers.update(headers or {})
        request = Request(self.endpoint+path, data=data, headers=all_headers)
        try:
            with build_opener(ProxyHandler({})).open(request,timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def test_authorized_client_uses_gateway_without_upstream_key(self):
        with patch.dict(os.environ, {}, clear=True):
            reply = GatewayClient('fixture-model', endpoint=self.endpoint, token=INVITE).complete('Return JSON.', {})
        self.assertEqual(self.client.calls,1)
        self.assertEqual(reply.value['answer'],'synthetic answer')
        self.assertEqual(reply.value['redaction_probe'],'[REDACTED]')
        self.assertNotIn(INVITE,json.dumps(reply.inference.request))
        self.assertNotIn(UPSTREAM,json.dumps(reply.inference.response))

    def test_missing_or_bad_invite_never_calls_upstream(self):
        for token in ('', 'wrong'):
            status, result = self.request(token=token)
            self.assertEqual(status,401)
            self.assertNotIn(token or UPSTREAM,json.dumps(result))
        self.assertEqual(self.client.calls,0)

    def test_browser_origin_and_wrong_model_are_rejected(self):
        self.assertEqual(self.request(headers={'Origin':'https://untrusted.invalid'})[0],403)
        self.assertEqual(self.request({**BODY,'model':'more-expensive-model'})[0],400)
        self.assertEqual(self.request({**BODY,'endpoint':'https://untrusted.invalid'})[0],400)
        self.assertEqual(self.client.calls,0)

    def test_oversize_and_unknown_route_never_call_upstream(self):
        self.assertEqual(self.request({**BODY,'evidence':{'text':'x'*MAX_GATEWAY_BODY}})[0],413)
        self.assertEqual(self.request(path='/v1/complete?key=synthetic')[0],404)
        self.assertEqual(self.client.calls,0)

    def test_upstream_error_is_generic_and_consumes_allowance(self):
        self.gateway.total_limit=1
        self.client.fail=True
        status, result=self.request()
        self.assertEqual(status,503)
        self.assertNotIn(UPSTREAM,json.dumps(result))
        self.assertEqual(self.request()[0],429)
        self.assertEqual(self.client.calls,1)

    def test_full_concurrency_rejects_without_reserving(self):
        self.gateway.slots.acquire();self.gateway.slots.acquire()
        try:
            self.assertEqual(self.request()[0],503)
        finally:
            self.gateway.slots.release();self.gateway.slots.release()
        self.gateway.total_limit=1
        self.assertEqual(self.request()[0],200)
        self.assertEqual(self.request()[0],429)

    def test_public_access_requires_explicit_mode(self):
        with self.assertRaises(ValueError):
            Gateway(self.temp.name,token='',client_factory=lambda:self.client)
        self.gateway.public=True
        self.assertEqual(self.request(token='')[0],200)

    def test_client_does_not_return_remote_error_body(self):
        with self.assertRaisesRegex(ValueError,'邀请码'):
            GatewayClient('fixture-model',endpoint=self.endpoint,token='wrong').complete('Return JSON.',{})

    def test_review_binds_gateway_destination_and_redacts_invite(self):
        client=GatewayClient('fixture-model',endpoint=self.endpoint,token=INVITE)
        path=Path(self.temp.name)/'review.json'
        payload={'text':'secret '+INVITE}
        with self.assertRaises(ValueError):
            review_payload(client,'Return JSON.',payload,{'synthetic':True},path)
        record=json.loads(path.read_text())
        self.assertNotIn(INVITE,path.read_text())
        self.assertEqual(record['review']['model']['endpoint'],self.endpoint)
        reviewed=review_payload(client,'Return JSON.',payload,{'synthetic':True},path,record['sha256'])
        client.endpoint='https://different.invalid'
        with self.assertRaisesRegex(ValueError,'reviewed'):
            reviewed.complete('Return JSON.',payload)
        self.assertEqual(self.client.calls,0)

    def test_learning_route_and_confirmed_question_cross_real_local_gateway(self):
        from test_learning_app import FILES, archive, wait_ready
        from test_learning_workspace import Tutor
        self.client=Tutor()
        with patch.dict(os.environ, {'EXAMPLEPROOF_GATEWAY_TOKEN':INVITE}, clear=True), \
                patch.object(GatewayClient,'evidence_kind','synthetic_gateway'):
            app=LearningApp(Path(self.temp.name)/'learning', 'gateway', 'fixture-model', gateway_endpoint=self.endpoint)
            try:
                record=wait_ready(app,app.create(name='Synthetic gateway project',goal='理解输入与输出',
                    level='beginner',upload=archive(FILES),auto_ai=True)['id'])
                self.assertEqual(record['guide']['mode'],'ai',record.get('error'))
                self.assertEqual(self.client.calls,1)
                workspace=app.workspace.view(record['id'])
                request=app.workspace.prepare(record['id'],{'route_id':workspace['route_id'],
                    'step_key':workspace['tasks'][0]['key'],'intent':'ask','question':'这一步为什么这样做？'})
                self.assertEqual(request['provider'],'gateway')
                self.assertEqual(self.client.calls,1,'Preparing a question must not call the model')
                app.workspace.send(record['id'],request['id'],request['approval'])
                for _ in range(200):
                    result=app.workspace.status(record['id'],request['id'])
                    if result['status'] in {'ready','failed'}:break
                    time.sleep(.01)
                self.assertEqual(result['status'],'ready',result)
                self.assertEqual(self.client.calls,2)
                for file in app.folder(record['id']).glob('*.json'):
                    self.assertNotIn(INVITE,file.read_text())
                    self.assertNotIn(UPSTREAM,file.read_text())
                attempt=json.loads(next(app.folder(record['id']).glob('attempt-*.json')).read_text())
                self.assertEqual(attempt['kind'],'test_provider')
            finally:
                app.pool.shutdown()


class GatewayQuotaTests(unittest.TestCase):
    def test_atomic_limit_and_persistence_across_restarts(self):
        with tempfile.TemporaryDirectory() as temp:
            factory=lambda:SyntheticClient()
            gateway=Gateway(temp,token=INVITE,client_factory=factory,total_limit=3)
            def reserve(_):
                try:
                    gateway.reserve()
                    return True
                except GatewayError:
                    return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(reserve,range(24))),3)
            restarted=Gateway(temp,token=INVITE,client_factory=factory,total_limit=3)
            with self.assertRaises(GatewayError):
                restarted.reserve()
            self.assertEqual(gateway.database.stat().st_mode & 0o777,0o600)
            self.assertNotIn(INVITE.encode(),gateway.database.read_bytes())
            self.assertNotIn(UPSTREAM.encode(),gateway.database.read_bytes())

    def test_hourly_daily_and_lifetime_budgets(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=[0]
            gateway=Gateway(temp,token=INVITE,client_factory=SyntheticClient,clock=lambda:clock[0],
                            hourly_limit=1,daily_limit=2,total_limit=3)
            gateway.reserve()
            with self.assertRaises(GatewayError):gateway.reserve()
            clock[0]=3600;gateway.reserve()
            clock[0]=7200
            with self.assertRaises(GatewayError):gateway.reserve()
            clock[0]=86400;gateway.reserve()
            clock[0]=172800
            with self.assertRaises(GatewayError):gateway.reserve()

    def test_limits_cannot_be_disabled_accidentally(self):
        with tempfile.TemporaryDirectory() as temp:
            for field in ('daily_limit','hourly_limit','total_limit','concurrency'):
                for value in (0,-1,False):
                    with self.assertRaises(ValueError):
                        Gateway(temp,token=INVITE,client_factory=SyntheticClient,**{field:value})


class GatewayConfigurationTests(unittest.TestCase):
    def test_published_public_defaults_enable_clone_without_api_key(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True), \
                patch('exampleproof.shared_service.SERVICE_URL','https://shared.invalid'):
            app=LearningApp(temp)
            try:
                self.assertEqual(app.provider,'gateway')
                self.assertEqual(app.factory().endpoint,'https://shared.invalid')
                self.assertEqual(app.factory()._key,'')
            finally:
                app.pool.shutdown()

    def test_explicit_direct_provider_overrides_published_gateway(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'DEEPSEEK_API_KEY':UPSTREAM}, clear=True), \
                patch('exampleproof.shared_service.SERVICE_URL','https://shared.invalid'):
            app=LearningApp(temp,'deepseek')
            try:
                self.assertEqual(app.factory().provider,'deepseek')
                self.assertIsNone(app.gateway_endpoint)
            finally:
                app.pool.shutdown()

    def test_remote_url_requires_https_without_embedded_credentials(self):
        for url in ('http://example.com','https://user:secret@example.com','https://example.com?key=secret',
                    'https://example.com#token','ftp://example.com','https://example.com:0',''):
            with self.subTest(url=url),self.assertRaises(ValueError):gateway_url(url)
        self.assertEqual(gateway_url('https://example.com/relay/'),'https://example.com/relay')
        self.assertEqual(gateway_url('http://127.0.0.1:8787'),'http://127.0.0.1:8787')

    def test_learning_config_exposes_service_but_no_credentials(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'EXAMPLEPROOF_GATEWAY_URL':'https://shared.invalid',
                'EXAMPLEPROOF_GATEWAY_TOKEN':INVITE,'DEEPSEEK_API_KEY':UPSTREAM}):
            app=LearningApp(temp)
            self.addCleanup(app.pool.shutdown)
            self.assertEqual(app.provider,'gateway')
            self.assertIsInstance(app.factory(),GatewayClient)
            self.assertEqual(app.public({'error':INVITE+' '+UPSTREAM})['error'],'[REDACTED] [REDACTED]')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=app
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with build_opener(ProxyHandler({})).open('http://127.0.0.1:'+str(server.server_port)+'/api/config') as response:
                    config=json.load(response)
                self.assertEqual(config['gateway_url'],'https://shared.invalid')
                self.assertNotIn(INVITE,json.dumps(config));self.assertNotIn(UPSTREAM,json.dumps(config))
            finally:
                server.shutdown();server.server_close();thread.join()
