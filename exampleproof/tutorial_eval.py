"""Frozen task evaluation with independent review gates and no inferred quality scores."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time

from .config import safe_path
from .tutorial_budget import validate_limits
from .tutorial import prepare_project, analyze_snapshot, write_analysis
from .tutorial_scope import EvidenceScope


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(root):
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("Evidence cannot contain symlinks")
    return {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in files if p.relative_to(root).as_posix() != "seal.json"}


def seal(root):
    value = manifest(root)
    dump(root / "seal.json", {"files": value, "sha256": digest(json.dumps(value, sort_keys=True).encode())})


def verify(root):
    record = json.loads((root / "seal.json").read_text())
    value = manifest(root)
    if value != record["files"] or digest(json.dumps(value, sort_keys=True).encode()) != record["sha256"]:
        raise ValueError("Frozen evaluation inputs or implementation changed")
    return record["sha256"]


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value):
        raise ValueError("Identifiers must use lowercase letters, digits, underscores or hyphens")
    return value


def freeze(spec, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Evaluation output must be new")
    if (spec.get("schema_version") != "tutorial-task-evaluation-1" or not spec.get("projects")
            or not spec.get("cases") or len(spec["cases"]) > 100):
        raise ValueError("Invalid task evaluation specification")
    context_chars = spec.get("context_chars", 12000)
    if type(context_chars) is not int or not 2000 <= context_chars <= 48000:
        raise ValueError("Invalid evaluation context budget")
    limits = spec.get("limits", {"max_retrieval_rounds": 3, "max_total_tokens": 32000, "deadline_seconds": 120})
    if set(limits) != {"max_retrieval_rounds", "max_total_tokens", "deadline_seconds"}:
        raise ValueError("Evaluation must freeze every retrieval and runtime limit")
    from .tutorial_retrieval import validate_round_limit
    validate_round_limit(limits["max_retrieval_rounds"])
    validate_limits(limits["max_total_tokens"], limits["deadline_seconds"])
    for name in spec["projects"]:
        _id(name)
    strategies = spec.get("strategies", ["lexical", "iterative"])
    if (not isinstance(strategies, list) or len(set(strategies)) != len(strategies) or not strategies
            or not set(strategies) <= {"lexical", "iterative", "direct", "documentation_only"}):
        raise ValueError("Invalid or duplicate evaluation strategies")
    roots = {name: Path(item["root"]).resolve() for name, item in spec["projects"].items()}
    if any(output.resolve().is_relative_to(root) for root in roots.values()):
        raise ValueError("Evaluation output must be outside all projects")
    scope = EvidenceScope(**spec.get("scope", {"include_tests": True}))
    snapshots = {name: prepare_project(root, spec["projects"][name]["provenance"], scope=scope)
                 for name, root in roots.items()}
    seen, cases = set(), []
    for case in spec["cases"]:
        cid = _id(case["id"])
        if cid in seen or case["project"] not in snapshots or not isinstance(case.get("task"), str) or not 0 < len(case["task"]) <= 2000:
            raise ValueError("Invalid or repeated evaluation task")
        seen.add(cid)
        snapshot = snapshots[case["project"]]
        spans = case.get("required_evidence", [])
        if not spans or not isinstance(case.get("acceptance"), str) or not case["acceptance"].strip():
            raise ValueError("Task needs evidence and explicit acceptance criteria")
        annotated = []
        for span in spans:
            item = snapshot.files.get(span.get("path"))
            first, last = span.get("start_line"), span.get("end_line")
            if (item is None or type(first) is not int or type(last) is not int
                    or not 1 <= first <= last <= len(item["text"].splitlines())):
                raise ValueError("Required evidence must refer to exact frozen input lines")
            text = "".join(item["text"].splitlines(keepends=True)[first - 1:last])
            annotated.append(dict(span, sha256=digest(text.encode())))
        gold = case.get("gold_issues", [])
        if not isinstance(gold, list) or len({_id(g["id"]) for g in gold}) != len(gold):
            raise ValueError("Gold issues need unique identifiers")
        cases.append({"id": cid, "project": case["project"], "task": case["task"],
                      "acceptance": case["acceptance"], "required_evidence": annotated, "gold_issues": gold})
    output.mkdir(parents=True)
    for name, snapshot in snapshots.items():
        _id(name)
        for relative, item in snapshot.files.items():
            target = output / "inputs" / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((b"\xef\xbb\xbf" if item["utf8_bom"] else b"") + item["text"].encode())
    source = Path(__file__).parent
    shutil.copytree(source, output / "implementation/exampleproof", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    script = source.parent / "scripts/run_tutorial_evaluation.py"
    scripts = {script.name: digest(script.read_bytes())} if script.is_file() else {}
    if script.is_file():
        (output / "implementation/scripts").mkdir()
        shutil.copyfile(script, output / "implementation/scripts" / script.name)
    license_path = source.parent / "LICENSE"
    if license_path.is_file():
        shutil.copyfile(license_path, output / "implementation/LICENSE")
    protocol = {"schema_version": "tutorial-task-evaluation-1", "frozen_at": datetime.now(timezone.utc).isoformat(),
                "annotation_origin": "assistant_draft_pending_independent_human_review",
                "review_schema": spec.get("review_schema", 1),
                "scope": scope.record(), "cases": cases,
                "projects": {n: {"provenance": s.provenance, "snapshot_id": s.snapshot_id} for n, s in snapshots.items()},
                "strategies": strategies, "context_chars": context_chars,
                "controls": {"direct": "Same task, candidate excerpts and character cap as lexical; generic prompt, no static rules or counter-evidence triage.",
                             "documentation_only": "Document subset of lexical candidates; same grounded prompt. Source/config omitted; actual token differences reported."},
                "model": spec.get("model", {"provider": "deepseek", "name": "deepseek-flash"}),
                "limits": limits, "request_settings": {"temperature": 0, "max_output_tokens": 2048, "socket_timeout_seconds": 60},
                "review": "Independent reviewer must approve the frozen tasks, evidence and complete gold issue inventory before model calls.",
                "cost_comparison": "Same task, scope and character cap; actual request and token costs reported separately, not equal-cost claims.",
                "implementation_scripts_sha256": scripts,
                "implementation_sha256": {p.name: digest(p.read_bytes()) for p in source.glob("*.py")}}
    dump(output / "protocol.json", protocol)
    seal(output)
    return {"seal": verify(output), "cases": len(cases), "status": "independent_review_pending"}


def check_review(review, expected_seal, cases=None):
    if (review.get("seal") != expected_seal or review.get("approved") is not True
            or review.get("independent_human") is not True or review.get("authored_candidates_or_annotations") is not False
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or review.get("complete_gold_inventory") is not True):
        raise ValueError("Independent human preflight review of this seal is required; no model calls started")
    if cases is not None:
        records = review.get("cases", [])
        expected = {c["id"] for c in cases}
        if len(records) != len(expected) or {r.get("id") for r in records} != expected:
            raise ValueError("Human preflight must cover every task exactly once")
        for record in records:
            if (any(record.get(k) is not True for k in ("task_valid", "evidence_sufficient", "gold_inventory_complete", "source_reviewed"))
                    or not isinstance(record.get("rationale"), str) or not record["rationale"].strip()
                    or record.get("amendments", "")):
                raise ValueError("Each task needs explicit source, task, evidence and complete gold review with rationale")


def run(frozen, output, review, client_factory):
    frozen, output = Path(frozen), Path(output)
    identity = verify(frozen)
    protocol = json.loads((frozen / "protocol.json").read_text())
    check_review(review, identity, protocol["cases"] if protocol.get("review_schema") == 2 else None)
    current = {p.name: digest(p.read_bytes()) for p in Path(__file__).parent.glob("*.py")}
    for name, expected in protocol.get("implementation_scripts_sha256", {}).items():
        script = Path(__file__).parent.parent / "scripts" / name
        if not script.is_file() or digest(script.read_bytes()) != expected:
            raise ValueError("Evaluation driver changed after freeze")
    if current != protocol["implementation_sha256"]:
        raise ValueError("Use the frozen implementation or freeze a new evaluation")
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(frozen.resolve()):
        raise ValueError("Evaluation run must use a fresh directory outside frozen inputs")
    scope = EvidenceScope(**protocol["scope"])
    prepared, preflight_errors = [], []
    # Complete all preflights before calling any model, including cloud approvals.
    for case in protocol["cases"]:
        project = protocol["projects"][case["project"]]
        snapshot = prepare_project(frozen / "inputs" / case["project"], project["provenance"], scope=scope, task=case["task"])
        if snapshot.snapshot_id != project["snapshot_id"]:
            raise ValueError("Evaluation snapshot changed")
        requirements = {"schema_version": "tutorial-evidence-requirements-1", "snapshot_id": snapshot.snapshot_id,
                        "evidence_kind": "human_annotation", "annotator": review["reviewer"],
                        "cases": [{"id": case["id"], "task": case["task"], "required": case["required_evidence"]}]}
        clients = {}
        for strategy in protocol["strategies"]:
            try:
                clients[strategy] = client_factory(case, snapshot, strategy, protocol)
            except ValueError as exc:
                preflight_errors.append(f"{case['id']}/{strategy}: {exc}")
        if len(clients) != len(protocol["strategies"]):
            continue
        if any(c.provider != protocol["model"]["provider"] or c.model != protocol["model"]["name"] for c in clients.values()):
            raise ValueError("Provider/model differs from frozen protocol")
        for client in clients.values():
            transport = getattr(client, "_client", client)
            if client.provider in {"deepseek", "ollama"}:
                settings = protocol["request_settings"]
                if (transport.timeout != settings["socket_timeout_seconds"]
                        or transport.options.get("temperature") != settings["temperature"]
                        or transport.options.get("num_predict") != settings["max_output_tokens"]):
                    raise ValueError("Generation settings differ from frozen protocol")
        prepared.append((case, snapshot, requirements, clients))
    if preflight_errors:
        raise ValueError("\n".join(preflight_errors))
    output.mkdir(parents=True)
    dump(output / "preflight-review.json", review)
    dump(output / "protocol.json", protocol)
    rows, review_rows = [], []
    for index, (case, snapshot, requirements, clients) in enumerate(prepared):
        offset = index % len(protocol["strategies"])
        order = protocol["strategies"][offset:] + protocol["strategies"][:offset]
        for strategy in order:
            started = time.monotonic()
            report = analyze_snapshot(snapshot, client=clients[strategy], strategy=strategy,
                                      context_chars=protocol["context_chars"], evidence_requirements=requirements, task_comparison=True,
                                      **protocol["limits"])
            write_analysis(output / case["id"] / strategy, report)
            report_path = output / case["id"] / strategy / "analysis.json"
            rows.append({"case": case["id"], "strategy": strategy, "snapshot_id": snapshot.snapshot_id,
                         "task": case["task"], "usage": report["usage"], "elapsed_seconds": time.monotonic() - started,
                         "warnings": report["warnings"], "coverage": report["necessary_evidence_coverage"],
                         "report_sha256": digest(report_path.read_bytes())})
            review_rows.append({"case": case["id"], "strategy": strategy,
                                "findings": [{"index": i, "finding_id": finding.get("id"), "judgment": None,
                                              "gold_ids": [], "reason": None, "factual_relation": None}
                                             for i, finding in enumerate(report["findings"])],
                                "reader_task": {"completed": None, "elapsed_seconds": None, "participant": None}})
    dump(output / "results.json", {"seal": identity, "status": "quality_review_pending", "rows": rows})
    dump(output / "quality-review-template.json", {"reviewer": None, "independent_human": False, "rows": review_rows})
    seal(output)
    return {"status": "quality_review_pending", "runs": len(rows)}


def summarize(frozen, run_dir, review=None, observations=None):
    verify(Path(frozen))
    verify(Path(run_dir))
    protocol = json.loads((Path(frozen) / "protocol.json").read_text())
    result = json.loads((Path(run_dir) / "results.json").read_text())
    if result["seal"] != verify(Path(frozen)):
        raise ValueError("Run does not belong to this evaluation")
    empty = {"status": "independent_quality_review_pending", "support_rate": None, "unsupported_rate": None,
             "issue_recall": None, "reader_task_completion_rate": None}
    operations = operational_metrics(protocol, result, run_dir)
    readers = reader_metrics(protocol, result["seal"], observations)
    if review is None:
        return empty | {"operational_metrics": operations, "reader_observations": readers}
    if review.get("independent_human") is not True or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ValueError("Quality scores require an identified independent human reviewer")
    rows = review.get("rows", [])
    expected = {(r["case"], r["strategy"]): r for r in result["rows"]}
    if len(rows) != len(expected) or {(r["case"], r["strategy"]) for r in rows} != set(expected):
        raise ValueError("Review must cover every run exactly once")
    gold = {c["id"]: {g["id"] for g in c["gold_issues"]} for c in protocol["cases"]}
    metrics = {}
    for strategy in protocol["strategies"]:
        judgments, matched, gold_count, tasks, durations = [], 0, 0, [], []
        unavailable = 0
        for row in (r for r in rows if r["strategy"] == strategy):
            report_path = safe_path(Path(run_dir), f"{row['case']}/{strategy}/analysis.json", max_bytes=16_000_000)
            report = json.loads(report_path.read_text())
            if digest(report_path.read_bytes()) != expected[(row["case"], strategy)]["report_sha256"]:
                raise ValueError("Reviewed report changed")
            if any(c["status"] == "error" for c in report["calls"]):
                unavailable += 1
                continue
            findings = row["findings"]
            if len(findings) != len(report["findings"]) or {f["index"] for f in findings} != set(range(len(findings))):
                raise ValueError("Review must assess every finding exactly once")
            found = set()
            for finding in findings:
                judgment = finding["judgment"]
                if (judgment not in {"supported", "partial", "unsupported", "unassessable"}
                        or not isinstance(finding.get("reason"), str) or not finding["reason"].strip()
                        or not set(finding["gold_ids"]) <= gold[row["case"]]):
                    raise ValueError("Every judgment needs rationale and valid frozen gold identifiers")
                from .tutorial_findings import MISSING
                actual = report["findings"][finding["index"]]
                absence_claim = bool(MISSING.search(" ".join(actual.get(k, "") for k in ("title", "impact", "suggestion"))))
                if (absence_claim and finding.get("factual_relation") in {"already_documented", "contradicted"}
                        and judgment == "supported"):
                    raise ValueError("An absence claim contradicted by existing documentation cannot be supported")
                judgments.append(judgment)
                if judgment == "supported":
                    found.update(finding["gold_ids"])
            matched += len(found)
            gold_count += len(gold[row["case"]])
            observation = row["reader_task"]
            if observation["completed"] is not None:
                elapsed = observation["elapsed_seconds"]
                if (type(observation["completed"]) is not bool or type(elapsed) not in {int, float}
                        or not math.isfinite(elapsed) or elapsed < 0 or not observation.get("participant")):
                    raise ValueError("Reader observation needs participant, completion and finite measured duration")
                tasks.append(observation["completed"])
                durations.append(elapsed)
        metrics[strategy] = {**operations[strategy], "findings": len(judgments), "unavailable_runs": unavailable,
                             "quality_denominators_complete": unavailable == 0,
                             "support_rate": judgments.count("supported") / len(judgments) if judgments and not unavailable else None,
                             "unsupported_rate": judgments.count("unsupported") / len(judgments) if judgments and not unavailable else None,
                             "judgments": {j: judgments.count(j) for j in ("supported", "partial", "unsupported", "unassessable")},
                             "matched_gold_issues": matched, "gold_issues": gold_count,
                             "issue_recall": matched / gold_count if gold_count and not unavailable else None,
                             "reader_tasks_observed": len(tasks),
                             "reader_task_completion_rate": sum(tasks) / len(tasks) if tasks else None,
                             "reader_task_mean_seconds": sum(durations) / len(durations) if durations else None}
    return {"status": "human_review_recorded", "reviewer": review["reviewer"], "metrics": metrics,
            "reader_observations": readers,
            "limits": "Reviewer declarations are not identity authentication; small sample, no statistical or population claim."}


def reader_metrics(protocol, seal, record=None):
    """Keep actual human observations separate from model costs and machine checks."""
    empty = {"status": "not_observed", "by_condition": {}, "observations": []}
    if record is None:
        return empty
    if (record.get("schema_version") != "reader-observations-1" or record.get("seal") != seal
            or record.get("origin") != "human_observation" or not isinstance(record.get("observations"), list)):
        raise ValueError("Reader observations must identify the frozen study and actual human observation")
    valid_cases = {c["id"] for c in protocol["cases"]}
    grouped, identities = {}, set()
    for row in record["observations"]:
        duration, help_count = row.get("elapsed_seconds"), row.get("help_count")
        if (row.get("case") not in valid_cases or row.get("condition") not in {"original", "tool_assisted", "candidate"}
                or type(row.get("completed")) is not bool
                or type(duration) not in {int, float} or not math.isfinite(duration) or duration <= 0
                or type(help_count) is not int or help_count < 0
                or any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("participant", "notes", "observed_at"))):
            raise ValueError("Reader observations need a known task, condition, participant, measured duration and notes")
        identity = (row["participant"], row["case"], row["condition"], row["observed_at"])
        if identity in identities:
            raise ValueError("Duplicate reader observation")
        identities.add(identity)
        grouped.setdefault(row["condition"], []).append(row)
    if not identities:
        return empty
    return {"status": "human_observations_recorded", "observations": record["observations"],
            "by_condition": {condition: {"observations": len(rows),
                "participants": len({r["participant"] for r in rows}),
                "completion_rate": sum(r["completed"] for r in rows) / len(rows),
                "mean_elapsed_seconds": sum(r["elapsed_seconds"] for r in rows) / len(rows),
                "mean_help_count": sum(r["help_count"] for r in rows) / len(rows)} for condition, rows in grouped.items()},
            "limits": "Descriptive observations only; conditions and repeated participants are not randomized."}


def operational_metrics(protocol, result, run_dir):
    """Always report measured cost/latency; unreviewed quality remains unknown."""
    metrics = {}
    expected_pairs = {(c["id"], s) for c in protocol["cases"] for s in protocol["strategies"]}
    rows = result["rows"]
    if len(rows) != len(expected_pairs) or {(r["case"], r["strategy"]) for r in rows} != expected_pairs:
        raise ValueError("Evaluation run is missing or duplicates task/strategy results")
    for strategy in protocol["strategies"]:
        selected = [r for r in rows if r["strategy"] == strategy]
        for row in selected:
            path = safe_path(Path(run_dir), f"{row['case']}/{strategy}/analysis.json", max_bytes=16_000_000)
            if digest(path.read_bytes()) != row["report_sha256"]:
                raise ValueError("Evaluation report changed")
        def total(key):
            values = [r["usage"].get(key) for r in selected]
            return sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
        metrics[strategy] = {"task_runs": len(selected), "requests": total("requests"),
            "input_tokens": total("input_tokens"), "output_tokens": total("output_tokens"),
            "total_tokens": total("input_tokens") + total("output_tokens") if total("input_tokens") is not None and total("output_tokens") is not None else None,
            "analysis_total_seconds": sum(r["elapsed_seconds"] for r in selected),
            "analysis_mean_seconds": sum(r["elapsed_seconds"] for r in selected) / len(selected),
            "per_task": [{"case": r["case"], "usage": r["usage"], "elapsed_seconds": r["elapsed_seconds"],
                          "warnings": r["warnings"], "necessary_evidence_coverage": r["coverage"]} for r in selected],
            "support_rate": None, "unsupported_rate": None, "issue_recall": None,
            "reader_task_completion_rate": None, "reader_task_mean_seconds": None}
    return metrics
