#!/usr/bin/env python3
"""Independently audit saved study evidence; never call models or execute snippets.

Exit 0 means all declared cells and independent checks passed, 1 means evidence
inconsistency, and 2 means incomplete evidence. The final stdout item is JSON.
The local protocol seal detects changes, but is not external attestation.
"""

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import gzip
import itertools
import json
import math
from pathlib import Path
import re
import sys


REPOSITORY = Path(__file__).resolve().parents[1]
WITHHELD = "Execution did not pass configured behavior checks; evaluator details are withheld."


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inventory(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(actual, expected, label):
    require(actual == expected, label + " differs")


def nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def feedback(execution):
    """Independent policy check: return only execution status and sanitized error."""
    if execution is None:
        return None
    error = execution["stderr"]
    if ((execution["oracle"] == "configured_behavior_checks" and execution["returncode"] != 21)
            or execution["returncode"] == 22 or "external-checks" in error
            or "Expected stdout did not match the configured oracle." in error):
        error = WITHHELD
    return {"status": execution["status"], "error": error[-8000:]}


def categorized_feedback(execution):
    """Independently reconstruct the fixed, non-oracle diagnostic vocabulary."""
    value = feedback(execution)
    if value is None:
        return None
    hints = {
        "none": "No classified failure.",
        "example_exception": "The setup or example raised an exception before external checks.",
        "behavior_check": "A configured behavior check failed. Review documented types, transformation, scope, side effects and boundary behavior.",
        "stdout_mismatch": "Execution and configured behavior checks completed, but stdout differed. Preserve the documented output and avoid adding prints to silent expressions.",
        "timeout": "Execution exceeded its time budget.",
        "abnormal_exit": "Execution exited abnormally.",
        "incomplete_execution": "Execution did not complete the required stages normally.",
        "environment": "The isolated execution environment was unavailable.",
    }
    kind = execution.get("failure_kind")
    kind = kind if kind in hints else "unknown"
    return {**value, "category": kind,
            "guidance": hints.get(kind, "No reliable failure category is available.")}


def inspect_failure_kind(execution, spec):
    """Cross-check recorded host categories against status/stage/output facts."""
    if execution is None:
        return
    status, code, kind = execution["status"], execution["returncode"], execution.get("failure_kind")
    if status == "blocked":
        expected = "environment"
    elif status == "timeout":
        expected = "timeout"
    elif status == "passed":
        require(code == 0, "Passed execution has nonzero returncode")
        expected = "none"
    elif code == 21:
        expected = "example_exception"
    elif code == 22:
        expected = "behavior_check"
    elif code != 0:
        expected = "abnormal_exit"
    elif execution["stderr"].endswith("\nExecution did not complete setup, the example and external checks normally."):
        expected = "incomplete_execution"
    else:
        require("expected_stdout" in spec and execution["stdout"] != spec["expected_stdout"],
                "Stdout mismatch category lacks a recorded mismatch")
        require(execution["stderr"].endswith("\nExpected stdout did not match the configured oracle."),
                "Stdout mismatch lacks host receipt")
        expected = "stdout_mismatch"
    same(kind, expected, "Host failure category versus execution facts")


def history_record(attempt, categorized=False):
    proposal = attempt.get("proposal")
    return {"number": attempt["number"], "status": attempt["status"],
            "candidate": {"code": proposal["code"], "rationale": proposal["rationale"]} if proposal else None,
            "execution": (categorized_feedback if categorized else feedback)(attempt.get("after")),
            "rejection": attempt.get("rejection")}


def static_system_prompts(path):
    """Read string assignments/concatenations without importing archived code."""
    values = {}
    def expression(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return expression(node.left) + expression(node.right)
        raise ValueError("Unsupported static SYSTEM expression")
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"SYSTEM", "SYSTEM_V2"}:
                    values[target.id] = expression(node.value)
    return values


def inspect_context(context, sources, limit, *, version, standard=None):
    require(isinstance(context, dict), "Source context is not a mapping")
    require(sum(len(k) + len(v) for k, v in context.items()) <= limit,
            "Source context character budget exceeded")
    selected = set()
    pattern = r"(.+):(\d+)-(\d+)" + (r" \((signature|body excerpt)\)" if version == "legacy" else "")
    for label, excerpt in context.items():
        match = re.fullmatch(pattern, label)
        eligible = sources if standard is None else {**sources, **standard["sources"]}
        require(match is not None and match[1] in eligible, "Context is not from a selected source")
        start, end = int(match[2]), int(match[3])
        lines = eligible[match[1]].splitlines(keepends=True)
        require(1 <= start <= end <= len(lines), "Source context line range is invalid")
        same(excerpt, "".join(lines[start - 1:end]), "Context excerpt versus original source lines")
        if match[1] not in sources:
            require(any(filename == match[1] and indexed_start <= start <= end <= indexed_end
                        for filename, indexed_start, indexed_end, _, _ in standard["entries"]),
                    "Stdlib excerpt exceeds frozen signature/docstring index")
        if version == "v2":
            positions = {(match[1], line) for line in range(start, end + 1)}
            require(not selected & positions, "V2 source context contains duplicate lines")
            selected.update(positions)


def inspect_stdlib_index(archived_core, repository):
    """Read archived constants, independently compare every entry to raw source."""
    fields = {"STDLIB_PROVENANCE", "STDLIB_LICENSE", "STDLIB_FILE_NOTICES", "STDLIB_INDEX"}
    values = {}
    for node in ast.parse((archived_core / "stdlib_index.py").read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in fields:
                    values[target.id] = ast.literal_eval(node.value)
    same(set(values), fields, "Archived stdlib index fields")
    provenance = values["STDLIB_PROVENANCE"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", provenance["release"]) is not None, "Invalid indexed CPython release")
    resource = repository / "benchmarks/semantic_v2/resources" / ("cpython-" + provenance["release"])
    compressed = (resource / "stdlib-sources.json.gz").read_bytes()
    same(hashlib.sha256(compressed).hexdigest(), provenance["corpus_sha256"], "Original stdlib corpus hash")
    same(read(resource / "provenance.json"), provenance, "Original stdlib provenance")
    sources = json.loads(gzip.decompress(compressed))
    same({name: text_sha(text) for name, text in sources.items()}, provenance["source_sha256"], "Original stdlib file hashes")
    same(len(sources), provenance["module_count"], "Stdlib source module count")
    same((resource / "LICENSE").read_text(), values["STDLIB_LICENSE"], "Redistributed CPython license")
    same(text_sha(values["STDLIB_LICENSE"]), provenance["license_sha256"], "CPython license hash")
    expected = []
    for filename, text in sorted(sources.items()):
        require(re.fullmatch(r"stdlib/[A-Za-z][A-Za-z0-9_]*\.py", filename) is not None,
                "Stdlib candidate file is not a public flat module")
        lines = text.splitlines(keepends=True)
        for node in ast.parse(text).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                first = node.body[0]
                is_doc = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
                end = first.end_lineno if is_doc else max(node.lineno, first.lineno - 1)
                expected.append((filename, node.lineno, end, node.name, "".join(lines[node.lineno - 1:end])))
    same(values["STDLIB_INDEX"], tuple(expected), "Complete public stdlib AST index versus original corpus")
    return {"sources": sources, "entries": values["STDLIB_INDEX"], "provenance": provenance}


def inspect_retrieval_pools(context, example, before, sources, design):
    """Independently check missing-import trigger and separate char allocations."""
    policy = design["retrieval_policy"]
    same(policy["triggered_character_budget"], {"project": 4000, "stdlib": 2000}, "Declared retrieval allocation")
    same(policy["untriggered_project_character_budget"], 6000, "Declared project-only allocation")
    error = feedback(before)["error"]
    match = re.search(r"(?:^|\n)ImportError: cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]", error)
    triggered = False
    if match:
        symbol, module = match.groups()
        stem = module.replace(".", "/")
        if stem + ".py" in sources or stem + "/__init__.py" in sources:
            tree = ast.parse(example["code"])
            triggered = any(isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == module
                            and any(alias.name == symbol for alias in node.names) for node in ast.walk(tree))
    standard = {key: value for key, value in context.items() if key.startswith("stdlib/")}
    project = {key: value for key, value in context.items() if not key.startswith("stdlib/")}
    budget = policy["triggered_character_budget"] if triggered else {"project": 6000, "stdlib": 0}
    require(sum(len(k) + len(v) for k, v in standard.items()) <= budget["stdlib"], "Stdlib retrieval budget or trigger violated")
    require(sum(len(k) + len(v) for k, v in project.items()) <= budget["project"], "Project retrieval allocation violated")
    require(len(standard) <= 3, "Stdlib retrieval exceeds maximum three snippets")


def inspect_method_lock(design, plan):
    if design["split"] != "holdout":
        require("method_lock" not in design, "Development design must not use a holdout method lock")
        return
    locked = design.get("method_lock")
    require(isinstance(locked, dict), "Holdout method lock is missing")
    same(set(locked), {"sha256", "locked_at", "implementation_sha256", "design"}, "Method lock fields")
    original = {key: value for key, value in locked.items() if key != "sha256"}
    # The writer's canonical JSON is part of this experiment's local seal.
    same(text_sha(json.dumps(original, ensure_ascii=False, indent=2) + "\n"), locked["sha256"], "Embedded method lock seal")
    same(locked["implementation_sha256"], plan["implementation_sha256"], "Method lock implementation")
    same(locked["design"], {key: value for key, value in design.items() if key != "method_lock"}, "Method lock design")
    require(datetime.fromisoformat(locked["locked_at"]) <= datetime.fromisoformat(plan["frozen_at"]),
            "Method was locked after input freeze")


def inspect_split(metadata, design):
    same(metadata.get("split"), design["split"] + "_v2", "Project development/holdout split")
    if design["split"] == "holdout":
        provenance = metadata.get("provenance", {})
        require(metadata.get("selection", {}).get("held_out_from_method_optimization") is True,
                "Holdout project lacks method-optimization exclusion declaration")
        require(provenance.get("held_out") is not False
                and provenance.get("previous_cases_and_live_results_seen") is not True
                and provenance.get("live_model_evaluation") is not True,
                "Holdout provenance conflicts with held-out declaration")


def apply_saved_patch(documents, patch):
    """Apply a textual unified diff in memory, validating all original context.

    No shell, repository writes, library imports or candidate execution occur.
    """
    changed = dict(documents)
    lines = patch.splitlines(keepends=True)
    cursor = 0
    seen = set()
    while cursor < len(lines):
        require(lines[cursor].startswith("--- a/"), "Unexpected patch header")
        name = lines[cursor][6:].rstrip("\r\n")
        cursor += 1
        require(cursor < len(lines) and lines[cursor].rstrip("\r\n") == "+++ b/" + name, "Patch renames are not permitted")
        require(name in documents and name not in seen, "Patch path is not a unique selected document")
        seen.add(name)
        cursor += 1
        original = documents[name].splitlines(keepends=True)
        result, original_cursor = [], 0
        while cursor < len(lines) and not lines[cursor].startswith("--- a/"):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?", lines[cursor])
            require(match is not None, "Invalid unified-diff hunk")
            old_start, old_count, new_start, new_count = (int(x) if x is not None else 1 for x in match.groups())
            offset = old_start if old_count == 0 else old_start - 1
            require(original_cursor <= offset <= len(original), "Overlapping or out-of-range patch hunk")
            result.extend(original[original_cursor:offset])
            require(len(result) == (new_start if new_count == 0 else new_start - 1), "New hunk position differs")
            original_cursor = offset
            cursor += 1
            removed = added = 0
            while cursor < len(lines) and not lines[cursor].startswith(("@@ ", "--- a/")):
                line = lines[cursor]
                require(line[:1] in (" ", "+", "-"), "Invalid patch operation")
                operation, contents = line[0], line[1:]
                cursor += 1
                if cursor < len(lines) and lines[cursor].startswith("\\ No newline at end of file"):
                    contents = contents.rstrip("\r\n")
                    cursor += 1
                if operation in (" ", "-"):
                    require(original_cursor < len(original) and original[original_cursor] == contents, "Patch context does not match frozen document")
                    original_cursor += 1
                    removed += 1
                if operation in (" ", "+"):
                    result.append(contents)
                    added += 1
            same((removed, added), (old_count, new_count), "Patch hunk line counts")
        result.extend(original[original_cursor:])
        changed[name] = "".join(result)
    return changed


def audit_example(example, documents):
    """Check the stored code/context directly against the frozen Markdown lines."""
    name = example["path"]
    require(name in documents, "Example path is not a selected document")
    lines = documents[name].removeprefix("\ufeff").splitlines(keepends=True)
    opening = example["start_line"] - 2
    ending = example["end_line"]
    require(0 <= opening < ending < len(lines), "Example line range is invalid")
    indent = len(lines[opening]) - len(lines[opening].lstrip(" "))
    code = "".join(re.sub(r"^ {0," + str(indent) + r"}", "", x) for x in lines[opening + 1:ending])
    same(example["code"], code, "Example code slice")
    heading = ""
    for line in lines[:opening]:
        if line.lstrip().startswith("#"):
            heading = line.strip()
    expected_context = (heading + "\n" + "".join(lines[max(0, opening - 4):opening]).strip())[-1200:]
    same(example["context"], expected_context, "Example document context")


def report_inputs(report, documents, sources, config):
    same(report["provenance"]["documents"], {k: text_sha(v) for k, v in documents.items()}, "Report document hashes")
    same(report["provenance"]["sources"], {k: text_sha(v) for k, v in sources.items()}, "Report source hashes")
    same(report["provenance"]["configuration_sha256"], text_sha(json.dumps(config, sort_keys=True)), "Report configuration hash")
    same(report["runner"], "bubblewrap", "Report execution backend")
    for row in report["results"]:
        audit_example(row["example"], documents)
        if row["status"] == "checked":
            require(row["before"]["status"] == "passed" and row["before"]["returncode"] == 0,
                    "Checked report row lacks successful execution")
            spec = config["examples"][row["example"]["id"]]
            if "expected_stdout" in spec:
                same(row["before"]["stdout"], spec["expected_stdout"], "Recorded checked stdout versus oracle")


def inspect_patch_validation(output, project, outcomes, evidence):
    """Read stage reports and independently reconstruct the patched documents."""
    path = output / "patch_validation"
    benchmark = read(path / "benchmark.json")
    same(benchmark["stage"], "complete", "Patch benchmark stage")
    same(benchmark["mode"], "recorded_candidates", "Patch verification mode")
    same(benchmark["implementation_sha256"], project["implementation"], "Patch benchmark implementation")
    same(benchmark["manifest_sha256"], sha(project["path"] / "metadata.json"), "Patch benchmark manifest hash")
    same(benchmark["manifest"], read(project["path"] / "metadata.json"), "Patch benchmark manifest")
    selected = {key: row["selected"] for key, row in outcomes.items() if row.get("selected") is not None}
    same(read(output / "selected.json"), selected, "Saved selected candidates")
    snapshot = path / "inputs"
    for name, contents in {**project["documents"], **project["sources"]}.items():
        same((snapshot / name).read_text(), contents, "Patch validation snapshot " + name)
    same(read(snapshot / "exampleproof.json"), project["config"], "Patch snapshot configuration")
    same(read(snapshot / "proposals.json"), {key: [value] for key, value in selected.items()}, "Patch snapshot candidates")
    same(benchmark["candidate_snapshot_sha256"], sha(snapshot / "proposals.json"), "Candidate snapshot hash")
    patch = (path / "repair/verified.patch").read_text()
    patched_documents = apply_saved_patch(project["documents"], patch)
    same(benchmark["patch_application"], "passed" if patch else "no_patch", "Saved patch application status")
    same(bool(patch), bool(selected), "Selected repairs versus patch presence")
    stages = {stage: read(path / stage / "report.json") for stage in ("baseline", "repair", "patched")}
    indexed = {}
    for stage, report in stages.items():
        report_inputs(report, patched_documents if stage == "patched" else project["documents"], project["sources"], project["config"])
        same(report["repair"]["inference_requests"], 0, "Patch replay must not call model")
        indexed[stage] = {r["example"]["id"]: r for r in report["results"]}
        same(set(indexed[stage]), set(project["expected"]), "Patch report case inventory")
    rows = []
    for key, expected in project["expected"].items():
        old, repair, new = (indexed[s][key] for s in ("baseline", "repair", "patched"))
        same(old["status"], expected, "Replayed baseline status")
        same(repair["status"], "verified_repair" if key in selected else expected, "Recorded candidate replay status")
        same(new["status"], "checked" if key in selected else expected, "Final patched status")
        same(new["example"]["code"], selected[key]["code"].replace("\r\n", "\n").rstrip("\n") + "\n" if key in selected else project["baseline"][key]["example"]["code"], "Patched example code")
        if key in selected:
            same({k: repair["proposal"][k] for k in ("code", "rationale")}, selected[key], "Replay proposal versus selected live candidate")
            require(new["before"]["status"] == "passed" and new["before"]["returncode"] == 0, "Patched repair did not execute successfully")
        rows.append({"id": key, "expected_before": expected, "baseline_status": old["status"],
                     "baseline_matches": True, "repair_status": repair["status"],
                     "patched_status": new["status"], "attempts": len(repair["attempts"])})
    metrics = benchmark["metrics"]
    same(metrics["cases"], rows, "Patch metric rows versus actual reports")
    same(evidence["patch_validation"], metrics, "Cell patch metrics versus benchmark")
    same(metrics["patch_confirmed_repairs"], len(selected), "Confirmed repair count")
    same(metrics["healthy_preserved"], sum(x == "checked" for x in project["expected"].values()), "Healthy preservation count")
    require(metrics["evaluation_complete"] is True and metrics["baseline_valid"] is True, "Patch verification incomplete")
    return indexed["patched"]


def inspect_attempt(attempt, previous, outcome, project, plan, cell, group):
    proposal = attempt.get("proposal")
    event = (proposal or {}).get("inference_evidence") or attempt.get("inference_evidence")
    require(isinstance(event, dict), "Missing actual inference request evidence")
    number = len(previous) + 1
    same(attempt["number"], number, "Attempt number")
    payload = event["request"]
    expected_options = {**plan["generation_options"], "seed": cell["seed"] + number - 1}
    same(set(payload), {"model", "stream", "format", "system", "prompt", "options"}, "Payload field whitelist")
    same(payload["model"], plan["model"], "Request model")
    definition = plan.get("design", {}).get("arms", {}).get(cell["arm"])
    same(payload["system"], definition["system_prompt"] if definition else plan["system_prompt"], "Request SYSTEM")
    same(payload["options"], expected_options, "Actual temperature/context/token/seed options")
    same(payload["stream"], False, "Streaming option")
    same(payload["format"], "json", "Generation format")
    same(event["timeout_seconds"], plan["timeout_seconds"], "Request timeout")
    require(datetime.fromisoformat(event["started_at"]) >= datetime.fromisoformat(plan["frozen_at"]), "Request preceded input freeze")
    example = outcome["example"]
    original = feedback(outcome["before"])
    source = project["contexts"][example["id"]]
    has_feedback = cell["arm"] == "source_feedback"
    categorized = False
    if definition:
        source = source[definition["context"]]
        has_feedback = definition["feedback"] != "none"
        categorized = definition["feedback"] == "categorized"
        spec = project["config"]["examples"][example["id"]]
        inspect_failure_kind(outcome["before"], spec)
        inspect_failure_kind(attempt.get("after"), spec)
    expected_prompt = {"example_id": example["id"], "context": example["context"], "code": example["code"],
                       "error": original["error"], "execution": {"status": original["status"]},
                       "sources": {} if cell["arm"] == "direct" else source}
    if has_feedback and previous:
        expected_prompt["previous_attempts"] = [history_record(item, categorized=categorized) for item in previous]
    same(json.loads(payload["prompt"]), expected_prompt, "Actual prompt fields/source/history separation")
    require(nonnegative(event["duration_seconds"]), "Invalid measured inference duration")
    group["requests"] += 1
    group["inference_seconds"] += event["duration_seconds"]
    group["statuses"][attempt["status"]] += 1
    response = event.get("response") or {}
    if response.get("model") is not None:
        same(response["model"], plan["model"], "Raw response model")
    if event.get("response_body") is not None:
        try:
            decoded = json.loads(event["response_body"])
        except json.JSONDecodeError:
            require(not proposal, "Malformed response body produced a proposal")
        else:
            if response:
                same(decoded, response, "Raw body versus decoded response")
    for total, raw in (("input_tokens", "prompt_eval_count"), ("output_tokens", "eval_count")):
        count = response.get(raw)
        require(count is None or type(count) is int and count >= 0, "Invalid raw token count")
        if count is None:
            group[total] = None
        elif group[total] is not None:
            group[total] += count
        if proposal:
            same(proposal[total], count, "Proposal token metadata versus raw response")
    if response.get("eval_count") is not None:
        require(response["eval_count"] <= plan["generation_options"]["num_predict"], "Generated-token budget exceeded")
    if "total_duration" in response:
        require(nonnegative(response["total_duration"]), "Invalid raw server duration")
        group["raw_server_seconds"] += response["total_duration"] / 1e9
        require(event["duration_seconds"] + 0.25 >= response["total_duration"] / 1e9, "Measured duration smaller than server generation duration")
    if proposal:
        same(proposal["provider"], "ollama", "Live proposal provider")
        same(proposal["model"], plan["model"], "Proposal model")
        same(proposal["duration_seconds"], event["duration_seconds"], "Proposal measured duration")
        require(response.get("done") is True and not response.get("error") and not event.get("response_truncated"), "Proposal came from unfinished/error/truncated response")
        value = json.loads(response["response"])
        same({key: proposal[key] for key in ("code", "rationale")}, {key: value[key] for key in ("code", "rationale")}, "Saved candidate versus actual model response")
    if attempt["status"] == "verified_repair":
        require(proposal is not None and attempt["after"]["status"] == "passed" and attempt["after"]["returncode"] == 0, "Successful attempt lacks executed behavior evidence")
    return payload


def audit(root, repository=REPOSITORY, *, archived_only=False):
    errors, incomplete, checked = [], [], Counter()
    groups, first_payloads, projects = {}, {}, {}
    standard = None
    try:
        plan = read(root / "protocol.json")
        same(sha(root / "protocol.json"), (root / "protocol.sha256").read_text().strip(), "Protocol seal")
        same(plan["status"], "frozen_before_live_inference", "Protocol freeze status")
        same(plan["system_sha256"], text_sha(plan["system_prompt"]), "Frozen SYSTEM hash")
        if not archived_only:
            same(plan["implementation_sha256"], {p.name: sha(p) for p in sorted((repository / "exampleproof").glob("*.py"))}, "Current core implementation hashes")
        archived_core = root / "implementation/exampleproof"
        require(archived_core.is_dir(), "Frozen implementation snapshot is missing")
        same(plan["implementation_sha256"], {p.name: sha(p) for p in sorted(archived_core.glob("*.py"))}, "Archived core implementation hashes")
        prompts = static_system_prompts(archived_core / "providers.py")
        same(prompts["SYSTEM"], plan["system_prompt"], "Archived core SYSTEM")
        if not archived_only:
            same(static_system_prompts(repository / "exampleproof/providers.py"), prompts, "Current core SYSTEM policies")
        design = plan.get("design")
        if design:
            same(design["name"], "semantic-v2-method-comparison", "Versioned experiment design")
            require(design["split"] in {"development", "holdout"}, "Invalid experiment split")
            same(plan["replicate_seeds"], design["seeds"], "Design seeds")
            same(plan["held_out_scope"], design["held_out_scope"], "Design held-out disclosure")
            expected_definitions = {
                "legacy_source": ("legacy", "none", "SYSTEM"),
                "legacy_feedback": ("legacy", "generic", "SYSTEM"),
                "source_v2": ("v2", "none", "SYSTEM_V2"),
                "generic_feedback_v2": ("v2", "generic", "SYSTEM_V2"),
                "feedback_v2": ("v2", "categorized", "SYSTEM_V2"),
            }
            same(set(plan["arms"]), set(expected_definitions), "Declared v2 experiment arms")
            same(set(design["arms"]), set(expected_definitions), "Design arm definitions")
            require(type(design["source_context_character_limit"]) is int and design["source_context_character_limit"] > 0,
                    "V2 context budget must be a positive integer")
            for arm, (context, feedback_mode, prompt_name) in expected_definitions.items():
                same(design["arms"][arm], {"context": context, "feedback": feedback_mode, "system_prompt": prompts[prompt_name]},
                     "Frozen arm policy " + arm)
            inspect_method_lock(design, plan)
            if design.get("method_revision", 1) >= 2:
                standard = inspect_stdlib_index(archived_core, repository)
                checked["stdlib_public_function_slices"] = len(standard["entries"])
        else:
            same(set(plan["arms"]), {"direct", "source", "source_feedback"}, "Declared experiment arms")
        expected_cells = set(itertools.product((p["name"] for p in plan["projects"]), plan["replicate_seeds"], plan["arms"]))
        scheduled = [(c["project"], c["seed"], c["arm"]) for c in plan["schedule"]]
        require(len(scheduled) == len(set(scheduled)) and set(scheduled) == expected_cells, "Schedule does not cover each project/seed/arm exactly once")
        expected_locations = {f"{seed}/{arm}/{name}/inference.json" for name, seed, arm in expected_cells}
        actual_locations = {p.relative_to(root / "runs").as_posix() for p in (root / "runs").rglob("inference.json")}
        require(actual_locations <= expected_locations, "Unscheduled inference cells are present")
        for item in plan["projects"]:
            name, path = item["name"], root / "inputs" / item["name"]
            same(inventory(path), item["input_sha256"], "Frozen input inventory " + name)
            if design:
                inspect_split(read(path / "metadata.json"), design)
            same(sha(root / "contexts" / (name + ".json")), item["context_sha256"], "Frozen context hash " + name)
            same(sha(root / "baseline" / name / "report.json"), item["baseline_sha256"], "Frozen baseline hash " + name)
            config = read(path / "exampleproof.json")
            documents = {p: (path / p).read_text() for p in config["documents"]}
            sources = {p: (path / p).read_text() for p in config["source_files"]}
            baseline = read(root / "baseline" / name / "report.json")
            report_inputs(baseline, documents, sources, config)
            indexed = {row["example"]["id"]: row for row in baseline["results"]}
            same({key: value["status"] for key, value in indexed.items()}, item["expected"], "Frozen baseline statuses")
            contexts = read(root / "contexts" / (name + ".json"))
            same(set(contexts), {key for key, value in item["expected"].items() if value == "failed"}, "Source context case inventory")
            for case_id, context in contexts.items():
                if design:
                    same(set(context), {"legacy", "v2"}, "Frozen source context variants")
                    inspect_context(context["legacy"], sources, plan["source_context_character_limit"], version="legacy")
                    inspect_context(context["v2"], sources, design["source_context_character_limit"], version="v2", standard=standard)
                    if standard is not None:
                        inspect_retrieval_pools(context["v2"], indexed[case_id]["example"], indexed[case_id]["before"], sources, design)
                else:
                    inspect_context(context, sources, plan["source_context_character_limit"], version="legacy")
            projects[name] = {**item, "path": path, "config": config, "documents": documents,
                              "sources": sources, "contexts": contexts, "baseline": indexed,
                              "implementation": plan["implementation_sha256"]}
            checked["frozen_projects"] += 1
        for marker in ("started.json", "finished.json"):
            if not (root / marker).exists():
                incomplete.append(marker + " is missing")
                continue
            value = read(root / marker)
            if marker == "finished.json" and value["status"] != "complete":
                incomplete.append("Run is not complete")
                if "metadata" in value:
                    same(value["metadata"], plan["model_metadata"], marker + " model/server identity")
                continue
            same(value.get("metadata"), plan["model_metadata"], marker + " model/server identity")
            if marker == "started.json":
                same(value["protocol_sha256"], sha(root / "protocol.json"), "Started protocol hash")
            elif value["status"] != "complete":
                incomplete.append("Run is not complete")
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        return {"status": "failed", "errors": [str(exc)], "incomplete": [], "checked": dict(checked)}
    for arm in plan["arms"]:
        groups[arm] = {"case_runs": 0, "first_try_passed": 0, "budget_passed": 0,
                       "healthy_case_runs": 0, "healthy_preserved": 0, "requests": 0,
                       "input_tokens": 0, "output_tokens": 0, "inference_seconds": 0.0,
                       "wall_seconds": 0.0, "raw_server_seconds": 0.0, "statuses": Counter(), "failures": []}
    for cell in plan["schedule"]:
        label = f"{cell['seed']}/{cell['arm']}/{cell['project']}"
        output = root / "runs" / label
        if not (output / "inference.json").exists():
            incomplete.append(label + ": no inference.json")
            continue
        try:
            evidence = read(output / "inference.json")
            if evidence["status"] != "complete":
                incomplete.append(label + ": " + evidence["status"])
                continue
            for key in ("project", "seed", "arm"):
                same(evidence[key], cell[key], "Cell " + key)
            same(evidence["mode"], "live_model_ablation", "Cell mode")
            project, group = projects[cell["project"]], groups[cell["arm"]]
            inference_seconds_before = group["inference_seconds"]
            outcomes = {row.get("id") or row["example"]["id"]: row for row in evidence["cases"]}
            same(set(outcomes), set(project["expected"]), "Actual case inventory")
            require(len(outcomes) == len(evidence["cases"]), "Duplicate case outcomes")
            patched = inspect_patch_validation(output, project, outcomes, evidence)
            for key, expected in project["expected"].items():
                outcome = outcomes[key]
                if expected == "checked":
                    same(outcome, {"id": key, "status": "healthy", "attempts": []}, "Healthy control behavior")
                    group["healthy_case_runs"] += 1
                    group["healthy_preserved"] += patched[key]["status"] == "checked"
                    continue
                same(outcome["example"], project["baseline"][key]["example"], "Original example versus freeze")
                same(outcome["before"], project["baseline"][key]["before"], "Original execution feedback versus freeze")
                attempts = outcome["attempts"]
                require(1 <= len(attempts) <= plan["calls_per_failure_max"], "Actual call count outside frozen budget")
                for index, attempt in enumerate(attempts):
                    payload = inspect_attempt(attempt, attempts[:index], outcome, project, plan, cell, group)
                    if index == 0:
                        first_payloads[(cell["project"], cell["seed"], key, cell["arm"])] = payload
                    if index < len(attempts) - 1:
                        require(attempt["status"] != "verified_repair", "Requests continued after first verified repair")
                verified = [i + 1 for i, a in enumerate(attempts) if a["status"] == "verified_repair"]
                if verified:
                    same(verified, [len(attempts)], "First verified candidate selection")
                    same(outcome["status"], "verified_repair", "Verified outcome status")
                    same(outcome["success_attempt"], len(attempts), "Success attempt number")
                    same(outcome["selected"], {k: attempts[-1]["proposal"][k] for k in ("code", "rationale")}, "Selected versus first passing proposal")
                else:
                    same(outcome["status"], "not_repaired", "Unrepaired outcome status")
                    same(outcome["selected"], None, "Unrepaired selected candidate")
                    same(outcome["success_attempt"], None, "Unrepaired success attempt")
                    same(len(attempts), plan["calls_per_failure_max"], "Unsuccessful complete case call budget")
                confirmed = bool(verified) and patched[key]["status"] == "checked"
                group["case_runs"] += 1
                group["budget_passed"] += confirmed
                group["first_try_passed"] += confirmed and len(attempts) == 1
                if not confirmed:
                    group["failures"].append({"project": cell["project"], "seed": cell["seed"], "id": key, "status": outcome["status"]})
            require(nonnegative(evidence["duration_seconds"]), "Invalid cell wall duration")
            require(evidence["duration_seconds"] + 0.05 >= group["inference_seconds"] - inference_seconds_before,
                    "Cell wall duration is smaller than its sequential inference durations")
            group["wall_seconds"] += evidence["duration_seconds"]
            checked["complete_cells"] += 1
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            errors.append(label + ": " + str(exc))
    for project in projects.values():
        for seed in plan["replicate_seeds"]:
            for key, expected in project["expected"].items():
                if expected != "failed":
                    continue
                pairs = [("source", "source_feedback")]
                if plan.get("design"):
                    pairs = [("legacy_source", "legacy_feedback"),
                             ("source_v2", "generic_feedback_v2", "feedback_v2")]
                for arms in pairs:
                    keys = [(project["name"], seed, key, arm) for arm in arms]
                    pair_label = "/".join(arms)
                    if all(k in first_payloads for k in keys):
                        if any(first_payloads[k] != first_payloads[keys[0]] for k in keys[1:]):
                            errors.append(f"{project['name']}/{seed}/{key}: {pair_label} first payloads differ")
                        else:
                            checked["equal_source_feedback_first_payloads"] += 1
                    else:
                        incomplete.append(f"{project['name']}/{seed}/{key}: missing {pair_label} paired first payload")
    complete = not incomplete and not errors
    for group in groups.values():
        for field in ("inference_seconds", "wall_seconds", "raw_server_seconds"):
            group[field] = round(group[field], 4)
        group["statuses"] = dict(group["statuses"])
        group["first_try_rate"] = group["first_try_passed"] / group["case_runs"] if complete and group["case_runs"] else None
        group["budget_rate"] = group["budget_passed"] / group["case_runs"] if complete and group["case_runs"] else None
    if (root / "summary.json").exists() and not incomplete and not errors:
        try:
            summary = read(root / "summary.json")
            same(summary["protocol_sha256"], sha(root / "protocol.json"), "Summary protocol hash")
            same(summary["complete"], True, "Summary completeness")
            same(summary["missing_or_incomplete"], [], "Summary missing cells")
            for arm, group in groups.items():
                for field, value in group.items():
                    if field != "raw_server_seconds":
                        same(summary["groups"][arm][field], value, f"Summary {arm}.{field} from independent raw traversal")
            checked["summary_reconciled"] = 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    elif not (root / "summary.json").exists():
        incomplete.append("summary.json is missing")
    return {"schema_version": 1, "status": "failed" if errors else "incomplete" if incomplete else "passed",
            "study": str(root), "protocol_sha256": sha(root / "protocol.json"),
            "checked": dict(checked), "scheduled_cells": len(plan["schedule"]),
            "implementation_check": "archived_only" if archived_only else "current_and_archived",
            "errors": errors, "incomplete": incomplete, "independent_groups": groups,
            "scope": "Read-only independent hash/payload/raw-cost/report audit. Unified diffs are applied only in memory and checked against recorded post-patch document hashes. No model calls or snippet execution. Local seal is not external attestation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--archived-only", action="store_true",
                        help="Audit historical evidence against its sealed implementation archive; skip current-worktree equality")
    args = parser.parse_args()
    result = audit(args.study.resolve(), archived_only=args.archived_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
