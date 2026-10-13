"""Deterministic source retrieval from public input, without running the library.

The retriever is deliberately lexical: a missing export cannot establish which
other library replaces it. Every returned value is an unchanged source slice.
"""

import ast
from collections import Counter
import keyword
import math
import re

from .providers import execution_feedback


_STOP = set(keyword.kwlist) | {
    "a", "an", "the", "of", "to", "by", "as", "at", "on", "this", "that",
    "these", "those", "it", "its", "be", "is", "are", "was", "were", "can",
    "will", "with", "which", "when", "then", "than", "only", "also", "have",
    "has", "do", "does", "not", "all", "any", "some", "each", "use", "used",
    "using", "self", "cls", "return", "returns", "param", "rtype", "args",
    "kwargs", "print", "repr", "str", "int", "list", "dict", "tuple", "set",
    "object", "value", "values", "true", "false", "none", "file", "line",
    "module", "traceback", "error", "example", "examples", "documented",
    "documentation", "upstream", "original", "code", "call", "calls",
    "official", "source", "target", "doctest", "repl", "statement",
    "statements", "expression", "expressions", "markdown", "form", "bare",
    "wrap", "wraps", "adds", "copied", "unchanged", "otherwise", "stored",
    "expected", "result", "results", "evaluator", "authored", "sentence",
    "contract", "context", "checked", "supported", "additional", "executable",
    "block", "listed", "command", "commands", "prompt", "prompts", "fixture",
    "sandbox", "cannot", "no", "name", "named", "so", "argument", "arguments",
}


def _terms(text):
    """Split identifiers and prose, including snake_case and CamelCase."""
    words = re.findall(r"[A-Za-z][A-Za-z_]*", text)
    result = []
    for word in words:
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", word).replace("_", " ").split()
        for part in parts:
            part = part.lower()
            # A light plural normalization, not a domain-specific synonym map.
            if len(part) > 4 and part.endswith("s") and not part.endswith(("ss", "is")):
                part = part[:-1]
            if len(part) > 1 and part not in _STOP:
                result.append(part)
    return result


def _doc(node):
    if node.body and isinstance(node.body[0], ast.Expr):
        value = node.body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return node.body[0]
    return None


def _names(node):
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _query(example, before):
    # Markdown destinations, hex revisions and traceback paths are provenance,
    # not task semantics. They otherwise dominate rare-word matching.
    context = re.sub(r"https?://[^\s)]+", "", example.context)
    context = re.sub(r"\b[a-fA-F0-9]{12,}\b", "", context)
    error = execution_feedback(before)["error"]
    # The final exception line carries the failure; preceding source lines and
    # runner frames can introduce irrelevant names into lexical retrieval.
    error = next((line for line in reversed(error.splitlines()) if line.strip()), "")
    query = Counter(_terms(context))
    called, imported, constructors = set(), set(), set()
    try:
        tree = ast.parse(example.code)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    aliases = {alias.asname or alias.name: alias.name
               for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
               for alias in node.names if alias.name != "*"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if isinstance(node.func, ast.Name):
                name = aliases.get(name, name)
            if name and name.lower() not in _STOP:
                called.add(name)
            for argument in node.keywords:
                for term in _terms(argument.arg or ""):
                    query[term] += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, (ast.Name, ast.Attribute)):
                name = getattr(func, "id", getattr(func, "attr", ""))
                if isinstance(func, ast.Name):
                    name = aliases.get(name, name)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        constructors.add(name)
    # Python's own exception exposes the actual receiver type even for dynamic
    # delegation. No configured evaluator output is admitted here.
    receiver_types = set(re.findall(r"'([^']+)' object has no attribute", error))
    failed = set(re.findall(r"(?:no attribute|cannot import name|name) ['\"]([\w]+)['\"]", error))
    for symbol in called | failed | receiver_types:
        for term in _terms(symbol):
            query[term] += 3 if symbol in called | failed else 1
    # Message words can distinguish runtime problems without allowing a long
    # traceback to overwhelm the task's prose.
    for term in set(_terms(error)):
        query[term] += 1
    # Library/class names are handled structurally below. Repeated branding in
    # docstrings is not evidence that a particular method repairs the behavior.
    for constructor in constructors:
        if constructor[:1].isupper():
            for term in _terms(constructor):
                query.pop(term, None)
    return query, called, imported, constructors | receiver_types, failed


def _units(sources):
    units = []
    for filename, text in sorted(sources.items()):
        lines = text.splitlines(keepends=True)
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue

        def add(node, owner="", kind="function"):
            start = node.lineno
            name = getattr(node, "name", "")
            if kind in {"function", "class"}:
                doc = _doc(node)
                end_header = max(start, node.body[0].lineno - 1)
                end_doc = doc.end_lineno if doc else end_header
                end = end_doc if kind == "class" else node.end_lineno
                # Prefer an entire short implementation or a complete API
                # docstring. Long docstrings get an explicitly bounded slice.
                ranges = [(start, end), (start, end_doc),
                          (start, min(end_doc, end_header + 12)), (start, end_header)]
                if kind == "function" and doc and len("".join(lines[start - 1:end])) > 900:
                    ranges.remove((start, end))
                ranges = list(dict.fromkeys(ranges))
                maximum = 1200 if kind == "class" else 2300
                feasible = [(a, b) for a, b in ranges
                            if len("".join(lines[a - 1:b])) <= maximum]
                if not feasible:
                    return
                ranges = feasible
            else:
                ranges = [(start, node.end_lineno)]
                if len("".join(lines[start - 1:node.end_lineno])) > 2300:
                    return
            evidence = "".join(lines[start - 1:node.end_lineno])
            if kind == "class":
                evidence = "".join(lines[start - 1:ranges[0][1]])
            if kind == "attribute":
                name = " ".join(sorted(_names(node)))
            units.append({"file": filename, "lines": lines, "ranges": ranges,
                          "name": name, "owner": owner, "kind": kind,
                          "terms": Counter(_terms(evidence)), "node": node})

        module_doc = _doc(tree)
        if module_doc:
            add(module_doc, kind="module")
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                add(node, kind="import")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                # Include public export/version metadata as real source, but
                # do not use arbitrary top-level data as an answer oracle.
                if _names(node) & {"__all__", "__version__"}:
                    add(node, kind="module")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add(node)
            elif isinstance(node, ast.ClassDef):
                add(node, kind="class")
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        add(child, owner=node.name)
                    elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                        add(child, owner=node.name, kind="attribute")
    return units


def source_context(example, before, sources, limit=6000):
    """Return relevant, disjoint source slices within a label+text char budget.

    Ranking combines saturated inverse-document-frequency term overlap with
    AST call/receiver scope. Class metadata and delegation methods are eligible
    so a similarly named method cannot hide default-instance semantics. Only
    the original snippet, public prose, sanitized runtime error and supplied
    source files affect retrieval; no case IDs or evaluator checks are read.
    """
    if type(limit) is not int or limit < 0:
        raise ValueError("source context limit must be a nonnegative integer")
    if not limit:
        return {}
    query, called, imported, roots, failed = _query(example, before)
    units = _units(sources)
    if not units:
        return {}
    # Resolve annotated return types for a receiver's method, without executing
    # descriptors, imports or any supplied code.
    for unit in units:
        node = unit["node"]
        if unit["owner"] in roots and unit["name"] in called and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns:
                roots.update(_names(node.returns))
    frequencies = Counter(term for unit in units for term in unit["terms"])
    average = sum(sum(unit["terms"].values()) for unit in units) / len(units) or 1
    for unit in units:
        terms = unit["terms"]
        length = sum(terms.values())
        lexical = 0.0
        for term in sorted(query.keys() & terms.keys()):
            idf = math.log(1 + (len(units) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            count = terms[term]
            lexical += idf * min(query[term], 3) * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        name, owner, kind = unit["name"], unit["owner"], unit["kind"]
        score = lexical
        in_scope = not owner or owner in roots
        if name in failed and in_scope:
            score += 80
        elif name in called and in_scope:
            # When a missing symbol is explicit, previously successful setup
            # calls should not displace the APIs needed to repair that failure.
            score += 10 if failed else 65
        if kind == "class" and name in roots:
            score += 65
        if owner in roots:
            if kind == "attribute":
                score += 18 if lexical else 0
            elif name == "__getattr__":
                score += 48
            elif name == "__init__":
                score += 5
            elif lexical:
                score += 5
        if name in imported:
            score += 3
        if kind in {"import", "module"}:
            score *= 0.3
        if name.startswith("_") and name not in called | failed and name not in {"__getattr__", "__init__"}:
            score *= 0.3
        # Saturated term frequency plus a modest cost penalty prevents verbose
        # repeated prose or common argument names from occupying the budget.
        start, end = unit["ranges"][0]
        cost = len("".join(unit["lines"][start - 1:end]))
        unit["score"] = score / (1 + cost / 3000)
    contexts, selected, used = {}, set(), 0
    ranked = sorted(units, key=lambda u: (-u["score"], u["file"], u["ranges"][0]))
    # Structural bonuses must not raise the cutoff for behavior matches in a
    # delegated type whose relationship is not expressible in static hints.
    minimum = 1.0
    for unit in ranked:
        if unit["score"] < minimum:
            continue
        for start, end in unit["ranges"]:
            # Decline overlapping units instead of sending the same signature
            # and body twice. Adjacent units remain separate for precise labels.
            positions = {(unit["file"], line) for line in range(start, end + 1)}
            if positions & selected:
                continue
            label = f"{unit['file']}:{start}-{end}"
            text = "".join(unit["lines"][start - 1:end])
            cost = len(label) + len(text)
            if text and used + cost <= limit:
                contexts[label] = text
                used += cost
                selected.update(positions)
                break
    return contexts
