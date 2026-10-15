"""Reproducible, manifest-scored runs with patch application in a disposable copy."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .config import safe_path
from .pipeline import read_project, run_project, validate_max_attempts
from .providers import FileProvider, OllamaProvider
from .report import write_report


def load_manifest(root, examples):
    raw = safe_path(root, "metadata.json").read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("metadata.json requires schema_version: 1")
    if not isinstance(manifest.get("suite_id"), str) or not manifest["suite_id"].strip():
        raise ValueError("metadata.json requires a nonempty suite_id")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("metadata.json requires a nonempty cases list")
    ids = []
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str)
                or not isinstance(case.get("expected_before"), str)
                or case["expected_before"] not in {"failed", "checked"}):
            raise ValueError("Every benchmark case requires id and expected_before: failed or checked")
        ids.append(case["id"])
    if len(ids) != len(set(ids)) or set(ids) != {example.id for example in examples}:
        raise ValueError("Benchmark cases must cover every extracted example exactly once")
    if not any(case["expected_before"] == "failed" for case in cases):
        raise ValueError("Benchmark requires at least one expected failure")
    return manifest, raw


def score_benchmark(manifest, baseline, repaired=None, patched=None):
    """Count declared cases, keeping unavailable evidence distinct from zero."""
    before = {r["example"]["id"]: r for r in (baseline or {}).get("results", [])}
    after = {r["example"]["id"]: r for r in (repaired or {}).get("results", [])}
    rechecked = {r["example"]["id"]: r for r in (patched or {}).get("results", [])}
    rows = []
    for case in manifest["cases"]:
        key, expected = case["id"], case["expected_before"]
        original, repair, recheck = before.get(key), after.get(key), rechecked.get(key)
        rows.append({"id": key, "expected_before": expected,
                     "baseline_status": original["status"] if original else None,
                     "baseline_matches": original is not None and original["status"] == expected,
                     "repair_status": repair["status"] if repair else None,
                     "patched_status": recheck["status"] if recheck else None,
                     "attempts": len(repair.get("attempts", [])) if repair else None})
    failures = [r for r in rows if r["expected_before"] == "failed"]
    healthy = [r for r in rows if r["expected_before"] == "checked"]
    valid = all(r["baseline_matches"] for r in rows)
    measurable = {
        "baseline": {"failed", "checked"},
        "repair": {"failed", "checked", "verified_repair", "repair_failed", "rejected", "declined", "candidate_format_error"},
        "patched": {"failed", "checked"},
    }
    infrastructure_errors = [
        {"stage": stage, "id": row["id"], "status": row[stage + "_status"]}
        for stage, result in (("baseline", baseline), ("repair", repaired), ("patched", patched))
        if result is not None
        for row in rows if row[stage + "_status"] not in measurable[stage]
    ]
    complete = (valid and repaired is not None and patched is not None and not infrastructure_errors)
    def available(group, stage, result):
        return result is not None and all(row[stage + "_status"] in measurable[stage] for row in group)

    repair_available = available(failures, "repair", repaired)
    patch_available = repair_available and available(failures, "patched", patched)
    verified = sum(r["repair_status"] == "verified_repair" for r in failures) if repair_available else None
    confirmed = sum(r["repair_status"] == "verified_repair" and r["patched_status"] == "checked"
                    for r in failures) if patch_available else None
    preserved = sum(r["repair_status"] == "checked" and r["patched_status"] == "checked"
                    and r["attempts"] == 0 for r in healthy) if (
                        available(healthy, "repair", repaired) and available(healthy, "patched", patched)) else None
    return {"baseline_valid": valid, "total": len(rows), "expected_failures": len(failures),
            "evaluation_complete": complete, "infrastructure_errors": infrastructure_errors,
            "detected_failures": sum(r["baseline_matches"] for r in failures),
            "healthy_controls": len(healthy),
            "healthy_false_alarms": sum(r["baseline_status"] == "failed" for r in healthy),
            "verified_repairs": verified, "patch_confirmed_repairs": confirmed,
            "repair_rate": confirmed / len(failures) if complete and failures else None,
            "healthy_preserved": preserved,
            "all_passed": complete and confirmed == len(failures) and preserved == len(healthy),
            "cases": rows}


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", errors="backslashreplace")


def run_benchmark(root: Path, output: Path, provider, max_attempts=1, *, progress=None):
    """Never change source inputs or overwrite an earlier evidence directory."""
    validate_max_attempts(max_attempts)
    root, output = root.resolve(), output.resolve()
    config, documents, sources, examples = read_project(root)
    manifest, manifest_raw = load_manifest(root, examples)
    for example in examples:
        spec = config["examples"].get(example.id, {})
        if spec.get("skip") or not (spec.get("checks", "").strip() or "expected_stdout" in spec):
            raise ValueError(f"Benchmark case requires configured behavior checks and cannot be skipped: {example.id}")
    if not shutil.which("git"):
        raise ValueError("Benchmark patch verification requires git")
    if output.exists():
        raise ValueError("Benchmark output must be a new directory; previous evidence is never overwritten")
    # Snapshot precisely the selected inputs; do not copy unrelated files or links.
    inputs = {**documents, **sources, "exampleproof.json": json.dumps(config, ensure_ascii=False)}
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    summary = {
        "schema_version": 1, "suite_id": manifest["suite_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "recorded_candidates" if isinstance(provider, FileProvider) else
                "live_model" if isinstance(provider, OllamaProvider) else "custom_provider",
        "model": getattr(provider, "model", None), "max_attempts": max_attempts,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(), "manifest": manifest,
        "scope": "Historical reproductions or declared fixtures only; finite configured checks, not semantic equivalence or a cross-project success rate.",
        "patch_application": "not_attempted",
        "stage": "snapshot",
    }
    baseline = repaired = patched = None
    run_options = {"progress": progress} if progress is not None else {}
    code = 2
    try:
        summary["implementation_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                            for p in sorted(Path(__file__).parent.glob("*.py"))}
        # The frozen input copy is itself useful for reproducing the evidence later.
        frozen = output / "inputs"
        frozen.mkdir()
        for name, content in inputs.items():
            target = frozen / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))
        (frozen / "metadata.json").write_bytes(manifest_raw)
        if isinstance(provider, FileProvider):
            candidates = {key: [{"code": p.code, "rationale": p.rationale} for p in values]
                          for key, values in provider.proposals.items()}
            _write_json(frozen / "proposals.json", candidates)
            summary["candidate_snapshot_sha256"] = hashlib.sha256((frozen / "proposals.json").read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="exampleproof-benchmark-") as temporary:
            project = Path(temporary) / root.name
            shutil.copytree(frozen, project)
            summary["stage"] = "baseline"
            if progress is not None:
                progress({"stage": "phase_start", "phase": "baseline"})
            baseline, _ = run_project(project, **run_options)
            summary["stage"] = "baseline_report"
            write_report(output / "baseline", baseline, "")
            summary["stage"] = "baseline_validation"
            if score_benchmark(manifest, baseline)["baseline_valid"]:
                summary["stage"] = "repair"
                if progress is not None:
                    progress({"stage": "phase_start", "phase": "repair"})
                repaired, patch = run_project(project, provider, max_attempts=max_attempts, **run_options)
                summary["repair"] = repaired["repair"]
                summary["stage"] = "repair_report"
                write_report(output / "repair", repaired, patch)
                summary["stage"] = "patch_application"
                if patch:
                    for arguments in (["--check"], []):
                        subprocess.run(["git", "apply", *arguments, "-"], input=patch,
                                       text=True, encoding="utf-8", cwd=project, check=True,
                                       capture_output=True, timeout=30)
                    summary["patch_application"] = "passed"
                else:
                    summary["patch_application"] = "no_patch"
                summary["stage"] = "patched"
                if progress is not None:
                    progress({"stage": "phase_start", "phase": "patched"})
                patched, _ = run_project(project, **run_options)
                summary["stage"] = "patched_report"
                write_report(output / "patched", patched, "")
                metrics = score_benchmark(manifest, baseline, repaired, patched)
                code = 2 if not metrics["evaluation_complete"] else 0 if metrics["all_passed"] else 1
                summary["stage"] = "complete"
    except subprocess.CalledProcessError as exc:
        summary["patch_application"] = "failed"
        summary["patch_error"] = str(exc) + "\n" + (exc.stderr or "")[:4000]
        code = 1
    except Exception as exc:
        # Preserve incomplete evidence and its failing stage. A failure to write
        # benchmark.json itself still propagates from finally to the caller.
        summary["error"] = {"type": type(exc).__name__, "message": str(exc), "stage": summary["stage"]}
        if summary["stage"] == "patch_application":
            summary["patch_application"] = "failed"
        code = 2
    finally:
        summary["metrics"] = score_benchmark(manifest, baseline, repaired, patched)
        if "error" in summary:
            summary["metrics"]["evaluation_complete"] = False
            summary["metrics"]["repair_rate"] = None
            summary["metrics"]["all_passed"] = False
            summary["metrics"]["infrastructure_errors"].append(summary["error"])
        summary["duration_seconds"] = round(time.monotonic() - started, 4)
        summary["exit_code"] = code
        _write_json(output / "benchmark.json", summary)
    return summary, code
