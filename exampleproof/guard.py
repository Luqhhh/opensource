"""Conservative integrity checks, not a proof of semantic correctness."""

import ast
from collections import Counter


def validate_candidate(original: str, candidate: str) -> str | None:
    if not candidate.strip():
        return "Empty replacement"
    if len(candidate.encode()) > 32_000:
        return "Replacement exceeds 32 KB"
    try:
        old = ast.parse(original)
        new = ast.parse(candidate)
    except SyntaxError as exc:
        return f"Cannot structurally validate code: {exc.msg}"
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
    for node in ast.walk(new):
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return "Dunder access is outside the supported repair scope"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return "Dunder access is outside the supported repair scope"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in banned_calls:
                return "Dynamic execution or process-control calls are outside the repair scope"
            if isinstance(node.func, ast.Attribute) and node.func.attr in banned_attrs:
                return "Process-control or runtime-introspection calls are outside the repair scope"
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(not isinstance(t, (ast.Name, ast.Tuple, ast.List)) for t in targets):
                return "Mutation of attributes or indexed values is outside the repair scope"
    return None
