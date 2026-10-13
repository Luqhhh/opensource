"""Verify upstream bytes/extraction; optionally check the old runtime in isolation."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from exampleproof.extract import extract_markdown
from exampleproof.pipeline import run_project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    provenance = json.loads((root / "provenance.json").read_text())
    for item in provenance["files"]:
        digest = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Upstream bytes changed: {item['path']}")
    for case in provenance["cases"]:
        code = ""
        for reference in case["source_ranges"]:
            source = root / "upstream/v3.15.2" / reference["upstream_path"]
            lines = source.read_text().splitlines(keepends=True)
            for number in reference["command_lines"]:
                if not lines[number - 1].startswith(">>> "):
                    raise ValueError("Declared source line is not a doctest command")
                code += lines[number - 1][4:]
        path = case["id"].split("#")[0]
        actual = extract_markdown((root / path).read_text(), path)[0].code
        if actual != code or hashlib.sha256(code.encode()).hexdigest() != case["extracted_code_sha256"]:
            raise ValueError(f"Extracted commands changed: {path}")
    print(f"Verified {len(provenance['files'])} upstream files and {len(provenance['cases'])} exact command extractions")

    if args.historical_output:
        if args.historical_output.exists():
            raise ValueError("Historical output must be a new file")
        config = json.loads((root / "exampleproof.json").read_text())
        with tempfile.TemporaryDirectory(prefix="exampleproof-tinydb-historical-") as temporary:
            project = Path(temporary)
            shutil.copytree(root / "cases", project / "cases")
            shutil.copytree(root / "upstream/v3.15.2/tinydb", project / "tinydb")
            config["source_files"] = [str(p.relative_to(project)) for p in sorted((project / "tinydb").glob("*.py"))]
            (project / "exampleproof.json").write_text(json.dumps(config))
            report, _ = run_project(project)
        result = {
            "schema_version": 1,
            "purpose": "Original upstream documentation on its matching historical library version with identical behavior checks and the isolated runner.",
            "mode": "no_model_historical_runtime_validation",
            "documentation_commit": provenance["documentation"]["commit"],
            "runtime_commit": provenance["documentation"]["commit"],
            "runtime_version": "3.15.2",
            "source_mapping": "upstream/v3.15.2/tinydb/*.py -> /workspace/tinydb/*.py, unchanged",
            "report": report,
        }
        args.historical_output.parent.mkdir(parents=True, exist_ok=True)
        with args.historical_output.open("x") as target:
            json.dump(result, target, ensure_ascii=False, indent=2)
            target.write("\n")
        print(json.dumps(report["summary"]))
        return 0 if report["summary"]["counts"] == {"checked": 3} else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
