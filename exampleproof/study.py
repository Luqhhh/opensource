"""Frozen, paired source/feedback ablations. All candidate execution stays isolated."""

import ast
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
from urllib.request import Request

from . import providers
from .benchmark import load_manifest, run_benchmark
from .models import Execution
from .pipeline import evaluate_example, read_project, run_project
from .providers import FileProvider, OllamaProvider, execution_feedback, urlopen
from .report import write_report
from .runner import SandboxRunner

ARMS = ("direct", "source", "source_feedback")
SEEDS = (17, 29, 43)
CONTEXT_CHARS = 12000


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", errors="backslashreplace")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def implementation_hashes():
    return {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}


def source_context(example, before, sources, limit=CONTEXT_CHARS):
    """Deterministic API signatures and lexical source windows; no checks/gold fixes."""
    identifiers = set(re.findall(r"[A-Za-z][A-Za-z0-9]*", example.code + "\n" + execution_feedback(before)["error"]))
    identifiers -= {"print", "from", "import", "assert", "File", "line", "module", "Traceback", "in"}
    candidates = []
    headers = []
    for filename, text in sorted(sources.items()):
        lines = text.splitlines(keepends=True)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_") and node.name != "__init__":
                continue
            first_body = node.body[0].lineno if node.body else node.lineno + 1
            end_header = max(node.lineno, min(first_body - 1, node.lineno + 7))
            header = "".join(lines[node.lineno - 1:end_header])
            name_tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9]*", node.name))
            score = 10 * len(name_tokens & identifiers) + (20 if node.name in identifiers else 0)
            headers.append((score, filename, node.lineno, end_header, header))
            if isinstance(node, ast.ClassDef):
                continue
            end = min(node.end_lineno, node.lineno + 49)
            excerpt = "".join(lines[node.lineno - 1:end])
            terms = set(re.findall(r"[A-Za-z][A-Za-z0-9]*", excerpt))
            score += min(20, len(terms & identifiers))
            if score:
                candidates.append((score, filename, node.lineno, end, excerpt))
    contexts = {}
    used = 0
    # A bounded signature index exposes the available API without manually
    # selecting the known replacement from a migration guide or reference patch.
    for score, filename, start, end, text in sorted(headers, key=lambda x: (-x[0], x[1], x[2])):
        label = f"{filename}:{start}-{end} (signature)"
        cost = len(label) + len(text)
        if used + cost > limit // 2:
            continue
        contexts[label] = text
        used += cost
    for score, filename, start, end, text in sorted(candidates, key=lambda x: (-x[0], x[1], x[2])):
        label = f"{filename}:{start}-{end} (body excerpt)"
        cost = len(label) + len(text)
        if used + cost > limit:
            continue
        contexts[label] = text
        used += cost
    return contexts


def local_metadata(endpoint, model):
    # Reuse the production provider's loopback validation and proxy-free opener.
    OllamaProvider(model, endpoint)
    def get(path):
        with urlopen(Request(endpoint.rstrip("/") + path), timeout=10) as response:
            data = response.read(256001)
        if len(data) > 256000:
            raise ValueError("Local model metadata exceeds 256 KB")
        return json.loads(data)
    models = [item for item in get("/api/tags")["models"] if item["name"] == model]
    if len(models) != 1:
        raise ValueError("The exact locally installed model tag is required")
    return {"server": get("/api/version"), "model": models[0]}


def freeze_study(projects, output, model="qwen2.5-coder:7b", endpoint="http://127.0.0.1:11434", *, design=None):
    output = output.resolve()
    if output.exists():
        raise ValueError("Freeze output must be a new directory")
    roots = [p.resolve() for p in projects]
    if len({p.name for p in roots}) != len(roots):
        raise ValueError("Study project names must be unique")
    if design:
        from .semantic_study import validate_project_splits
        validate_project_splits(roots, design)
    metadata = local_metadata(endpoint, model)
    design = deepcopy(design)
    arms = tuple(design["arms"]) if design else ARMS
    seeds = tuple(design["seeds"]) if design else SEEDS
    if not arms or not seeds or len(set(arms)) != len(arms) or len(set(seeds)) != len(seeds):
        raise ValueError("Study arms and seeds must be nonempty and unique")
    output.mkdir(parents=True)
    plan = {"schema_version": 1, "status": "preparing", "frozen_at": datetime.now(timezone.utc).isoformat(),
            "model": model, "model_metadata": metadata,
            "system_prompt": providers.SYSTEM,
            "system_sha256": hashlib.sha256(providers.SYSTEM.encode()).hexdigest(),
            "implementation_sha256": implementation_hashes(),
            "arms": list(arms), "replicate_seeds": list(seeds), "calls_per_failure_max": 3,
            "generation_options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024},
            "timeout_seconds": 180, "source_context_character_limit": CONTEXT_CHARS,
            "stop_policy": "All arms stop on first verified candidate or infrastructure failure; declines/rejections/duplicates consume a call and may continue up to three. Nonfeedback retries are independent.",
            "seed_policy": "replicate_seed + zero-based attempt; identical across arms and cases",
            "selection_policy": "First candidate passing frozen checks; no selection based on human preference or post-hoc test changes",
            "held_out_scope": "Not used to tune this application prompt; public historical documentation may be present in foundation-model pretraining. This is a purposively selected migration benchmark, not a random sample of current upstream bugs.",
            "cost_scope": "Equal maximum call and generated-token budgets, not equal actual input tokens or latency; source/history input costs are reported.",
            "host_python": platform.python_version(), "platform": platform.platform(),
            "runner_python": subprocess.check_output(["/usr/bin/python3", "--version"], text=True).strip(),
            "bubblewrap": subprocess.check_output(["bwrap", "--version"], text=True).strip(),
            "projects": [], "schedule": []}
    if design:
        plan["design"] = design
        plan["held_out_scope"] = design["held_out_scope"]
    try:
        archive = output / "implementation" / "exampleproof"
        archive.mkdir(parents=True)
        for filename, expected_hash in plan["implementation_sha256"].items():
            shutil.copyfile(Path(__file__).parent / filename, archive / filename)
            if digest(archive / filename) != expected_hash:
                raise ValueError("Implementation changed while archiving the study")
        for root in roots:
            project = output / "inputs" / root.name
            if output.is_relative_to(root):
                raise ValueError("Study output cannot be inside a selected project")
            shutil.copytree(root, project, ignore=shutil.ignore_patterns("evidence", "__pycache__", "*.pyc", ".git"))
            config, documents, sources, examples = read_project(project)
            manifest, _ = load_manifest(project, examples)
            if not (project / "provenance.json").is_file():
                raise ValueError(f"Missing upstream provenance for {root.name}")
            baseline, _ = run_project(project)
            expected = {c["id"]: c["expected_before"] for c in manifest["cases"]}
            if any(r["status"] != expected[r["example"]["id"]] for r in baseline["results"]):
                raise ValueError(f"Unexpected baseline for {root.name}")
            if any(config["examples"].get(e.id, {}).get("skip") or not (
                    config["examples"].get(e.id, {}).get("checks", "").strip()
                    or "expected_stdout" in config["examples"].get(e.id, {})) for e in examples):
                raise ValueError("Every study case requires frozen behavior checks")
            write_report(output / "baseline" / root.name, baseline, "")
            contexts = {e.id: source_context(e, Execution(**baseline["results"][i]["before"]), sources)
                        for i, e in enumerate(examples) if expected[e.id] == "failed"}
            if design:
                from .context import source_context as context_v2
                contexts = {e.id: {"legacy": contexts[e.id],
                                   "v2": context_v2(e, Execution(**baseline["results"][i]["before"]), sources,
                                                    limit=design["source_context_character_limit"])}
                            for i, e in enumerate(examples) if expected[e.id] == "failed"}
            write_json(output / "contexts" / f"{root.name}.json", contexts)
            plan["projects"].append({"name": root.name, "suite_id": manifest["suite_id"],
                                     "expected": expected, "input_sha256": inventory(project),
                                     "baseline_sha256": digest(output / "baseline" / root.name / "report.json"),
                                     "context_sha256": digest(output / "contexts" / f"{root.name}.json")})
        # Rotate arm order per project and replicate to reduce order/cache bias.
        for repeat, seed in enumerate(seeds):
            for index, project in enumerate(plan["projects"]):
                offset = (repeat + index) % len(arms)
                for arm in arms[offset:] + arms[:offset]:
                    plan["schedule"].append({"project": project["name"], "seed": seed, "arm": arm})
        plan["status"] = "frozen_before_live_inference"
    except Exception as exc:
        plan["status"] = "freeze_failed"
        plan["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(output / "protocol.json", plan)
    (output / "protocol.sha256").write_text(digest(output / "protocol.json") + "\n", encoding="ascii")
    return plan


class StudyProvider(OllamaProvider):
    def __init__(self, model, endpoint, timeout, *, options, arm, context, history,
                 system_prompt=None, feedback_mode="legacy"):
        super().__init__(model, endpoint, timeout, options=options,
                         system_prompt=system_prompt, feedback_mode=feedback_mode)
        self.arm, self.context, self.history = arm, context, history

    def propose(self, example, before, sources, *, history=()):
        return super().propose(example, before, {} if self.arm == "direct" else self.context,
                               history=self.history if self.arm == "source_feedback" else ())


class BaselineThenSandbox:
    """Reuse the frozen observed baseline, then execute the proposed candidate."""
    def __init__(self, before, runner):
        self.before, self.runner, self.first = before, runner, True

    def run(self, code, spec):
        if self.first:
            self.first = False
            return deepcopy(self.before)
        return self.runner.run(code, spec)


def infrastructure_failure(attempt):
    if attempt.status == "blocked":
        return True
    if attempt.status != "provider_error":
        return False
    evidence = attempt.inference_evidence
    # A completed generation containing invalid candidate JSON is a consumed
    # failed attempt. Transport/server errors make the cell incomplete instead.
    response = evidence.response if evidence else None
    return not (isinstance(response, dict) and response.get("done") is True
                and "error" not in response and isinstance(response.get("response"), str)
                and all(response.get(key) is None or (type(response[key]) is int and response[key] >= 0)
                        for key in ("prompt_eval_count", "eval_count")))


def evaluate_study_case(example, spec, sources, before, context, plan, arm, seed, endpoint,
                        provider_factory=StudyProvider, runner=None):
    attempts = []
    selected = None
    blocked = False
    runner = runner or SandboxRunner(sources, plan.get("sandbox_timeout_seconds", 5))
    for index in range(plan["calls_per_failure_max"]):
        options = {**plan["generation_options"], "seed": seed + index}
        selected_context, provider_arm, policy = context, arm, {}
        if plan.get("design"):
            definition = plan["design"]["arms"][arm]
            selected_context = context[definition["context"]]
            provider_arm = "source" if definition["feedback"] == "none" else "source_feedback"
            policy = {"system_prompt": definition["system_prompt"],
                      "feedback_mode": "categorized" if definition["feedback"] == "categorized" else "legacy"}
        provider = provider_factory(plan["model"], endpoint, plan["timeout_seconds"], options=options,
                                    arm=provider_arm, context=selected_context, history=tuple(attempts), **policy)
        result = evaluate_example(example, spec, sources, BaselineThenSandbox(before, runner), provider)
        if not result.attempts:
            raise ValueError("A study inference call did not produce an attempt record")
        attempt = result.attempts[0]
        attempt.number = index + 1
        attempts.append(attempt)
        if result.status == "verified_repair":
            selected = attempt.proposal
            break
        if infrastructure_failure(attempt):
            blocked = True
            break
    return {"example": example.__dict__, "before": before.__dict__,
            "status": "incomplete" if blocked else "verified_repair" if selected else "not_repaired",
            "success_attempt": len(attempts) if selected else None,
            "selected": {"code": selected.code, "rationale": selected.rationale} if selected else None,
            "attempts": [a.__dict__ for a in attempts]}, attempts


def serialize_case(case, attempts):
    from dataclasses import asdict
    return {**case, "attempts": [asdict(a) for a in attempts]}


def verify_protocol(root, plan):
    """Detect accidental protocol edits; this local seal is not external attestation."""
    if digest(root / "protocol.json") != (root / "protocol.sha256").read_text(encoding="ascii").strip():
        raise ValueError("Frozen protocol changed")
    if json.loads((root / "protocol.json").read_text(encoding="utf-8")) != plan:
        raise ValueError("In-memory protocol differs from frozen protocol")


def verify_freeze(root, plan):
    verify_protocol(root, plan)
    if plan["status"] != "frozen_before_live_inference":
        raise ValueError("Study protocol was not successfully frozen")
    if plan["system_prompt"] != providers.SYSTEM or plan["implementation_sha256"] != implementation_hashes():
        raise ValueError("Implementation or prompt changed after freeze; start a separately declared study")
    for item in plan["projects"]:
        if inventory(root / "inputs" / item["name"]) != item["input_sha256"]:
            raise ValueError(f"Frozen project changed: {item['name']}")
        if digest(root / "contexts" / f"{item['name']}.json") != item["context_sha256"]:
            raise ValueError(f"Frozen source context changed: {item['name']}")
        if digest(root / "baseline" / item["name"] / "report.json") != item["baseline_sha256"]:
            raise ValueError(f"Frozen baseline changed: {item['name']}")


def run_cell(root, plan, cell, endpoint):
    project = root / "inputs" / cell["project"]
    output = root / "runs" / str(cell["seed"]) / cell["arm"] / cell["project"]
    output.mkdir(parents=True, exist_ok=False)
    config, _, sources, examples = read_project(project)
    baseline = json.loads((root / "baseline" / cell["project"] / "report.json").read_text())
    before = {r["example"]["id"]: r for r in baseline["results"]}
    contexts = json.loads((root / "contexts" / f"{cell['project']}.json").read_text())
    outcomes, selected = [], {}
    start = time.monotonic()
    evidence = {"schema_version": 1, **cell, "mode": "live_model_ablation", "status": "running", "cases": outcomes}
    write_json(output / "inference.json", evidence)
    for example in examples:
        if before[example.id]["status"] == "checked":
            outcomes.append({"id": example.id, "status": "healthy", "attempts": []})
            continue
        outcome, attempts = evaluate_study_case(
            example, config["examples"][example.id], sources, Execution(**before[example.id]["before"]),
            contexts[example.id], plan, cell["arm"], cell["seed"], endpoint,
            runner=SandboxRunner(sources, config["timeout_seconds"]))
        outcomes.append(serialize_case(outcome, attempts))
        if outcome["selected"]:
            selected[example.id] = outcome["selected"]
        write_json(output / "inference.json", evidence)
    write_json(output / "selected.json", selected)
    # This is explicitly a replay of the actual model-selected proposals, solely
    # to apply/recheck their final document patch, not extra model success data.
    recheck, _ = run_benchmark(project, output / "patch_validation", FileProvider(output / "selected.json"))
    evidence["patch_validation"] = recheck["metrics"]
    evidence["status"] = "incomplete" if any(r["status"] == "incomplete" for r in outcomes) or not recheck["metrics"]["evaluation_complete"] else "complete"
    evidence["duration_seconds"] = round(time.monotonic() - start, 4)
    write_json(output / "inference.json", evidence)
    return evidence


def summarize_study(root):
    plan = json.loads((root / "protocol.json").read_text())
    verify_protocol(root, plan)
    groups = {arm: {"case_runs": 0, "first_try_passed": 0, "budget_passed": 0,
                    "healthy_case_runs": 0, "healthy_preserved": 0, "requests": 0,
                    "input_tokens": 0, "output_tokens": 0, "inference_seconds": 0.0,
                    "wall_seconds": 0.0, "failures": [], "statuses": Counter(), "cells": []} for arm in plan["arms"]}
    missing = []
    for cell in plan["schedule"]:
        location = Path("runs") / str(cell["seed"]) / cell["arm"] / cell["project"] / "inference.json"
        if not (root / location).exists():
            missing.append(cell)
            continue
        evidence = json.loads((root / location).read_text())
        group = groups[cell["arm"]]
        group["cells"].append({**cell, "path": str(location), "status": evidence["status"]})
        if evidence["status"] != "complete":
            missing.append(cell)
        recheck = {r["id"]: r for r in evidence.get("patch_validation", {}).get("cases", [])}
        for outcome in evidence["cases"]:
            if outcome["status"] == "healthy":
                group["healthy_case_runs"] += 1
                group["healthy_preserved"] += recheck.get(outcome["id"], {}).get("patched_status") == "checked"
                continue
            group["case_runs"] += 1
            key = outcome["example"]["id"]
            confirmed = (outcome["status"] == "verified_repair" and recheck.get(key, {}).get("patched_status") == "checked")
            group["budget_passed"] += confirmed
            group["first_try_passed"] += confirmed and outcome["success_attempt"] == 1
            if not confirmed:
                group["failures"].append({"project": cell["project"], "seed": cell["seed"], "id": key, "status": outcome["status"]})
            for attempt in outcome["attempts"]:
                group["statuses"][attempt["status"]] += 1
                proposal = attempt.get("proposal")
                request = (proposal or {}).get("inference_evidence") or attempt.get("inference_evidence")
                if request:
                    group["requests"] += 1
                    group["inference_seconds"] += request["duration_seconds"]
                response = (request or {}).get("response") or {}
                for field, returned in (("input_tokens", "prompt_eval_count"), ("output_tokens", "eval_count")):
                    value = response.get(returned)
                    if type(value) is not int or value < 0:
                        group[field] = None
                    elif group[field] is not None:
                        group[field] += value
        group["wall_seconds"] += evidence.get("duration_seconds", 0)
    run_status = None
    if (root / "started.json").exists():
        run_status = json.loads((root / "finished.json").read_text()) if (root / "finished.json").exists() else {"status": "running_or_interrupted"}
    complete = not missing and (run_status is None or run_status["status"] == "complete")
    for group in groups.values():
        group["first_try_rate"] = group["first_try_passed"] / group["case_runs"] if complete and group["case_runs"] else None
        group["budget_rate"] = group["budget_passed"] / group["case_runs"] if complete and group["case_runs"] else None
        group["inference_seconds"] = round(group["inference_seconds"], 4)
        group["wall_seconds"] = round(group["wall_seconds"], 4)
        group["statuses"] = dict(group["statuses"])
    result = {"schema_version": 1, "complete": complete, "missing_or_incomplete": missing,
              "run_status": run_status,
              "split": plan.get("design", {}).get("split", "original_v1"),
              "protocol_sha256": digest(root / "protocol.json"), "groups": groups,
              "interpretation": "Case-runs repeat the same cases under paired seeds, not additional independent defects. Small purposively selected migration set; no population success-rate inference."}
    write_json(root / "summary.json", result)
    return result


def run_study(root, endpoint="http://127.0.0.1:11434"):
    root = root.resolve()
    plan = json.loads((root / "protocol.json").read_text())
    verify_freeze(root, plan)
    if (root / "runs").exists():
        raise ValueError("Study runs already exist; do not overwrite or silently retry outcomes")
    metadata = local_metadata(endpoint, plan["model"])
    if metadata != plan["model_metadata"]:
        raise ValueError("Model digest or server metadata changed after freeze")
    write_json(root / "started.json", {"started_at": datetime.now(timezone.utc).isoformat(),
                                      "protocol_sha256": digest(root / "protocol.json"), "metadata": metadata})
    finished = {"status": "incomplete", "reason": "Run interrupted before final model and input verification"}
    try:
        for cell in plan["schedule"]:
            result = run_cell(root, plan, cell, endpoint)
            print(json.dumps({**cell, "status": result["status"], "patch_confirmed": result["patch_validation"]["patch_confirmed_repairs"]}), flush=True)
        final_metadata = local_metadata(endpoint, plan["model"])
        if final_metadata != plan["model_metadata"]:
            raise ValueError("Model digest or server metadata changed during the study")
        verify_freeze(root, plan)
        finished = {"status": "complete", "metadata": final_metadata}
    except Exception as exc:
        finished["reason"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        finished["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(root / "finished.json", finished)
        summary = summarize_study(root)
    # A complete experiment can contain unsuccessful repairs; failure is data.
    return summary, 0 if summary["complete"] else 2
