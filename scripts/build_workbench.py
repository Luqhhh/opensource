"""Export the read-only user-facing evidence workbench."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof.workbench import export_workbench

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--engineering-cases", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--quality-review", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(export_workbench(args.frozen, args.output, run=args.run, engineering_cases=args.engineering_cases, preflight=args.preflight, quality_review=args.quality_review), ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
