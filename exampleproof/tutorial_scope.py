"""Configurable tutorial evidence scope, separate from repair input policy."""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath


BUILD_NAMES = {"dockerfile", "containerfile", "makefile", "gnumakefile"}
NEVER_DIRS = {".git", ".hg", ".svn"}


@dataclass(frozen=True)
class EvidenceScope:
    include_tests: bool = False
    include_paths: tuple = ()
    exclude_paths: tuple = ()

    def __post_init__(self):
        for pattern in self.include_paths + self.exclude_paths:
            path = PurePosixPath(pattern)
            if (not pattern or path.is_absolute() or ".." in path.parts or "\\" in pattern
                    or any(ord(c) < 32 or ord(c) == 127 for c in pattern)):
                raise ValueError("Evidence patterns must be relative POSIX paths without traversal")

    def record(self):
        return {"include_tests": self.include_tests, "include_paths": list(self.include_paths),
                "exclude_paths": list(self.exclude_paths)}

    def explicitly_includes(self, path):
        return any(fnmatchcase(str(path), pattern) for pattern in self.include_paths)

    def allows(self, path, *, directory=False):
        from .project_input import SKIP_DIRS
        parts = PurePosixPath(path).parts
        if any(p in NEVER_DIRS or p == ".env" or p.startswith(".env.") for p in parts):
            return False
        ancestors = [PurePosixPath(*parts[:i]).as_posix() for i in range(1, len(parts) + 1)]
        if any(fnmatchcase(ancestor, p) for p in self.exclude_paths for ancestor in ancestors):
            return False
        included = self.explicitly_includes(path)
        if directory:
            # Descend only toward the literal prefix of an explicit pattern.
            included |= any(p.startswith(str(path) + "/") for p in self.include_paths)
        return included or all(not p.startswith(".") and
                               (p not in SKIP_DIRS or self.include_tests and p in {"test", "tests"})
                               for p in parts)
