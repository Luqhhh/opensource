"""Verify an explicit tutorial edit against a frozen task, using only SandboxRunner."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .config import MAX_TOTAL_BYTES, safe_path
from .extract import extract_markdown
from .guard import validate_candidate
from .pipeline import unified_diff
from .runner import SandboxRunner


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_task_blocks(text, path):
    """Bounded Markdown/RST Python blocks; preserve all recorded REPL outputs."""
    if path.endswith(".md"):
        return [(e.code, ()) for e in extract_markdown(text, path)]
    if not path.endswith(".rst"):
        raise ValueError("Task validation currently supports Markdown and explicit RST Python code blocks")
    lines, blocks, index = text.splitlines(keepends=True), [], 0
    while index < len(lines):
        match = re.fullmatch(r"( *)\.\. code-block:: (python|pycon)\s*\n?", lines[index])
        if not match:
            index += 1
            continue
        indent = len(match[1])
        index += 1
        content = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
                break
            content.append(line)
            index += 1
        nonblank = [len(line) - len(line.lstrip(" ")) for line in content if line.strip()]
        if not nonblank:
            raise ValueError("Empty RST Python code block")
        margin = min(nonblank)
        content = [line[margin:] if line.strip() else line for line in content]
        if any(line.startswith(":") for line in content if line.strip()):
            raise ValueError("RST code-block options require explicit support")
        pycon = any(line.startswith(">>> ") for line in content)
        code, outputs = [], []
        for line in content:
            if pycon:
                if line.startswith((">>> ", "... ")):
                    code.append(line[4:])
                elif line.strip() == "...":
                    code.append("\n")
                elif line.strip():
                    outputs.append(line)
            else:
                code.append(line)
        blocks.append(("".join(code).strip() + "\n", tuple(outputs)))
    return blocks


def review_task_edit(document, path, contract, candidate):
    required = {"schema_version", "document_sha256", "original", "replacement", "origin", "rationale"}
    if (not isinstance(candidate, dict) or set(candidate) - required - {"diagnosis_reference"}
            or not required <= candidate.keys() or candidate["schema_version"] != "tutorial-task-edit-1"
            or candidate["document_sha256"] != _hash(document)
            or not isinstance(candidate["origin"], str) or candidate["origin"] not in {"assistant_authored_candidate", "recorded_candidate", "live_model_candidate", "synthetic_candidate"}
            or any(not isinstance(candidate[k], str) or not candidate[k] or len(candidate[k]) > 32000
                   for k in ("original", "replacement", "rationale"))):
        raise ValueError("Invalid task edit or document hash mismatch")
    original = document.decode("utf-8")
    if original.count(candidate["original"]) != 1 or candidate["original"] == candidate["replacement"]:
        raise ValueError("Task edit must match exactly once and change the document")
    changed = original.replace(candidate["original"], candidate["replacement"], 1)
    before, after = extract_task_blocks(original, path), extract_task_blocks(changed, path)
    selected = contract["block"] - 1
    if len(before) != len(after) or not 0 <= selected < len(before):
        raise ValueError("Python block count and selected block must remain stable")
    for index, (old, new) in enumerate(zip(before, after)):
        if old[1] != new[1] or index != selected and old != new:
            raise ValueError("Other Python blocks and recorded expected outputs must remain unchanged")
    old_directives = re.findall(r"^\s*\.\. [\w-]+::[^\n]*", original, re.M)
    if old_directives != re.findall(r"^\s*\.\. [\w-]+::[^\n]*", changed, re.M):
        raise ValueError("RST directives must remain unchanged")
    rejection = validate_candidate(before[selected][0], after[selected][0])
    if rejection:
        raise ValueError(rejection)
    patch = unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True), f"a/{path}", f"b/{path}")
    return before[selected][0], after[selected][0], changed.encode("utf-8"), patch


def prepare_task_inputs(root, contract_path):
    root = Path(root).resolve()
    contract_raw = Path(contract_path).read_bytes()
    if len(contract_raw) > 128000:
        raise ValueError("Task contract exceeds 128 KB")
    contract = json.loads(contract_raw)
    allowed = {"schema_version", "task", "document", "block", "source_files", "checks", "setup", "expected_stdout",
               "timeout_seconds", "source_revision", "checks_author", "support_files"}
    if (not isinstance(contract, dict) or set(contract) - allowed
            or contract.get("schema_version") != "tutorial-task-1"
            or not isinstance(contract.get("task"), str) or not contract["task"].strip()
            or type(contract.get("block")) is not int or contract["block"] < 1
            or not isinstance(contract.get("source_files"), list) or len(contract["source_files"]) > 1000
            or any(not isinstance(p, str) or not p.endswith(".py") for p in contract["source_files"])
            or len(set(contract["source_files"])) != len(contract["source_files"])
            or not isinstance(contract.get("document"), str)
            or not contract["document"].endswith((".md", ".rst"))):
        raise ValueError("Invalid explicit tutorial task contract")
    for field in ("setup", "checks", "expected_stdout"):
        if field in contract and not isinstance(contract[field], str):
            raise ValueError("Task setup, checks and expected_stdout must be strings")
    if not contract.get("checks", "").strip() and "expected_stdout" not in contract:
        raise ValueError("A frozen task oracle is required; candidate assertions are not independent evidence")
    timeout = contract.get("timeout_seconds", 5)
    if type(timeout) not in {int, float} or not 0.1 <= timeout <= 30:
        raise ValueError("Task timeout must be 0.1..30 seconds")
    spec = {k: contract[k] for k in ("setup", "checks", "expected_stdout") if k in contract}
    compile(spec.get("setup", ""), "task-setup", "exec")
    compile(spec.get("checks", ""), "task-checks", "exec")
    support = contract.get("support_files", [])
    if not isinstance(support, list) or len(support) > 100 or any(not isinstance(p, str) for p in support):
        raise ValueError("Support files must be an explicit bounded path list")
    paths = [contract["document"]] + contract["source_files"] + support
    if len(paths) != len(set(paths)):
        raise ValueError("Task input paths must be distinct")
    raw_files = {p: safe_path(root, p).read_bytes() for p in paths}
    if sum(map(len, raw_files.values())) > MAX_TOTAL_BYTES:
        raise ValueError("Task input exceeds 2 MB")
    sources = {p: raw_files[p].decode("utf-8") for p in contract["source_files"]}
    old_blocks = extract_task_blocks(raw_files[contract["document"]].decode("utf-8"), contract["document"])
    if contract["block"] > len(old_blocks):
        raise ValueError("Task Python block does not exist")
    old_code = old_blocks[contract["block"] - 1][0]
    return contract_raw, contract, raw_files, spec, old_code


def validate_tutorial_task(root, contract_path, candidate_path, output):
    root, output = Path(root).resolve(), Path(output)
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):
        raise ValueError("Task output must be a new directory outside the project")
    contract_raw, contract, raw_files, spec, old_code = prepare_task_inputs(root, contract_path)
    timeout = contract.get("timeout_seconds", 5)
    sources = {p: raw_files[p].decode("utf-8") for p in contract["source_files"]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "contract.json").write_bytes(contract_raw)
    for p, raw in raw_files.items():
        target = output / "inputs" / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    _dump(output / "input-manifest.json", {p: _hash(raw) for p, raw in raw_files.items()})
    shutil.copytree(Path(__file__).parent, output / "implementation/exampleproof",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    license_path = Path(__file__).parent.parent / "LICENSE"
    if license_path.is_file():
        shutil.copyfile(license_path, output / "implementation/LICENSE")
    _dump(output / "protocol.json", {"frozen_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": _hash(contract_raw), "source_revision": contract.get("source_revision"),
        "runner": "bubblewrap", "timeout_seconds": timeout, "candidate_read_after_baseline": True,
        "implementation_sha256": {p.name: _hash(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))},
        "oracle_source": "caller-supplied frozen contract; no independent human review inferred"})
    runner = SandboxRunner(sources, timeout)
    before = runner.run(old_code, spec)
    _dump(output / "before.json", asdict(before))
    candidate_raw = Path(candidate_path).read_bytes()
    if len(candidate_raw) > 128000:
        raise ValueError("Task candidate exceeds 128 KB")
    candidate = json.loads(candidate_raw)
    (output / "candidate.json").write_bytes(candidate_raw)
    before_code, after_code, changed, patch = review_task_edit(raw_files[contract["document"]], contract["document"], contract, candidate)
    if before_code != old_code:
        raise ValueError("Frozen task extraction changed")
    (output / "candidate.patch").write_text(patch, encoding="utf-8", newline="")
    after = runner.run(after_code, spec)
    _dump(output / "after.json", asdict(after))
    with tempfile.TemporaryDirectory(prefix="exampleproof-task-") as temporary:
        copied = Path(temporary)
        for p, raw in raw_files.items():
            target = copied / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        for args in (["git", "apply", "--check", "-"], ["git", "apply", "-"]):
            applied = subprocess.run(args, cwd=copied, input=patch.encode(), capture_output=True, timeout=10)
            if applied.returncode:
                raise ValueError("Exported task patch could not apply to the frozen copy")
        patched = (copied / contract["document"]).read_bytes()
        if patched != changed:
            raise ValueError("Applied document bytes differ from the reviewed candidate")
        replay_blocks = extract_task_blocks(patched.decode("utf-8"), contract["document"])
        replay_sources = {p: (copied / p).read_bytes().decode("utf-8") for p in contract["source_files"]}
        replay = SandboxRunner(replay_sources, timeout).run(replay_blocks[contract["block"] - 1][0], spec)
    _dump(output / "replay.json", asdict(replay))
    unchanged = all(safe_path(root, p).read_bytes() == raw for p, raw in raw_files.items())
    passed = before.status in {"failed", "timeout"} and after.status == replay.status == "passed" and unchanged
    status = "task_validation_passed" if passed else "blocked" if "blocked" in {before.status, after.status, replay.status} else "task_validation_failed"
    report = {"schema_version": "tutorial-task-result-1", "status": status, "task": contract["task"],
              "document": contract["document"], "source_revision": contract.get("source_revision"),
              "candidate_origin": candidate["origin"], "diagnosis_reference": candidate.get("diagnosis_reference"),
              "before": asdict(before), "after": asdict(after), "replay": asdict(replay),
              "contract_sha256": _hash(contract_raw), "inputs_unchanged": unchanged,
              "patch_applied_to_temporary_copy": True, "model_requests": 0,
              "adoption_status": "human_review_pending", "independent_human_review": False,
              "limitations": ["One explicit reader task and caller-supplied oracle, not general semantic correctness.",
                              "Candidate and checks may share an author; no independent quality or user-study result inferred.",
                              "Package installation and full documentation rendering are outside this task."]}
    if passed:
        (output / "adoptable.patch").write_text(patch, encoding="utf-8", newline="")
    _dump(output / "task-report.json", report)
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>教程任务验证</title><style>body{max-width:950px;margin:40px auto;font:16px/1.6 system-ui}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:12px}</style>'
            f'<h1>教程任务验证：{escape(status)}</h1><p>{escape(contract["task"])}</p>'
            f'<p>原始：{before.status} · 修改后：{after.status} · 应用补丁复查：{replay.status}</p>'
            '<p>待人工审阅；没有完成独立人工质量评审或上游采纳。</p>'
            f'<h2>原始失败</h2><pre>{escape(before.stderr)}</pre><h2>补丁</h2><pre>{escape(patch)}</pre></html>')
    (output / "task-report.html").write_text(html, encoding="utf-8")
    return report
