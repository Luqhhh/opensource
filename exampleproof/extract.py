"""A deliberately bounded fenced-code parser (no indented/list code blocks)."""

import re
from .models import Example

OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")
LANGUAGES = {"python", "py", "python3"}


def extract_markdown(text: str, path: str) -> list[Example]:
    lines = text.splitlines(keepends=True)
    results = []
    opening = None
    heading = ""
    index = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if opening is not None:
            start, fence, language, context = opening
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", stripped):
                if language in LANGUAGES:
                    index += 1
                    results.append(Example(
                        id=f"{path}#{index}", path=path,
                        start_line=start + 2, end_line=i,
                        code="".join(lines[start + 1:i]), context=context,
                    ))
                opening = None
            continue
        if stripped.lstrip().startswith("#"):
            heading = stripped.strip()
        match = OPEN.fullmatch(stripped)
        if match:
            fence, info = match.groups()
            language = info.strip().split()[0].lower() if info.strip() else ""
            if fence[0] == "`" and "`" in info:
                continue
            preceding = "".join(lines[max(0, i - 4):i]).strip()
            opening = (i, fence, language, (heading + "\n" + preceding)[-1200:])
    if opening is not None:
        start, _, language, _ = opening
        if language in LANGUAGES:
            raise ValueError(f"{path}:{start + 1}: unclosed Python code fence")
    return results
