"""Freeze and run a small, explicit 2x2 live tutorial analysis study."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.model_api import JSONClient
from exampleproof.project_input import project_input
from exampleproof.tutorial import prepare_project
from exampleproof.tutorial_study import audit_comparison, run_comparison


PROJECTS = [("tinydb", "msiemens/tinydb", "edff96aeb2616402e9489d46e90a592c05565621", "previously_seen_development_project"),
            ("schedule", "dbader/schedule", None, "new_project_snapshot_not_claimed_holdout"),
            ("humanize", "python-humanize/humanize", None, "new_project_snapshot_not_claimed_holdout")]
SEEDS = [17, 29]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="backslashreplace")


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    projects = {}
    for name, repository, ref, exposure in PROJECTS:
        with project_input(repository, ref=ref) as (root, provenance):
            snapshot = prepare_project(root, provenance)
            destination = output / "inputs" / name
            for relative, item in snapshot.files.items():
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = (b"\xef\xbb\xbf" if item["utf8_bom"] else b"") + item["text"].encode("utf-8")
                if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    raise ValueError("Input round-trip failed")
                path.write_bytes(raw)
            projects[name] = {"project": provenance, "exposure": exposure, "snapshot_id": snapshot.snapshot_id,
                              "files": len(snapshot.files), "chunks": len(snapshot.chunks),
                              "hashes": {p: f["sha256"] for p, f in snapshot.files.items()},
                              "candidate_ids": [c.id for c in snapshot.candidates], "skipped": snapshot.skipped}
        print(json.dumps({"event": "input_frozen", "project": name, "commit": provenance["commit"],
                          "files": projects[name]["files"]}), flush=True)
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "exampleproof", output / "implementation/exampleproof",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(source / "LICENSE", output / "implementation/LICENSE")
    shutil.copyfile(Path(__file__), output / "implementation/run_tutorial_factorial.py")
    protocol = {"schema_version": "tutorial-factorial-1", "frozen_at": datetime.now(timezone.utc).isoformat(),
                "projects": projects, "providers": {"deepseek": "deepseek-flash", "ollama": "qwen2.5-coder:7b"},
                "strategies": ["lexical", "ai"], "repetitions": 2, "ollama_seeds": SEEDS,
                "context_chars": 12000, "max_output_tokens": 2048, "temperature": 0, "timeout_seconds": 180,
                "ollama_context_tokens": 8192, "max_parallel_requests_per_provider": 1,
                "execution_order": "two concurrent provider streams; same project order; strategy order reversed in repetition 2",
                "max_benchmark_model_requests": 36,
                "model_primary_comparison": "providers with identical lexical evidence; prompts and inputs equal; model families differ",
                "context_comparison": "lexical versus ai within each provider; same final character cap, actual extra selection costs included",
                "quality_review": {"reviewer": "assistant_source_review_after_anonymous_shuffling",
                                   "independent_human_review": False,
                                   "rubric": {"supported": "Main claim is specifically supported by frozen project sources and actionable",
                                              "partial": "Plausible local improvement, but missing scope or qualification prevents a firm defect claim",
                                              "unsupported": "Contradicted by sources, unsupported absence claim, or unsupported incompatibility claim",
                                              "unassessable": "Evidence is insufficient to check the main claim"},
                                   "no_recall_estimate": "No independent exhaustive gold issue list exists",
                                   "no_learning_efficiency_claim": True},
                "implementation_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted((source / "exampleproof").glob("*.py"))},
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limitations": ["Only three projects; repeats are not additional independent projects.",
                                "Providers use different models, tokenizers and chat templates; no transport-only inference.",
                                "Same final character limit is not the same total token or money budget.",
                                "Source review is by an assistant, not independent human validation."]}
    dump(output / "protocol.json", protocol)


def client_for(provider, repetition):
    if provider == "deepseek":
        return JSONClient("deepseek", "deepseek-flash", timeout=180)
    return JSONClient("ollama", "qwen2.5-coder:7b", timeout=180,
                      ollama_options={"temperature": 0, "seed": SEEDS[repetition], "num_ctx": 8192, "num_predict": 2048})


def run(output):
    protocol = json.loads((output / "protocol.json").read_text())
    source = Path(__file__).resolve().parents[1] / "exampleproof"
    if any(hashlib.sha256((source / name).read_bytes()).hexdigest() != expected
           for name, expected in protocol["implementation_sha256"].items()):
        raise ValueError("Implementation changed after freeze")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != protocol["script_sha256"]:
        raise ValueError("Study script changed after freeze")
    def stream(provider):
        for name, project in protocol["projects"].items():
            for repetition in range(protocol["repetitions"]):
                root = output / "inputs" / name
                current = prepare_project(root, project["project"])
                if current.snapshot_id != project["snapshot_id"]:
                    raise ValueError("Frozen input changed")
                destination = output / "runs" / name / provider / str(repetition + 1)
                if destination.exists():
                    raise ValueError("Refusing to overwrite or rerun an existing result")
                print(json.dumps({"event": "starting", "project": name, "provider": provider,
                                  "repetition": repetition + 1}), flush=True)
                result = run_comparison(root, project["project"], destination, client_for(provider, repetition),
                                        context_chars=protocol["context_chars"],
                                        arm_order=("lexical", "ai") if repetition == 0 else ("ai", "lexical"))
                audit = audit_comparison(destination)
                dump(destination / "audit.json", audit)
                print(json.dumps({"event": "completed", "project": name, "provider": provider,
                                  "repetition": repetition + 1, "status": result["run_status"],
                                  "audit": audit["status"], "requests": result["model_requests"]}), flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(stream, provider) for provider in protocol["providers"]]
        for future in futures:
            future.result()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    (freeze if args.command == "freeze" else run)(args.output)


if __name__ == "__main__":
    main()
