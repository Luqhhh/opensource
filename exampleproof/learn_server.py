"""Single-user local learner app; bounded uploads, read-only project analysis."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import threading
from urllib.parse import parse_qs, urlparse
import zipfile

from .learning import LEVELS, SYSTEM, LEGACY_SYSTEM, guide_text, local_guide, model_guide, model_payload
from .learning_tasks import outline
from .learning_workspace import StudyWorkspace, StudyConflict
from .model_api import JSONClient
from .project_input import MAX_ARCHIVE_BYTES, MAX_ENTRIES, MAX_EXPANDED_BYTES, eligible, github_repository, project_input
from .tutorial import prepare_project
from .tutorial_privacy import redact, review_payload
from .tutorial_scope import EvidenceScope


def unpack_upload(data, destination):
    """Accept a flat project or one wrapper directory; validate before writing."""
    scope = EvidenceScope()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('ZIP 超过 20 MB，请移除依赖目录和构建产物后重试。')
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError('这不是可读取的 ZIP 项目文件。') from None
    with z:
        entries = z.infolist()
        if len(entries) > MAX_ENTRIES or sum(i.file_size for i in entries) > MAX_EXPANDED_BYTES:
            raise ValueError('解压后的文件数量或大小超过限制。')
        names, files = set(), []
        for item in entries:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename or not path.parts
                    or ':' in path.parts[0] or str(path) != item.filename.rstrip('/')
                    or any(ord(c) < 32 or ord(c) == 127 for c in item.filename) or item.filename in names):
                raise ValueError('ZIP 中包含不安全或重复的路径。')
            names.add(item.filename)
            kind = stat.S_IFMT(item.external_attr >> 16)
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
                raise ValueError('ZIP 包含不支持的特殊文件。')
            if not item.is_dir() and kind != stat.S_IFLNK:
                files.append(item)
        roots = {PurePosixPath(i.filename).parts[0] for i in files}
        wrapped = len(roots) == 1 and all(len(PurePosixPath(i.filename).parts) > 1 for i in files)
        copied, total, skipped, targets = 0, 0, 0, set()
        for item in files:
            parts = PurePosixPath(item.filename).parts[1:] if wrapped else PurePosixPath(item.filename).parts
            relative = PurePosixPath(*parts)
            if not eligible(relative, scope) or item.file_size > 256000 or copied >= 1000 or total + item.file_size > 8000000:
                skipped += 1
                continue
            if str(relative) in targets:
                raise ValueError('ZIP 包含重复的项目文件。')
            targets.add(str(relative))
            content = z.read(item)
            try:
                content.decode('utf-8-sig')
            except UnicodeError:
                skipped += 1
                continue
            if b'\0' in content:
                skipped += 1
                continue
            path = destination.joinpath(*relative.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            copied += 1
            total += len(content)
        return {'copied_files': copied, 'skipped_files': skipped, 'archive_entries': len(entries)}


def now():
    return datetime.now(timezone.utc).isoformat()


class LearningApp:
    def __init__(self, data, provider='auto', model=None, client_factory=None, *, gateway_endpoint=None):
        self.data = Path(data).resolve()
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        from . import shared_service
        if gateway_endpoint and provider not in {'auto', 'gateway'}:
            raise ValueError('共享服务地址不能与直接模型配置混用。')
        configured_gateway = gateway_endpoint or os.environ.get('EXAMPLEPROOF_GATEWAY_URL')
        if provider == 'auto':
            self.provider = ('gateway' if configured_gateway else 'deepseek' if os.environ.get('DEEPSEEK_API_KEY')
                             else 'gateway' if shared_service.SERVICE_URL else 'none')
        else:
            self.provider = provider
        gateway_endpoint = configured_gateway or shared_service.SERVICE_URL
        self.model = model or (shared_service.MODEL if self.provider == 'gateway'
                              else 'deepseek-flash' if self.provider == 'deepseek' else '')
        self.gateway_endpoint = None
        if self.provider == 'gateway':
            from .gateway_client import GatewayClient, gateway_url
            self.gateway_endpoint = gateway_url(gateway_endpoint or '')
            self.factory = client_factory or (lambda: GatewayClient(self.model, endpoint=self.gateway_endpoint))
        else:
            self.factory = client_factory or (lambda: JSONClient(self.provider, self.model, timeout=60))
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='learner')
        self.workspace = StudyWorkspace(self)
        for path in self.data.glob('*/record.json'):
            try:
                record = json.loads(path.read_text())
                if record['status'] in {'importing', 'analyzing'}:
                    record.update(status='ready' if record.get('guide') else 'failed', error='服务重启打断了处理。可重新导入或再次分析。')
                    self.save(record)
            except (ValueError, KeyError, OSError):
                pass

    def folder(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('项目不存在。')
        return self.data / identifier

    def save(self, record):
        with self.lock:
            folder = self.folder(record['id'])
            folder.mkdir(exist_ok=True, mode=0o700)
            temp = folder / 'record.pending'
            temp.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            temp.replace(folder / 'record.json')

    def read(self, identifier):
        with self.lock:
            path = self.folder(identifier) / 'record.json'
            if not path.is_file():
                raise ValueError('项目不存在。')
            return json.loads(path.read_text())

    def public(self, record):
        from .tutorial_privacy import _redact_value
        value = {k: v for k, v in record.items() if k not in {'provenance', 'payload', 'binding', 'review_file', 'regenerate_ready', 'route_system'}}
        return _redact_value(value, tuple(v for v in [os.environ.get('DEEPSEEK_API_KEY'), os.environ.get('EXAMPLEPROOF_GATEWAY_TOKEN')] if v))

    def list(self):
        result = []
        for path in self.data.glob('*/record.json'):
            r = self.read(path.parent.name)
            result.append({k: r.get(k) for k in ('id', 'name', 'goal', 'level', 'status', 'created_at', 'completed_steps', 'error')} | {
                'step_count': len(r.get('guide', {}).get('steps', [])), 'mode': r.get('guide', {}).get('mode', 'local')})
        return sorted(result, key=lambda r: r['created_at'], reverse=True)

    def create(self, *, name, goal, level, upload=None, repository=None, ref=None, auto_ai=False):
        # The import form selects AI by default and submits this choice explicitly.
        # Older callers and saved projects keep their preview-first behavior.
        if type(auto_ai) is not bool:
            raise ValueError('请选择是否自动生成 AI 学习路线。')
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 2000:
            raise ValueError('请用 1–2000 个字符描述你想完成的事。')
        if level not in LEVELS:
            raise ValueError('请选择你的基础水平。')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
            raise ValueError('项目名称长度应为 1–160 个字符。')
        if repository is not None:
            repository = github_repository(repository)
        if ref is not None and (not isinstance(ref, str) or len(ref) > 256):
            raise ValueError('项目版本格式不正确。')
        with self.lock:
            rows = self.list()
            if sum(r['status'] in {'importing', 'analyzing'} for r in rows) >= 2:
                raise ValueError('已有两个项目正在处理，请稍后再试。')
            if len(rows) >= 100:
                raise ValueError('本机已达到 100 个项目的存储上限。请使用新的 --data 目录。')
            identifier = secrets.token_hex(16)
            record = {'id': identifier, 'name': name.strip(), 'goal': goal.strip(), 'level': level,
                      'created_at': now(), 'status': 'importing', 'stage': '读取项目文件', 'error': None,
                      'completed_steps': [], 'source': 'github' if repository else 'zip',
                      'auto_ai': auto_ai and self.provider != 'none'}
            self.save(record)
            self.pool.submit(self._import, identifier, upload, repository, ref)
        return self.public(record)

    def _import(self, identifier, upload, repository, ref):
        record = self.read(identifier)
        folder = self.folder(identifier)
        root = folder / 'input'
        root.mkdir()
        try:
            if repository:
                with project_input(repository, ref=ref or None) as (download, provenance):
                    shutil.copytree(download, root, dirs_exist_ok=True)
            else:
                meta = unpack_upload(upload, root)
                provenance = {'kind': 'uploaded_zip', 'snapshot': meta}
            record.update(stage='整理文档、环境要求与源码入口', provenance=provenance)
            self.save(record)
            snapshot = prepare_project(root, provenance, task=record['goal'])
            if not snapshot.files:
                raise ValueError('项目中没有可读取的 UTF-8 文档或源码。请上传源码项目，避免仅上传安装包或二进制文件。')
            record['guide'] = local_guide(snapshot, record['name'], record['goal'], record['level'])
            record['guide_revision'] = 1
            record['snapshot_id'] = snapshot.snapshot_id
            record['import_summary'] = provenance.get('snapshot', {})
            if self.provider != 'none':
                try:
                    self._preview(record, snapshot)
                except Exception as exc:
                    record['error'] = self.safe_error(exc)
                    record['guide']['warnings'].append('AI 服务尚未准备好，基础路线仍可使用。')
            if record['auto_ai'] and record.get('ai_preview'):
                # Continue in this worker, without publishing a transient ready
                # state or relying on the browser to start the model request.
                record.update(status='analyzing', stage='AI 正在围绕你的目标细化学习路线')
                record['ai_trigger'] = 'import_choice'
                self.save(record)
                self._analyze(identifier, record['ai_preview']['approval'])
                return
            record.update(status='ready', stage='基础评估已就绪')
        except Exception as exc:
            record.update(status='failed', error=self.safe_error(exc), stage='导入未完成')
        self.save(record)

    def safe_error(self, exc):
        if isinstance(exc, (ValueError, zipfile.BadZipFile)):
            return redact(str(exc), tuple(v for v in [os.environ.get('DEEPSEEK_API_KEY'), os.environ.get('EXAMPLEPROOF_GATEWAY_TOKEN')] if v))[:500]
        return '处理未完成。GitHub 项目请确认地址、公开访问权限和网络；ZIP 请检查文件格式后重试。'

    def _preview(self, record, snapshot):
        client = self.factory()
        payload = model_payload(snapshot, record['name'], record['goal'], record['level'], tuple(v for v in [getattr(client, '_key', None)] if v))
        record['payload'] = payload
        record['route_system'] = SYSTEM
        record['binding'] = {'snapshot_id': snapshot.snapshot_id, 'goal': record['goal'], 'level': record['level'],
                             'guide_revision': record.get('guide_revision', 1), 'nonce': secrets.token_hex(12)}
        record['review_file'] = 'cloud-review-' + record['binding']['nonce'] + '.json'
        path = self.folder(record['id']) / record['review_file']
        if self.provider in {'deepseek', 'gateway'}:
            try:
                review_payload(client, SYSTEM, payload, record['binding'], path)
            except ValueError:
                if not path.is_file():
                    raise
            manifest = json.loads(path.read_text())
        else:
            from .tutorial_privacy import _digest
            manifest = {'sha256': _digest({'system': SYSTEM, 'payload': payload, 'model': self.model})}
        record['ai_preview'] = {'approval': manifest['sha256'], 'provider': self.provider, 'model': self.model,
                                'files': sorted({e['path'] for e in payload['evidence']}), 'excerpts': len(payload['evidence'])}

    def regenerate_preview(self, identifier):
        with self.lock:
            record = self.read(identifier)
            if record['status'] != 'ready' or self.provider == 'none':
                raise ValueError('请等待项目就绪并配置模型。')
            self._preview(record, prepare_project(self.folder(identifier)/'input', record['provenance'], task=record['goal']))
            record['regenerate_ready'] = True
            self.save(record)
            return {'payload': record['payload'], 'preview': record['ai_preview']}

    def analyze(self, identifier, approval, regenerate=False):
        with self.lock:
            record = self.read(identifier)
            if record['status'] != 'ready' or not record.get('ai_preview'):
                raise ValueError('项目尚未就绪，或 AI 服务未配置。')
            if type(regenerate) is not bool or regenerate and not record.get('regenerate_ready'):
                raise ValueError('请先查看重新规划的发送内容。')
            if record['guide']['mode'] == 'ai' and not regenerate:
                raise ValueError('该项目已生成 AI 路线，无需重复请求。')
            if not isinstance(approval, str) or not secrets.compare_digest(approval, record['ai_preview']['approval']):
                raise ValueError('发送内容已变化，请刷新项目后重新确认。')
            record.update(status='analyzing', stage='围绕你的目标生成学习路线', error=None)
            record['ai_trigger'] = 'manual_request'
            record['regenerate_ready'] = False
            self.save(record)
            self.pool.submit(self._analyze, identifier, approval)
            return self.public(record)

    def _analyze(self, identifier, approval):
        record = self.read(identifier)
        folder = self.folder(identifier)
        reply = None
        try:
            snapshot = prepare_project(folder / 'input', record['provenance'], task=record['goal'])
            if snapshot.snapshot_id != record['snapshot_id']:
                raise ValueError('导入文件已发生变化，请重新导入项目。')
            client = self.factory()
            system = record.get('route_system', LEGACY_SYSTEM)
            if self.provider in {'deepseek', 'gateway'}:
                client = review_payload(client, system, record['payload'], record['binding'], folder / record.get('review_file', 'cloud-review.json'), approval)
            reply = client.complete(system, record['payload'])
            # Save attempts before validation, including invalid model outputs.
            attempt = {'kind': 'live_model' if getattr(client, 'evidence_kind', '') == 'live_model' else 'test_provider',
                       'value': reply.value, 'input_tokens': reply.input_tokens, 'output_tokens': reply.output_tokens,
                       'inference': asdict(reply.inference), 'received_at': now()}
            (folder / ('attempt-' + secrets.token_hex(6) + '.json')).write_text(json.dumps(attempt, ensure_ascii=False, indent=2))
            new_guide = model_guide(snapshot, record['guide'], record['payload'], reply)
            self.workspace.archive(record)
            record['guide'] = new_guide
            record['guide_revision'] = record.get('guide_revision', 1) + 1
            record['completed_steps'] = []
            record['stage'] = '你的学习路线已生成'
        except Exception as exc:
            record['error'] = self.safe_error(exc)
            record['stage'] = 'AI 生成未完成，基础路线已保留'
            inference = getattr(exc, 'inference_evidence', None)
            (folder / ('failure-' + secrets.token_hex(6) + '.json')).write_text(json.dumps({
                'at': now(), 'error': record['error'], 'inference': asdict(inference) if inference else None,
                'input_tokens': reply.input_tokens if reply else None, 'output_tokens': reply.output_tokens if reply else None,
            }, ensure_ascii=False, indent=2))
        record['status'] = 'ready'
        self.save(record)

    def progress(self, identifier, steps):
        with self.lock:
            r = self.read(identifier)
            if r['status'] != 'ready':
                raise ValueError('请等待路线生成完成。')
            ids = {s['id'] for s in r['guide']['steps']}
            if not isinstance(steps, list) or any(not isinstance(s, str) or s not in ids for s in steps):
                raise ValueError('学习步骤不存在。')
            r['completed_steps'] = sorted(set(steps))
            self.save(r)
            return self.public(r)


class Handler(BaseHTTPRequestHandler):
    server_version = 'ExampleProof'

    def log_message(self, format, *args):
        # Avoid recording goals/source URLs in HTTP access logs.
        pass

    def respond(self, value, status=200, kind='application/json; charset=utf-8'):
        raw = json.dumps(value, ensure_ascii=False).encode() if kind.startswith('application/json') else value
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def route(self, post=False):
        app = self.server.app
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in allowed:
            return self.respond({'error': '仅允许本机访问。'}, 403)
        if post and (self.headers.get('Origin') not in {None, 'http://' + host} or not secrets.compare_digest(self.headers.get('X-ExampleProof-Token', ''), app.csrf)):
            return self.respond({'error': '请求来源无效，请刷新页面。'}, 403)
        url = urlparse(self.path)
        path = url.path
        try:
            body = None
            if post:
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('不支持该上传编码。')
                size = int(self.headers.get('Content-Length', '0'))
                limit = MAX_ARCHIVE_BYTES if path == '/api/projects/upload' else 64000
                if not 0 < size <= limit:
                    raise ValueError('上传为空或超过大小限制（ZIP 最大 20 MB）。')
                self.connection.settimeout(30)
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError('上传未完成，请重试。')
                if path != '/api/projects/upload':
                    body = json.loads(body)
                    if not isinstance(body, dict):
                        raise ValueError('请求内容格式错误。')
            if not post and path == '/api/config':
                return self.respond({'csrf': app.csrf, 'ai_available': app.provider != 'none', 'provider': app.provider, 'model': app.model,
                                     'gateway_url': app.gateway_endpoint})
            if path == '/api/projects' and not post:
                return self.respond({'projects': app.list()})
            if path == '/api/projects' and post:
                repo = body.get('repository')
                if not isinstance(repo, str):
                    raise ValueError('请输入公开 GitHub 仓库地址。')
                return self.respond(app.create(name=repo.strip('/').split('/')[-1], goal=body.get('goal'), level=body.get('level'), repository=repo, ref=body.get('ref'), auto_ai=body.get('auto_ai', False)), 202)
            if path == '/api/projects/upload' and post:
                query = parse_qs(url.query)
                auto_ai = query.get('auto_ai', ['false'])
                if auto_ai not in (['true'], ['false']):
                    raise ValueError('请选择是否自动生成 AI 学习路线。')
                return self.respond(app.create(name=query.get('name', ['我的项目'])[0], goal=query.get('goal', [''])[0], level=query.get('level', ['beginner'])[0], upload=body, auto_ai=auto_ai == ['true']), 202)
            match = re.fullmatch(r'/api/projects/([a-f0-9]{32})(?:/(analyze|preview|progress|source|export|workspace|journal|help-prepare|help-send|help-status|regenerate-preview|run-check))?', path)
            if match:
                identifier, action = match.groups()
                if post and action == 'analyze':
                    return self.respond(app.analyze(identifier, body.get('approval'), body.get('regenerate', False)), 202)
                if action == 'workspace':
                    return self.respond(app.workspace.mutate(identifier, body) if post else app.workspace.view(identifier))
                if not post and action == 'journal':
                    return self.respond(app.workspace.export(identifier).encode(), kind='text/plain; charset=utf-8')
                if post and action == 'regenerate-preview':
                    return self.respond(app.regenerate_preview(identifier))
                if post and action == 'help-prepare':
                    return self.respond(app.workspace.prepare(identifier, body))
                if post and action == 'help-send':
                    return self.respond(app.workspace.send(identifier, body.get('request_id'), body.get('approval')), 202)
                if post and action == 'run-check':
                    return self.respond(app.workspace.run_check(identifier, body))
                if not post and action == 'help-status':
                    return self.respond(app.workspace.status(identifier, parse_qs(url.query).get('id', [''])[0]))
                if post and action == 'progress':
                    return self.respond(app.progress(identifier, body.get('completed_steps')))
                if post:
                    raise ValueError('不支持的操作。')
                r = app.read(identifier)
                if not action:
                    return self.respond(app.public(r))
                if action == 'preview':
                    return self.respond({'payload': r.get('payload'), 'preview': r.get('ai_preview')})
                if action == 'source':
                    file = parse_qs(url.query).get('path', [''])[0]
                    snapshot = prepare_project(app.folder(identifier) / 'input', r['provenance'])
                    if file not in snapshot.files:
                        raise ValueError('此文件不在已导入的分析范围内。')
                    text = redact(snapshot.files[file]['text'], tuple(v for v in [os.environ.get('DEEPSEEK_API_KEY'), os.environ.get('EXAMPLEPROOF_GATEWAY_TOKEN')] if v))
                    return self.respond({'path': file, 'text': text, 'outline': outline(file, text),
                                         'kind': next((f['kind'] for f in r['guide']['files'] if f['path'] == file), 'source')})
                if action == 'export':
                    return self.respond(guide_text(r).encode(), kind='text/plain; charset=utf-8')
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/app.css': ('app.css', 'text/css; charset=utf-8'),
                      '/study.js': ('study.js', 'text/javascript; charset=utf-8'), '/study.css': ('study.css', 'text/css; charset=utf-8'),
                      '/code_highlight.js': ('code_highlight.js', 'text/javascript; charset=utf-8')}
            if not post and path in assets:
                name, kind = assets[path]
                return self.respond((Path(__file__).parent / 'learner_web' / name).read_bytes(), kind=kind)
            return self.respond({'error': '页面或项目不存在。'}, 404)
        except StudyConflict as exc:
            return self.respond({'error': str(exc)}, 409)
        except (ValueError, KeyError, TypeError, UnicodeError, OSError) as exc:
            return self.respond({'error': app.safe_error(exc)}, 400)

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route(True)


def serve(data, port=8765, provider='auto', model=None, *, gateway_endpoint=None):
    if provider == 'ollama' and not model:
        raise ValueError('本地 Ollama 需要指定 --model。')
    app = LearningApp(data, provider, model, gateway_endpoint=gateway_endpoint)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.app = app
    print(f'例证学习入口：http://127.0.0.1:{server.server_port}', flush=True)
    print(f'项目存储：{app.data}；AI：{app.provider}。上传的项目代码不会被执行。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.pool.shutdown(wait=False, cancel_futures=True)
