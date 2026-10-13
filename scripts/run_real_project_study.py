#!/usr/bin/env python3
"""Freeze/run/summarize the declared real-project migration experiment."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.study import freeze_study, run_study, summarize_study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("projects", nargs="+", type=Path)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--model", default="qwen2.5-coder:7b")
    freeze.add_argument("--endpoint", default="http://127.0.0.1:11434")
    run = commands.add_parser("run")
    run.add_argument("study", type=Path)
    run.add_argument("--endpoint", default="http://127.0.0.1:11434")
    summary = commands.add_parser("summarize")
    summary.add_argument("study", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze_study(args.projects, args.output, args.model, args.endpoint)
        print(json.dumps({"status": result["status"], "projects": len(result["projects"]),
                          "scheduled_cells": len(result["schedule"])}))
        return 0
    if args.command == "run":
        _, code = run_study(args.study, args.endpoint)
        return code
    result = summarize_study(args.study)
    print(json.dumps({"complete": result["complete"], "groups": result["groups"]}, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"study: {exc}", file=sys.stderr)
        sys.exit(2)
