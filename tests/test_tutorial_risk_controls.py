"""Synthetic fixtures and mocked transport; no independent quality evidence."""

import contextlib
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from exampleproof.cli import main
from exampleproof.model_api import JSONClient
from exampleproof.project_input import project_input
from exampleproof.tutorial import analyze_snapshot, prepare_project, Chunk
from exampleproof.tutorial_coverage import _covered, measure_coverage
from exampleproof.tutorial_privacy import review_cloud
from exampleproof.tutorial_scope import EvidenceScope
from exampleproof.tutorial_study import audit_comparison, run_comparison


class RiskControlsTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "README.md").write_text("# Setup\n\nRead the configuration before starting.\n", encoding="utf-8")
        (root / "app.py").write_text('api_key = "synthetic-project-secret"\nvalue = "custom-sensitive-value"\n')
        return root

    def client(self):
        client = JSONClient("deepseek", "fixture", api_key="synthetic-auth-key")
        client.evidence_kind = "synthetic_fixture"
        return client

    def approve(self, snapshot, client, path, **options):
        with self.assertRaisesRegex(ValueError, "No model request was sent"):
            review_cloud(snapshot, client, path, **options)
        record = json.loads(path.read_text())
        return review_cloud(snapshot, client, path, record["sha256"], **options)

    def response(self, request, **kwargs):
        payload = json.loads(request.data)
        data = json.loads(payload["messages"][1]["content"])
        value = {"selected_ids": [c["id"] for c in data["candidates"]]} if "candidates" in data else {"findings": [], "edits": []}
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode())

    def test_tutorial_scope_has_build_files_and_explicit_tests_hidden_paths_with_github_parity(self):
        root = self.fixture()
        additions = {"Dockerfile": "FROM fixture\n", "Makefile": "all:\n\tfixture\n",
                     "tests/test_api.py": "assert True\n", ".github/workflows/ci.yml": "name: synthetic\n",
                     ".git/config": "private metadata\n", ".env": "secret\n",
                     "tests/metadata.json": "evaluator-owned\n", "docs/private.md": "exclude me\n"}
        for relative, text in additions.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        default = prepare_project(root, {})
        self.assertTrue({"Dockerfile", "Makefile"} <= default.files.keys())
        self.assertNotIn("tests/test_api.py", default.files)
        self.assertNotIn(".github/workflows/ci.yml", default.files)
        scope = EvidenceScope(True, (".github/**", ".git/**", ".env"), ("docs/**",))
        local = prepare_project(root, {}, scope=scope)
        self.assertTrue({"tests/test_api.py", ".github/workflows/ci.yml"} <= local.files.keys())
        for excluded in (".git/config", ".env", "tests/metadata.json", "docs/private.md"):
            self.assertNotIn(excluded, local.files)
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            for relative in ("README.md", "app.py", *additions):
                archive.writestr("root/" + relative, (root / relative).read_bytes())
        with patch("exampleproof.project_input.fetch", side_effect=[json.dumps({"sha": "a" * 40}).encode(), archive_bytes.getvalue()]):
            with project_input("owner/repo", scope=scope) as (remote, provenance):
                self.assertEqual(prepare_project(remote, provenance, scope=scope).snapshot_id, local.snapshot_id)

    def test_necessary_evidence_distinguishes_index_candidate_and_selected_gaps(self):
        root = self.fixture()
        for index in range(55):
            (root / f"source{index:02}.py").write_text("value = 1\n")
        (root / "zzz.py").write_text("necessary = 1\n")
        snapshot = prepare_project(root, {})
        requirements = {"schema_version": "tutorial-evidence-requirements-1", "snapshot_id": snapshot.snapshot_id,
                        "evidence_kind": "synthetic_fixture", "annotator": "synthetic engineering fixture",
                        "cases": [{"id": "cross-file", "required": [
                            {"path": "README.md", "start_line": 1, "end_line": 3},
                            {"path": "zzz.py", "start_line": 1, "end_line": 1}]}]}
        report = analyze_snapshot(snapshot, evidence_requirements=requirements)
        result = report["necessary_evidence_coverage"]
        self.assertEqual(result["stages"]["indexed"]["complete_cases"], 1)
        self.assertEqual(result["stages"]["candidates"]["complete_cases"], 0)
        self.assertEqual(result["stages"]["selected"]["complete_cases"], 0)
        self.assertEqual(len(snapshot.candidates), 40)
        self.assertEqual(result["evidence_kind"], "synthetic_fixture")
        self.assertEqual(report["quality_review_status"], "not_reviewed")
        requirements["snapshot_id"] = "wrong snapshot"
        with self.assertRaisesRegex(ValueError, "snapshot mismatch"):
            analyze_snapshot(snapshot, evidence_requirements=requirements)
        self.assertEqual(measure_coverage(snapshot, [])['status'], "not_measured")

    def test_required_span_needs_complete_contiguous_coverage(self):
        span = {"path": "README.md", "start_line": 2, "end_line": 10}
        first = Chunk("a", "README.md", 1, 5, "document", "", "")
        second = Chunk("b", "README.md", 6, 10, "document", "", "")
        hole = Chunk("b", "README.md", 7, 10, "document", "", "")
        self.assertTrue(_covered(span, [second, first]))
        self.assertFalse(_covered(span, [first, hole]))
        self.assertFalse(_covered(span, [first]))

    def test_cloud_requires_prior_manifest_and_matching_approval_even_with_library_api(self):
        root = self.fixture()
        snapshot, client = prepare_project(root, {}), self.client()
        with tempfile.TemporaryDirectory() as temporary, patch("exampleproof.model_api.urlopen") as send:
            path = Path(temporary) / "review.json"
            with self.assertRaisesRegex(ValueError, "requires a reviewed"):
                analyze_snapshot(snapshot, client=client)
            with self.assertRaisesRegex(ValueError, "requires review"):
                review_cloud(snapshot, client, path, "arbitrary approval")
            with self.assertRaisesRegex(ValueError, "requires review"):
                review_cloud(snapshot, client, path, "wrong digest")
            send.assert_not_called()
            record = json.loads(path.read_text())
            self.assertNotIn("synthetic-project-secret", path.read_text())
            self.assertIn("custom-sensitive-value", path.read_text())
            self.assertEqual({v["path"] for v in record["review"]["files"]}, {"README.md", "app.py"})
            (root / "app.py").write_text("changed = True\n")
            with self.assertRaisesRegex(ValueError, "differs from current"):
                review_cloud(prepare_project(root, {}), client, path, record["sha256"])
            with self.assertRaisesRegex(ValueError, "outside"):
                review_cloud(prepare_project(root, {"kind": "local", "path": str(root)}), client, root / "review.json")

    def test_cloud_redacts_both_selection_previews_and_analysis_and_enforces_budget(self):
        snapshot, client = prepare_project(self.fixture(), {}), self.client()
        originals = {p: f["text"] for p, f in snapshot.files.items()}
        with tempfile.TemporaryDirectory() as temporary:
            reviewed = self.approve(snapshot, client, Path(temporary) / "review.json", strategies=("ai",),
                                    context_chars=2000, redact_values=["custom-sensitive-value"])
            with patch("exampleproof.model_api.urlopen", side_effect=self.response) as send:
                report = analyze_snapshot(snapshot, client=reviewed, strategy="ai", context_chars=2000)
            self.assertEqual(send.call_count, 2)
            for call in send.call_args_list:
                body = call.args[0].data.decode()
                self.assertNotIn("synthetic-project-secret", body)
                self.assertNotIn("custom-sensitive-value", body)
                self.assertNotIn("synthetic-auth-key", body)
                self.assertIn("[REDACTED]", body)
                payload = json.loads(json.loads(body)["messages"][1]["content"])
                self.assertLessEqual(len(json.dumps(payload.get("evidence", payload.get("candidates")), ensure_ascii=False)), 2000)
            self.assertEqual({p: f["text"] for p, f in snapshot.files.items()}, originals)
            self.assertEqual(report["mode"], "synthetic_fixture")
            self.assertFalse(report["execution"]["performed"])
            client.model = "changed-model"
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                analyze_snapshot(snapshot, client=reviewed, strategy="ai", context_chars=2000)

    def test_redaction_handles_private_key_split_across_chunks_and_preview_boundary(self):
        root = self.fixture()
        (root / "config.txt").write_text("-----BEGIN PRIVATE KEY-----\n" + "synthetic-private-material\n" * 170 +
                                         "-----END PRIVATE KEY-----\n")
        snapshot = prepare_project(root, {})
        with tempfile.TemporaryDirectory() as temporary:
            reviewed = self.approve(snapshot, self.client(), Path(temporary) / "review.json")
            serialized = json.dumps(reviewed.review_record)
            self.assertNotIn("synthetic-private-material", serialized)
            for original in snapshot.candidates:
                sanitized = reviewed.render_chunk(original)
                self.assertEqual(len(original.text.splitlines()), len(sanitized["text"].splitlines()))

    def test_reviewed_client_rejects_added_evidence_before_transport(self):
        from exampleproof.tutorial import ANALYZE_SYSTEM
        from exampleproof.tutorial_privacy import analysis_coverage
        snapshot = prepare_project(self.fixture(), {})
        with tempfile.TemporaryDirectory() as temporary, patch("exampleproof.model_api.urlopen") as send:
            reviewed = self.approve(snapshot, self.client(), Path(temporary) / "review.json")
            chunk = asdict(snapshot.candidates[0]) | {"text": "unreviewed text"}
            with self.assertRaisesRegex(ValueError, "Unreviewed cloud evidence"):
                reviewed.complete(ANALYZE_SYSTEM, {"coverage": analysis_coverage(snapshot, 1), "evidence": [chunk]})
            send.assert_not_called()

    def test_cli_two_step_flow_does_not_modify_input_or_create_report_before_approval(self):
        root = self.fixture()
        before = {p.name: p.read_bytes() for p in root.iterdir()}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-auth-key"}), \
                patch.object(JSONClient, "evidence_kind", "synthetic_fixture"), \
                patch("exampleproof.model_api.urlopen", side_effect=self.response) as send, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            output = Path(temporary) / "analysis"
            args = ["analyze", str(root), "--output", str(output)]
            self.assertEqual(main(args), 2)
            self.assertFalse(output.exists())
            send.assert_not_called()
            review_path = Path(str(output) + "-cloud-review.json")
            digest = json.loads(review_path.read_text())["sha256"]
            self.assertEqual(main(args + ["--approve-cloud", digest]), 0)
            self.assertEqual(send.call_count, 1)
            self.assertTrue((output / "evidence-coverage.json").exists())
        self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)

    def test_cloud_comparison_audit_and_coverage_leave_quality_unassessed(self):
        root = self.fixture()
        snapshot = prepare_project(root, {})
        requirements = {"schema_version": "tutorial-evidence-requirements-1", "snapshot_id": snapshot.snapshot_id,
                        "evidence_kind": "synthetic_fixture", "annotator": "fixture",
                        "cases": [{"id": "setup", "required": [{"path": "README.md", "start_line": 1, "end_line": 3}]}]}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            reviewed = self.approve(snapshot, self.client(), base / "review.json", strategies=("lexical", "ai"))
            with patch("exampleproof.model_api.urlopen", side_effect=self.response):
                summary = run_comparison(root, {}, base / "comparison", reviewed, snapshot=snapshot, evidence_requirements=requirements)
            audit = audit_comparison(base / "comparison")
            self.assertEqual(audit["status"], "passed", audit)
            self.assertIsNone(audit["quality_passed"])
            self.assertEqual(summary["quality_review_status"], "not_reviewed")
            path = base / "comparison/lexical/analysis.json"
            record = json.loads(path.read_text())
            record["necessary_evidence_coverage"]["stages"]["selected"]["covered_spans"] += 1
            path.write_text(json.dumps(record))
            self.assertEqual(audit_comparison(base / "comparison")["status"], "failed")

    def test_factorial_cloud_preflight_finishes_before_any_provider_requests(self):
        import hashlib
        from scripts import run_tutorial_factorial as factorial
        root = self.fixture()
        snapshot = prepare_project(root, {})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            import shutil
            shutil.copytree(root, output / "inputs" / "fixture")
            protocol = {"implementation_sha256": {}, "script_sha256": hashlib.sha256(Path(factorial.__file__).read_bytes()).hexdigest(),
                        "providers": ["deepseek", "ollama"], "context_chars": 12000,
                        "projects": {"fixture": {"project": {}, "snapshot_id": snapshot.snapshot_id}}}
            (output / "protocol.json").write_text(json.dumps(protocol))
            with patch.object(factorial, "client_for", return_value=self.client()), \
                    patch.object(factorial, "ThreadPoolExecutor") as executor, \
                    patch("exampleproof.model_api.urlopen") as send:
                with self.assertRaisesRegex(ValueError, "no model calls started"):
                    factorial.run(output)
                send.assert_not_called()
                executor.assert_not_called()
                self.assertTrue((output / "cloud-reviews/fixture.json").is_file())


if __name__ == "__main__":
    unittest.main()
