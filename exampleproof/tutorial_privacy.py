"""Review and approve a frozen, redacted cloud evidence envelope before sending."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def redact(text, literals=()):
    # This is a bounded heuristic, supplemented by user-supplied literal values.
    for literal in sorted(set(literals), key=len, reverse=True):
        text = text.replace(literal, re.sub(r"[^\r\n]+", "[REDACTED]", literal))
    text = re.sub(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z]+ )?PRIVATE KEY-----|\Z)",
                  lambda m: re.sub(r"[^\r\n]+", "[REDACTED]", m[0]), text)
    name = r"[\w-]*(?:api[_-]?key|access[_-]?key|secret|password|passwd|token|credential)[\w-]*"
    text = re.sub(rf'''(?im)(\b{name}["']?\s*[:=]\s*)(["'])([^\r\n]*?)\2''',
                  lambda m: m[1] + m[2] + "[REDACTED]" + m[2], text)
    text = re.sub(rf'''(?im)(\b{name}["']?\s*[:=]\s*)(?!["'\s])([^\s,;}}]+)''',
                  lambda m: m[1] + "[REDACTED]", text)
    text = re.sub(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+", r"\1[REDACTED]", text)
    return re.sub(r"(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", text)


def _redact_value(value, literals):
    if isinstance(value, str):
        return redact(value, literals)
    if isinstance(value, list):
        return [_redact_value(v, literals) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v, literals) for k, v in value.items()}
    return value


def selection_summary(chunk):
    return {k: chunk[k] for k in ("id", "path", "start_line", "end_line", "kind", "title")} | {"preview": chunk["text"][:240]}


def analysis_coverage(snapshot, count):
    return {"indexed_files": len(snapshot.files), "indexed_chunks": len(snapshot.chunks),
            "selected_chunks": count, "skipped": snapshot.skipped}


def review_cloud(snapshot, client, path, approval=None, *, context_chars=12000,
                 strategies=("lexical",), redact_values=(), max_retrieval_rounds=3,
                 max_total_tokens=None, deadline_seconds=None):
    """Write a first preview or validate an already reviewed immutable manifest."""
    from .tutorial import ANALYZE_SYSTEM, SELECT_SYSTEM, DIRECT_SYSTEM
    path = Path(path)
    local_root = snapshot.provenance.get("path") if snapshot.provenance.get("kind") == "local" else None
    if path.is_symlink() or local_root and path.resolve().is_relative_to(Path(local_root).resolve()):
        raise ValueError("Cloud review must be outside the input project and cannot be a symlink")
    if client.provider != "deepseek":
        raise ValueError("Cloud review applies only to DeepSeek tutorial analysis")
    if (not isinstance(redact_values, (list, tuple)) or
            any(not isinstance(v, str) or not v for v in redact_values)):
        raise ValueError("Redaction values must be a list of non-empty strings")
    literals = tuple(redact_values) + ((client._key,) if getattr(client, "_key", None) else ())
    iterative = "iterative" in strategies
    corpus = snapshot.chunks if iterative else snapshot.candidates
    originals = [asdict(c) for c in corpus]
    # Redact whole files before slicing so a key block split across chunks is
    # still masked. Keep line endings to preserve the original evidence labels.
    sanitized_lines = {p: redact(snapshot.files[p]["text"], literals).splitlines(keepends=True)
                       for p in {c.path for c in corpus}}
    redacted = [_redact_value(c, literals) | {"id": c["id"], "text": "".join(
        sanitized_lines[c["path"]][c["start_line"] - 1:c["end_line"]])} for c in originals]
    body = {"schema_version": "tutorial-cloud-review-1", "snapshot_id": snapshot.snapshot_id,
            "model": {"provider": client.provider, "name": client.model, "endpoint": client.endpoint},
            "context_chars": context_chars, "strategies": list(strategies),
            "evidence_scope": snapshot.evidence_scope,
            "prompts": {"analysis": ANALYZE_SYSTEM, "selection": SELECT_SYSTEM},
            "coverage_metadata": analysis_coverage(snapshot, 0),
            "files": [{"path": p, "sha256": snapshot.files[p]["sha256"]}
                      for p in sorted({c.path for c in corpus})],
            "permitted_evidence": redacted,
            "notice": "Review every permitted excerpt; automated redaction cannot find all sensitive content. "
                      "AI selection can send any subset of these excerpts, including previews. "
                      "Approval is specific to this snapshot, model, scope, prompts and budget."}
    if iterative:
        from .tutorial_retrieval import ITERATIVE_SYSTEM, MAX_REQUESTS, RESULTS_PER_REQUEST, validate_round_limit
        validate_round_limit(max_retrieval_rounds)
        body["prompts"]["iterative"] = ITERATIVE_SYSTEM
        body["retrieval"] = {"max_rounds": max_retrieval_rounds, "max_requests_per_round": MAX_REQUESTS,
                             "results_per_request": RESULTS_PER_REQUEST,
                             "task": redact(snapshot.task, literals) if snapshot.task is not None else None,
                             "search_scope": "all reviewed indexed chunks; no filesystem or network tools"}
        body["initial_candidate_ids"] = [c.id for c in snapshot.candidates]
        body["notice"] += " Iterative retrieval may send any reviewed indexed chunk, including beyond the initial 40 candidates."
    if "direct" in strategies:
        body["prompts"]["direct"] = DIRECT_SYSTEM
    if snapshot.task is not None:
        body["task"] = redact(snapshot.task, literals)
    if max_total_tokens is not None or deadline_seconds is not None:
        from .tutorial_budget import validate_limits
        validate_limits(max_total_tokens, deadline_seconds)
        body["budget"] = {"max_total_tokens": max_total_tokens, "deadline_seconds": deadline_seconds}
    record = {"sha256": _digest(body), "review": body}
    existed = path.exists()
    if existed:
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("Cloud review differs from current input/configuration; choose a new --cloud-review path")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as target:
            json.dump(record, target, ensure_ascii=False, indent=2)
            target.write("\n")
    if not existed or approval != record["sha256"]:
        raise ValueError(f"Cloud upload requires review: {path}. Inspect files and redacted excerpts, then rerun "
                         f"with --approve-cloud {record['sha256']}. No model request was sent.")
    return ReviewedCloudClient(client, snapshot, record)


class ReviewedCloudClient:
    """Allow only frozen evidence, transforming it to the exact reviewed text."""

    def __init__(self, client, snapshot, record):
        self._client, self._snapshot, self.review_record = client, snapshot, record
        self.provider, self.model, self.endpoint = client.provider, client.model, client.endpoint
        self.timeout, self.evidence_kind = client.timeout, client.evidence_kind
        self._corpus = snapshot.chunks if "iterative" in record["review"]["strategies"] else snapshot.candidates
        self._originals = {c.id: asdict(c) for c in self._corpus}
        self._redacted = {c["id"]: c for c in record["review"]["permitted_evidence"]}
        self._next_round, self._previous_requests = 0, []

    def render_chunk(self, chunk):
        return self._redacted[chunk.id]

    def render_summaries(self, summaries):
        return [selection_summary(self._redacted[c["id"]]) for c in summaries]

    def validate_project(self, snapshot, strategy, context_chars):
        review = self.review_record["review"]
        if (snapshot is not self._snapshot or snapshot.snapshot_id != review["snapshot_id"]
                or strategy not in review["strategies"] or context_chars != review["context_chars"]
                or self.model != self._client.model or self.endpoint != self._client.endpoint
                or _digest(review) != self.review_record["sha256"]
                or {c.id: asdict(c) for c in self._corpus} != self._originals):
            raise ValueError("Cloud approval no longer matches the frozen analysis")

    def validate_iteration_limit(self, value):
        if self.review_record["review"].get("retrieval", {}).get("max_rounds") != value:
            raise ValueError("Cloud approval does not match the retrieval round limit")

    def validate_budget(self, max_total_tokens, deadline_seconds):
        expected = {"max_total_tokens": max_total_tokens, "deadline_seconds": deadline_seconds}
        approved = self.review_record["review"].get("budget", {"max_total_tokens": None, "deadline_seconds": None})
        if approved != expected:
            raise ValueError("Cloud approval does not match analysis budget")

    def _iteration_metadata(self, metadata):
        from .tutorial_retrieval import MAX_REQUESTS, RESULTS_PER_REQUEST, SEARCH_STATUSES
        limit = self.review_record["review"]["retrieval"]["max_rounds"]
        if (not isinstance(metadata, dict) or set(metadata) != {"round", "max_rounds", "last_search"}
                or type(metadata["round"]) is not int or metadata["round"] != self._next_round
                or metadata["round"] > limit or metadata["max_rounds"] != limit
                or not isinstance(metadata["last_search"], list) or len(metadata["last_search"]) > MAX_REQUESTS
                or [s.get("request") for s in metadata["last_search"]] != self._previous_requests):
            raise ValueError("Unreviewed cloud iteration metadata")
        for receipt in metadata["last_search"]:
            if (set(receipt) != {"request", "status", "matched_chunks", "returned_ids"}
                    or receipt["status"] not in SEARCH_STATUSES
                    or (receipt["matched_chunks"] is not None and
                        (type(receipt["matched_chunks"]) is not int or receipt["matched_chunks"] < 0))
                    or not isinstance(receipt["returned_ids"], list) or len(receipt["returned_ids"]) > RESULTS_PER_REQUEST
                    or any(not isinstance(i, str) or i not in self._originals for i in receipt["returned_ids"])):
                raise ValueError("Unreviewed cloud search receipt")

    def complete(self, system, evidence):
        review = self.review_record["review"]
        iterative = system == review["prompts"].get("iterative")
        if iterative:
            self.validate_project(self._snapshot, "iterative", review["context_chars"])
            if set(evidence) != {"coverage", "evidence", "task", "retrieval"} or evidence["task"] != self._snapshot.task:
                raise ValueError("Unreviewed cloud iterative payload")
            self._iteration_metadata(evidence["retrieval"])
        analysis_keys = {"coverage", "evidence"} | ({"task"} if self._snapshot.task is not None else set())
        if (system in {review["prompts"]["analysis"], review["prompts"].get("direct")} and set(evidence) == analysis_keys) or iterative:
            if not iterative and evidence.get("task") != self._snapshot.task:
                raise ValueError("Unreviewed task query")
            chunks = evidence["evidence"]
            if evidence["coverage"] != analysis_coverage(self._snapshot, len(chunks)):
                raise ValueError("Unreviewed cloud coverage metadata")
            if any(c != self._originals.get(c.get("id")) for c in chunks):
                raise ValueError("Unreviewed cloud evidence")
            payload = {"coverage": evidence["coverage"], "evidence": [self._redacted[c["id"]] for c in chunks]}
            if len(json.dumps(payload["evidence"], ensure_ascii=False)) > review["context_chars"]:
                raise ValueError("Cloud evidence exceeds approved context budget")
            if not iterative and self._snapshot.task is not None:
                payload["task"] = review["task"]
            if iterative:
                payload.update(task=review["retrieval"]["task"], retrieval=evidence["retrieval"])
        elif system == review["prompts"]["selection"] and set(evidence) == {"candidates"}:
            if any(c != selection_summary(self._originals[c["id"]]) for c in evidence["candidates"]):
                raise ValueError("Unreviewed cloud selection evidence")
            payload = {"candidates": [selection_summary(self._redacted[c["id"]]) for c in evidence["candidates"]]}
        else:
            raise ValueError("Unreviewed cloud prompt or payload")
        reply = self._client.complete(system, payload)
        if iterative:
            self._next_round += 1
            self._previous_requests = reply.value.get("evidence_requests", []) if isinstance(reply.value, dict) else []
        return reply


class ReviewedPayloadClient:
    """Permit one exact redacted task-proposal request, bound to the private contract hash."""
    def __init__(self, client, system, payload, record):
        self._client, self._system, self._payload = client, system, payload
        self.review_record = record
        self.provider, self.model, self.evidence_kind = client.provider, client.model, client.evidence_kind
        self.used = False

    def complete(self, system, payload):
        model = self.review_record["review"]["model"]
        if (self.used or system != self._system or payload != self._payload
                or {"provider": self._client.provider, "name": self._client.model, "endpoint": self._client.endpoint} != model
                or _digest(self.review_record["review"]) != self.review_record["sha256"]):
            raise ValueError("Task proposal does not match the reviewed request")
        self.used = True
        return self._client.complete(system, self.review_record["review"]["payload"])


def review_payload(client, system, payload, binding, path, approval=None, *, redact_values=()):
    """Review exact proposal payload; never include evaluator setup, checks or expected output."""
    path = Path(path)
    if path.is_symlink() or client.provider != "deepseek":
        raise ValueError("Exact request review requires DeepSeek and a regular review file")
    if not isinstance(redact_values, (list, tuple)) or any(not isinstance(v, str) or not v for v in redact_values):
        raise ValueError("Redaction values must be nonempty strings")
    literals = tuple(redact_values) + ((client._key,) if getattr(client, "_key", None) else ())
    body = {"schema_version": "tutorial-proposal-cloud-review-1", "binding": binding,
            "model": {"provider": client.provider, "name": client.model, "endpoint": client.endpoint},
            "system": system, "payload": _redact_value(payload, literals), "max_requests": 1,
            "notice": "Review all project text and diagnosis; task oracle contents are withheld."}
    record = {"review": body, "sha256": _digest(body)}
    existed = path.exists()
    if existed and json.loads(path.read_text()) != record:
        raise ValueError("Proposal review changed; select a new review path")
    if not existed:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
    if not existed or approval != record["sha256"]:
        raise ValueError(f"Review {path}, then pass --approve-cloud {record['sha256']}; no model call was sent")
    return ReviewedPayloadClient(client, system, payload, record)
