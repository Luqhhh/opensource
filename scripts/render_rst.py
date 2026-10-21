"""Render RST safely with an explicitly supplied pinned optional Docutils wheel."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.rst_render import render_rst

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("document", type=Path)
parser.add_argument("--docutils-wheel", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
try:
    result = render_rst(args.document, args.docutils_wheel, args.output)
    print(json.dumps({k: result[k] for k in ("status", "document_sha256", "renderer", "scope")}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "render_passed" else 2)
except (ValueError, OSError) as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)
