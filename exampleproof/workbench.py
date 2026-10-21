"""Export a read-only product demonstration bound to frozen evidence; no review UI."""
import hashlib
from html import escape
import json
from pathlib import Path
import shutil

from .tutorial_eval import verify, summarize


def export_workbench(frozen, output, *, run=None, engineering_cases=None, preflight=None, quality_review=None):
    frozen, output = Path(frozen).resolve(), Path(output)
    identity = verify(frozen)
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(frozen):
        raise ValueError("Workbench output must be new and outside the frozen evidence")
    protocol = json.loads((frozen / "protocol.json").read_text())
    files = {}
    for project in protocol["projects"]:
        files[project] = {p.relative_to(frozen / "inputs" / project).as_posix(): p.read_text(encoding="utf-8-sig")
                          for p in sorted((frozen / "inputs" / project).rglob("*")) if p.is_file()}
    payload = {"schema_version": "exampleproof-workbench-1", "seal": identity, "protocol": protocol,
               "files": files, "reports": {}, "summary": None, "engineering_cases": [], "preflight_approved": False,
               "evidence_status": "frozen_tasks_pending_human_review"}
    if preflight:
        from .tutorial_eval import check_review
        review = json.loads(Path(preflight).read_text())
        check_review(review, identity, protocol["cases"] if protocol.get("review_schema") == 2 else None)
        payload["preflight_approved"] = True
        payload["evidence_status"] = "tasks_human_reviewed"
    if run:
        run = Path(run).resolve()
        verify(run)
        quality = json.loads(Path(quality_review).read_text()) if quality_review else None
        payload["summary"] = summarize(frozen, run, quality)
        payload["summary"].pop("reviewer", None)  # The demonstration does not need the reviewer's identity.
        payload["evidence_status"] = "model_results_human_reviewed" if quality else "model_results_pending_independent_quality_review"
        for case in protocol["cases"]:
            for strategy in protocol["strategies"]:
                payload["reports"][case["id"] + "/" + strategy] = json.loads((run / case["id"] / strategy / "analysis.json").read_text())
        if quality:
            for row in quality["rows"]:
                report = payload["reports"][row["case"] + "/" + row["strategy"]]
                for finding in row["findings"]:
                    report["findings"][finding["index"]]["human_review"] = {
                        k: finding.get(k) for k in ("judgment", "reason", "factual_relation")}
    if engineering_cases:
        from .config import safe_path
        suite = Path(engineering_cases).resolve()
        payload["engineering_seal"] = verify(suite)
        index = json.loads((suite / "case-index.json").read_text())
        if index.get("schema_version") != "engineering-case-suite-1":
            raise ValueError("Expected a sealed engineering-case suite")
        for entry in index["cases"]:
            report = json.loads(safe_path(suite, entry["report"]).read_text())
            if report.get("schema_version") != "tutorial-task-result-1":
                raise ValueError("Expected a real task execution report")
            payload["engineering_cases"].append(entry | {"validation": report,
                "patch_text": safe_path(suite, entry["patch"]).read_text(),
                "diagnosis": json.loads(safe_path(suite, entry["analysis"], max_bytes=16_000_000).read_text())["findings"][entry["finding_index"]]})
        payload["engineering_comparison"] = json.loads((suite / "comparison-audit.json").read_text())
    output.mkdir(parents=True)
    assets = Path(__file__).parent / "web"
    for name in ("workbench.css", "workbench.js"):
        shutil.copyfile(assets / name, output / name)
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = (assets / "index.html").read_text().replace("__EVIDENCE_DATA__", data)
    (output / "index.html").write_text(html, encoding="utf-8")
    # Preserve licenses for the source excerpts carried in the offline page.
    for project, entries in files.items():
        for path, content in entries.items():
            if Path(path).name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
                destination = output / "licenses" / project / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
    if engineering_cases:
        for p in suite.rglob("*"):
            if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
                destination = output / "licenses/engineering" / p.relative_to(suite)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, destination)
    (output / "manifest.json").write_text(json.dumps({"seal": identity, "source_frozen": str(frozen),
        "files": {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(output.rglob("*")) if p.is_file()},
        "privacy": "Offline local page. No external assets, model calls, telemetry or automatic uploads.",
        "presentation_scope": "Read-only user-facing demonstration. No approvals, scoring, observer forms or automatic uploads."}, ensure_ascii=False, indent=2))
    return {"status": "local_demo_ready", "page": str(output / "index.html"), "seal": identity,
            "tasks": len(protocol["cases"]), "design": "research"}
