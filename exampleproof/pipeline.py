from collections import Counter
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import platform

from .config import load_config, safe_path
from .extract import extract_markdown
from .guard import validate_candidate
from .models import Execution, Result
from .runner import SandboxRunner


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_project(root: Path):
    root = root.resolve()
    config = load_config(root)
    documents = {name: safe_path(root, name).read_bytes().decode("utf-8") for name in config["documents"]}
    sources = {name: safe_path(root, name).read_text(encoding="utf-8") for name in config["source_files"]}
    examples = [example for name, document in documents.items() for example in extract_markdown(document, name)]
    unknown = set(config["examples"]) - {e.id for e in examples}
    if unknown:
        raise ValueError("Configuration refers to missing examples: " + ", ".join(sorted(unknown)))
    return config, documents, sources, examples


def evaluate_example(example, spec, sources, runner, provider=None):
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
    try:
        proposal = provider.propose(example, before, sources)
    except Exception as exc:
        result.status = "provider_error"
        result.rejection = f"{type(exc).__name__}: {exc}"
        return result
    if proposal is None:
        return result
    result.proposal = proposal
    if not proposal.code.strip():
        result.status = "declined"
        result.rejection = proposal.rationale
        return result
    rejection = validate_candidate(example.code, proposal.code)
    if rejection:
        result.status, result.rejection = "rejected", rejection
        return result
    # Preserve the evaluator's original oracle classification. A model-added
    # assertion cannot turn an unverified example into a verified repair.
    result.after = runner.run(proposal.code, spec)
    result.after.oracle = before.oracle
    if result.after.status == "blocked":
        result.status = "blocked"
    elif result.after.status != "passed":
        result.status = "repair_failed"
    elif before.oracle == "none":
        result.status = "candidate_unverified"
    else:
        result.status = "verified_repair"
    result.diff = "".join(difflib.unified_diff(
        example.code.splitlines(keepends=True), proposal.code.splitlines(keepends=True),
        fromfile=f"original/{example.id}", tofile=f"candidate/{example.id}",
    ))
    return result


def run_project(root: Path, provider=None, runner=None):
    config, documents, sources, examples = read_project(root)
    runner = runner or SandboxRunner(sources, config["timeout_seconds"])
    results = [evaluate_example(example, config["examples"].get(example.id, {}), sources, runner, provider) for example in examples]
    patch = []
    for name, original in documents.items():
        lines = original.splitlines(keepends=True)
        repairs = sorted((r for r in results if r.example.path == name and r.status == "verified_repair"),
                         key=lambda r: r.example.start_line, reverse=True)
        for result in repairs:
            replacement = result.proposal.code
            if not replacement.endswith("\n"):
                replacement += "\n"
            # Use the document's newline style so a one-line repair stays small.
            if "\r\n" in original:
                replacement = replacement.replace("\r\n", "\n").replace("\n", "\r\n")
            lines[result.example.start_line - 1:result.example.end_line] = replacement.splitlines(keepends=True)
        if repairs:
            patch.append("".join(difflib.unified_diff(original.splitlines(keepends=True), lines,
                                                   fromfile=f"a/{name}", tofile=f"b/{name}")))
    counts = Counter(result.status for result in results)
    report = {
        "schema_version": 1,
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
        "verification_scope": "verified_repair means the configured checks or preserved original assertions passed; it is not a proof of general semantic equivalence",
        "results": [result.to_dict() for result in results],
    }
    return report, "".join(patch)


def exit_code(report):
    counts = report["summary"]["counts"]
    if not report["summary"]["total"] or counts.get("blocked") or sum(v for k, v in counts.items() if k != "skipped") == 0:
        return 2
    bad = {"failed", "provider_error", "rejected", "repair_failed", "declined", "candidate_unverified"}
    return 1 if any(counts.get(key) for key in bad) else 0
