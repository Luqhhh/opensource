"""Bounded evidence-gap retrieval over a frozen static index; never execute code."""

from collections import Counter
from dataclasses import asdict
from pathlib import PurePosixPath

from .tutorial import ANALYZE_SYSTEM, _call, _tutorial_terms, pack_context


MAX_REQUESTS = 3
RESULTS_PER_REQUEST = 6
SEARCH_STATUSES = {"matches", "already_seen", "no_indexed_match", "repeated_request"}
ITERATIVE_SYSTEM = ANALYZE_SYSTEM + """
You may request more evidence when the supplied excerpts are insufficient.
Also return evidence_requests: [] and retain_ids: [] in every response.
For an evidence gap, return at most 3 requests, each with exactly kind, query,
reason, and optionally start_line for a path request. kind is path, symbol,
or text. path is an exact repository-relative file or directory; symbol is a
Python function or qualified method name; text is a short literal/keyword query.
Explain the gap in reason. Never request shell commands, imports, URLs or tools.
Search is limited to the frozen eligible static index, including chunks outside
the initial candidates. No match does not establish absence from the project.
retain_ids may contain at most 12 currently supplied IDs needed alongside new
evidence. A tutorial anchor is preserved automatically when it fits. Other old
excerpts may be evicted to admit retrieved evidence. Cite only current evidence.
Return evidence_requests: [] when ready to finish; this is your assessment, not
independent verification of completeness. Findings and edits remain unverified.
Respect the supplied retrieval round limit; do not claim unperformed searches.
"""


def validate_round_limit(value):
    if type(value) is not int or not 1 <= value <= 5:
        raise ValueError("Retrieval round limit must be an integer from 1 to 5")


def validate_requests(value, current_ids):
    if not isinstance(value, dict):
        raise ValueError("Expected an iterative analysis object")
    requests, retained = value.get("evidence_requests"), value.get("retain_ids", [])
    if not isinstance(requests, list) or len(requests) > MAX_REQUESTS:
        raise ValueError("Expected at most three evidence requests")
    if (not isinstance(retained, list) or len(retained) > 12
            or any(not isinstance(i, str) or i not in current_ids for i in retained)
            or len(set(retained)) != len(retained)):
        raise ValueError("Retention must cite distinct currently supplied IDs")
    for request in requests:
        if (not isinstance(request, dict) or not {"kind", "query", "reason"} <= request.keys()
                or not request.keys() <= {"kind", "query", "reason", "start_line"}
                or request["kind"] not in {"path", "symbol", "text"}
                or any(not isinstance(request[k], str) or not request[k].strip() or len(request[k]) > limit
                       for k, limit in (("query", 240), ("reason", 1000)))
                or any(ord(c) < 32 or ord(c) == 127 for c in request["query"])):
            raise ValueError("Invalid evidence request")
        query = request["query"]
        if request["kind"] == "path":
            path = PurePosixPath(query)
            if (path.is_absolute() or ".." in path.parts or "\\" in query or ":" in query
                    or str(path) != query or query == "."):
                raise ValueError("Evidence paths must be normalized relative repository paths")
        if request["kind"] == "symbol" and any(not part.isidentifier() for part in query.split(".")):
            raise ValueError("Symbol queries must be qualified identifiers")
        if "start_line" in request and (request["kind"] != "path" or
                                         type(request["start_line"]) is not int or request["start_line"] < 1):
            raise ValueError("Only path requests accept a positive start_line")
    return requests, retained


def search_index(snapshot, request, seen=(), render=asdict):
    """Resolve validated queries only against indexed, optionally redacted text."""
    query, kind = request["query"], request["kind"]
    terms = Counter(_tutorial_terms(query))
    hits = []
    for chunk in snapshot.chunks:
        item = render(chunk)
        if kind == "path":
            if item["path"] != query and not item["path"].startswith(query + "/"):
                continue
            line = request.get("start_line")
            if line is not None and not chunk.start_line <= line <= chunk.end_line:
                continue
            score = 1
        elif kind == "symbol":
            title = item["title"]
            if title == item["path"] or chunk.kind != "source" or not chunk.path.endswith(".py") or not (
                    title == query or title.endswith("." + query) or query.endswith("." + title)):
                continue
            score = 2 if title == query else 1
        else:
            text = item["title"] + " " + item["path"] + " " + item["text"]
            tokens = Counter(_tutorial_terms(text))
            score = sum(min(tokens[t], 3) * min(terms[t], 3) for t in terms.keys() & tokens.keys())
            if query.casefold() in text.casefold():
                score += 20
            if not score:
                continue
        hits.append((-score, item["path"], chunk.start_line, chunk))
    hits.sort(key=lambda item: item[:3])
    unseen = [item[-1] for item in hits if item[-1].id not in seen]
    results = unseen[:RESULTS_PER_REQUEST]
    return results, {"request": dict(request), "status": "matches" if results else "already_seen" if hits else "no_indexed_match",
                     "matched_chunks": len(hits), "returned_ids": [c.id for c in results]}


def explore(snapshot, client, selected, used, before_budget, context_chars, max_rounds, calls, warnings):
    validate_round_limit(max_rounds)
    render = client.render_chunk if hasattr(client, "render_chunk") else asdict
    seen = {c.id for c in selected}
    queries, retrieved_ids, rounds = set(), set(), []
    prior_search = []
    last = {"value": None, "selected": selected, "used": used, "before_budget": before_budget}
    stop_reason, unresolved = "no_evidence", []
    for number in range(max_rounds + 1):
        payload = {"coverage": {"indexed_files": len(snapshot.files), "indexed_chunks": len(snapshot.chunks),
                                "selected_chunks": len(selected), "skipped": snapshot.skipped},
                   "task": snapshot.task, "evidence": [asdict(c) for c in selected],
                   "retrieval": {"round": number, "max_rounds": max_rounds, "last_search": prior_search}}
        value = _call(client, ITERATIVE_SYSTEM, payload, "analysis", calls)
        calls[-1]["retrieval_round"] = number
        record = {"round": number, "context_ids": [c.id for c in selected], "used_chars": used,
                  "requests": [], "searches": [], "retain_ids": [], "next_context_ids": [], "stop_reason": None}
        rounds.append(record)
        if value is None:
            stop_reason = "model_error"
            unresolved = [s["request"] for s in prior_search]
            break
        try:
            requests, retained = validate_requests(value, {c.id for c in selected})
        except (ValueError, TypeError):
            stop_reason = "invalid_evidence_request"
            unresolved = [s["request"] for s in prior_search]
            warnings.append("补充检索请求或保留 ID 无效，已停止；没有执行模型提出的命令。")
            break
        last = {"value": value, "selected": selected, "used": used, "before_budget": before_budget}
        record.update(requests=requests, retain_ids=retained)
        if not requests:
            stop_reason = "model_finished"
            break
        unresolved = requests
        if number == max_rounds:
            stop_reason = "round_limit"
            break
        found, searches = [], []
        for request in requests:
            key = (request["kind"], request["query"].casefold() if request["kind"] == "text" else request["query"], request.get("start_line"))
            matches, receipt = search_index(snapshot, request, seen | {c.id for c in found}, render)
            if key in queries and not matches:
                receipt["status"] = "repeated_request"
            queries.add(key)
            searches.append(receipt)
            for chunk in matches:
                retrieved_ids.add(chunk.id)
                if chunk not in found:
                    found.append(chunk)
        record["searches"] = searches
        if not found:
            stop_reason = "no_new_evidence"
            break
        by_id = {c.id: c for c in selected}
        anchor = next((c for c in selected if c.kind == "document"), None)
        proposed = ([anchor] if anchor else []) + [by_id[i] for i in retained] + found + list(selected)
        proposed = list({c.id: c for c in proposed}.values())
        next_selected, next_used = pack_context(proposed, context_chars, render)
        record["next_context_ids"] = [c.id for c in next_selected]
        if not any(c.id not in seen for c in next_selected):
            stop_reason = "context_budget_exhausted"
            break
        selected, used, before_budget = next_selected, next_used, proposed
        seen.update(c.id for c in selected)
        prior_search = searches
        unresolved = []
    if stop_reason == "model_finished":
        unresolved = []
    else:
        warnings.append(f"补充检索停止：{stop_reason}；剩余证据缺口未经验证，不能据此判断项目缺失。")
    rounds[-1]["stop_reason"] = stop_reason
    trace = {"schema_version": "tutorial-retrieval-1", "max_rounds": max_rounds,
             "max_model_requests": max_rounds + 1, "rounds": rounds, "stop_reason": stop_reason,
             "unresolved_requests": unresolved, "retrieved_ids": sorted(retrieved_ids),
             "initial_candidate_ids": [c.id for c in snapshot.candidates],
             "final_evidence_ids": [c.id for c in last["selected"]],
             "evidence": {c.id: asdict(c) for c in snapshot.chunks if c.id in seen | retrieved_ids},
             "scope": "Frozen eligible index only; model-reported completion is not independent verification"}
    return last | {"trace": trace}
