"""Verify archive hashes and recount saved reports; never execute archived code."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "bundle-manifest.json").read_text(encoding="utf-8"))
    archive = directory / "raw-evidence.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    with zipfile.ZipFile(archive) as source:
        assert set(source.namelist()) == set(manifest["members"])
        for name, expected in manifest["members"].items():
            assert hashlib.sha256(source.read(name)).hexdigest() == expected, name

        def read(name):
            return json.loads(source.read(name))

        first = read("round1/summary.json")
        assert not first["complete"] and first["error"] is not None
        assert all(group["repair_rate"] is None for group in first["groups"].values())
        rounds = {}
        for label in ("round2", "round3", "round4"):
            summary, protocol = read(label + "/summary.json"), read(label + "/protocol.json")
            assert summary["complete"] and summary["error"] is None
            assert len(summary["cells"]) == len(protocol["seeds"]) * len(protocol["projects"]) * 2
            counts = {policy: Counter() for policy in ("semantic-v2", "semantic-v3")}
            for cell in summary["cells"]:
                base = f"{label}/runs/{cell['seed']}/{cell['policy']}/{cell['project']}/"
                benchmark = read(base + "benchmark.json")
                assert benchmark["mode"] == "live_model" and benchmark["model"] == protocol["model"]
                reports = {phase: {row["example"]["id"]: row for row in read(base + phase + "/report.json")["results"]}
                           for phase in ("baseline", "repair", "patched")}
                count = counts[cell["policy"]]
                requests = 0
                for case in benchmark["manifest"]["cases"]:
                    key = case["id"]
                    before, repair, patched = (reports[phase][key] for phase in ("baseline", "repair", "patched"))
                    assert before["status"] == case["expected_before"]
                    assert repair["status"] != "provider_error"
                    if case["expected_before"] == "failed":
                        count["case_runs"] += 1
                        count["confirmed_repairs"] += repair["status"] == "verified_repair" and patched["status"] == "checked"
                    else:
                        assert repair["status"] == patched["status"] == "checked" and repair["attempts"] == []
                        count["healthy_preserved"] += 1
                    assert len(repair["attempts"]) <= protocol["max_attempts"]
                    for attempt in repair["attempts"]:
                        proposal = attempt["proposal"]
                        evidence = proposal["inference_evidence"] if proposal else attempt["inference_evidence"]
                        assert evidence is not None
                        if proposal:
                            assert proposal["provider"] == "ollama" and proposal["model"] == protocol["model"]
                        assert evidence["request"]["model"] == protocol["model"]
                        assert evidence["request"]["options"]["num_predict"] == 2048
                        requests += 1
                assert requests == benchmark["repair"]["inference_requests"]
                count["inference_requests"] += requests
            for policy, values in counts.items():
                for key, value in values.items():
                    assert value == summary["groups"][policy][key], (label, policy, key)
                assert values["confirmed_repairs"] / values["case_runs"] == summary["groups"][policy]["repair_rate"]
            rounds[label] = {policy: dict(values) for policy, values in counts.items()}
    return {"verified": True, "members": len(manifest["members"]), "rounds": rounds,
            "scope": "Archive integrity and saved-report consistency only; no model call or candidate execution."}


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parent), ensure_ascii=False, indent=2))
