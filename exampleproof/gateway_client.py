"""Client for a maintainer-hosted inference gateway; no upstream API key is needed."""
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .model_api import JSONReply
from .models import InferenceEvidence
from .tutorial_privacy import _redact_value

MAX_GATEWAY_BODY = 96_000
MAX_GATEWAY_REPLY = 256_000


def gateway_url(value):
    """Remote credentials require HTTPS; plain HTTP is only for local development."""
    if not isinstance(value, str) or not value or '\\' in value or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('请配置 EXAMPLEPROOF_GATEWAY_URL，共享服务地址不能为空。')
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError('共享服务地址无效。') from None
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or parts.scheme not in {'https', 'http'} or port == 0):
        raise ValueError('共享服务地址必须是不含账号、查询参数和片段的 HTTPS 地址。')
    try:
        local = ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        local = parts.hostname == 'localhost'
    if parts.scheme != 'https' and not local:
        raise ValueError('远程共享服务必须使用 HTTPS；HTTP 仅允许本机回环地址。')
    return value.rstrip('/')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('共享服务拒绝重定向，请核对配置地址。')


class GatewayClient:
    provider = 'gateway'
    evidence_kind = 'live_model'

    def __init__(self, model, *, endpoint=None, token=None, timeout=70):
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('共享服务超时必须是有限正数。')
        self.model = model
        if not isinstance(model, str) or not model or len(model) > 128 or any(c.isspace() for c in model):
            raise ValueError('共享服务模型名称无效。')
        self.endpoint = gateway_url(endpoint or os.environ.get('EXAMPLEPROOF_GATEWAY_URL', ''))
        self._key = token if token is not None else os.environ.get('EXAMPLEPROOF_GATEWAY_TOKEN', '')
        if (not isinstance(self._key, str) or len(self._key) > 256
                or any(ord(c) < 33 or ord(c) > 126 for c in self._key)):
            raise ValueError('共享服务邀请码格式无效。')
        self.timeout = timeout

    def complete(self, system, evidence):
        payload = _redact_value({'model': self.model, 'system': system, 'evidence': evidence},
                                (self._key,) if self._key else ())
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(raw) > MAX_GATEWAY_BODY:
            raise ValueError('发送内容超过共享服务的单次大小限制，请缩小问题或项目范围。')
        inference = InferenceEvidence(request=payload, started_at=datetime.now(timezone.utc).isoformat(),
                                      timeout_seconds=self.timeout)
        headers = {'Content-Type': 'application/json'}
        if self._key:
            headers['Authorization'] = 'Bearer ' + self._key
        request = Request(self.endpoint + '/v1/complete', data=raw, headers=headers, method='POST')
        # Loopback development traffic must not be sent through an environment proxy.
        handlers = [_NoRedirect()]
        if urlsplit(self.endpoint).scheme == 'http':
            handlers.insert(0, ProxyHandler({}))
        try:
            with build_opener(*handlers).open(request, timeout=self.timeout) as response:
                data = response.read(MAX_GATEWAY_REPLY + 1)
            if len(data) > MAX_GATEWAY_REPLY:
                raise ValueError('共享服务返回内容过大。')
            result = json.loads(data)
            if (not isinstance(result, dict) or not isinstance(result.get('value'), dict)
                    or result.get('model') != self.model):
                raise ValueError('共享服务返回格式或模型与配置不匹配。')
            for name in ('input_tokens', 'output_tokens'):
                value = result.get(name)
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError('共享服务返回了无效用量。')
            result = _redact_value(result, (self._key,) if self._key else ())
            inference.response = result
            return JSONReply(result['value'], inference, result.get('input_tokens'), result.get('output_tokens'))
        except HTTPError as exc:
            # Never expose a remote error body: it may echo credentials or prompts.
            message = {401:'共享服务邀请码无效或已撤销。', 413:'发送内容超过共享服务限制。',
                       429:'共享服务调用额度已用完，请稍后再试或联系维护者。',
                       503:'共享服务正忙或暂不可用，请稍后重试。',
                       400:'共享服务拒绝请求，请核对服务版本与模型名称。'}.get(exc.code, '共享服务调用失败，请联系维护者。')
            exc.close()
            raise ValueError(message) from None
        except (URLError, TimeoutError, OSError):
            raise ValueError('无法连接共享服务，请检查地址与网络后重试。') from None
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError('共享服务未返回有效 JSON。') from None
