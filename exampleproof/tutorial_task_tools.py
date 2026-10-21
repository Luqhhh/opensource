"""Task templates, isolated prerequisite checks and a safe document preview."""
import ast
from dataclasses import asdict
from html import escape
import json
from pathlib import Path, PurePosixPath
import re

from .config import safe_path
from .runner import SandboxRunner


def runtime_sources(contract, raw_files):
    root = contract.get("import_root", ".")
    if (not isinstance(root, str) or not root or PurePosixPath(root).is_absolute()
            or ".." in PurePosixPath(root).parts or "\\" in root or str(PurePosixPath(root)) != root):
        raise ValueError("import_root must be a normalized project-relative path")
    sources = {}
    for name in contract["source_files"]:
        path = PurePosixPath(name)
        if root != ".":
            if not path.is_relative_to(PurePosixPath(root)):
                raise ValueError("Every source file must be inside import_root")
            path = path.relative_to(root)
        target = path.as_posix()
        if target in sources:
            raise ValueError("Duplicate runtime source path")
        sources[target] = raw_files[name].decode("utf-8-sig")
    return sources


def prerequisite_check(code, sources, timeout=5):
    """Import only modules explicitly named in the example, inside Bubblewrap.

    Failure is an environment/prerequisite result, never proof of a tutorial bug.
    No project modules are imported into the host interpreter.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"status": "not_measured", "reason": "example_syntax_error", "execution": None}
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend("import " + alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imports.append("import " + node.module)
    imports = list(dict.fromkeys(imports))
    if not imports:
        return {"status": "not_required", "imports": [], "execution": None}
    execution = SandboxRunner(sources, timeout).run("\n".join(imports), {})
    missing = re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)", execution.stderr)
    name = missing[1] if missing else None
    generated = bool(name and name.split(".")[-1] in {"version", "_version", "_version_info", "_generated"})
    return {"status": "ready" if execution.status == "passed" else "environment_unprepared",
            "imports": imports, "execution": asdict(execution), "missing_module": name,
            "diagnostic": "possible_missing_generated_file" if generated else "missing_dependency" if name else
                          "sandbox_unavailable" if execution.status == "blocked" else "import_probe_failed" if execution.status != "passed" else "imports_passed",
            "advice": "核对固定版本的构建产物和依赖来源；不要把准备失败计为教程缺陷，也不要自动生成替代版本文件。" if execution.status != "passed" else None,
            "scope": "Selected imports only; package installation and all runtime paths are not verified."}


def create_template(project, document, block, task, output, *, import_root="."):
    from .tutorial_task import extract_task_blocks
    root, output = Path(project).resolve(), Path(output)
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):
        raise ValueError("Task template output must be new and outside the project")
    text = safe_path(root, document).read_text(encoding="utf-8-sig")
    blocks = extract_task_blocks(text, document)
    if type(block) is not int or not 1 <= block <= len(blocks):
        raise ValueError("Select an existing Python block")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A concrete reader task is required")
    # Reuse bounded input discovery and its sensitive-path/symlink exclusions.
    from .tutorial import discover
    files, skipped = discover(root)
    sources = sorted(p for p in files if p.endswith(".py") and
                     (import_root == "." or PurePosixPath(p).is_relative_to(import_root)))
    contract = {"schema_version": "tutorial-task-1", "task": task, "document": document, "block": block,
                "source_files": sources, "import_root": import_root, "setup": "", "checks": "",
                "checks_author": "PENDING: fill actual evaluator", "timeout_seconds": 5}
    # Empty checks deliberately cannot pass the task validator.
    runtime_sources(contract, {p: files[p]["text"].encode() for p in sources})
    output.mkdir(parents=True)
    (output / "task.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")
    (output / "selected-example.py").write_text(blocks[block - 1][0])
    (output / "instructions.txt").write_text(
        "这是待审核模板，不是冻结检查或独立评测。\n1. 核对源码清单、导入根目录和运行前提。\n"
        "2. 由评测者填写 setup/checks 或 expected_stdout，覆盖任务意图和典型错误。\n"
        "3. 在生成候选前冻结合同；模型不能编写或放宽这些检查。\n"
        "4. 运行 task-diagnose 检查导入准备，再用 task-improve 或 task-check。\n"
        "验证只覆盖选中代码块及显式检查，不包含完整安装、所有操作系统或完整 Sphinx 构建。\n")
    return {"status": "evaluator_contract_pending", "blocks": len(blocks), "selected_block": block,
            "sources": len(sources), "skipped": skipped, "output": str(output)}


def render_preview(text, path):
    """Escaped local preview; no RST includes, raw HTML or scripts are interpreted."""
    from .tutorial_task import extract_task_blocks
    blocks = extract_task_blocks(text, path)
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>文档结构预览</title><style>body{font:16px/1.7 system-ui;max-width:1050px;margin:40px auto}'
            'pre{white-space:pre-wrap;background:#f1f5f9;padding:20px}article{margin:24px 0}</style>'
            '<h1>文档结构预览</h1><p>仅渲染转义原文和已识别的 Python 块；不是 Sphinx/docutils 构建结果。</p>'
            f'<details><summary>完整原文：{escape(path)}</summary><pre>{escape(text)}</pre></details>' +
            ''.join(f'<article><h2>Python 块 {i}</h2><pre>{escape(code)}</pre><p>保留的 REPL 输出</p>'
                    f'<pre>{escape("".join(outputs))}</pre></article>' for i, (code, outputs) in enumerate(blocks, 1)) + '</html>')
