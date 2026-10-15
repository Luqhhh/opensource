from collections import Counter
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import platform
import re

from .config import load_config, safe_path
from .extract import extract_markdown
from .guard import validate_candidate
from .models import Execution, RepairAttempt, Result
from .runner import SandboxRunner


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_project(root: Path):
    root = root.resolve()
    config = load_config(root)
    documents = {name: safe_path(root, name).read_bytes().decode("utf-8") for name in config["documents"]}
    sources = {name: safe_path(root, name).read_bytes().decode("utf-8") for name in config["source_files"]}
    examples = [example for name, document in documents.items() for example in extract_markdown(document, name)]
    unknown = set(config["examples"]) - {e.id for e in examples}
    if unknown:
        raise ValueError("Configuration refers to missing examples: " + ", ".join(sorted(unknown)))
    return config, documents, sources, examples


def validate_max_attempts(max_attempts):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be an integer between 1 and 5")


def unified_diff(original, replacement, fromfile, tofile):
    # difflib does not add Git's marker for a missing final newline.
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                   for line in difflib.unified_diff(original, replacement, fromfile=fromfile, tofile=tofile))


def evaluate_example(example, spec, sources, runner, provider=None, max_attempts=1, *, progress=None):
    validate_max_attempts(max_attempts)
    if spec.get("skip"):
        return Result(example, Execution("skipped", stderr=spec["skip"]), "skipped")
    before = runner.run(example.code, spec)
    if before.status == "passed":
        return Result(example, before, "checked" if before.oracle != "none" else "runnable_unverified")
    if before.status == "blocked":
        return Result(example, before, "blocked")
    result = Result(example, before, "failed")
    if provider is None:
        return result
    seen = set()
    for number in range(1, max_attempts + 1):
        if progress is not None:
            progress({"stage": "attempt_start", "example_id": example.id,
                      "attempt": number, "max_attempts": max_attempts})
        attempt = RepairAttempt(number, "provider_error")
        try:
            if result.attempts:
                proposal = provider.propose(example, before, sources, history=tuple(result.attempts))
            else:
                proposal = provider.propose(example, before, sources)
        except Exception as exc:
            if getattr(exc, "retryable_candidate_error", False):
                attempt.status = "candidate_format_error"
            attempt.rejection = f"{type(exc).__name__}: {exc}"
            attempt.inference_evidence = getattr(exc, "inference_evidence", None)
        else:
            if proposal is None:
                result.stop_reason = "no_candidate"
                break
            attempt.proposal = proposal
            normalized = proposal.code.replace("\r\n", "\n")
            if not normalized.strip():
                attempt.status, attempt.rejection = "declined", proposal.rationale
            elif normalized in seen:
                # The previous attempt already records its rejection or execution.
                # Keep that outcome and avoid paying for the same sandbox run.
                attempt.status = "repeated_candidate"
                attempt.rejection = "Provider repeated an earlier candidate; execution was not repeated"
            else:
                seen.add(normalized)
                attempt.rejection = validate_candidate(example.code, proposal.code)
                attempt.diff = unified_diff(
                    example.code.splitlines(keepends=True), proposal.code.splitlines(keepends=True),
                    fromfile=f"original/{example.id}", tofile=f"candidate/{example.id}",
                )
                if attempt.rejection:
                    attempt.status = "rejected"
                else:
                    attempt.after = runner.run(proposal.code, spec)
                    # Only the original evaluator can supply independent evidence.
                    attempt.after.oracle = before.oracle
                    if attempt.after.status == "blocked":
                        attempt.status = "blocked"
                    elif attempt.after.status != "passed":
                        attempt.status = "repair_failed"
                    elif before.oracle == "none":
                        attempt.status = "candidate_unverified"
                    else:
                        attempt.status = "verified_repair"
        result.attempts.append(attempt)
        if progress is not None:
            progress({"stage": "attempt_complete", "example_id": example.id,
                      "attempt": number, "status": attempt.status})
        if attempt.status == "repeated_candidate":
            result.stop_reason = "repeated_candidate"
            break
        result.status = attempt.status
        result.proposal, result.after = attempt.proposal, attempt.after
        result.rejection, result.diff = attempt.rejection, attempt.diff
        if attempt.status not in {"rejected", "repair_failed", "candidate_format_error"}:
            result.stop_reason = attempt.status
            break
    else:
        result.stop_reason = "max_attempts"
    return result


def run_project(root: Path, provider=None, runner=None, max_attempts=1, *, progress=None):
    validate_max_attempts(max_attempts)
    config, documents, sources, examples = read_project(root)
    runner = runner or SandboxRunner(sources, config["timeout_seconds"])
    if progress is not None:
        progress({"stage": "project_start", "total": len(examples)})
    results = []
    for index, example in enumerate(examples, 1):
        if progress is not None:
            progress({"stage": "example_start", "index": index, "total": len(examples),
                      "example_id": example.id})
        result = evaluate_example(example, config["examples"].get(example.id, {}), sources,
                                  runner, provider, max_attempts, progress=progress)
        results.append(result)
        if progress is not None:
            progress({"stage": "example_complete", "index": index, "total": len(examples),
                      "example_id": example.id, "status": result.status})
    patch = []
    for name, original in documents.items():
        lines = original.splitlines(keepends=True)
        repairs = sorted((r for r in results if r.example.path == name and r.status == "verified_repair"),
                         key=lambda r: r.example.start_line, reverse=True)
        for result in repairs:
            replacement = result.proposal.code.replace("\r\n", "\n")
            if not replacement.endswith("\n"):
                replacement += "\n"
            opening_index = result.example.start_line - 2
            opening = lines[opening_index]
            bom = "\ufeff" if opening_index == 0 and opening.startswith("\ufeff") else ""
            opening_text = opening[len(bom):]
            fence = re.match(r"( {0,3})(`{3,}|~{3,})", opening_text)
            indent, delimiter = fence.groups()
            # A Python multiline string may contain a Markdown closing fence.
            # Widen the surrounding fences to keep the repaired document valid.
            closing_runs = re.findall(r"^ {0,3}(" + re.escape(delimiter[0]) + r"{3,})[ \t]*$",
                                      replacement, re.MULTILINE)
            width = max([len(delimiter)] + [len(run) + 1 for run in closing_runs])
            if width > len(delimiter):
                widened = delimiter[0] * width
                lines[opening_index] = bom + indent + widened + opening_text[fence.end():]
                lines[result.example.end_line] = re.sub(
                    re.escape(delimiter[0]) + r"{3,}", widened, lines[result.example.end_line], count=1)
            replacement = "".join(indent + line for line in replacement.splitlines(keepends=True))
            # Use the document's newline style so a one-line repair stays small.
            if "\r\n" in original:
                replacement = replacement.replace("\r\n", "\n").replace("\n", "\r\n")
            lines[result.example.start_line - 1:result.example.end_line] = replacement.splitlines(keepends=True)
        if repairs:
            patch.append(unified_diff(original.splitlines(keepends=True), lines,
                                      fromfile=f"a/{name}", tofile=f"b/{name}"))
    counts = Counter(result.status for result in results)
    attempts = [attempt for result in results for attempt in result.attempts]
    proposals = [attempt.proposal for attempt in attempts if attempt.proposal is not None]
    evidence = [attempt.proposal.inference_evidence if attempt.proposal else attempt.inference_evidence
                for attempt in attempts]
    evidence = [item for item in evidence if item is not None]
    def token_total(field):
        values = []
        response_field = {"input_tokens": "prompt_eval_count", "output_tokens": "eval_count"}[field]
        for attempt in attempts:
            if attempt.proposal is not None:
                value = getattr(attempt.proposal, field)
            else:
                response = attempt.inference_evidence.response if attempt.inference_evidence else None
                value = response.get(response_field) if response else None
            if type(value) is not int or value < 0:
                return None
            values.append(value)
        # Missing usage is unknown, not zero or a complete-looking subtotal.
        return sum(values) if values else None
    report = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": root.resolve().name,
        "runner": getattr(runner, "backend", "test_double"),
        "runner_interpreter": "/usr/bin/python3 -I -S",
        "host_python": platform.python_version(),
        "provenance": {
            "documents": {name: fingerprint(text) for name, text in documents.items()},
            "sources": {name: fingerprint(text) for name, text in sources.items()},
            "configuration_sha256": fingerprint(json.dumps(config, sort_keys=True)),
        },
        "summary": {"total": len(results), "counts": dict(counts)},
        "repair": {"max_attempts": max_attempts, "attempts": len(attempts), "proposals": len(proposals),
                   "input_tokens": token_total("input_tokens"), "output_tokens": token_total("output_tokens"),
                   "inference_requests": len(evidence),
                   "inference_duration_seconds": round(sum(item.duration_seconds for item in evidence), 4),
                   "proposal_duration_seconds": round(sum(p.duration_seconds for p in proposals), 4)},
        "verification_scope": "verified_repair means the configured checks or preserved original assertions passed; it is not a proof of general semantic equivalence",
        "results": [result.to_dict() for result in results],
    }
    return report, "".join(patch)


def exit_code(report):
    counts = report["summary"]["counts"]
    if not report["summary"]["total"] or counts.get("blocked") or sum(v for k, v in counts.items() if k != "skipped") == 0:
        return 2
    bad = {"failed", "provider_error", "candidate_format_error", "rejected", "repair_failed", "declined", "candidate_unverified"}
    return 1 if any(counts.get(key) for key in bad) else 0
