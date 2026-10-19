"""Release artifact validation; only trusted tooling runs on the host."""

import configparser
from email.parser import Parser
import hashlib
import argparse
from pathlib import Path
import subprocess
import tarfile
import tempfile
import venv
import zipfile

parser = argparse.ArgumentParser(description="Verify built artifacts against the source manifest and installed commands.")
parser.add_argument("artifacts", type=Path)
args = parser.parse_args()
wheels = list(args.artifacts.glob("*.whl"))
assert len(wheels) == 1, wheels
wheel = wheels[0].resolve()
assert wheel.name == "aic_exampleproof-0.1.0-py3-none-any.whl", wheel.name
modules = {p.relative_to("exampleproof").as_posix(): p.read_bytes()
           for p in Path("exampleproof").rglob("*.py")}
assert modules, "Source module manifest must not be empty"
licenses = {p.name: p.read_bytes() for p in Path("exampleproof/licenses").glob("*.txt")}
assert set(licenses) == {"Apache-2.0.txt", "CPython-3.10.12.txt", "stdlib-attribution.txt"}
assert hashlib.sha256(licenses["Apache-2.0.txt"]).hexdigest() == "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
assert licenses["CPython-3.10.12.txt"] == Path("benchmarks/semantic_v2/resources/cpython-3.10.12/LICENSE").read_bytes()
for marker in (b"stdlib/doctest.py", b"stdlib/inspect.py", b"stdlib/tabnanny.py", b"stdlib/socket.py", b"No warranties."):
    assert marker in licenses["stdlib-attribution.txt"], marker
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    assert {"exampleproof/benchmark.py", "exampleproof/study.py", "exampleproof/context.py", "exampleproof/semantic_study.py", "exampleproof/cli.py", "exampleproof/__main__.py"} <= set(names)
    assert {name.removeprefix("exampleproof/") for name in names if name.startswith("exampleproof/") and name.endswith(".py")} == set(modules)
    for name, data in modules.items():
        assert archive.read("exampleproof/" + name) == data, name
    for name, data in licenses.items():
        assert archive.read("exampleproof/licenses/" + name) == data, name
    metadata_files = [name for name in names if name.endswith(".dist-info/METADATA")]
    assert len(metadata_files) == 1, metadata_files
    metadata = Parser().parsestr(archive.read(metadata_files[0]).decode("utf-8"))
    assert metadata["Name"] == "aic-exampleproof", metadata["Name"]
    assert metadata["Version"] == "0.1.0", metadata["Version"]
    assert metadata["Requires-Python"] == ">=3.10", metadata["Requires-Python"]
    assert not metadata.get_all("Requires-Dist"), metadata.get_all("Requires-Dist")
    entries = configparser.ConfigParser()
    entries.read_string(archive.read(metadata_files[0].rsplit("/", 1)[0] + "/entry_points.txt").decode("utf-8"))
    assert entries.get("console_scripts", "exampleproof") == "exampleproof.cli:main"

sdists = list(wheel.parent.glob("*.tar.gz"))
assert len(sdists) == 1, sdists
with tarfile.open(sdists[0], "r:gz") as archive:
    for name, data in modules.items():
        members = [m for m in archive.getmembers() if m.isfile() and m.name.endswith("/exampleproof/" + name)]
        assert len(members) == 1 and archive.extractfile(members[0]).read() == data, name
    for name, data in licenses.items():
        members = [member for member in archive.getmembers() if member.isfile() and member.name.endswith("/exampleproof/licenses/" + name)]
        assert len(members) == 1, name
        assert archive.extractfile(members[0]).read() == data, name

with tempfile.TemporaryDirectory(prefix="exampleproof-installed-") as temporary:
    outside = Path(temporary)
    environment = outside / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = str(environment / "bin/python")
    command = str(environment / "bin/exampleproof")
    subprocess.run([python, "-m", "pip", "install", "--no-deps", str(wheel)], cwd=outside, check=True)
    subprocess.run([python, "-m", "pip", "check"], cwd=outside, check=True)
    installed = Path(subprocess.check_output([python, "-I", "-c", "import exampleproof,pathlib; print(pathlib.Path(exampleproof.__file__).parent)"], cwd=outside, text=True).strip())
    for name, data in modules.items():
        assert (installed / name).read_bytes() == data, name
    for name, data in licenses.items():
        assert (installed / "licenses" / name).read_bytes() == data, name
    for invocation in ([python, "-I", "-m", "exampleproof"], [command]):
        version = subprocess.check_output([*invocation, "--version"], cwd=outside, text=True).strip()
        assert version == "0.1.0", version
        help_text = subprocess.check_output([*invocation, "benchmark", "--help"], cwd=outside, text=True)
        assert "--proposals" in help_text and "--max-attempts" in help_text, help_text
        assert "--repair-policy" in help_text and "semantic-v2" in help_text, help_text
        for name in ("analyze", "compare", "compare-audit", "task-check", "task-improve"):
            help_text = subprocess.check_output([*invocation, name, "--help"], cwd=outside, text=True)
            assert "usage:" in help_text, name
        project = outside / ("project-" + ("module" if len(invocation) > 1 else "console"))
        project.mkdir()
        (project / "README.md").write_text("# Quick start\n\nRead this tutorial.\n", encoding="utf-8")
        output = project.with_name(project.name + "-analysis")
        subprocess.run([*invocation, "analyze", str(project), "--static", "--output", str(output)], cwd=outside, check=True)
        assert (output / "analysis.json").is_file()
