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


def history_record(attempt):
    proposal = attempt.get("proposal")
    return {"number": attempt["number"], "status": attempt["status"],
            "candidate": {"code": proposal["code"], "rationale": proposal["rationale"]} if proposal else None,
            "execution": feedback(attempt.get("after")), "rejection": attempt.get("rejection")}


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
    same(payload["system"], plan["system_prompt"], "Request SYSTEM")
    same(payload["options"], expected_options, "Actual temperature/context/token/seed options")
    same(payload["stream"], False, "Streaming option")
    same(payload["format"], "json", "Generation format")
    same(event["timeout_seconds"], plan["timeout_seconds"], "Request timeout")
    require(datetime.fromisoformat(event["started_at"]) >= datetime.fromisoformat(plan["frozen_at"]), "Request preceded input freeze")
    example = outcome["example"]
    original = feedback(outcome["before"])
    expected_prompt = {"example_id": example["id"], "context": example["context"], "code": example["code"],
                       "error": original["error"], "execution": {"status": original["status"]},
                       "sources": {} if cell["arm"] == "direct" else project["contexts"][example["id"]]}
    if cell["arm"] == "source_feedback" and previous:
        expected_prompt["previous_attempts"] = [history_record(item) for item in previous]
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


def audit(root, repository=REPOSITORY):
    errors, incomplete, checked = [], [], Counter()
    groups, first_payloads, projects = {}, {}, {}
    try:
        plan = read(root / "protocol.json")
        same(sha(root / "protocol.json"), (root / "protocol.sha256").read_text().strip(), "Protocol seal")
        same(plan["status"], "frozen_before_live_inference", "Protocol freeze status")
        same(plan["system_sha256"], text_sha(plan["system_prompt"]), "Frozen SYSTEM hash")
        same(plan["implementation_sha256"], {p.name: sha(p) for p in sorted((repository / "exampleproof").glob("*.py"))}, "Current core implementation hashes")
        archived_core = root / "implementation/exampleproof"
        require(archived_core.is_dir(), "Frozen implementation snapshot is missing")
        same(plan["implementation_sha256"], {p.name: sha(p) for p in sorted(archived_core.glob("*.py"))}, "Archived core implementation hashes")
        tree = ast.parse((repository / "exampleproof/providers.py").read_text())
        system = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SYSTEM" for t in n.targets))
        same(system, plan["system_prompt"], "Current core SYSTEM")
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
            for context in contexts.values():
                require(sum(len(k) + len(v) for k, v in context.items()) <= plan["source_context_character_limit"], "Source context character budget exceeded")
                for label, excerpt in context.items():
                    match = re.fullmatch(r"(.+):(\d+)-(\d+) \((signature|body excerpt)\)", label)
                    require(match is not None and match[1] in sources, "Context is not from a selected source")
                    same(excerpt, "".join(sources[match[1]].splitlines(keepends=True)[int(match[2]) - 1:int(match[3])]), "Context excerpt versus original source lines")
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
                keys = [(project["name"], seed, key, arm) for arm in ("source", "source_feedback")]
                if all(k in first_payloads for k in keys):
                    if first_payloads[keys[0]] != first_payloads[keys[1]]:
                        errors.append(f"{project['name']}/{seed}/{key}: source/feedback first payloads differ")
                    else:
                        checked["equal_source_feedback_first_payloads"] += 1
                else:
                    incomplete.append(f"{project['name']}/{seed}/{key}: missing paired first payload")
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
            "errors": errors, "incomplete": incomplete, "independent_groups": groups,
            "scope": "Read-only independent hash/payload/raw-cost/report audit. Unified diffs are applied only in memory and checked against recorded post-patch document hashes. No model calls or snippet execution. Local seal is not external attestation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    args = parser.parse_args()
    result = audit(args.study.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
