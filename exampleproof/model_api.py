"""Bounded JSON calls for tutorial analysis; no repository code is executed."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import InferenceEvidence
from .providers import MAX_RESPONSE_BYTES, OllamaProvider, urlopen as local_urlopen


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Model HTTP redirects are disabled")


def urlopen(request, *, timeout):
    if request.full_url.startswith("https://api.deepseek.com/"):
        # Cloud APIs may use the developer's HTTPS proxy; local inference never does.
        return build_opener(_NoRedirect()).open(request, timeout=timeout)
    return local_urlopen(request, timeout=timeout)


@dataclass
class JSONReply:
    value: dict
    inference: InferenceEvidence
    input_tokens: int | None
    output_tokens: int | None


class JSONClient:
    """Single-request transport; tutorial uploads require tutorial_privacy review.

    The transport's API-key scrubber is not a repository-secret detector.
    """

    evidence_kind = "live_model"

    def __init__(self, provider, model, *, endpoint=None, timeout=60, api_key=None, ollama_options=None):
        if provider not in {"deepseek", "ollama"}:
            raise ValueError("Unknown model provider")
        if not isinstance(model, str) or not model.strip() or len(model) > 128 or any(c.isspace() for c in model):
            raise ValueError("A valid model name is required")
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Model timeout must be a finite positive number")
        self.provider, self.model, self.timeout = provider, model, timeout
        self._key = None
        self.options = {"temperature": 0, "num_predict": 2048}
        if provider == "deepseek":
            if ollama_options is not None:
                raise ValueError("Ollama options apply only to the Ollama provider")
            self.endpoint = (endpoint or "https://api.deepseek.com").rstrip("/")
            if self.endpoint not in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}:
                raise ValueError("DeepSeek endpoint must be the official HTTPS API")
            self._key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY")
            if (not isinstance(self._key, str) or not self._key.strip()
                    or any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in self._key)):
                raise ValueError("Set DEEPSEEK_API_KEY to a valid API key")
        else:
            # Preserve the existing loopback-only Ollama transport policy.
            local = OllamaProvider(model, endpoint or "http://127.0.0.1:11434", timeout, options=ollama_options)
            self.endpoint = local.endpoint
            self.options.update(local.options)

    def _clean(self, text):
        return text.replace(self._key, "[REDACTED]") if self._key else text

    def complete(self, system, evidence):
        prompt = json.dumps(evidence, ensure_ascii=False)
        if self.provider == "deepseek":
            payload = {"model": self.model, "stream": False,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": prompt}],
                       "response_format": {"type": "json_object"},
                       "thinking": {"type": "disabled"}, "max_tokens": 2048,
                       "temperature": 0}
            route = "/chat/completions"
        else:
            payload = {"model": self.model, "stream": False, "format": "json",
                       "system": system, "prompt": prompt,
                       "options": dict(self.options)}
            route = "/api/generate"
        # Neither headers nor environment variables are part of the evidence.
        payload = json.loads(self._clean(json.dumps(payload, ensure_ascii=False)))
        inference = InferenceEvidence(request=payload,
                                      started_at=datetime.now(timezone.utc).isoformat(),
                                      timeout_seconds=self.timeout)
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = "Bearer " + self._key
        start = time.monotonic()
        try:
            request = Request(self.endpoint + route, data=json.dumps(payload).encode(),
                              headers=headers, method="POST")
            status = None
            try:
                response = urlopen(request, timeout=self.timeout)
            except HTTPError as exc:
                response, status = exc, exc.code
            with response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            inference.response_body = self._clean(raw[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace"))
            if len(raw) > MAX_RESPONSE_BYTES:
                inference.response_truncated = True
                raise ValueError("Model response exceeds 256 KB")
            if status is not None:
                try:
                    error_result = json.loads(inference.response_body)
                    if isinstance(error_result, dict):
                        inference.response, inference.response_body = error_result, None
                except ValueError:
                    pass
                raise ValueError(f"{self.provider} HTTP {status}; inspect redacted inference evidence")
            result = json.loads(inference.response_body)
            if not isinstance(result, dict):
                raise ValueError("Model response must be a JSON object")
            inference.response, inference.response_body = result, None
            if "error" in result:
                raise ValueError("Model service returned an error; inspect inference evidence")
            if self.provider == "deepseek":
                usage = result.get("usage", {})
                if not isinstance(usage, dict):
                    raise ValueError("Invalid model usage")
                incoming, outgoing = usage.get("prompt_tokens"), usage.get("completion_tokens")
                choices = result.get("choices")
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    raise ValueError("Expected exactly one completion")
                choice = choices[0]
                if choice.get("finish_reason") != "stop" or not isinstance(choice.get("message"), dict):
                    raise ValueError("Model completion is incomplete")
                content = choice["message"].get("content")
            else:
                incoming, outgoing = result.get("prompt_eval_count"), result.get("eval_count")
                if result.get("done") is not True or result.get("done_reason", "stop") != "stop":
                    raise ValueError("Model completion is incomplete")
                content = result.get("response")
            for value in (incoming, outgoing):
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError("Model token counts must be non-negative integers")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Model returned empty or invalid content")
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("Model content must be a JSON object")
            return JSONReply(value, inference, incoming, outgoing)
        except Exception as exc:
            # Servers can echo credentials in errors; never propagate raw errors.
            error = ValueError(self._clean(str(exc)))
            error.inference_evidence = inference
            raise error from None
        finally:
            inference.duration_seconds = round(time.monotonic() - start, 4)
