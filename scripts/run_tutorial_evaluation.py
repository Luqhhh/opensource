"""Prepare independently reviewed tasks; preserve missing quality/reader outcomes as null."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exampleproof import tutorial_eval
from exampleproof.model_api import JSONClient
from exampleproof.tutorial_privacy import review_cloud


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="获取规范中固定提交的公开快照并冻结，不调用模型")
    prepare.add_argument("spec", type=Path)
    prepare.add_argument("output", type=Path)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("spec", type=Path)
    freeze.add_argument("output", type=Path)
    run = sub.add_parser("run")
    run.add_argument("frozen", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--review", required=True, type=Path)
    run.add_argument("--cloud-approvals", type=Path)
    run.add_argument("--cloud-reviews", type=Path, required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("frozen", type=Path)
    summary.add_argument("run", type=Path)
    summary.add_argument("--review", type=Path)
    args = parser.parse_args()
    try:
        if args.command in {"freeze", "prepare"}:
            specification = json.loads(args.spec.read_text())
            if args.command == "prepare":
                from exampleproof.project_input import project_input
                from exampleproof.tutorial import prepare_project
                from exampleproof.tutorial_scope import EvidenceScope
                if args.output.exists():
                    raise ValueError("Preparation output must be new")
                args.output.mkdir(parents=True)
                scope = EvidenceScope(**specification["scope"])
                for name, project in specification["projects"].items():
                    tutorial_eval._id(name)
                    provenance = project["provenance"]
                    with project_input(provenance["url"], ref=provenance["commit"], scope=scope) as (root, actual):
                        if actual["commit"] != provenance["commit"]:
                            raise ValueError("Upstream commit differs from frozen specification")
                        snapshot = prepare_project(root, actual, scope=scope)
                        target = args.output / "inputs" / name
                        for relative, item in snapshot.files.items():
                            destination = target / relative
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            destination.write_bytes((b"\xef\xbb\xbf" if item["utf8_bom"] else b"") + item["text"].encode())
                        project["root"] = str(target.resolve())
                args.output = args.output / "frozen"
            else:
                for project in specification["projects"].values():
                    if not Path(project["root"]).is_absolute():
                        project["root"] = str((args.spec.parent / project["root"]).resolve())
            result = tutorial_eval.freeze(specification, args.output)
            template = args.output.with_name(args.output.name + "-preflight-review-template.json")
            with template.open("x", encoding="utf-8") as stream:
                json.dump({"seal": result["seal"], "approved": False, "reviewer": None,
                           "independent_human": False, "authored_candidates_or_annotations": None,
                           "complete_gold_inventory": False}, stream, indent=2)
        elif args.command == "run":
            approvals = json.loads(args.cloud_approvals.read_text()) if args.cloud_approvals else {}
            if args.cloud_reviews.resolve().is_relative_to(args.frozen.resolve()):
                raise ValueError("Review files must stay outside the frozen evaluation")
            def factory(case, snapshot, strategy, protocol):
                model = protocol["model"]
                client = JSONClient(model["provider"], model["name"], timeout=60)
                if client.provider == "deepseek":
                    key = case["id"] + "-" + strategy
                    client = review_cloud(snapshot, client, args.cloud_reviews / (key + ".json"), approvals.get(key),
                                          context_chars=protocol["context_chars"], strategies=(strategy,), **protocol["limits"])
                return client
            result = tutorial_eval.run(args.frozen, args.output, json.loads(args.review.read_text()), factory)
        else:
            review = json.loads(args.review.read_text()) if args.review else None
            result = tutorial_eval.summarize(args.frozen, args.run, review)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
