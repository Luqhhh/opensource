"""Conservative integrity checks, not a proof of semantic correctness."""

import ast
from collections import Counter


def is_local_target(node: ast.AST) -> bool:
    """Allow local bindings, including nested unpacking, without object writes."""
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(is_local_target(item) for item in node.elts)
    if isinstance(node, ast.Starred):
        return is_local_target(node.value)
    return False


def validate_candidate(original: str, candidate: str) -> str | None:
    if not candidate.strip():
        return "Empty replacement"
    if len(candidate.encode()) > 32_000:
        return "Replacement exceeds 32 KB"
    try:
        old = ast.parse(original)
        new = ast.parse(candidate)
        return _validate_structure(old, new)
    except SyntaxError as exc:
        return f"Cannot structurally validate code: {exc.msg}"
    except RecursionError:
        # A short source can still produce a deeply nested AST, for example
        # a long addition chain. Parsing and assertion comparison must fail
        # closed without aborting evaluation of the remaining examples.
        return "Cannot structurally validate code: AST exceeds the supported recursion limit"


def _validate_structure(old: ast.Module, new: ast.Module) -> str | None:
    # The first release accepts only repairs of straight-line examples. This
    # prevents moving a preserved assertion under `if False` or `try/except`.
    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr, ast.Assert)
    if any(not isinstance(node, allowed) for node in new.body):
        return "v0.1 repairs must remain straight-line code (imports, assignments, calls, assertions)"
    original_asserts = Counter(ast.dump(n, include_attributes=False) for n in ast.walk(old) if isinstance(n, ast.Assert))
    candidate_asserts = Counter(ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, ast.Assert))
    if original_asserts - candidate_asserts:
        return "An original assertion was removed, changed, or moved out of top-level execution"
    banned_calls = {"exit", "quit", "eval", "exec", "compile", "__import__", "setattr", "delattr"}
    banned_attrs = {"exit", "_exit", "abort", "kill", "killpg", "_getframe", "settrace"}
    banned_references = banned_calls | banned_attrs
    for node in ast.walk(new):
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return "Dunder access is outside the supported repair scope"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return "Dunder access is outside the supported repair scope"
        # Check references, not only call sites: `stop = os._exit` and
        # `from os import _exit as stop` must not bypass the call restrictions.
        if isinstance(node, ast.Name) and node.id in banned_references:
            return "Dynamic execution or process-control references are outside the repair scope"
        if isinstance(node, ast.Attribute) and node.attr in banned_references:
            return "Process-control or runtime-introspection references are outside the repair scope"
        if isinstance(node, ast.ImportFrom) and any(alias.name in banned_references for alias in node.names):
            return "Dynamic execution or process-control imports are outside the repair scope"
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(not is_local_target(target) for target in targets):
                return "Mutation of attributes or indexed values is outside the repair scope"
    return None
