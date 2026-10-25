#!/usr/bin/env python3
"""Build the reviewed-source submission draft with already-installed tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "submission"


def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments, check=True, text=True, capture_output=True, **kwargs
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/submission")
    args = parser.parse_args()
    required = ["pandoc", "xelatex", "pdfinfo", "pdftotext"]
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise ValueError("Install required tools before building: " + ", ".join(missing))

    abstract_path = SOURCE / "abstract.txt"
    paragraphs = abstract_path.read_text(encoding="utf-8").strip().split("\n\n")
    if len(paragraphs) != 2:
        raise ValueError("abstract.txt must contain a title and one abstract paragraph")
    title, abstract = paragraphs
    lengths = {
        "title_characters": len(re.sub(r"\s", "", title)),
        "abstract_characters": len(re.sub(r"\s", "", abstract)),
    }
    if lengths["title_characters"] > 20 or lengths["abstract_characters"] > 300:
        raise ValueError("Title or abstract exceeds the competition character limit")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = SOURCE / "technical-report.md"
    resources = SOURCE / "resource-list.md"
    header = SOURCE / "pdf-header.tex"
    pdf_filter = SOURCE / "pdf-filter.lua"
    combined = output / "technical-report-with-resources.md"
    appendix = resources.read_text(encoding="utf-8").split("\n", 1)[1]
    combined.write_text(
        report.read_text(encoding="utf-8").rstrip()
        + "\n\n\\clearpage\n\n# 附件：开源及第三方资源使用清单\n"
        + appendix,
        encoding="utf-8",
    )
    pdf = output / "technical-report-draft.pdf"
    command = [
        "pandoc", str(combined), "--standalone", "--from=markdown",
        "--pdf-engine=xelatex", "--pdf-engine-opt=-no-shell-escape",
        "--variable=documentclass:ctexart", "--variable=classoption:fontset=fandol",
        "--variable=fontsize:10pt", "--variable=geometry:margin=20mm",
        "--variable=papersize:a4", "--lua-filter", str(pdf_filter),
        "--variable=colorlinks:true", "--variable=urlcolor:blue",
        "--include-in-header", str(header), "--output", str(pdf),
        "--resource-path", os.pathsep.join((str(SOURCE), str(ROOT))),
    ]
    result = run(command, cwd=ROOT)
    (output / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    info = run(["pdfinfo", str(pdf)]).stdout
    match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    if not match:
        raise ValueError("pdfinfo returned no page count")
    pages, byte_count = int(match.group(1)), pdf.stat().st_size
    text_path = output / "technical-report-draft.txt"
    run(["pdftotext", "-layout", str(pdf), str(text_path)])
    extracted = text_path.read_text(encoding="utf-8")
    if "开源及第三方资源使用清单" not in extracted or "源途" not in extracted:
        raise ValueError("Chinese title or resource appendix missing from extracted PDF text")
    checks = {
        **lengths, "pdf_total_pages_including_appendix": pages,
        "pdf_bytes": byte_count,
        "total_pages_within_15": pages <= 15,
        "size_within_10_mb_decimal": byte_count <= 10_000_000,
        "chinese_text_extraction": True,
    }
    versions = {}
    for name in ["pandoc", "xelatex"]:
        version = run([name, "--version"])
        versions[name] = version.stdout.strip() or version.stderr.strip()
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
        "checks": checks,
        "tools": versions,
        "source_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in [report, resources, abstract_path, header, pdf_filter, Path(__file__).resolve(),
                         *sorted((SOURCE / "figures").glob("*.png"))]
        },
        "output_sha256": {pdf.name: digest(pdf)},
        "command": command,
        "limits_note": "All PDF pages including appendix are checked against 15 pages; rules recommend 15 for body only.",
        "reproducibility_note": "Font/tool versions and timestamps can change PDF bytes. This manifest identifies this build only.",
    }
    (output / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"pdf": str(pdf), **checks}, ensure_ascii=False, indent=2))
    if pages > 15 or byte_count > 10_000_000:
        raise ValueError("Draft exceeds the configured submission limits")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc.stdout or str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except (OSError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
