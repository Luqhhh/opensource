import json
from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 2_000_000


def safe_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in {"..", "."} or p.startswith(".") for p in path.parts):
        raise ValueError(f"Only explicit, non-hidden relative paths are allowed: {relative}")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlinks are not allowed in project inputs: {relative}")
    target = current.resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError(f"Not a regular project file: {relative}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Input exceeds {MAX_FILE_BYTES} bytes: {relative}")
    return target


def load_config(root: Path) -> dict:
    config_path = root / "exampleproof.json"
    config = json.loads(safe_path(root, "exampleproof.json").read_text()) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("exampleproof.json must contain an object")
    config.setdefault("documents", ["README.md"])
    config.setdefault("source_files", [])
    config.setdefault("examples", {})
    config.setdefault("timeout_seconds", 5)
    if not isinstance(config["examples"], dict):
        raise ValueError("examples must be an object keyed by document#block")
    if not isinstance(config["timeout_seconds"], (int, float)) or not 0.1 <= config["timeout_seconds"] <= 30:
        raise ValueError("timeout_seconds must be between 0.1 and 30")
    total = 0
    for group in ("documents", "source_files"):
        if not isinstance(config[group], list) or not all(isinstance(x, str) for x in config[group]):
            raise ValueError(f"{group} must be a list of explicit paths")
        if len(config[group]) != len(set(config[group])):
            raise ValueError(f"Duplicate paths in {group}")
        for name in config[group]:
            if group == "documents" and not name.endswith(".md"):
                raise ValueError("Only Markdown documents are supported in v0.1")
            if group == "source_files" and not name.endswith(".py"):
                raise ValueError("Only explicitly selected Python source files are supported in v0.1")
            total += safe_path(root, name).stat().st_size
    if total > MAX_TOTAL_BYTES:
        raise ValueError("Selected inputs exceed the 2 MB limit")
    for key, spec in config["examples"].items():
        if not isinstance(spec, dict):
            raise ValueError(f"{key}: example configuration must be an object")
        for field in ("skip", "setup", "checks", "expected_stdout"):
            if field in spec and not isinstance(spec[field], str):
                raise ValueError(f"{key}: {field} must be a string")
        if spec.get("checks", "").strip():
            compile(spec["checks"], f"{key}:checks", "exec")
        compile(spec.get("setup", ""), f"{key}:setup", "exec")
    return config
