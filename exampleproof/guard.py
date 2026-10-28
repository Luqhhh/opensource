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


def validate_candidate(original: str, candidate: str, *, allow_helpers=False,
                       preserve_existing_mutations=False) -> str | None:
    if not candidate.strip():
        return "Empty replacement"
    if len(candidate.encode()) > 32_000:
        return "Replacement exceeds 32 KB"
    try:
        old = ast.parse(original)
        new = ast.parse(candidate)
        return _validate_structure(old, new, allow_helpers=allow_helpers,
                                   preserve_existing_mutations=preserve_existing_mutations)
    except SyntaxError as exc:
        return f"Cannot structurally validate code: {exc.msg}"
    except RecursionError:
        # A short source can still produce a deeply nested AST, for example
        # a long addition chain. Parsing and assertion comparison must fail
        # closed without aborting evaluation of the remaining examples.
        return "Cannot structurally validate code: AST exceeds the supported recursion limit"


def _validate_structure(old: ast.Module, new: ast.Module, *, allow_helpers=False,
                        preserve_existing_mutations=False) -> str | None:
    # The first release accepts only repairs of straight-line examples. This
    # prevents moving a preserved assertion under `if False` or `try/except`.
    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr, ast.Assert)
    helpers = [node for node in new.body if isinstance(node, ast.FunctionDef)]
    if allow_helpers and helpers:
        if len(helpers) > 4:
            return "At most four local adapter functions are supported"
        for function in helpers:
            if function.name.startswith("__"):
                return "Dunder adapter names are outside the supported repair scope"
            if function.decorator_list or function.returns is not None or any(
                    argument.annotation is not None
                    for argument in (*function.args.posonlyargs, *function.args.args,
                                     *function.args.kwonlyargs,
                                     *([function.args.vararg] if function.args.vararg else []),
                                     *([function.args.kwarg] if function.args.kwarg else []))):
                return "Adapter functions cannot use decorators or annotations"
            defaults = [*function.args.defaults, *[value for value in function.args.kw_defaults if value is not None]]
            if any(not (isinstance(value, ast.Constant)
                        or isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.UAdd, ast.USub))
                        and isinstance(value.operand, ast.Constant)
                        and type(value.operand.value) in (int, float, complex)) for value in defaults):
                return "Adapter default arguments must be constants"
            body = function.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            if (not body or not isinstance(body[-1], ast.Return)
                    or any(not isinstance(node, (ast.Assign, ast.AnnAssign)) for node in body[:-1])):
                return "Adapters require local assignments followed by one return; no nested control flow or assertions"
    supported = allowed + ((ast.FunctionDef,) if allow_helpers else ())
    if any(not isinstance(node, supported) for node in new.body):
        return "v0.1 repairs must remain straight-line code (imports, assignments, calls, assertions)"
    original_asserts = Counter(ast.dump(n, include_attributes=False) for n in ast.walk(old) if isinstance(n, ast.Assert))
    candidate_asserts = Counter(ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, ast.Assert))
    if original_asserts - candidate_asserts:
        return "An original assertion was removed, changed, or moved out of top-level execution"
    banned_calls = {"exit", "quit", "eval", "exec", "compile", "__import__", "setattr", "delattr"}
    banned_attrs = {"exit", "_exit", "abort", "kill", "killpg", "_getframe", "settrace"}
    banned_references = banned_calls | banned_attrs
    preserved = {ast.dump(n, include_attributes=False) for n in old.body
                 if isinstance(n, (ast.Assign, ast.AnnAssign))} if preserve_existing_mutations else set()
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
            if any(not is_local_target(target) for target in targets) and ast.dump(node, include_attributes=False) not in preserved:
                return "Mutation of attributes or indexed values is outside the repair scope"
    return None
