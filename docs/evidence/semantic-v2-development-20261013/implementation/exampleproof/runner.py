"""Fail-closed Bubblewrap runner; never falls back to host execution.

Completion receipts detect early exits, including os._exit(0), independently of
stdout and stderr. They are not an integrity boundary against code deliberately
tampering with its own interpreter or inspecting and forging the harness receipt:
the example and evaluator checks still share one Python process.
"""

import ast
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import tempfile
import time

from .models import Execution

OUTPUT_LIMIT = 64_000

# The receipt is written only after setup, the example and external checks have
# returned normally. Exit status alone cannot distinguish os._exit(0) from this.
HARNESS = '''import resource, runpy, sys, traceback
# Apply only after Bubblewrap has created its namespaces. An early NPROC
# ceiling counts other processes owned by the host UID and can block startup.
# v0.1 snippets are single-process; they do not need subprocesses or threads.
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
sys.path.insert(0, "/workspace")
try:
    namespace = runpy.run_path("/work/setup.py")
    namespace = runpy.run_path("/work/example.py", init_globals=namespace)
except BaseException:
    traceback.print_exc()
    sys.exit(21)
try:
    exec(compile(open("/work/checks.py").read(), "external-checks", "exec"), namespace)
except BaseException:
    traceback.print_exc()
    sys.exit(22)
with open("/completion", "wb") as receipt:
    receipt.write({completion_token!r})
'''


def oracle_type(code: str, spec: dict) -> str:
    if spec.get("checks", "").strip() or "expected_stdout" in spec:
        return "configured_behavior_checks"
    try:
        if any(isinstance(node, ast.Assert) for node in ast.parse(code).body):
            return "original_top_level_assertions"
    except SyntaxError:
        pass
    return "none"


def limits(timeout: float):
    def apply():
        cpu = max(1, math.ceil(timeout))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


class SandboxRunner:
    backend = "bubblewrap"

    def __init__(self, sources: dict[str, str], timeout: float = 5):
        self.sources = sources
        self.timeout = timeout

    def run(self, code: str, spec: dict) -> Execution:
        oracle = oracle_type(code, spec)
        for name in self.sources:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or path == Path("."):
                return Execution("blocked", stderr=f"Source path must stay inside the workspace: {name!r}", oracle=oracle, failure_kind="environment")
        if not shutil.which("bwrap") or not Path("/usr/bin/python3").exists():
            return Execution("blocked", stderr="Requires Linux, bubblewrap and /usr/bin/python3; host execution is disabled", oracle=oracle, failure_kind="environment")
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="exampleproof-") as temporary:
            base = Path(temporary)
            workspace, work = base / "workspace", base / "work"
            workspace.mkdir()
            work.mkdir()
            completion_token = os.urandom(32)
            for name, source in self.sources.items():
                target = workspace / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            harness = HARNESS.format(completion_token=completion_token)
            for name, content in {"example.py": code, "setup.py": spec.get("setup", ""), "checks.py": spec.get("checks", ""), "harness.py": harness}.items():
                (work / name).write_text(content, encoding="utf-8")
            command = ["bwrap", "--die-with-parent", "--unshare-all", "--new-session", "--cap-drop", "ALL", "--clearenv"]
            for path in ("/usr", "/lib", "/lib64"):
                if Path(path).exists():
                    command += ["--ro-bind", path, path]
            command += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                        "--ro-bind", str(workspace), "/workspace", "--ro-bind", str(work), "/work",
                        "--bind", str(base / "completion"), "/completion",
                        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
                        "--chdir", "/tmp", "/usr/bin/python3", "-I", "-S", "/work/harness.py"]
            # Bind only this file, and read through its original descriptor: the
            # sandbox cannot replace it with a symlink to a host-side path.
            with (
                (base / "completion").open("w+b") as receipt,
                (base / "stdout").open("w+b") as out,
                (base / "stderr").open("w+b") as err,
            ):
                try:
                    proc = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                            start_new_session=True, preexec_fn=limits(self.timeout))
                    try:
                        proc.wait(timeout=self.timeout)
                        status = "passed" if proc.returncode == 0 else "failed"
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                        status = "timeout"
                    out.seek(0)
                    err.seek(0)
                    stdout = out.read(OUTPUT_LIMIT).decode("utf-8", errors="replace")
                    stderr = err.read(OUTPUT_LIMIT).decode("utf-8", errors="replace")
                    if proc.returncode != 0 and stderr.startswith("bwrap:"):
                        status = "blocked"
                    failure_kind = ("environment" if status == "blocked" else "timeout" if status == "timeout"
                                    else "none" if status == "passed" else "example_exception" if proc.returncode == 21
                                    else "behavior_check" if proc.returncode == 22 else "abnormal_exit")
                    if status == "passed":
                        receipt.seek(0)
                        if receipt.read(len(completion_token) + 1) != completion_token:
                            status = "failed"
                            failure_kind = "incomplete_execution"
                            stderr += "\nExecution did not complete setup, the example and external checks normally."
                    if status == "passed" and "expected_stdout" in spec and stdout != spec["expected_stdout"]:
                        status = "failed"
                        failure_kind = "stdout_mismatch"
                        stderr += "\nExpected stdout did not match the configured oracle."
                    return Execution(status, proc.returncode, stdout, stderr,
                                     round(time.monotonic() - start, 4), oracle, failure_kind)
                except (OSError, subprocess.SubprocessError) as exc:
                    return Execution("blocked", stderr=str(exc), duration_seconds=round(time.monotonic() - start, 4), oracle=oracle, failure_kind="environment")
