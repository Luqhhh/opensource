"""Synthetic engineering checks, including code-block and frozen-input guards."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from exampleproof.cli import main
from exampleproof.model_api import JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.project_input import eligible, project_input
from exampleproof.tutorial import analyze_snapshot, build_chunks, prepare_project, ranked_candidates, Chunk, write_analysis
from exampleproof.tutorial_edits import review_edits
from exampleproof.tutorial_study import audit_comparison, run_comparison


class SyntheticClient:
    provider = "synthetic_fixture"
    model = "fixture-flash"
    evidence_kind = "synthetic_fixture"
    timeout = 60
    endpoint = "synthetic://no-network"

    def __init__(self, values, before_call=None):
        self.values = iter(values)
        self.before_call = before_call
        self.requests = []

    def complete(self, system, evidence):
        if self.before_call:
            self.before_call(len(self.requests), evidence)
        self.requests.append(evidence)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(evidence)
        return JSONReply(value, InferenceEvidence({"system": system, "evidence": evidence}, "synthetic", 60), 20, 5)


class ComparisonFixture(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "README.md").write_text("# Getting started\n\nConfigure the application first.\n\n"
                                       "```python\nassert 2 + 2 == 4\nprint('expected')\n```\n", encoding="utf-8")
        (root / "app.py").write_text("def configure(path):\n    return path\n", encoding="utf-8")
        (root / "go.mod").write_text("module fixture\n\ngo 1.22\n")
        (root / "LICENSE").write_text("Synthetic fixture license notice.\n")
        return root

    def responses(self):
        return [{"findings": [], "edits": []},
                lambda evidence: {"selected_ids": [evidence["candidates"][0]["id"]]},
                {"findings": [], "edits": []}]


class ComparisonTests(ComparisonFixture):

    def test_protocol_and_snapshot_exist_before_calls_and_source_is_read_once(self):
        root = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            def before(index, evidence):
                self.assertTrue((output / "protocol.json").is_file())
                self.assertTrue((output / "snapshot.json").is_file())
                if index == 0:
                    (root / "README.md").write_text("CHANGED AFTER FREEZE\n")
            client = SyntheticClient(self.responses(), before)
            from exampleproof import tutorial
            with patch("exampleproof.tutorial.discover", wraps=tutorial.discover) as discover:
                summary = run_comparison(root, {"kind": "local"}, output, client)
            self.assertEqual(discover.call_count, 1)
            self.assertEqual(summary["evidence_kind"], "synthetic_fixture")
            self.assertEqual(summary["run_status"], "completed")
            self.assertIsNone(summary["quality_winner"])
            self.assertEqual(summary["model_requests"], 3)
            self.assertEqual(summary["arms"]["lexical"]["usage"]["input_tokens"], 20)
            self.assertEqual(summary["arms"]["ai"]["usage"]["input_tokens"], 40)
            self.assertEqual(summary["arms"]["lexical"]["snapshot_id"], summary["arms"]["ai"]["snapshot_id"])
            self.assertNotIn("CHANGED AFTER FREEZE", json.dumps(client.requests))
            protocol = json.loads((output / "protocol.json").read_text())
            self.assertIn("not matched", protocol["budget_matching"])
            self.assertTrue((output / "lexical/analysis.html").exists())
            self.assertTrue((output / "ai/analysis.html").exists())
            self.assertTrue((output / "review-template.json").exists())
            self.assertEqual(audit_comparison(output)["status"], "passed")

    def test_failure_and_fallback_are_visible_and_unknown_usage_is_not_zero(self):
        root = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            client = SyntheticClient([{"findings": []}, ValueError("synthetic timeout"), {"findings": []}])
            summary = run_comparison(root, {}, Path(temporary) / "comparison", client)
        self.assertEqual(summary["run_status"], "partial")
        self.assertEqual(summary["arms"]["ai"]["actual_strategy"], "lexical")
        self.assertEqual(summary["arms"]["ai"]["failed_requests"], 1)
        self.assertIsNone(summary["arms"]["ai"]["usage"]["input_tokens"])

    def test_reversed_arm_order_is_recorded_and_auditable(self):
        root = self.fixture()
        values = [lambda evidence: {"selected_ids": [evidence["candidates"][0]["id"]]},
                  {"findings": []}, {"findings": []}]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            run_comparison(root, {}, output, SyntheticClient(values), arm_order=("ai", "lexical"))
            self.assertEqual(json.loads((output / "protocol.json").read_text())["arm_order"], ["ai", "lexical"])
            self.assertEqual(audit_comparison(output)["status"], "passed")

    def test_snapshot_bom_crlf_and_raw_hash_reconstruct_exactly(self):
        import hashlib
        root = self.fixture()
        raw = b'\xef\xbb\xbf# Tutorial\r\n\r\nConfigure the application first.\r\n'
        (root / "README.md").write_bytes(raw)
        snapshot = prepare_project(root, {})
        item = snapshot.files["README.md"]
        restored = (b'\xef\xbb\xbf' if item["utf8_bom"] else b'') + item["text"].encode()
        self.assertEqual(restored, raw)
        self.assertEqual(hashlib.sha256(restored).hexdigest(), item["sha256"])

    def test_local_and_mocked_github_discovery_have_same_snapshot_id(self):
        import zipfile
        root = self.fixture()
        local = prepare_project(root, {"kind": "local"})
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            for path in root.iterdir():
                archive.writestr("repo-sha/" + path.name, path.read_bytes())
        with patch("exampleproof.project_input.fetch", side_effect=[json.dumps({"sha": "b" * 40}).encode(), data.getvalue()]):
            with project_input("owner/project") as (remote_root, provenance):
                remote = prepare_project(remote_root, provenance)
        self.assertEqual(local.snapshot_id, remote.snapshot_id)
        self.assertIn("go.mod", remote.files)
        self.assertIn("LICENSE", remote.files)

    def test_cli_comparison_uses_requested_flash_and_new_external_output(self):
        root = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            client = SyntheticClient(self.responses())
            output = Path(temporary) / "comparison"
            with patch("exampleproof.model_api.JSONClient", return_value=client) as constructor, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["compare", str(root), "--provider", "deepseek", "--model", "deepseek-flash",
                                       "--output", str(output)]), 0)
            constructor.assert_called_once_with("deepseek", "deepseek-flash", endpoint=None, timeout=60)
            with patch("exampleproof.model_api.JSONClient") as constructor, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["compare", str(root), "--provider", "deepseek", "--output", str(output)]), 2)
            constructor.assert_not_called()

    def test_cli_comparison_defaults_to_flash(self):
        root = self.fixture()
        client = SyntheticClient(self.responses())
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary) / "comparison"
            with patch("exampleproof.model_api.JSONClient", return_value=client) as constructor:
                self.assertEqual(main(["compare", str(root), "--output", str(output)]), 0)
            constructor.assert_called_once_with("deepseek", "deepseek-flash", endpoint=None, timeout=60)
            self.assertEqual(len(client.requests), 3)
            self.assertEqual(audit_comparison(output)["status"], "passed")

    def test_candidate_limit_and_chinese_terms_preserve_project_coverage(self):
        chunks = [Chunk(f"c{i}", f"file{i:02}.py", 1, 1, "source", "source", "unrelated") for i in range(50)]
        self.assertEqual(len(ranked_candidates(chunks)), 40)
        chinese = [Chunk("doc", "README.md", 1, 2, "document", "安装配置", "安装配置"),
                   Chunk("unrelated", "a.py", 1, 1, "source", "abc", "unrelated"),
                   Chunk("relevant", "z.py", 1, 1, "source", "初始化", "安装配置后初始化")]
        ids = [c.id for c in ranked_candidates(chinese)]
        self.assertLess(ids.index("relevant"), ids.index("unrelated"))
        self.assertTrue(eligible("go.mod"))

    def test_chunk_labels_match_exact_source_across_line_character_and_ast_boundaries(self):
        sources = {"long.md": "# First\n" + "".join(f"paragraph line {i}\n" for i in range(200)) + "# Second\nnext\n",
                   "wide.md": "# Wide\n" + "x" * 2500 + "\n" + "y" * 2500 + "\nlast\n",
                   "source.py": "def first():\n    return 1\n\ndef second():\n    return 2\n"}
        chunks, _ = build_chunks({p: {"text": text} for p, text in sources.items()})
        seen = set()
        for chunk in chunks:
            lines = sources[chunk.path].splitlines(keepends=True)
            self.assertEqual(chunk.text, "".join(lines[chunk.start_line - 1:chunk.end_line]))
            self.assertLessEqual(len(chunk.text), 4000)
            self.assertLessEqual(chunk.end_line - chunk.start_line + 1, 80)
            for number in range(chunk.start_line, chunk.end_line + 1):
                self.assertNotIn((chunk.path, number), seen)
                seen.add((chunk.path, number))
        self.assertEqual(len(seen), sum(len(t.splitlines()) for t in sources.values()))

    def test_audit_detects_snapshot_cost_code_and_evidence_tampering(self):
        root = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / "comparison"
            run_comparison(root, {}, original, SyntheticClient(self.responses()))
            for case in ("snapshot", "cost", "code", "evidence"):
                output = Path(temporary) / case
                shutil.copytree(original, output)
                if case == "snapshot":
                    path = output / "snapshot.json"
                    value = json.loads(path.read_text())
                    value["files"]["README.md"]["text"] += "changed"
                    path.write_text(json.dumps(value))
                elif case == "cost":
                    path = output / "comparison.json"
                    value = json.loads(path.read_text())
                    value["arms"]["ai"]["usage"]["input_tokens"] = 0
                    path.write_text(json.dumps(value))
                elif case == "code":
                    with (output / "implementation/exampleproof/tutorial.py").open("a") as changed:
                        changed.write("\n# modified\n")
                else:
                    path = output / "ai/analysis.json"
                    value = json.loads(path.read_text())
                    value["context"]["selected"][0]["text"] = "fabricated evidence"
                    path.write_text(json.dumps(value))
                self.assertEqual(audit_comparison(output)["status"], "failed", case)
            self.assertEqual(audit_comparison(Path(temporary) / "missing")["status"], "failed")


class ProseEditTests(ComparisonFixture):
    def snapshot(self):
        root = self.fixture()
        return root, prepare_project(root, {})

    def edit(self, snapshot, **updates):
        document = next(c for c in snapshot.chunks if c.path == "README.md")
        return {"evidence_id": document.id, "original": "Configure the application first.",
                "replacement": "Create the configuration file before starting the application."} | updates

    def test_valid_prose_patch_applies_to_copy_and_preserves_all_code(self):
        root, snapshot = self.snapshot()
        result = review_edits(snapshot, snapshot.candidates, [self.edit(snapshot)])
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["rejected"], [])
        self.assertIn("+Create the configuration file", result["patch"])
        before = (root / "README.md").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "project"
            shutil.copytree(root, copied)
            subprocess.run(["git", "apply", "-"], input=result["patch"], text=True, cwd=copied, check=True, capture_output=True)
            after = (copied / "README.md").read_bytes()
        self.assertEqual(before, (root / "README.md").read_bytes())
        self.assertEqual(before.split(b'```python', 1)[1], after.split(b'```python', 1)[1])

    def test_code_assertions_missing_evidence_substrings_and_overlap_are_rejected(self):
        _, snapshot = self.snapshot()
        invalid = [self.edit(snapshot, original="assert 2 + 2 == 4", replacement="assert True"),
                   self.edit(snapshot, evidence_id="invented"),
                   self.edit(snapshot, original="the application", replacement="a program"),
                   self.edit(snapshot, original="not in source"),
                   self.edit(snapshot, replacement="```python\nassert True\n```"),
                   self.edit(snapshot, replacement="<script>unsafe</script>")]
        for edit in invalid:
            with self.subTest(edit=edit):
                result = review_edits(snapshot, snapshot.candidates, [edit])
                self.assertEqual(result["accepted"], [])
                self.assertTrue(result["rejected"])
                self.assertEqual(result["patch"], "")
        result = review_edits(snapshot, snapshot.candidates, [self.edit(snapshot), self.edit(snapshot)])
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(len(result["rejected"]), 1)

    def test_fenced_non_assert_code_is_protected(self):
        root = self.fixture()
        (root / "README.md").write_text("# Tutorial\n\n```text\n\nConfiguration goes here.\n\n```\n")
        snapshot = prepare_project(root, {})
        result = review_edits(snapshot, snapshot.candidates, [self.edit(snapshot, original="Configuration goes here.", replacement="Changed prose.")])
        self.assertEqual(result["accepted"], [])
        self.assertIn("protected", result["rejected"][0]["reason"])

    def test_inline_code_and_links_are_preserved(self):
        root = self.fixture()
        old = "Use `configure()` after reading [setup](docs/setup.md)."
        (root / "README.md").write_text("# Tutorial\n\n" + old + "\n")
        snapshot = prepare_project(root, {})
        for replacement in ("Use `other()` after reading [setup](docs/setup.md).", "Use `configure()` after reading [setup](other.md)."):
            result = review_edits(snapshot, snapshot.candidates, [self.edit(snapshot, original=old, replacement=replacement)])
            self.assertEqual(result["accepted"], [])
        valid = review_edits(snapshot, snapshot.candidates, [self.edit(snapshot, original=old,
                             replacement="Read [setup](docs/setup.md) before invoking `configure()`.")])
        # Reordering the protected tokens is conservatively rejected as well.
        self.assertEqual(valid["accepted"], [])
        valid = review_edits(snapshot, snapshot.candidates, [self.edit(snapshot, original=old,
                             replacement="Invoke `configure()` only after reading [setup](docs/setup.md).")])
        self.assertEqual(len(valid["accepted"]), 1)

    def test_report_labels_synthetic_edits_and_writes_only_review_patch(self):
        _, snapshot = self.snapshot()
        client = SyntheticClient([{"findings": [], "edits": [self.edit(snapshot)]}])
        report = analyze_snapshot(snapshot, client=client)
        self.assertEqual(report["mode"], "synthetic_fixture")
        self.assertFalse(report["execution"]["performed"])
        self.assertEqual(report["execution"]["verified_repairs"], 0)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            write_analysis(output, report)
            self.assertTrue((output / "suggestions.patch").read_text())
            self.assertFalse((output / "verified.patch").exists())


if __name__ == "__main__":
    unittest.main()
