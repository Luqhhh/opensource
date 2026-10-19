"""Exploratory paired context comparison, frozen before any model call."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import shutil

from . import tutorial


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="backslashreplace")


def run_comparison(root, provenance, output, client, *, context_chars=12000, arm_order=("lexical", "ai"),
                   scope=None, snapshot=None, evidence_requirements=None):
    if client is None:
        raise ValueError("A model provider is required for context comparison")
    if type(context_chars) is not int or not 2000 <= context_chars <= 48000:
        raise ValueError("Context budget must be 2000..48000 characters")
    if len(arm_order) != 2 or set(arm_order) != {"lexical", "ai"}:
        raise ValueError("Arm order must contain lexical and ai exactly once")
    root, output = Path(root).resolve(), Path(output)
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):
        raise ValueError("Comparison output must be a new directory outside the input project")
    snapshot = snapshot or tutorial.prepare_project(root, provenance, scope=scope)
    if snapshot.task is not None:
        raise ValueError("The lexical/ai comparison requires a snapshot without an iterative task query")
    if getattr(client, "provider", None) == "deepseek":
        from .tutorial_privacy import ReviewedCloudClient
        if not isinstance(client, ReviewedCloudClient):
            raise ValueError("Cloud comparison requires a reviewed cloud manifest and explicit approval")
        for strategy in arm_order:
            client.validate_project(snapshot, strategy, context_chars)
    if evidence_requirements is not None:
        from .tutorial_coverage import validate_requirements
        validate_requirements(evidence_requirements, snapshot)
    output.mkdir(parents=True, exist_ok=False)
    snapshot_record = {"schema_version": "tutorial-snapshot-1", "snapshot_id": snapshot.snapshot_id,
                       "project": snapshot.provenance, "files": snapshot.files,
                       "skipped": snapshot.skipped, "chunks": [asdict(c) for c in snapshot.chunks],
                       "static_observations": snapshot.static_observations}
    _dump(output / "snapshot.json", snapshot_record)
    shutil.copytree(Path(__file__).parent, output / "implementation/exampleproof",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    license_path = Path(__file__).parent.parent / "LICENSE"
    if license_path.is_file():
        shutil.copyfile(license_path, output / "implementation/LICENSE")
    kind = getattr(client, "evidence_kind", "custom_provider_unverified")
    implementation = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(Path(__file__).parent.glob("*.py"))}
    protocol = {"schema_version": "tutorial-comparison-1", "frozen_at": datetime.now(timezone.utc).isoformat(),
                "evidence_kind": kind, "snapshot_id": snapshot.snapshot_id,
                "snapshot_sha256": hashlib.sha256((output / "snapshot.json").read_bytes()).hexdigest(),
                "model": {"provider": client.provider, "name": client.model,
                          "timeout_seconds": getattr(client, "timeout", None),
                          "endpoint": getattr(client, "endpoint", None)},
                "implementation_sha256": implementation,
                "prompts": {"selection": tutorial.SELECT_SYSTEM, "analysis": tutorial.ANALYZE_SYSTEM},
                "arm_order": list(arm_order), "context_chars_per_stage": context_chars,
                "generation_token_limit_per_call": 2048, "max_model_requests": 3,
                "budget_matching": "same final evidence character limit; total token costs are measured, not matched",
                "quality_evaluation": "unreviewed; no quality or learning-efficiency winner can be inferred",
                "evidence_scope": snapshot.evidence_scope, "evidence_requirements": evidence_requirements,
                "cloud_review": client.review_record if getattr(client, "provider", None) == "deepseek" else None,
                "project_code_execution": False}
    _dump(output / "protocol.json", protocol)
    arms, reviews, edit_reviews = {}, [], []
    for strategy in protocol["arm_order"]:
        report = tutorial.analyze_snapshot(snapshot, client=client, strategy=strategy, context_chars=context_chars,
                                           evidence_requirements=evidence_requirements)
        tutorial.write_analysis(output / strategy, report)
        selected = report["context"]["selected"]
        findings = [f for f in report["findings"] if f["origin"] != "static"]
        arms[strategy] = {"actual_strategy": report["context"]["actual"],
                          "fallback_reason": report["context"]["fallback_reason"],
                          "snapshot_id": report["coverage"]["snapshot_id"],
                          "selected_ids": [c["id"] for c in selected],
                          "selected_paths": sorted({c["path"] for c in selected}),
                          "context_chars": report["context"]["used_chars"],
                          "usage": report["usage"], "suggestions": len(findings),
                          "prose_edits_for_review": len(report["improvements"]["accepted"]),
                          "warnings": report["warnings"],
                          "necessary_evidence_coverage": report["necessary_evidence_coverage"],
                          "failed_requests": sum(c["status"] == "error" for c in report["calls"])}
        for number, finding in enumerate(findings, 1):
            reviews.append({"review_id": f"{strategy}-{number}", "arm": strategy,
                            "title": finding["title"], "evidence": finding["evidence"],
                            "impact": finding["impact"], "suggestion": finding["suggestion"],
                            "human_correct": None, "human_evidence_supports_claim": None,
                            "human_actionable": None, "reviewer": None, "notes": ""})
        for number, edit in enumerate(report["improvements"]["accepted"], 1):
            edit_reviews.append({"review_id": f"{strategy}-edit-{number}", "arm": strategy, "edit": edit,
                                 "human_correct": None, "human_preserves_meaning": None,
                                 "human_actionable": None, "reviewer": None, "notes": ""})
    lexical, ai = set(arms["lexical"]["selected_ids"]), set(arms["ai"]["selected_ids"])
    summary = {"schema_version": "tutorial-comparison-1", "evidence_kind": kind,
               "completed_at": datetime.now(timezone.utc).isoformat(), "snapshot_id": snapshot.snapshot_id,
               "arms": arms, "context_overlap": {"shared_ids": sorted(lexical & ai),
                                                   "lexical_only_ids": sorted(lexical - ai),
                                                   "ai_only_ids": sorted(ai - lexical)},
               "model_requests": sum(a["usage"]["requests"] for a in arms.values()),
               "run_status": "partial" if any(a["warnings"] or a["failed_requests"] for a in arms.values()) else "completed",
               "quality_review_status": "not_reviewed", "quality_winner": None,
               "limitations": ["同一快照、候选集、分析提示词及最终证据字符上限；总 token 预算未匹配。",
                               "单次运行顺序已记录；未控制服务端缓存和采样波动。",
                               "发现数量及补丁数量不是准确率；需要独立人工标注和读者任务评估。"]}
    _dump(output / "comparison.json", summary)
    _dump(output / "review-template.json", {"status": "unreviewed", "evidence_kind": kind,
                                           "items": reviews, "edits": edit_reviews})
    rows = []
    for name, arm in arms.items():
        usage = arm["usage"]
        values = [name, arm["actual_strategy"], usage["requests"], usage["input_tokens"],
                  usage["output_tokens"], usage["duration_seconds"], arm["context_chars"],
                  arm["suggestions"], arm["prose_edits_for_review"]]
        rows.append("<tr>" + "".join(f"<td>{escape(str(v) if v is not None else '未知')}</td>" for v in values) + "</tr>")
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>上下文策略对照</title><style>body{max-width:1100px;margin:40px auto;padding:20px;'
            'font:16px/1.6 system-ui}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style>'
            '<h1>上下文策略对照</h1><p>结果尚未人工评审，无法据此判定质量收益。</p>'
            f'<p>证据类型：{escape(kind)} · 状态：{escape(summary["run_status"])} · 相同快照：{snapshot.snapshot_id}</p>'
            '<table><tr><th>请求策略</th><th>实际策略</th><th>请求数</th><th>输入 token</th>'
            '<th>输出 token</th><th>推理秒数</th><th>证据字符</th><th>建议数</th><th>文字补丁数</th></tr>'
            + ''.join(rows) + '</table><p><a href="lexical/analysis.html">规则检索报告</a> · '
            '<a href="ai/analysis.html">AI 选择报告</a></p>'
            + ''.join(f'<p>{escape(x)}</p>' for x in summary["limitations"]) + '</html>')
    (output / "comparison.html").write_text(html, encoding="utf-8")
    return summary


def audit_comparison(output):
    try:
        result = _audit_comparison(output)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        result = {"status": "failed", "problems": ["Incomplete or malformed comparison evidence"],
                  "scope": "Internal consistency only; not an independent quality evaluation"}
    return result | {"quality_review_status": "not_assessed_by_audit", "quality_passed": None}


def _audit_comparison(output):
    """Verify frozen inputs, archived code and cost summaries without model calls."""
    from .providers import response_token_count
    output = Path(output)
    protocol = json.loads((output / "protocol.json").read_text())
    snapshot = json.loads((output / "snapshot.json").read_text())
    summary = json.loads((output / "comparison.json").read_text())
    problems = []
    if hashlib.sha256((output / "snapshot.json").read_bytes()).hexdigest() != protocol["snapshot_sha256"]:
        problems.append("snapshot.json hash differs from protocol")
    hashes = {}
    for name, item in snapshot["files"].items():
        raw = (b"\xef\xbb\xbf" if item.get("utf8_bom") else b"") + item["text"].encode("utf-8")
        hashes[name] = hashlib.sha256(raw).hexdigest()
        if hashes[name] != item["sha256"] or len(raw) != item["bytes"]:
            problems.append(f"Snapshot file bytes do not match: {name}")
    snapshot_id = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    if any(record.get("snapshot_id") != snapshot_id for record in (snapshot, protocol, summary)):
        problems.append("Snapshot IDs differ")
    for name, expected in protocol["implementation_sha256"].items():
        # Never resolve paths from an untrusted protocol outside its archive.
        if Path(name).name != name or not name.endswith(".py"):
            problems.append("Unsafe implementation path in protocol")
            continue
        path = output / "implementation/exampleproof" / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"Implementation hash mismatch: {name}")
    requests, reference_candidates = 0, None
    for strategy in ("lexical", "ai"):
        report = json.loads((output / strategy / "analysis.json").read_text())
        review = report.get("cloud_review")
        if review:
            from .tutorial_privacy import _digest
            if (review != protocol.get("cloud_review") or _digest(review["review"]) != review["sha256"]
                    or review["review"]["snapshot_id"] != snapshot_id):
                problems.append(f"{strategy}: cloud approval record differs")
        calls = report["calls"]
        requests += len(calls)
        arm = summary["arms"][strategy]
        candidates = report["context"]["candidate_ids"]
        if protocol.get("evidence_requirements") is not None:
            from .tutorial_coverage import measure_coverage
            chunks = tuple(tutorial.Chunk(**c) for c in snapshot["chunks"])
            by_id = {c.id: c for c in chunks}
            frozen = tutorial.ProjectSnapshot(snapshot["project"], snapshot["files"], snapshot["skipped"],
                                              chunks, tuple(by_id[i] for i in candidates), (), False, snapshot_id,
                                              protocol.get("evidence_scope", {}))
            selected = [by_id[c["id"]] for c in report["context"]["selected"]]
            before_budget = [by_id[i] for i in report["context"]["pre_budget_ids"]]
            expected_coverage = measure_coverage(frozen, selected, protocol["evidence_requirements"],
                                                 report["context"].get("selector_shown_ids"),
                                                 before_budget=before_budget, actual_strategy=report["context"]["actual"])
            if (report.get("necessary_evidence_coverage") != expected_coverage or
                    arm.get("necessary_evidence_coverage") != expected_coverage):
                problems.append(f"{strategy}: necessary evidence coverage differs from frozen annotations")
        if reference_candidates is None:
            reference_candidates = candidates
        elif candidates != reference_candidates:
            problems.append("Candidate sets differ between arms")
        for chunk in report["context"]["selected"]:
            item = snapshot["files"].get(chunk["path"])
            expected = "".join(item["text"].splitlines(keepends=True)[chunk["start_line"] - 1:chunk["end_line"]]) if item else None
            if chunk["text"] != expected:
                problems.append(f"{strategy}: selected evidence differs from snapshot")
        evidence_ids = {chunk["id"] for chunk in report["context"]["selected"]}
        for finding in report["findings"]:
            for evidence in finding["evidence"]:
                item = snapshot["files"].get(evidence["path"])
                expected = "".join(item["text"].splitlines(keepends=True)[evidence["start_line"] - 1:evidence["end_line"]]) if item else None
                if finding["origin"] == "static" and expected is not None:
                    expected = expected.rstrip("\r\n")
                if evidence["text"] != expected or (finding["origin"] != "static" and evidence["id"] not in evidence_ids):
                    problems.append(f"{strategy}: finding evidence differs from snapshot or selection")
        if report["coverage"].get("snapshot_id") != snapshot_id or arm.get("snapshot_id") != snapshot_id:
            problems.append(f"{strategy}: input snapshot differs")
        if report["context"]["actual"] != arm["actual_strategy"]:
            problems.append(f"{strategy}: strategy summary differs")
        if arm["usage"] != report["usage"] or report["usage"]["requests"] != len(calls):
            problems.append(f"{strategy}: usage summary differs")
        for field in ("input_tokens", "output_tokens"):
            counts = []
            for call in calls:
                inference = call.get("inference")
                response = inference.get("response") if inference else None
                count = response_token_count(response, field)
                # Synthetic clients may have explicitly supplied fixture counts.
                if protocol["evidence_kind"] == "live_model" and count != call.get(field):
                    problems.append(f"{strategy}: {field} differs from recorded service usage")
                counts.append(call.get(field))
            total = sum(counts) if counts and all(type(c) is int and c >= 0 for c in counts) else None
            if report["usage"][field] != total:
                problems.append(f"{strategy}: {field} total differs")
        if protocol["evidence_kind"] != report["mode"]:
            problems.append(f"{strategy}: evidence kind differs")
        for call in calls:
            if not call.get("inference"):
                continue
            payload = call["inference"]["request"]
            if protocol["evidence_kind"] != "live_model" and "model" not in payload:
                continue
            if payload.get("model") != protocol["model"]["name"]:
                problems.append(f"{strategy}: requested model differs")
            messages = payload.get("messages")
            system = messages[0].get("content") if messages else payload.get("system")
            expected_system = protocol["prompts"]["selection" if call["stage"] == "selection" else "analysis"]
            if system != expected_system:
                problems.append(f"{strategy}: system prompt differs from frozen protocol")
            if call["stage"] == "analysis":
                prompt = messages[1].get("content") if messages else payload.get("prompt")
                sent = json.loads(prompt)
                expected_evidence = report["context"]["selected"]
                if review:
                    permitted = {c["id"]: c for c in review["review"]["permitted_evidence"]}
                    expected_evidence = [permitted[c["id"]] for c in expected_evidence]
                if sent.get("evidence") != expected_evidence:
                    problems.append(f"{strategy}: analysis request evidence differs from report")
            elif call["stage"] == "selection" and review:
                from .tutorial_privacy import selection_summary
                prompt = messages[1].get("content") if messages else payload.get("prompt")
                permitted = {c["id"]: c for c in review["review"]["permitted_evidence"]}
                shown = set(report["context"].get("selector_shown_ids") or ())
                expected_summaries = [selection_summary(permitted[i]) for i in candidates if i in shown]
                if json.loads(prompt).get("candidates") != expected_summaries:
                    problems.append(f"{strategy}: selection request differs from approved excerpts")
    if requests != summary["model_requests"] or requests > protocol["max_model_requests"]:
        problems.append("Model request totals differ or exceed frozen limit")
    return {"status": "failed" if problems else "passed", "problems": problems,
            "evidence_kind": protocol["evidence_kind"], "snapshot_id": snapshot_id,
            "scope": "Internal evidence consistency only; no independent quality review or server attestation"}
