#!/usr/bin/env python3
"""Freeze, run or summarize the v2 semantic experiment (no automatic downloads)."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.semantic_study import study_design
from exampleproof.study import (digest, freeze_study, implementation_hashes, run_study,
                                summarize_study, write_json)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    lock = commands.add_parser("lock-method", help="Lock method before viewing holdout case details")
    lock.add_argument("output", type=Path)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("projects", nargs="+", type=Path)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--split", choices=("development", "holdout"), required=True)
    freeze.add_argument("--method-lock", type=Path)
    freeze.add_argument("--model", default="qwen2.5-coder:7b")
    freeze.add_argument("--endpoint", default="http://127.0.0.1:11434")
    run = commands.add_parser("run")
    run.add_argument("study", type=Path)
    run.add_argument("--endpoint", default="http://127.0.0.1:11434")
    summarize = commands.add_parser("summarize")
    summarize.add_argument("study", type=Path)
    args = parser.parse_args()
    if args.command == "lock-method":
        if args.output.exists():
            raise ValueError("Method lock cannot be overwritten")
        write_json(args.output, {"locked_at": datetime.now(timezone.utc).isoformat(),
                                "implementation_sha256": implementation_hashes(),
                                "design": study_design("holdout")})
        args.output.with_suffix(args.output.suffix + ".sha256").write_text(digest(args.output) + "\n", encoding="ascii")
        print(json.dumps({"method_lock": str(args.output), "sha256": digest(args.output)}))
        return 0
    if args.command == "freeze":
        design = study_design(args.split)
        if args.split == "holdout":
            if args.method_lock is None:
                raise ValueError("Holdout requires a method lock created before viewing case details")
            if digest(args.method_lock) != args.method_lock.with_suffix(args.method_lock.suffix + ".sha256").read_text().strip():
                raise ValueError("Holdout method lock seal differs")
            locked = json.loads(args.method_lock.read_text())
            if locked["implementation_sha256"] != implementation_hashes() or locked["design"] != design:
                raise ValueError("Implementation/design changed after the holdout method lock")
            design["method_lock"] = {"sha256": digest(args.method_lock), **locked}
        elif args.method_lock is not None:
            raise ValueError("A method lock applies only to holdout studies")
        plan = freeze_study(args.projects, args.output, args.model, args.endpoint, design=design)
        print(json.dumps({"status": plan["status"], "split": args.split, "cells": len(plan["schedule"])}))
        return 0
    if args.command == "run":
        _, code = run_study(args.study, args.endpoint)
        return code
    summary = summarize_study(args.study)
    print(json.dumps({"complete": summary["complete"], "groups": summary["groups"]}, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, SyntaxError, KeyError) as exc:
        print(f"semantic-study: {exc}", file=sys.stderr)
        sys.exit(2)
