"""Public RepoPath entry point, sharing the existing implementation and data."""

from exampleproof.cli import main as _main


def main(argv=None):
    return _main(argv, prog="repopath")
