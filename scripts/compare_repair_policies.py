#!/usr/bin/env python3
"""Compare repair policies on frozen development inputs with matched budgets."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.benchmark import load_manifest, run_benchmark
from exampleproof.config import safe_path
from exampleproof.pipeline import read_project, validate_max_attempts
from exampleproof.providers import AdaptiveOllamaProvider, EditOllamaProvider, OllamaProvider, SemanticOllamaProvider, SignatureOllamaProvider
from exampleproof.study import local_metadata


class PairedV2Provider(SemanticOllamaProvider):
    def generation_options(self, history):
        options = dict(self.options)
        options["seed"] = (options["seed"] + len(history)) % 2**31
        return options


POLICIES = {"semantic-v2": PairedV2Provider, "semantic-v3": AdaptiveOllamaProvider,
            "semantic-v4": EditOllamaProvider, "semantic-v5": SignatureOllamaProvider}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def inventory(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def method_files():
    root = Path(__file__).resolve().parents[1]
    core = root / "exampleproof"
    return {**{path.name: path for path in sorted(core.glob("*.py"))},
            **{f"licenses/{path.name}": path for path in sorted((core / "licenses").glob("*.txt"))},
            "LICENSE": root / "LICENSE", "compare_repair_policies.py": Path(__file__).resolve()}


def current_method_hashes():
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in method_files().items()}


def supporting_files(root):
    # Keep attribution with copied inputs, without loading references/proposals
    # or unrelated upstream documentation into the model's source selection.
    selected = {name for name in ("provenance.json", "upstream-provenance.json") if (root / name).is_file()}
    for path in root.rglob("*"):
        if path.is_file() and (path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
                               or path.name.upper().endswith("-NOTICE.MD")):
            selected.add(path.relative_to(root).as_posix())
    return sorted(selected)


def summarize(plan, cells, complete, error=None):
    groups = {}
    for policy in plan.get("policies", ("semantic-v2", "semantic-v3")):
        selected = [cell for cell in cells if cell["policy"] == policy]
        usable = [cell for cell in selected if cell["metrics"]["evaluation_complete"]]
        failures = sum(cell["metrics"]["expected_failures"] for cell in usable)
        confirmed = sum(cell["metrics"]["patch_confirmed_repairs"] for cell in usable)
        group = {"completed_cells": len(usable), "case_runs": failures, "confirmed_repairs": confirmed,
                 "repair_rate": confirmed / failures if complete and failures else None,
                 "healthy_preserved": sum(cell["metrics"]["healthy_preserved"] for cell in usable)}
        for field in ("inference_requests", "input_tokens", "output_tokens", "inference_duration_seconds"):
            values = [cell.get("repair", {}).get(field) for cell in selected]
            group[field] = sum(values) if values and all(value is not None for value in values) else None
        groups[policy] = group
    return {"schema_version": 1, "complete": complete, "split": "development_regression",
            "independent_failure_cases": sum(project["failures"] for project in plan["projects"]),
            "groups": groups, "cells": cells, "error": error,
            "scope": "Previously observed development/regression cases; repeated seeds are not independent defects. This combined policy comparison is not a new holdout or an isolated causal ablation."}


def compare(projects, output, model, endpoint="http://127.0.0.1:11434", *, seeds=(17,), max_attempts=3, timeout=180,
            progress=None, policies=("semantic-v2", "semantic-v3")):
    validate_max_attempts(max_attempts)
    if len(policies) != 2 or len(set(policies)) != 2 or any(policy not in POLICIES for policy in policies):
        raise ValueError("Choose two different supported repair policies")
    if not seeds or len(set(seeds)) != len(seeds) or any(type(seed) is not int or not 0 <= seed < 2**31 for seed in seeds):
        raise ValueError("Seeds must be unique nonnegative 31-bit integers")
    options = {"temperature": 0.2, "num_ctx": 8192, "num_predict": 2048, "seed": seeds[0]}
    OllamaProvider(model, endpoint, timeout, options=options)
    # Shared comparison setting, not a policy-specific retry or answer hint.
    # Ollama's disabled default can abort degenerate small-model generations.
    options["repeat_penalty"] = 1.1
    roots = [Path(project).resolve() for project in projects]
    if not roots or any(not root.name for root in roots) or len({root.name for root in roots}) != len(roots):
        raise ValueError("Project names must be nonempty and unique")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Comparison output must be a new directory")
    prepared = []
    for root in roots:
        config, documents, sources, examples = read_project(root)
        manifest, raw = load_manifest(root, examples)
        prepared.append((root, config, documents, sources, manifest, raw))
    output.mkdir(parents=True)
    implementation = output / "implementation"
    implementation.mkdir()
    for name, path in method_files().items():
        target = implementation / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    plan = {"schema_version": 1, "status": "preparing", "split": "development_regression",
            "model": model, "max_attempts": max_attempts, "seeds": list(seeds), "options": options,
            "policies": list(policies),
            "implementation_sha256": inventory(implementation), "projects": []}
    for root, config, documents, sources, manifest, raw in prepared:
        frozen = output / "inputs" / root.name
        frozen.mkdir(parents=True)
        for name in sorted(set(documents) | set(sources) | set(supporting_files(root))):
            target = frozen / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(safe_path(root, name).read_bytes())
        (frozen / "exampleproof.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        (frozen / "metadata.json").write_bytes(raw)
        plan["projects"].append({"name": root.name, "input_sha256": inventory(frozen),
                                 "failures": sum(case["expected_before"] == "failed" for case in manifest["cases"])})
    write_json(output / "protocol.json", plan)
    cells, complete, error = [], False, None
    try:
        metadata = local_metadata(endpoint, model)
        digest = metadata["model"].get("digest")
        if not isinstance(digest, str) or not digest:
            raise ValueError("Model metadata lacks an exact digest")
        plan.update(status="frozen_before_inference", model_metadata=metadata,
                    frozen_at=datetime.now(timezone.utc).isoformat())
        write_json(output / "protocol.json", plan)
        write_json(output / "summary.json", summarize(plan, cells, False))
        if current_method_hashes() != plan["implementation_sha256"]:
            raise ValueError("Current implementation differs from frozen method")
        for seed in seeds:
            # Alternate policy order across seeds to reduce fixed ordering bias.
            ordered_policies = policies if seeds.index(seed) % 2 == 0 else policies[::-1]
            for project in plan["projects"]:
                frozen = output / "inputs" / project["name"]
                for policy in ordered_policies:
                    if (inventory(frozen) != project["input_sha256"]
                            or inventory(implementation) != plan["implementation_sha256"]
                            or current_method_hashes() != plan["implementation_sha256"]):
                        raise ValueError("Frozen inputs or implementation changed")
                    provider_type = POLICIES[policy]
                    provider = provider_type(model, endpoint, timeout)
                    provider.options = {**options, "seed": seed}
                    cell = {"seed": seed, "policy": policy, "project": project["name"]}
                    run_options = {}
                    if progress is not None:
                        progress({**cell, "stage": "comparison_cell_start"})
                        def cell_progress(event):
                            progress({**cell, **event})
                        run_options["progress"] = cell_progress
                    evidence, code = run_benchmark(frozen, output / "runs" / str(seed) / policy / project["name"],
                                                   provider, max_attempts=max_attempts, **run_options)
                    cells.append({"seed": seed, "policy": policy, "project": project["name"], "exit_code": code,
                                  "metrics": evidence["metrics"], "repair": evidence.get("repair", {})})
                    write_json(output / "summary.json", summarize(plan, cells, False))
                    if progress is not None:
                        progress({**cell, "stage": "comparison_cell_complete", "exit_code": code,
                                  "confirmed_repairs": evidence["metrics"]["patch_confirmed_repairs"]})
                    if code == 2:
                        raise ValueError("Comparison stopped because execution or model evidence is incomplete")
        if local_metadata(endpoint, model)["model"].get("digest") != digest:
            raise ValueError("Model digest changed during comparison")
        for project in plan["projects"]:
            if inventory(output / "inputs" / project["name"]) != project["input_sha256"]:
                raise ValueError("Frozen inputs changed during comparison")
        if (inventory(implementation) != plan["implementation_sha256"]
                or current_method_hashes() != plan["implementation_sha256"]):
            raise ValueError("Frozen implementation changed during comparison")
        complete = all(cell["metrics"]["evaluation_complete"] for cell in cells)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    result = summarize(plan, cells, complete, error)
    write_json(output / "summary.json", result)
    return result, 0 if complete else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--seeds", nargs="+", type=int, default=[17])
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--model-timeout", type=float, default=180)
    parser.add_argument("--policies", nargs=2, choices=tuple(POLICIES), default=("semantic-v2", "semantic-v3"))
    parser.add_argument("--quiet", action="store_true", help="Suppress progress on stderr")
    args = parser.parse_args()
    def progress(event):
        print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
    result, code = compare(args.projects, args.output, args.model, args.endpoint,
                           seeds=tuple(args.seeds), max_attempts=args.max_attempts, timeout=args.model_timeout,
                           progress=None if args.quiet else progress, policies=tuple(args.policies))
    print(json.dumps({key: result[key] for key in ("complete", "groups", "error")}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, SyntaxError) as exc:
        print(f"comparison: {exc}", file=sys.stderr)
        sys.exit(2)
