"""Archive existing evidence without executing inputs; verify every member by SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(source, output, kind):
    source, output = Path(source).resolve(), Path(output)
    index = output.with_name(output.name + ".index.json")
    if output.exists() or index.exists() or output.resolve().is_relative_to(source):
        raise ValueError("Archive/index must be new and outside the evidence directory")
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Evidence symlinks are not accepted")
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
            files.append(path)
    if not files or any(p.stat().st_size > 64_000_000 for p in files):
        raise ValueError("Evidence is empty or a member exceeds 64 MB")
    records = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "x:gz") as bundle:
        for path in files:
            raw = path.read_bytes()
            name = path.relative_to(source).as_posix()
            records.append({"path": name, "bytes": len(raw), "sha256": sha(raw)})
            import io
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(raw), 0o644, 0
            bundle.addfile(info, io.BytesIO(raw))
    record = {"schema_version": "tutorial-evidence-archive-1", "archive": output.name,
              "archive_sha256": sha(output.read_bytes()), "evidence_kind": kind,
              "files": records, "independent_quality_review": False,
              "notice": "Byte integrity only; no new model requests, human evaluation or publication. Review contents before sharing."}
    with index.open("x", encoding="utf-8") as target:
        json.dump(record, target, ensure_ascii=False, indent=2)
        target.write("\n")
    return audit(output, index)


def audit(archive_path, index_path):
    record = json.loads(Path(index_path).read_text())
    archive_path = Path(archive_path)
    if sha(archive_path.read_bytes()) != record["archive_sha256"]:
        raise ValueError("Archive digest mismatch")
    expected = {r["path"]: r for r in record["files"]}
    if len(expected) != len(record["files"]):
        raise ValueError("Duplicate manifest paths")
    found = set()
    with tarfile.open(archive_path, "r:gz") as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts or "\\" in member.name
                    or member.name not in expected or member.name in found):
                raise ValueError("Unexpected or unsafe archive member")
            found.add(member.name)
            item = expected[member.name]
            if member.size != item["bytes"] or member.size > 64_000_000:
                raise ValueError("Archive member size mismatch")
            if sha(bundle.extractfile(member).read()) != item["sha256"]:
                raise ValueError("Archive member digest mismatch")
    if found != set(expected):
        raise ValueError("Archive is incomplete")
    return {"status": "byte_integrity_passed", "files": len(found), "archive_sha256": record["archive_sha256"],
            "evidence_kind": record["evidence_kind"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("source", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--kind", required=True, choices=("recorded_live_model_study", "recorded_candidate_replay", "pending_task_evaluation"))
    verify = sub.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("index", type=Path)
    args = parser.parse_args()
    try:
        result = archive(args.source, args.output, args.kind) if args.command == "create" else audit(args.archive, args.index)
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, tarfile.TarError) as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
