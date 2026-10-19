"""Measure annotated necessary evidence, without inferring suggestion quality."""

from collections import Counter
from pathlib import PurePosixPath


def validate_requirements(value, snapshot):
    if (not isinstance(value, dict) or value.get("schema_version") != "tutorial-evidence-requirements-1"
            or value.get("snapshot_id") != snapshot.snapshot_id
            or value.get("evidence_kind") not in {"human_annotation", "synthetic_fixture"}
            or not isinstance(value.get("annotator"), str) or not value["annotator"].strip()
            or not isinstance(value.get("cases"), list) or not 1 <= len(value["cases"]) <= 1000):
        raise ValueError("Invalid evidence requirements or snapshot mismatch")
    ids = set()
    for case in value["cases"]:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]
                or case["id"] in ids or not isinstance(case.get("required"), list)
                or not 1 <= len(case["required"]) <= 100):
            raise ValueError("Each evidence case needs a unique ID and required spans")
        ids.add(case["id"])
        if "task" in case and (not isinstance(case["task"], str) or not case["task"].strip()
                               or len(case["task"]) > 2000):
            raise ValueError("Annotated tasks must be non-empty strings of at most 2000 characters")
        for span in case["required"]:
            if not isinstance(span, dict) or not isinstance(span.get("path"), str):
                raise ValueError("Invalid required evidence span")
            path = PurePosixPath(span["path"])
            if (path.is_absolute() or ".." in path.parts or "\\" in span["path"]
                    or str(path) != span["path"]
                    or type(span.get("start_line")) is not int or type(span.get("end_line")) is not int
                    or not 1 <= span["start_line"] <= span["end_line"]):
                raise ValueError("Required spans need relative paths and positive line ranges")


def _covered(span, chunks):
    next_line = span["start_line"]
    for chunk in sorted((c for c in chunks if c.path == span["path"]), key=lambda c: c.start_line):
        if chunk.start_line > next_line:
            break
        if chunk.end_line >= next_line:
            next_line = chunk.end_line + 1
        if next_line > span["end_line"]:
            return True
    return False


def _role(path):
    path = PurePosixPath(path)
    if any(p in {"test", "tests"} for p in path.parts[:-1]) or path.name.startswith("test_") and path.suffix.lower() == ".py":
        return "test"
    if path.suffix.lower() in {".md", ".mdx", ".rst"}:
        return "document"
    if path.name.lower() in {"dockerfile", "containerfile", "makefile", "gnumakefile"}:
        return "build"
    if path.suffix.lower() in {".toml", ".json", ".yaml", ".yml", ".ini", ".cfg"} or path.name in {"go.mod", "requirements.txt"}:
        return "configuration"
    return "other_source"


def _diagnose(span, snapshot, coverage, before_budget, actual_strategy):
    """Attribute observable loss stages, never infer why a ranker/model chose."""
    from .project_input import eligible
    from .tutorial_scope import EvidenceScope
    diagnostic = {"status": "covered", "first_gap": None, "path_role": _role(span["path"])}
    item = snapshot.files.get(span["path"])
    if item is not None and span["end_line"] > len(item["text"].splitlines()):
        return diagnostic | {"status": "invalid_annotation", "first_gap": "annotation_out_of_range"}
    if coverage["selected"]:
        return diagnostic
    if item is None:
        scope = EvidenceScope(**snapshot.evidence_scope)
        gap = "input_policy_exclusion" if not eligible(span["path"], scope) else "input_not_indexed_unknown"
    elif not coverage["indexed"]:
        gap = "chunk_index_omission"
    elif not coverage["candidates"] and not coverage.get("available_after_retrieval", False):
        gap = "not_retrieved_from_index" if actual_strategy == "iterative" else "candidate_pool_omission"
    elif actual_strategy == "ai" and coverage.get("shown_to_selector") is False:
        gap = "selector_visibility_limit"
    elif before_budget is None:
        gap = "final_context_omission_unknown"
    elif not coverage["before_budget"]:
        gap = ("ai_selection_omission" if actual_strategy == "ai" else "iterative_context_selection_omission"
               if actual_strategy == "iterative" else "pre_budget_omission_unknown")
    else:
        gap = "context_budget_omission"
    return diagnostic | {"status": "uncovered", "first_gap": gap}


def _distribution(spans):
    diagnostics = [s["diagnostic"] for s in spans]
    missing = [d for d in diagnostics if d["status"] == "uncovered"]
    return {"total_spans": len(spans),
            "covered_spans": sum(d["status"] == "covered" for d in diagnostics),
            "uncovered_spans": len(missing),
            "invalid_annotation_spans": sum(d["status"] == "invalid_annotation" for d in diagnostics),
            "by_first_gap": dict(sorted(Counter(d["first_gap"] for d in missing).items()))}


def measure_coverage(snapshot, selected, requirements=None, shown_ids=None, *, before_budget=None, actual_strategy=None,
                     retrieved=None):
    result = {"schema_version": "tutorial-evidence-coverage-2", "status": "not_measured",
              "evidence_kind": None, "annotator": None, "omissions": None,
              "cases": [], "stages": {},
              "scope": "Source span presence only; redaction may remove information. "
                       "Not correctness, issue recall or learning efficiency"}
    if requirements is None:
        return result
    validate_requirements(requirements, snapshot)
    groups = {"indexed": snapshot.chunks, "candidates": snapshot.candidates, "selected": selected}
    if retrieved is not None:
        groups["retrieved"] = retrieved
        groups["available_after_retrieval"] = list(snapshot.candidates) + list(retrieved)
    if before_budget is not None:
        groups["before_budget"] = before_budget
    if shown_ids is not None:
        groups["shown_to_selector"] = [c for c in snapshot.candidates if c.id in shown_ids]
    rows = []
    for case in requirements["cases"]:
        spans = [dict(span, coverage={stage: _covered(span, chunks) for stage, chunks in groups.items()})
                 for span in case["required"]]
        for span in spans:
            span["diagnostic"] = _diagnose(span, snapshot, span["coverage"], before_budget, actual_strategy)
        rows.append({"id": case["id"], "task": case.get("task"), "required": spans,
                     "valid_annotation": all(s["diagnostic"]["status"] != "invalid_annotation" for s in spans),
                     "omissions": _distribution(spans),
                     "complete": {stage: all(s["coverage"][stage] for s in spans) for stage in groups}})
    valid_spans = [s for row in rows for s in row["required"] if s["diagnostic"]["status"] != "invalid_annotation"]
    valid_rows = [row for row in rows if row["valid_annotation"]]
    stages = {stage: {"covered_spans": sum(s["coverage"][stage] for s in valid_spans),
                      "total_spans": len(valid_spans), "complete_cases": sum(row["complete"][stage] for row in valid_rows),
                      "total_cases": len(valid_rows)} for stage in groups}
    spans = [span for row in rows for span in row["required"]]
    omissions = _distribution(spans) | {
        "unit": "annotated_span_occurrence", "causal_conclusions": "not_established",
        "by_path_role": {role: _distribution([s for s in spans if s["diagnostic"]["path_role"] == role])
                         for role in sorted({s["diagnostic"]["path_role"] for s in spans})},
        "limitations": ["Policy exclusion describes configured eligibility; excluded paths were not read.",
                        "Input-not-indexed and chunk omissions do not identify a unique filesystem/limit cause.",
                        "Candidate omission does not establish task-query mismatch; AI omission does not establish semantic error."]}
    return result | {"status": "measured", "evidence_kind": requirements["evidence_kind"],
                     "annotator": requirements["annotator"], "cases": rows, "stages": stages, "omissions": omissions}
