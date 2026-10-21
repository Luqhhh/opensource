"""Optional pinned Docutils rendering in the existing fail-closed runner."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from .runner import SandboxRunner

DOCUTILS_WHEEL_SHA256 = "dafca5b9e384f0e419294eb4d2ff9fa826435bf15f15b7bd45723e8ad76811b2"


def render_rst(document, wheel, output):
    document, wheel, output = Path(document), Path(wheel), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Rendering output must be a new directory")
    raw = document.read_bytes()
    if len(raw) > 128000:
        raise ValueError("RST render input exceeds 128 KB")
    wheel_raw = wheel.read_bytes()
    if hashlib.sha256(wheel_raw).hexdigest() != DOCUTILS_WHEEL_SHA256:
        raise ValueError("Renderer must be the official docutils 0.21.2 wheel with the documented SHA256")
    sources, licenses = {}, {}
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if item.is_dir():
                continue
            if path.is_absolute() or ".." in path.parts or item.file_size > 1_000_000:
                raise ValueError("Invalid renderer archive member")
            if item.filename.startswith("docutils/"):
                try:
                    sources[item.filename] = archive.read(item).decode("utf-8")
                except UnicodeError:
                    pass  # No binary fonts or images are needed by this restricted renderer.
            elif "COPYING" in item.filename or "LICENSE" in item.filename:
                licenses[path.name] = archive.read(item)
    if len(sources) > 1000 or sum(len(s) for s in sources.values()) > 8_000_000:
        raise ValueError("Renderer archive exceeds source limits")
    sources["input.rst"] = raw.decode("utf-8-sig")
    code = '''import io, json
from docutils.core import publish_parts
warnings = io.StringIO()
with open('/workspace/input.rst') as stream:
    parts = publish_parts(stream.read(), source_path='input.rst', writer_name='html5', settings_overrides={
        'file_insertion_enabled': False, 'raw_enabled': False, 'warning_stream': warnings,
        'report_level': 2, 'halt_level': 6, 'syntax_highlight': 'none',
        'embed_stylesheet': False, 'stylesheet_path': None, 'doctitle_xform': False})
body = parts['fragment']
result = {'warnings': warnings.getvalue(), 'html': body if len(body.encode()) < 48000 else None,
          'rendered_bytes': len(body.encode()), 'preview_truncated': len(body.encode()) >= 48000}
print(json.dumps(result, ensure_ascii=False))
'''
    execution = SandboxRunner(sources, timeout=15).run(code, {})
    output.mkdir(parents=True)
    result = {"schema_version": "tutorial-rst-render-1", "document_sha256": hashlib.sha256(raw).hexdigest(),
              "renderer": "docutils 0.21.2", "wheel_sha256": DOCUTILS_WHEEL_SHA256,
              "status": "render_failed", "execution": asdict(execution),
              "scope": "Docutils HTML5 only; includes and raw directives disabled. No project conf.py, Sphinx extensions, network or code examples executed."}
    if execution.status == "passed":
        try:
            rendered = json.loads(execution.stdout)
            body = rendered.pop("html")
            result.update(rendered, status="render_warnings" if rendered["warnings"] else "render_passed")
            if body is not None:
                (output / "rendered.html").write_text(
                    '<!doctype html><html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
                    'content="default-src \'none\'; style-src \'unsafe-inline\'">'
                    '<title>Docutils 文档渲染</title><style>body{max-width:1000px;margin:40px auto;font:16px/1.7 system-ui}'
                    'pre{white-space:pre-wrap;padding:16px;background:#f4f7fa}img{max-width:100%}</style>' + body + '</html>')
        except (ValueError, KeyError, TypeError):
            result["status"] = "render_output_incomplete"
    for name, license_raw in licenses.items():
        (output / ("docutils-" + name)).write_bytes(license_raw)
    (output / "render.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result
