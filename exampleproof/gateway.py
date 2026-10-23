"""Bounded inference relay. Bind to loopback behind an HTTPS reverse proxy.

Quota reservations persist before upstream calls, including failures and restarts.
Only usage counters are stored; prompts, responses and API keys are not persisted.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from .gateway_client import MAX_GATEWAY_BODY, MAX_GATEWAY_REPLY
from .model_api import JSONClient
from .tutorial_privacy import _redact_value


class GatewayError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class Gateway:
    def __init__(self, data, *, model='deepseek-flash', public=False, token=None,
                 daily_limit=50, hourly_limit=10, total_limit=500, concurrency=2,
                 client_factory=None, clock=time.time):
        for value in (daily_limit, hourly_limit, total_limit, concurrency):
            if type(value) is not int or value < 1:
                raise ValueError('调用上限和并发数必须是正整数。')
        if concurrency > 8:
            raise ValueError('小规模共享服务最多允许 8 个并发调用。')
        token = token if token is not None else os.environ.get('EXAMPLEPROOF_GATEWAY_TOKEN', '')
        if not public and (not isinstance(token, str) or len(token) < 24
                           or len(token) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise ValueError('请在服务端设置至少 24 字符的 EXAMPLEPROOF_GATEWAY_TOKEN，或显式选择 --public。')
        self.public, self.model, self.clock = public, model, clock
        self.token_hash = hashlib.sha256(token.encode()).digest() if token else None
        self.factory = client_factory or (lambda: JSONClient('deepseek', model, timeout=60))
        # Fail before accepting traffic if the upstream credential/model is invalid.
        self.factory()
        self.daily_limit, self.hourly_limit, self.total_limit = daily_limit, hourly_limit, total_limit
        self.slots = threading.BoundedSemaphore(concurrency)
        directory = Path(data).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = directory / 'gateway-usage.sqlite3'
        if self.database.is_symlink():
            raise ValueError('用量数据库不能是符号链接。')
        fd = os.open(self.database, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.database, 0o600)
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE IF NOT EXISTS usage (bucket TEXT PRIMARY KEY, requests INTEGER NOT NULL)')

    def authenticate(self, authorization):
        if self.public:
            return
        value = authorization[7:] if authorization.startswith('Bearer ') else ''
        if not secrets.compare_digest(hashlib.sha256(value.encode()).digest(), self.token_hash):
            raise GatewayError(401, '邀请码无效。')

    def reserve(self):
        now = int(self.clock())
        buckets = [('total', self.total_limit), ('day:'+str(now//86400), self.daily_limit),
                   ('hour:'+str(now//3600), self.hourly_limit)]
        with sqlite3.connect(self.database, timeout=5) as db:
            db.execute('BEGIN IMMEDIATE')
            for key, limit in buckets:
                row = db.execute('SELECT requests FROM usage WHERE bucket=?', (key,)).fetchone()
                if row and row[0] >= limit:
                    raise GatewayError(429, '共享调用额度已用完。')
            for key, _ in buckets:
                db.execute('INSERT INTO usage VALUES (?,1) ON CONFLICT(bucket) DO UPDATE SET requests=requests+1', (key,))
            # Only current buckets and lifetime consumption are needed.
            db.execute('DELETE FROM usage WHERE bucket NOT IN (?,?,?)', tuple(key for key, _ in buckets))

    def complete(self, body):
        if (not isinstance(body, dict) or set(body) != {'model', 'system', 'evidence'}
                or body['model'] != self.model or not isinstance(body['system'], str)
                or not 1 <= len(body['system']) <= 16000 or not isinstance(body['evidence'], dict)):
            raise GatewayError(400, '请求格式或模型名称无效。')
        if not self.slots.acquire(blocking=False):
            raise GatewayError(503, '共享服务正忙。')
        try:
            self.reserve()
            # Model, destination and maximum output tokens are controlled on the server.
            client = self.factory()
            reply = client.complete(body['system'], body['evidence'])
            result = {'model': self.model, 'value': reply.value,
                      'input_tokens': reply.input_tokens, 'output_tokens': reply.output_tokens}
            result = _redact_value(result, (client._key,) if getattr(client, '_key', None) else ())
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(encoded) > MAX_GATEWAY_REPLY:
                raise GatewayError(502, '模型返回内容超出限制。')
            return result
        finally:
            self.slots.release()


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = 'ExampleProofGateway'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Do not log URLs, Authorization, request bodies or upstream error details.
        pass

    def respond(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != '/health':
            return self.respond(404, {'error':'未找到接口。'})
        return self.respond(200, {'status':'ok','model':self.server.gateway.model,
                                  'access':'public' if self.server.gateway.public else 'invite'})

    def do_POST(self):
        try:
            if self.path != '/v1/complete':
                raise GatewayError(404, '未找到接口。')
            if self.headers.get('Origin'):
                raise GatewayError(403, '请通过本机工作台后端调用共享服务。')
            auth = self.headers.get_all('Authorization', [])
            if len(auth) > 1:
                raise GatewayError(401, '邀请码无效。')
            self.server.gateway.authenticate(auth[0] if auth else '')
            lengths = self.headers.get_all('Content-Length', [])
            if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isdigit():
                raise GatewayError(400, '请求需要明确且唯一的内容长度。')
            length = int(lengths[0])
            if not 0 < length <= MAX_GATEWAY_BODY:
                raise GatewayError(413, '请求内容过大或为空。')
            if self.headers.get_content_type() != 'application/json':
                raise GatewayError(415, '请求必须是 JSON。')
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise GatewayError(400, '请求内容不完整。')
            try:
                body = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid number')))
            except (ValueError, RecursionError):
                raise GatewayError(400, '无效 JSON。') from None
            return self.respond(200, self.server.gateway.complete(body))
        except GatewayError as exc:
            return self.respond(exc.status, {'error':str(exc)})
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            return self.respond(400, {'error':'无效 JSON。'})
        except Exception:
            # Fail closed. Upstream failures still consume the reserved allowance.
            return self.respond(503, {'error':'共享服务暂不可用，请稍后重试。'})


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, gateway):
        self.gateway = gateway
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(address, GatewayHandler)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()

    def handle_error(self, request, client_address):
        pass


def serve_gateway(data, *, port=8787, **options):
    gateway = Gateway(data, **options)
    with GatewayServer(('127.0.0.1', port), gateway) as server:
        print(f'共享代理：http://127.0.0.1:{server.server_port}；对外请配置 HTTPS 反向代理。', flush=True)
        print('公开限额模式。' if gateway.public else '邀请码模式。', flush=True)
        server.serve_forever()
