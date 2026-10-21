"""Conservative, source-bound observations and claim triage. Never execute inputs."""
import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import PurePosixPath
import re


def citation(files, path, first, last=None):
    lines = files[path]["text"].splitlines(keepends=True)
    last = last or first
    return {"path": path, "start_line": first, "end_line": last,
            "text": "".join(lines[first - 1:last])}


def _observation(rule, title, impact, suggestion, evidence, claim_type, **details):
    return {"origin": "static", "status": "static_observation", "rule": rule,
            "title": title, "category": "consistency" if claim_type == "source_conflict" else "prerequisites",
            "impact": impact, "suggestion": suggestion, "evidence": evidence,
            "claim_type": claim_type, "verification": "source_observation_only",
            "details": details}


def deterministic_findings(files):
    """Only compare explicit declarations, never infer runtime incompatibility."""
    findings, requirements, defaults = [], [], {}
    for path, item in sorted(files.items()):
        if PurePosixPath(path).name == "pyproject.toml":
            for line, text in enumerate(item["text"].splitlines(), 1):
                match = re.match(r'''\s*requires-python\s*=\s*["']\s*>=\s*(\d+)\.(\d+)(?:[,'"\s]|$)''', text)
                if match:
                    requirements.append((path, line, tuple(map(int, match.groups()))))
        if path.endswith(".py"):
            try:
                tree = ast.parse(item["text"])
            except (SyntaxError, ValueError, RecursionError):
                continue
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                args = node.args.posonlyargs + node.args.args
                pairs = list(zip(args[-len(node.args.defaults):], node.args.defaults)) if node.args.defaults else []
                pairs += list(zip(node.args.kwonlyargs, node.args.kw_defaults))
                for arg, default in pairs:
                    if isinstance(default, ast.Constant) and type(default.value) in {bool, type(None)}:
                        defaults.setdefault((node.name, arg.arg), []).append((path, node.lineno, default.end_lineno, default.value))
    for path, item in sorted(files.items()):
        if not path.endswith((".md", ".rst", ".mdx")):
            continue
        for line, text in enumerate(item["text"].splitlines(), 1):
            # Deliberately narrow: a README minimum-version declaration, not an arbitrary example.
            if "readme" in path.lower():
                version = re.search(r"\bPython\s+(\d+)\.(\d+)\+", text, re.I)
                if version:
                    declared = tuple(map(int, version.groups()))
                    for meta, meta_line, minimum in requirements:
                        if PurePosixPath(meta).parent == PurePosixPath(path).parent and declared != minimum:
                            findings.append(_observation("python-minimum-conflict", "Python 最低版本声明不一致",
                                "读者可能按 README 选择环境，而安装元数据要求另一最低版本；这里只比较声明。",
                                "核对项目实际支持范围后统一 README 与 requires-python。",
                                [citation(files, path, line), citation(files, meta, meta_line)], "source_conflict",
                                documented_minimum=list(declared), metadata_minimum=list(minimum)))
            if re.search(r"(?:/path/to/|/your/(?:path|directory)/)", text):
                findings.append(_observation("placeholder-path", "示例包含需要替换的占位路径",
                    "首次使用者若字面复制，可能找不到目录或文件；占位符本身不等于教程缺陷。",
                    "说明要替换的路径、父目录要求和预期运行位置。",
                    [citation(files, path, line)], "experience_suggestion"))
            # Compare only an explicit sentence about a named function's parameter default.
            match = re.search(r"\b(\w+)\s*\([^\n]*?\b(\w+)\s*=\s*(True|False|None)[^\n]*?\).*?(?:by default|默认)", text, re.I)
            if not match:
                match = re.search(r"(?:by default|默认).*?\b(\w+)\s*\([^\n]*?\b(\w+)\s*=\s*(True|False|None)", text, re.I)
            if match:
                function, parameter, written = match.groups()
                matches = defaults.get((function, parameter), [])
                if len(matches) == 1 and repr(matches[0][3]).casefold() != written.casefold():
                    source, source_line, source_end, actual = matches[0]
                    findings.append(_observation("literal-default-conflict", "参数默认值的文字与源码不一致",
                        "按文字理解的默认行为可能与当前函数签名不同；包装器和版本差异仍需人工确认。",
                        "核对所指函数和版本后修正文档中的默认值说明。",
                        [citation(files, path, line), citation(files, source, source_line, source_end)], "source_conflict",
                        function=function, parameter=parameter, documented=written, source_default=repr(actual)))
            if len(findings) >= 100:
                return findings
    return findings


MISSING = re.compile(r"缺少|缺失|未(?:说明|介绍|提供|记录|覆盖|提示|演示|提及|解释|描述)|没有(?:说明|介绍|提供|记录|提示|演示)|未文档化|\b(?:missing|undocumented|not documented|no documentation|does not document)\b", re.I)


def enrich_findings(snapshot, findings, *, search_missing=True):
    """Attach stable IDs, claim class, and local counter-evidence search receipts.

    Search hits are review leads, not independently established refutations. No
    extra model calls or cloud uploads occur, and a zero hit never proves absence.
    """
    from .tutorial import _tutorial_terms
    result, seen = [], set()
    for original in findings:
        item = dict(original)
        text = " ".join(str(item.get(k, "")) for k in ("title", "impact", "suggestion"))
        missing = bool(MISSING.search(text)) and item.get("origin") != "static"
        if "claim_type" not in item:
            item["claim_type"] = ("evidence_gap" if missing else "source_conflict" if item.get("category") == "consistency"
                                  else "example_risk" if re.search(r"Error|异常|运行失败|执行失败", text)
                                  else "experience_suggestion")
        item.setdefault("verification", "not_executed_not_independently_reviewed")
        if missing and search_missing:
            terms = set(_tutorial_terms(text))
            identifiers = re.findall(r"`([\w.]+)`|\b([A-Za-z_]\w{3,})\b", text)
            strong = {a or b for a, b in identifiers}
            ranked = []
            cited = {(e["path"], e["start_line"], e["end_line"]) for e in item.get("evidence", [])}
            for chunk in snapshot.chunks:
                searchable = chunk.path + " " + chunk.title + " " + chunk.text
                score = len(terms & set(_tutorial_terms(searchable)))
                score += 10 * sum(word in searchable for word in strong)
                if score:
                    ranked.append((-score, chunk.path, chunk.start_line, chunk))
            ranked.sort(key=lambda row: row[:3])
            hits = [row[3] for row in ranked[:6]]
            item["status"] = "needs_confirmation"
            item["source_search"] = {"status": "review_leads_found" if hits else "no_indexed_match",
                "scope": "frozen_eligible_index", "searched_chunks": len(snapshot.chunks),
                "query": text[:1000], "hits": [asdict(c) for c in hits],
                "new_evidence_spans": sum((c.path, c.start_line, c.end_line) not in cited for c in hits),
                "absence_established": False, "counterevidence_confirmed": False}
            item["review_note"] = "已补查冻结索引。命中只是待核对原文，不能据此确认缺陷或反驳；零命中也不证明项目缺失。"
        identity = {"snapshot": snapshot.snapshot_id, "origin": item.get("origin"), "rule": item.get("rule"),
                    "title": item.get("title"), "claim_type": item["claim_type"],
                    "evidence": [(e["path"], e["start_line"], e["end_line"]) for e in item.get("evidence", [])]}
        item["id"] = "f-" + hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        if item["id"] not in seen:
            result.append(item)
            seen.add(item["id"])
    return result
