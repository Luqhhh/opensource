"""Read-only local input and bounded public GitHub snapshots (no Git hooks)."""

from contextlib import contextmanager
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


MAX_ARCHIVE_BYTES = 20_000_000
MAX_EXPANDED_BYTES = 64_000_000
MAX_ENTRIES = 20_000
SKIP_DIRS = {"node_modules", "__pycache__", "build", "dist", "vendor", "third_party",
             "artifacts", "outputs", "tests", "test", "evidence"}
TEXT_SUFFIXES = {".md", ".mdx", ".rst", ".py", ".js", ".jsx", ".ts", ".tsx", ".go",
                 ".rs", ".java", ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sh",
                 ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".txt"}
SENSITIVE_NAME = re.compile(r"(?:secret|credential|password|token|private[_-]?key)", re.I)


def eligible(path, scope=None):
    path = PurePosixPath(path)
    if (path.is_absolute() or ".." in path.parts or "\\" in str(path)
            or (not scope.allows(path) if scope is not None else
                any(p.startswith(".") or p in SKIP_DIRS for p in path.parts))
            or any(ord(c) < 32 or ord(c) == 127 for c in str(path))
            or SENSITIVE_NAME.search(path.name)
            or path.name in {"exampleproof.json", "metadata.json", "proposals.json", "negative_proposals.json"}
            or path.name.endswith((".pem", ".key", ".lock"))):
        return False
    if scope is not None:
        from .tutorial_scope import BUILD_NAMES
        if path.name.lower() in BUILD_NAMES or scope.explicitly_includes(path):
            return True
    return (path.suffix.lower() in TEXT_SUFFIXES or path.name.lower() in {"go.mod", "license", "notice", "copying"}
            or path.name.lower().startswith(("license.", "notice.", "copying.")))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("GitHub snapshot redirects are disabled")


def fetch(url, limit):
    request = Request(url, headers={"User-Agent": "ExampleProof", "Accept": "application/vnd.github+json"})
    with build_opener(_NoRedirect()).open(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("GitHub response exceeds download limit")
    return data


def github_repository(value):
    """Accept OWNER/REPO and canonical HTTPS repository URLs only."""
    if "://" in value:
        parsed = urlparse(value)
        if (parsed.scheme != "https" or parsed.netloc != "github.com"
                or parsed.query or parsed.fragment or parsed.params):
            raise ValueError("Use https://github.com/OWNER/REPO or OWNER/REPO")
        value = parsed.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}", value):
        raise ValueError("Use https://github.com/OWNER/REPO or an existing local directory")
    return value


def unpack_snapshot(data, destination, scope=None):
    """Copy selected regular files only; validate all archive paths first."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("GitHub archive exceeds download limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid GitHub ZIP archive") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(i.file_size for i in entries) > MAX_EXPANDED_BYTES:
            raise ValueError("GitHub archive exceeds expanded input limits")
        names, roots = set(), set()
        for info in entries:
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if (path.is_absolute() or ".." in path.parts or "\\" in info.filename
                    or not path.parts or str(path) != info.filename.rstrip("/")
                    or any(ord(c) < 32 for c in info.filename)
                    or info.filename in names):
                raise ValueError("Unsafe or duplicate GitHub archive path")
            names.add(info.filename)
            roots.add(path.parts[0])
            if stat.S_ISLNK(mode):
                continue
            if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError("Unsupported GitHub archive entry")
        if len(roots) != 1:
            raise ValueError("Expected a single GitHub archive root")
        omitted_paths, copied = [], 0
        for info in entries:
            relative = PurePosixPath(info.filename).parts[1:]
            if (not relative or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16)
                    or not eligible(PurePosixPath(*relative), scope) or info.file_size > 256_000):
                if relative and not info.is_dir() and eligible(PurePosixPath(*relative), scope):
                    omitted_paths.append(PurePosixPath(*relative).as_posix())
                continue
            target = destination.joinpath(*relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                content = archive.read(info)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
                raise ValueError("Cannot read GitHub archive member") from exc
            target.write_bytes(content)
            copied += 1
        return {"archive_entries": len(entries), "copied_files": copied,
                "omitted_eligible_paths": omitted_paths}


@contextmanager
def project_input(value, *, ref=None, scope=None):
    if scope is None:
        from .tutorial_scope import EvidenceScope
        scope = EvidenceScope()
    local = Path(value).expanduser()
    if local.is_dir():
        if ref is not None:
            raise ValueError("--ref applies only to GitHub input")
        yield local.resolve(), {"kind": "local", "path": str(local.resolve())}
        return
    # A clearly local missing path must not accidentally trigger a network call.
    if value.startswith(("/", "./", "../", "~")):
        raise ValueError("Local project directory does not exist")
    repository = github_repository(value)
    selected_ref = ref or "HEAD"
    if not isinstance(selected_ref, str) or not selected_ref or len(selected_ref) > 256:
        raise ValueError("Invalid GitHub ref")
    metadata = json.loads(fetch(f"https://api.github.com/repos/{repository}/commits/{quote(selected_ref, safe='')}", 1_000_000))
    commit = metadata.get("sha") if isinstance(metadata, dict) else None
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("GitHub did not return a valid commit SHA")
    archive = fetch(f"https://codeload.github.com/{repository}/zip/{commit}", MAX_ARCHIVE_BYTES)
    with tempfile.TemporaryDirectory(prefix="exampleproof-github-") as temporary:
        root = Path(temporary)
        snapshot = unpack_snapshot(archive, root, scope)
        yield root, {"kind": "github", "url": f"https://github.com/{repository}",
                     "ref": selected_ref, "commit": commit,
                     "snapshot_policy": "eligible text files only; symlinks and excluded paths omitted",
                     "snapshot": snapshot}
