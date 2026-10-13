"""Verify copied bytes and deterministic doctest conversion without host imports.

An optional historical control executes only through ExampleProof's fail-closed
SandboxRunner; it never imports any downloaded library into this interpreter.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[2]


def verify():
    provenance = json.loads((ROOT / "provenance.json").read_text())
    config = json.loads((ROOT / "exampleproof.json").read_text())
    for item in provenance["files"]:
        contents = (ROOT / item["local_path"]).read_bytes()
        assert hashlib.sha256(contents).hexdigest() == item["sha256"], item["local_path"]
        assert len(contents) == item["size_bytes"], item["local_path"]
    for case in provenance["cases"]:
        source = ROOT / "upstream/5.0.0" / case["documentation_path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == case["documentation_file_sha256"]
        lines = source.read_text().splitlines(keepends=True)
        excerpt = "".join("".join(lines[a - 1:b]) + "\n" for a, b in case["line_ranges"])
        original = ROOT / case["original_excerpt_path"]
        assert original.read_text() == excerpt, original
        assert hashlib.sha256(original.read_bytes()).hexdigest() == case["original_excerpt_sha256"]
        commands, expected = [], []
        for a, b in case["line_ranges"]:
            for line in lines[a - 1:b]:
                stripped = line.strip()
                if stripped.startswith(">>> "):
                    command = stripped[4:]
                    commands.append("print(" + command + ")" if isinstance(ast.parse(command).body[0], ast.Expr) else command)
                else:
                    expected.append(stripped)
        document = ROOT / case["document_path"]
        text = document.read_text()
        assert hashlib.sha256(document.read_bytes()).hexdigest() == case["document_sha256"]
        code = text.split("```python\n", 1)[1].split("```", 1)[0]
        symbol = {"collate": "collate", "grouper": "grouper", "healthy_chunked": "chunked"}[document.stem]
        assert code == "from more_itertools import " + symbol + "\n" + "\n".join(commands) + "\n", document
        assert config["examples"][case["id"]]["expected_stdout"] == "\n".join(expected) + "\n", case["id"]
    selected = config["documents"] + config["source_files"]
    assert all((ROOT / path).stat().st_size <= 256_000 for path in selected)
    assert sum((ROOT / path).stat().st_size for path in selected) <= 2_000_000
    return provenance, config


def historical_control(destination, provenance, config):
    # Only repository-owned verifier modules are imported on the host.
    sys.path.insert(0, str(REPOSITORY))
    from exampleproof.pipeline import exit_code, run_project
    from exampleproof.report import write_report

    destination.mkdir(parents=True, exist_ok=False)
    inputs = destination / "inputs"
    inputs.mkdir()
    for path in config["documents"]:
        target = inputs / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    mapping = provenance["historical_positive_control"]["source_mapping"]
    for runtime_path, stored_path in mapping.items():
        target = inputs / runtime_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / stored_path, target)
    historical_config = dict(config, source_files=list(mapping))
    (inputs / "exampleproof.json").write_text(json.dumps(historical_config, indent=2) + "\n")
    report, patch = run_project(inputs)
    write_report(destination / "check", report, patch)
    validation = {
        "schema_version": 1,
        "mode": "historical_positive_control",
        "library_version": "5.0.0",
        "dependency_version": "six 1.16.0",
        "runner": report["runner"],
        "summary": report["summary"],
        "same_documents_and_examples_configuration": True,
        "live_model_requests": report["repair"]["inference_requests"],
        "exit_code": exit_code(report),
    }
    (destination / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))
    return exit_code(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-output", type=Path, help="New output directory for the sandbox-only 5.0.0 positive control")
    args = parser.parse_args()
    provenance, config = verify()
    print(json.dumps({"provenance": "verified", "upstream_files": len(provenance["files"]), "cases": len(provenance["cases"])}))
    if args.historical_output:
        return historical_control(args.historical_output, provenance, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
