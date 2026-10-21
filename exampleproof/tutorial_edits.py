"""Export conservative prose-only edits for review, never as verified repairs."""

from collections import defaultdict
import re

from .pipeline import unified_diff


def _protected_lines(text):
    protected, fence = set(), None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            protected.add(number)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
            protected.add(number)
        elif line.startswith(("    ", "\t")):
            protected.add(number)
    return protected


def _plain_paragraph(text):
    return (isinstance(text, str) and 1 <= len(text) <= 4000 and text == text.strip()
            and not re.search(r"\n\s*\n|[<>\x00-\x08\x0b\x0c\x0e-\x1f]", text)
            and not re.search(r"\b(?:assert|expected_stdout|stdout|stderr)\b", text)
            and re.search(r"[A-Za-z\u3400-\u9fff]", text) is not None
            and all(not re.match(r"^\s*(?:[#>*|+~`-]|\.\.\s|:[\w-]+:|\d+[.)]\s| {4}|\t)", line) for line in text.splitlines())
            and not text.endswith("::"))


def _tokens(text):
    return re.findall(r"(?::[\w:-]+:)?`+[^\r\n]*?`+_?|!?\[[^\]\r\n]*\]\([^\)\r\n]*\)|\b\w+__?\b", text)


def review_edits(snapshot, selected, proposals):
    result = {"status": "unverified_prose_edits", "quality_review_status": "not_reviewed",
              "validation_scope": "Exact paragraph match and protected-content guards only",
              "accepted": [], "rejected": [], "patch": ""}
    if not isinstance(proposals, list) or len(proposals) > 2:
        result["rejected"].append({"index": None, "reason": "Expected at most two prose edits"})
        return result
    available = {c.id: c for c in selected}
    grouped = defaultdict(list)
    for index, proposal in enumerate(proposals):
        try:
            if not isinstance(proposal, dict) or not isinstance(proposal.get("evidence_id"), str):
                raise ValueError("Invalid edit structure")
            chunk = available.get(proposal["evidence_id"])
            if chunk is None or not chunk.path.endswith((".md", ".rst")):
                raise ValueError("Edit must cite a selected Markdown or RST document")
            original, replacement = proposal.get("original"), proposal.get("replacement")
            if not _plain_paragraph(original) or not _plain_paragraph(replacement) or original == replacement:
                raise ValueError("Only changed, complete prose paragraphs are eligible")
            text = snapshot.files[chunk.path]["text"]
            if original not in chunk.text or text.count(original) != 1:
                raise ValueError("Original text must match exactly and uniquely in selected evidence")
            start = text.index(original)
            end = start + len(original)
            before, after = text[:start], text[end:]
            if ((before and not before.endswith(("\n\n", "\r\n\r\n")))
                    or (after not in {"", "\n", "\r\n"} and not after.startswith(("\n\n", "\r\n\r\n")))):
                raise ValueError("Edit must cover a whole paragraph")
            first = text.count("\n", 0, start) + 1
            last = first + original.count("\n")
            if _protected_lines(text) & set(range(first, last + 1)):
                raise ValueError("Code blocks and indented code are protected")
            if chunk.path.endswith(".rst") and (re.search(r"^\s*[:.\\]", replacement, re.M)
                    or re.search(r"^[=~^\"'#*+_-]{3,}\s*$", replacement, re.M)):
                raise ValueError("RST directives, roles and section structure cannot be introduced")
            if _tokens(original) != _tokens(replacement):
                raise ValueError("Inline code, roles and links must remain unchanged")
            if any(a < end and start < b for a, b, _ in grouped[chunk.path]):
                raise ValueError("Overlapping prose edits are not allowed")
            # Preserve the input document's newline convention.
            replacement = replacement.replace("\r\n", "\n")
            if "\r\n" in text:
                replacement = replacement.replace("\n", "\r\n")
            grouped[chunk.path].append((start, end, replacement))
            result["accepted"].append({"index": index, "evidence_id": chunk.id, "path": chunk.path,
                                       "start_line": first, "end_line": last,
                                       "original": original, "replacement": replacement,
                                       "status": "unverified_prose_edit"})
        except ValueError as exc:
            result["rejected"].append({"index": index, "reason": str(exc)})
    for path, edits in sorted(grouped.items()):
        original = snapshot.files[path]["text"]
        changed = original
        for start, end, replacement in sorted(edits, reverse=True):
            changed = changed[:start] + replacement + changed[end:]
        if snapshot.files[path].get("utf8_bom"):
            original, changed = "\ufeff" + original, "\ufeff" + changed
        result["patch"] += unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True),
                                        f"a/{path}", f"b/{path}")
    return result
