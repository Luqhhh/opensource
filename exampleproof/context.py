"""Deterministic source retrieval from public input, without running the library.

The retriever is deliberately lexical: a missing export cannot establish which
other library replaces it. Every returned value is an unchanged source slice.
"""

import ast
from collections import Counter
import keyword
import json
import math
import re

from .providers import execution_feedback
from .stdlib_index import STDLIB_INDEX


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
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                receiver = aliases.get(node.func.value.id, node.func.value.id)
                if receiver[:1].isupper() and receiver in imported:
                    constructors.add(receiver)
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


def _index_terms(entries):
    units = [(entry, Counter(_terms(entry[4]))) for entry in entries]
    frequencies = Counter(term for _, terms in units for term in terms)
    average = sum(sum(terms.values()) for _, terms in units) / len(units) if units else 1
    return units, frequencies, average or 1


class SourceContextCache:
    """Provider-owned cache for one source snapshot; never execute input code.

    Exact contents, not filenames or object identity, invalidate the cache.
    Rankings are calculated afresh for every task and cannot mutate cached units.
    """

    def __init__(self):
        self._snapshot = None
        self._project_units = None
        self._standard_terms = None

    def project_units(self, sources):
        snapshot = tuple(sorted(sources.items()))
        if snapshot != self._snapshot:
            self._project_units = _units(sources)
            self._snapshot = snapshot
        return self._project_units

    def standard_terms(self):
        if self._standard_terms is None:
            self._standard_terms = _index_terms(STDLIB_INDEX)
        return self._standard_terms


def _project_context(example, before, sources, limit, *, units=None):
    """Return relevant, disjoint source slices within a label+text char budget.

    Ranking combines saturated inverse-document-frequency term overlap with
    AST call/receiver scope. Class metadata and delegation methods are eligible
    so a similarly named method cannot hide default-instance semantics. Only
    the original snippet, public prose, sanitized runtime error and supplied
    source files affect retrieval; no case IDs or evaluator checks are read.
    """
    if not limit:
        return {}
    query, called, imported, roots, failed = _query(example, before)
    # Only score dictionaries are mutable; AST nodes and source lines stay read-only.
    units = _units(sources) if units is None else [dict(unit) for unit in units]
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
        structure = owner in roots and name in {"__getattr__", "__init__"}
        explicit = name in called | failed
        if (owner.startswith("_") and owner not in roots
                or name.startswith("_") and not (explicit or structure or name in roots)
                or owner and owner not in roots and not explicit and len(query.keys() & terms.keys()) < 2):
            unit["score"] = 0
            continue
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


def missing_project_import(example, before, sources):
    """Require an observed missing import from a selected project package."""
    error = execution_feedback(before)["error"]
    match = re.search(r"(?:^|\n)ImportError: cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]", error)
    if not match:
        return False
    symbol, module = match.groups()
    stem = module.replace(".", "/")
    if stem + ".py" not in sources and stem + "/__init__.py" not in sources:
        return False
    try:
        tree = ast.parse(example.code)
    except SyntaxError:
        return False
    return any(isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == module
               and any(alias.name == symbol for alias in node.names) for node in ast.walk(tree))


def _stdlib_context(example, before, limit, entries=STDLIB_INDEX, *, index=None):
    """Rank the complete fixed public-function index without host inspection."""
    if not limit or not entries:
        return {}
    query, called, _, _, failed = _query(example, before)
    # A replacement search targets the missing import. Existing surrounding
    # calls are setup/context, not requests to replace those same names again.
    for symbol in called - failed:
        for term in _terms(symbol):
            query.pop(term, None)
    units, frequencies, average = _index_terms(entries) if index is None else index
    ranked = []
    for entry, terms in units:
        shared = query.keys() & terms.keys()
        named = set(_terms(entry[3])) & query.keys()
        # A rare topical word alone (e.g. a data type in unrelated utilities)
        # is weak evidence for an API replacement. Require the public name and
        # another query term to support a standard-library suggestion.
        if len(shared) < 2 or not named:
            continue
        score = 0.0
        length = sum(terms.values())
        for term in sorted(shared):
            idf = math.log(1 + (len(units) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            count = terms[term]
            score += idf * min(query[term], 3) * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        # A function name directly describing the public task is stronger than
        # the same term in a long list of parameter documentation.
        score += 3 * len(named)
        ranked.append((score / (1 + len(entry[4]) / 3000), entry))
    contexts, used = {}, 0
    ranked.sort(key=lambda value: (-value[0], value[1][:4]))
    if not ranked:
        return {}
    minimum = max(1, ranked[0][0] * 0.35)
    for score, (filename, start, end, name, text) in ranked:
        if score < minimum or len(contexts) >= 3:
            continue
        lines = text.splitlines(keepends=True)
        # Full signatures/docstrings are preferred. A long API docstring can
        # contribute its initial 12 source lines, retaining precise line labels.
        for count in dict.fromkeys((len(lines), min(len(lines), 12))):
            excerpt = "".join(lines[:count])
            label = f"{filename}:{start}-{start + count - 1}"
            cost = len(label) + len(excerpt)
            if cost + used <= limit:
                contexts[label] = excerpt
                used += cost
                break
    return contexts


def source_context(example, before, sources, limit=6000, *, cache=None):
    """Return deterministic real source slices, with a bounded stdlib fallback.

    A runtime-confirmed missing project import allocates two thirds to project
    sources and one third to the static CPython index (4000/2000 at the default
    limit); unused allocation does not flow between pools. Otherwise all 6000
    characters are available to project evidence. Evaluator checks and candidate
    patches never affect retrieval. No indexed source is imported or executed.
    """
    if type(limit) is not int or limit < 0:
        raise ValueError("source context limit must be a nonnegative integer")
    if not limit:
        return {}
    project_options = {"units": cache.project_units(sources)} if cache is not None else {}
    if not missing_project_import(example, before, sources):
        return _project_context(example, before, sources, limit, **project_options)
    project_limit = limit * 2 // 3
    standard_options = {"index": cache.standard_terms()} if cache is not None else {}
    return {**_project_context(example, before, sources, project_limit, **project_options),
            **_stdlib_context(example, before, limit - project_limit, **standard_options)}


def merge_source_contexts(groups, *, limit=6000):
    """Merge ranked exact slices without duplicate lines or exceeding the budget."""
    if type(limit) is not int or limit < 0:
        raise ValueError("source context limit must be a nonnegative integer")
    result, selected, used = {}, set(), 0
    for group in groups:
        for label, text in group.items():
            filename, positions = label.rsplit(":", 1)
            start, end = map(int, positions.split("-"))
            lines = text.splitlines(keepends=True)
            if len(lines) != end - start + 1:
                raise ValueError("Source context labels must match the original source lines")
            cursor = 0
            while cursor < len(lines):
                if (filename, start + cursor) in selected:
                    cursor += 1
                    continue
                first = cursor
                while cursor < len(lines) and (filename, start + cursor) not in selected:
                    cursor += 1
                new_label = f"{filename}:{start + first}-{start + cursor - 1}"
                excerpt = "".join(lines[first:cursor])
                cost = len(new_label) + len(excerpt)
                if cost + used <= limit:
                    result[new_label] = excerpt
                    selected.update((filename, start + index) for index in range(first, cursor))
                    used += cost
    return result


def source_api_headers(context, units, *, limit=1200):
    """Label API owners using only complete headers in the selected excerpts."""
    result = {}
    for label in context:
        filename, span = label.rsplit(":", 1)
        start, end = map(int, span.split("-"))
        for unit in units:
            node = unit["node"]
            if unit["file"] != filename or unit["kind"] != "function" or unit["name"].startswith("_"):
                continue
            header_end = max(node.lineno, node.body[0].lineno - 1)
            if not start <= node.lineno <= header_end <= end:
                continue
            signature = "".join(unit["lines"][node.lineno - 1:header_end])
            supplied = context[label].splitlines(keepends=True)
            if "".join(supplied[node.lineno - start:header_end - start + 1]) != signature:
                continue
            key = f"{filename}:{node.lineno}-{header_end}"
            value = {"qualified_name": ".".join(part for part in (unit["owner"], unit["name"]) if part),
                     "signature": signature}
            candidate = {**result, key: value}
            if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
                result = candidate
    return result


def _accepts_calls(node, calls, *, bound=False):
    """Conservative static argument binding; unknown *args/**kwargs stay eligible."""
    positional = [*node.args.posonlyargs, *node.args.args]
    if bound:
        positional = positional[1:]
    names = [arg.arg for arg in positional]
    required = set(names[:max(0, len(positional) - len(node.args.defaults))])
    keyword_only = {arg.arg for arg in node.args.kwonlyargs}
    required_keywords = {arg.arg for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults) if default is None}
    positional_only = {arg.arg for arg in node.args.posonlyargs}
    for call in calls:
        if any(isinstance(arg, ast.Starred) for arg in call.args) or any(arg.arg is None for arg in call.keywords):
            continue
        count, keys = len(call.args), {arg.arg for arg in call.keywords}
        if (count > len(names) and node.args.vararg is None
                or keys & positional_only and node.args.kwarg is None
                or keys & (set(names[:count]) - positional_only)
                or keys - set(names) - keyword_only and node.args.kwarg is None
                or required - set(names[:count]) - (keys - positional_only)
                or required_keywords - keys):
            return False
    return True


def _public_import_path(filename, name, sources):
    """Resolve explicit top-level reexports without importing a project."""
    module = filename.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
    if filename.startswith("stdlib/") and filename not in sources:
        return module.removeprefix("stdlib."), name
    paths = {(module, name)}
    for source_file, text in sorted(sources.items()):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        public_module = source_file.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        package = public_module.split(".") if source_file.endswith("/__init__.py") else public_module.split(".")[:-1]
        pending = list(tree.body)
        while pending:
            item = pending.pop(0)
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(item, ast.ImportFrom):
                if item.level:
                    if item.level > len(package):
                        continue
                    imported = ".".join(package[:len(package) - item.level + 1] + (item.module or "").split("."))
                else:
                    imported = item.module
                for alias in item.names:
                    exposed = alias.asname or alias.name
                    if imported == module and alias.name == name and not exposed.startswith("_"):
                        paths.add((public_module, exposed))
            else:
                # Follow module-level try/if bodies; never enter function/class scopes.
                for field in ("body", "orelse", "finalbody", "handlers"):
                    pending.extend(getattr(item, field, ()))
    public = [path for path in paths if all(part.isidentifier() and not part.startswith("_") for part in path[0].split("."))]
    return min(public, key=lambda path: (len(path[0].split(".")), path)) if public else None


def source_repair_choices(example, before, sources, context, units, *, limit=1200):
    """Offer source-derived renames with compatible calls, never evaluator answers.

    Only observed missing imports/names/attributes trigger this finite search.
    Candidates remain unverified until the unchanged guard and sandbox accept
    them. Source excerpts and public argument shapes are the only API evidence.
    """
    from .guard import validate_candidate
    from .providers import apply_line_edits, validate_public_bindings

    error = execution_feedback(before)["error"].splitlines()
    error = error[-1] if error else ""
    imported = re.fullmatch(r"ImportError: cannot import name ['\"](\w+)['\"] from ['\"]([^'\"]+)['\"].*", error)
    undefined = re.fullmatch(r"NameError: name ['\"](\w+)['\"] is not defined.*", error)
    attribute = re.fullmatch(r"AttributeError: ['\"]([^'\"]+)['\"] object has no attribute ['\"](\w+)['\"].*", error)
    if not (imported or undefined or attribute):
        return []
    missing = imported[1] if imported else undefined[1] if undefined else attribute[2]
    try:
        tree = ast.parse(example.code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    lines = example.code.split("\n")
    targets = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == missing]
    import_node = next((node for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 0
                        and imported and node.module == imported[2]
                        and any(alias.name == missing for alias in node.names)), None)
    if imported and (import_node is None or import_node.lineno != import_node.end_lineno):
        return []
    bound_names = {missing}
    if import_node:
        bound_names = {alias.asname or alias.name for alias in import_node.names if alias.name == missing}
    for item in tree.body:
        if isinstance(item, ast.Assign) and (isinstance(item.value, ast.Name) and item.value.id in bound_names
                or isinstance(item.value, ast.Attribute) and item.value in targets):
            bound_names.update(target.id for target in item.targets if isinstance(target, ast.Name))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and (isinstance(node.func, ast.Name) and node.func.id in bound_names or node.func in targets)]
    roots = _query(example, before)[3]
    headers = source_api_headers(context, units, limit=100_000)
    available = [(key, header["qualified_name"], next(unit["node"] for unit in units
                  if unit["file"] == key.rsplit(":", 1)[0] and unit["kind"] == "function"
                  and unit["node"].lineno == int(key.rsplit(":", 1)[1].split("-")[0])))
                 for key, header in headers.items()]
    if not attribute:
        # Include only static stdlib signatures actually present in this request.
        for filename, start, end, name, text in STDLIB_INDEX:
            for label, excerpt in context.items():
                source_file, span = label.rsplit(":", 1)
                first, last = map(int, span.split("-"))
                if source_file != filename or not first <= start <= last:
                    continue
                node = ast.parse(text).body[0]
                count = max(1, node.body[0].lineno - 1)
                signature = "".join(text.splitlines(keepends=True)[:count])
                if start + count - 1 <= last and signature == "".join(excerpt.splitlines(keepends=True)[start - first:start - first + count]):
                    available.append((f"{filename}:{start}-{start + count - 1}", name, node))
    choices, seen = [], set()
    for location, qualified, node in available:
        owner, _, name = qualified.rpartition(".")
        if attribute and (owner not in roots or not targets or any(target.lineno != target.end_lineno for target in targets)):
            continue
        if not attribute and owner:
            continue
        decorators = {getattr(decorator, "id", getattr(decorator, "attr", "")) for decorator in node.decorator_list}
        if decorators - {"staticmethod", "classmethod"}:
            continue
        if not _accepts_calls(node, calls, bound=bool(owner) and "staticmethod" not in decorators):
            continue
        replacements = {}
        if attribute:
            for number in {target.lineno for target in targets}:
                text = lines[number - 1].encode("utf-8")
                for target in sorted((target for target in targets if target.lineno == number), key=lambda target: -target.end_col_offset):
                    end = target.end_col_offset
                    text = text[:end - len(missing.encode("utf-8"))] + name.encode("utf-8") + text[end:]
                replacements[number] = text.decode("utf-8").removesuffix("\r")
            api = qualified
        else:
            path = _public_import_path(location.rsplit(":", 1)[0], name, sources)
            if path is None:
                continue
            module, exported = path
            api = f"{module}.{exported}"
            if import_node:
                remaining = [alias for alias in import_node.names if alias.name != missing]
                replacement = ast.unparse(ast.ImportFrom(module=import_node.module, names=remaining, level=0)) + "\n" if remaining else ""
                replacement += "\n".join(f"from {module} import {exported}" + (f" as {bound}" if bound != exported else "") for bound in sorted(bound_names & {alias.asname or alias.name for alias in import_node.names}))
                replacements[import_node.lineno] = replacement
            else:
                replacements[1] = f"from {module} import {exported}" + (f" as {missing}" if missing != exported else "") + "\n" + lines[0].removesuffix("\r")
        edit = {"edits": [{"line": number, "replacement": text} for number, text in sorted(replacements.items())], "rationale": ""}
        try:
            code = apply_line_edits(example.code, edit)["code"]
        except ValueError:
            continue
        if (code in seen or validate_candidate(example.code, code, allow_helpers=True)
                or validate_public_bindings(example, code)):
            continue
        choice = {"id": len(choices) + 1, "api": api, "source": location, "edit": edit}
        if len(json.dumps([*choices, choice], ensure_ascii=False)) <= limit:
            choices.append(choice)
            seen.add(code)
        if len(choices) >= 8:
            break
    return choices


def _parameter_usage_hints(node, parameters):
    """Static usage clues for ranking only; names can be rebound by a project."""
    hints = {}

    def add(name, kind, line, value=None):
        if name not in parameters:
            return
        hint = hints.setdefault(name, {})
        entries = hint.setdefault(kind, {} if value is not None else [])
        if value is not None:
            if len(entries) < 5:
                entries[value] = line
        elif line not in entries and len(entries) < 3:
            entries.append(line)

    for item in ast.walk(node):
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name):
            if item.func.id in {"iter", "len"} and item.args and isinstance(item.args[0], ast.Name):
                add(item.args[0].id, "iterable", item.lineno)
            elif item.func.id == "range":
                for argument in item.args:
                    if isinstance(argument, ast.Name):
                        add(argument.id, "integer_index", item.lineno)
        elif isinstance(item, ast.BinOp) and isinstance(item.op, ast.Mult):
            for sequence, count in ((item.left, item.right), (item.right, item.left)):
                if (isinstance(count, ast.Name) and (isinstance(sequence, (ast.List, ast.Tuple))
                        or isinstance(sequence, ast.Constant) and isinstance(sequence.value, (str, bytes)))):
                    add(count.id, "integer_index", item.lineno)
        elif (isinstance(item, ast.Compare) and isinstance(item.left, ast.Name) and len(item.ops) == 1
              and isinstance(item.ops[0], ast.Eq) and isinstance(item.comparators[0], ast.Constant)
              and isinstance(item.comparators[0].value, str) and len(item.comparators[0].value) <= 40):
            add(item.left.id, "branch_values", item.lineno, item.comparators[0].value)
    # A single equality is a special case, not useful enum-like evidence.
    for hint in hints.values():
        if len(hint.get("branch_values", {})) < 2:
            hint.pop("branch_values", None)
    return {name: hint for name, hint in hints.items() if hint}


def call_repair_context(example, before, context, units, *, limit=1200):
    """Describe one observed failing invocation using selected real signatures.

    This is a proposal scope, not a diagnosis of all TypeErrors. Unknown
    receivers, ambiguous source definitions and unpacked inputs stay outside
    this constrained mode. No project import or expression is evaluated.
    """
    if before.returncode != 21:
        return None
    error = execution_feedback(before)["error"]
    if not any(line.startswith("TypeError:") for line in error.splitlines()):
        return None
    locations = re.findall(r'File [\'"]/work/example\.py[\'"], line (\d+)', error)
    if not locations:
        return None
    line = int(locations[-1])
    try:
        tree = ast.parse(example.code)
    except (SyntaxError, ValueError, RecursionError):
        return None
    aliases = {alias.asname or alias.name: (node.module, alias.name)
               for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 0
               for alias in node.names if alias.name != "*"}
    modules = {alias.asname or alias.name.split(".")[0]: alias.name for node in tree.body
               if isinstance(node, ast.Import) for alias in node.names}
    roots = _query(example, before)[3]
    protected = {id(node) for assertion in ast.walk(tree) if isinstance(assertion, ast.Assert)
                 for node in ast.walk(assertion)}
    headers = source_api_headers(context, units, limit=100_000)
    selected = {(key.rsplit(":", 1)[0], int(key.rsplit(":", 1)[1].split("-")[0])): key for key in headers}
    candidates = []
    for call in ast.walk(tree):
        if (not isinstance(call, ast.Call) or id(call) in protected
                or not call.lineno <= line <= call.end_lineno
                or any(isinstance(arg, ast.Starred) for arg in call.args)
                or any(arg.arg is None for arg in call.keywords)):
            continue
        name, namespace, bound = "", None, False
        if isinstance(call.func, ast.Name):
            namespace, name = aliases.get(call.func.id, (None, call.func.id))
        elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            name = call.func.attr
            namespace = modules.get(call.func.value.id)
            bound = namespace is None
        else:
            continue
        matches = []
        for unit in units:
            node = unit["node"]
            if (unit["kind"] != "function" or not isinstance(node, ast.FunctionDef)
                    or unit["name"] != name or (unit["file"], node.lineno) not in selected
                    or bool(unit["owner"]) != bound or bound and unit["owner"] not in roots
                    or namespace and unit["file"].split("/")[0].removesuffix(".py") != namespace.split(".")[0]):
                continue
            decorators = {getattr(item, "id", getattr(item, "attr", "")) for item in node.decorator_list}
            if decorators - {"staticmethod", "classmethod"} or node.args.vararg or node.args.kwarg:
                continue
            positional = [*node.args.posonlyargs, *node.args.args]
            defaults = {arg.arg: default for arg, default in zip(positional[-len(node.args.defaults):], node.args.defaults)} if node.args.defaults else {}
            if bound and "staticmethod" not in decorators:
                positional = positional[1:]
            parameters = []
            for parameter in positional:
                item = {"name": parameter.arg, "kind": "positional_only" if parameter in node.args.posonlyargs else "keyword"}
                if parameter.arg in defaults:
                    item["default"] = ast.unparse(defaults[parameter.arg])
                else:
                    item["required"] = True
                parameters.append(item)
            for parameter, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                parameters.append({"name": parameter.arg, "kind": "keyword_only",
                                   **({"required": True} if default is None else {"default": ast.unparse(default)})})
            arguments = [{"id": index, "expression": ast.get_source_segment(example.code, argument)}
                         for index, argument in enumerate([*call.args, *[keyword.value for keyword in call.keywords]], 1)]
            if (not arguments or len(arguments) > 8 or len(arguments) > len(parameters)
                    or len(arguments) < sum(item.get("required", False) for item in parameters)
                    or len(arguments) == 1 and _accepts_calls(node, [call], bound=bound and "staticmethod" not in decorators)):
                continue
            evidence = {"function": ast.get_source_segment(example.code, call.func),
                        "source": selected[(unit["file"], node.lineno)],
                        "span": [call.lineno, call.col_offset, call.end_lineno, call.end_col_offset],
                        "parameters": parameters, "arguments": arguments,
                        "original_binding_valid": _accepts_calls(node, [call], bound=bound and "staticmethod" not in decorators)}
            hints = _parameter_usage_hints(node, {parameter["name"] for parameter in parameters})
            if hints and len(json.dumps({**evidence, "usage_hints": hints}, ensure_ascii=False)) <= limit:
                evidence["usage_hints"] = hints
            if len(json.dumps(evidence, ensure_ascii=False)) <= limit:
                matches.append(evidence)
        if len(matches) == 1:
            candidates.append(matches[0])
    return candidates[0] if len(candidates) == 1 else None
