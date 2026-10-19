"""One post-hoc real-project task case from the archived study; no model calls."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.tutorial_task import validate_tutorial_task


COMMIT = "edff96aeb2616402e9489d46e90a592c05565621"
SOURCE_NAMES = ["__init__.py", "database.py", "middlewares.py", "operations.py", "queries.py", "storages.py", "table.py", "utils.py", "version.py"]
CHECKS = """from pathlib import Path
from tinydb.storages import JSONStorage
expected = [{'int': 1, 'char': 'a'}, {'int': 1, 'char': 'b'}]
assert isinstance(db, TinyDB), 'Task must use TinyDB'
assert isinstance(db._storage, JSONStorage), 'Task requires JSON persistence'
assert Path(db._storage._handle.name).name == 'db.json', 'Use the documented relative database file'
assert db.all() == expected, 'Both original documents must be stored unchanged'
assert db.search(Query().char == 'b') == [expected[1]], 'The stored data must remain queryable'
db.close()
assert Path('db.json').is_file(), 'The example must create the database file'
with TinyDB('db.json') as reopened:
    assert reopened.all() == expected, 'Both documents must survive close and reopen'
    assert reopened.search(Query().char == 'a') == [expected[0]]
print('first-run-persistence-ok')
"""


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(study, output):
    study, output = Path(study).resolve(), Path(output)
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(study):
        raise ValueError("Case output must be new and outside the archived study")
    protocol = json.loads((study / "protocol.json").read_text())
    project = protocol["projects"]["tinydb"]
    if project["project"]["commit"] != COMMIT:
        raise ValueError("This case requires the exact archived TinyDB commit")
    root = study / "inputs/tinydb"
    source_files = ["tinydb/" + name for name in SOURCE_NAMES]
    selected = ["README.rst", "LICENSE", "pyproject.toml"] + source_files
    for relative in selected:
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != project["hashes"][relative]:
            raise ValueError("Archived project bytes changed: " + relative)
    diagnosis_path = study / "runs/tinydb/deepseek/1/lexical/analysis.json"
    analysis = json.loads(diagnosis_path.read_text())
    finding = next(f for f in analysis["findings"] if f["title"] == "入门示例使用占位路径且未说明文件创建行为")
    if analysis["mode"] != "live_model":
        raise ValueError("Expected an archived live-model diagnosis, not a synthetic finding")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(diagnosis_path, output / "recorded-analysis.json")
    contract = {"schema_version": "tutorial-task-1", "task": "从空的可写工作目录复制 README 首个示例，写入原有两条记录，关闭重开后核对持久化及查询",
                "source_revision": COMMIT, "document": "README.rst", "block": 1, "source_files": source_files,
                "support_files": ["LICENSE", "pyproject.toml"], "checks": CHECKS,
                "checks_author": "assistant-authored evaluator contract, frozen before candidate construction; not independent human review",
                "expected_stdout": "first-run-persistence-ok\n", "timeout_seconds": 5}
    dump(output / "task.json", contract)  # Freeze checks before constructing any candidate.
    text = (root / "README.rst").read_bytes().decode("utf-8")
    start = text.index(".. code-block:: python", text.index("Example Code\n"))
    stop = text.index("Query Language\n", start)
    original = text[start:stop]
    paragraph = ("Run this example in an empty, writable working directory. It creates\n"
                 "``db.json`` there and reuses that file on later runs. If you use another\n"
                 "path, create its parent directory first.\n\n")
    replacement = paragraph + original.replace("TinyDB('/path/to/db.json')", "TinyDB('db.json')", 1)
    candidate = {"schema_version": "tutorial-task-edit-1", "document_sha256": project["hashes"]["README.rst"],
                 "original": original, "replacement": replacement, "origin": "assistant_authored_candidate",
                 "rationale": "Apply the recorded local first-run recommendation; use a writable relative file and explain parent directories.",
                 "diagnosis_reference": {"type": "recorded_live_model_diagnosis", "provider": analysis["model"],
                    "generated_at": analysis["generated_at"], "finding": finding,
                    "analysis_sha256": hashlib.sha256(diagnosis_path.read_bytes()).hexdigest()}}
    dump(output / "candidate.json", candidate)
    report = validate_tutorial_task(root, output / "task.json", output / "candidate.json", output / "validation")
    negative = dict(candidate)
    negative["rationale"] = "Synthetic negative control: in-memory insertion cannot satisfy persistence"
    negative["replacement"] = original.replace("from tinydb import TinyDB, Query", "from tinydb import TinyDB, Query\n    >>> from tinydb.storages import MemoryStorage").replace(
        "TinyDB('/path/to/db.json')", "TinyDB(storage=MemoryStorage)")
    dump(output / "negative-candidate.json", negative)
    negative_report = validate_tutorial_task(root, output / "task.json", output / "negative-candidate.json", output / "negative-control")
    baseline = report["before"]
    if (report["status"] != "task_validation_passed" or baseline["failure_kind"] != "example_exception"
            or "FileNotFoundError" not in baseline["stderr"]
            or negative_report["after"]["status"] != "failed"
            or negative_report["after"]["failure_kind"] != "behavior_check"):
        raise ValueError("The intended case or negative control did not complete as specified; inspect retained reports")
    summary = {"schema_version": "tinydb-first-run-case-1", "status": "task_validation_passed",
               "project": "TinyDB", "commit": COMMIT, "version": "4.9.0", "case_type": "same_revision_first_run_usability",
               "diagnosis_kind": "recorded_live_model_diagnosis_reuse", "candidate_kind": "assistant_authored_candidate",
               "new_model_requests": 0, "diagnosis_title": finding["title"], "task": contract["task"],
               "before": baseline, "after": report["after"], "patch_replay": report["replay"],
               "negative_control": {"kind": "synthetic_candidate", "execution": negative_report["after"]},
               "contract_sha256": report["contract_sha256"], "adoption_status": "human_review_pending",
               "independent_human_review": False,
               "selection": "Post-hoc selected from known development-project findings; not an unseen evaluation sample",
               "limitations": ["Copy-and-run task assumes a fresh writable directory and takes the original placeholder literally.",
                               "Experienced readers who already replace the placeholder may not encounter this obstacle.",
                               "No package-install, RST-rendering, reader-efficiency or maintainer-adoption result.",
                               "The same assistant wrote checks and the candidate; checks were frozen first, but not independently human authored."]}
    dump(output / "case-summary.json", summary)
    dump(output / "provenance.json", {"repository": "https://github.com/msiemens/tinydb", "commit": COMMIT,
         "license": "MIT", "license_path": "validation/inputs/LICENSE", "source_files": selected,
         "source_hashes": {p: project["hashes"][p] for p in selected},
         "diagnosis_source": str(diagnosis_path), "diagnosis_sha256": hashlib.sha256(diagnosis_path.read_bytes()).hexdigest(),
         "study_protocol_sha256": hashlib.sha256((study / "protocol.json").read_bytes()).hexdigest(),
         "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    shutil.copyfile(output / "validation/adoptable.patch", output / "tinydb-first-run.patch")
    shutil.copyfile(Path(__file__), output / "run_tinydb_first_run_case.py")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.study, args.output)
    print(json.dumps({k: summary[k] for k in ("status", "commit", "candidate_kind", "new_model_requests")}, ensure_ascii=False))
