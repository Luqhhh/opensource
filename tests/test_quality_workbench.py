"""Synthetic engineering checks, never independent quality or live-model evidence."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from exampleproof.model_api import JSONReply
from exampleproof.models import InferenceEvidence
from exampleproof.tutorial import prepare_project, analyze_snapshot
from exampleproof.tutorial_findings import deterministic_findings, enrich_findings
from exampleproof.tutorial_task import extract_task_blocks, review_task_edit, prepare_task_inputs
from exampleproof.tutorial_task_tools import create_template, runtime_sources, prerequisite_check, render_preview
from exampleproof.guard import validate_candidate
from exampleproof import tutorial_eval
from exampleproof.workbench import export_workbench
from exampleproof.tutorial_edits import review_edits


class SyntheticClient:
    provider = "synthetic_fixture"
    model = "fixture"
    evidence_kind = "synthetic_fixture"
    def __init__(self):
        self.requests = []
    def complete(self, system, payload):
        self.requests.append((system, payload))
        return JSONReply({"findings": [], "edits": [], "evidence_requests": []},
                         InferenceEvidence({"system": system, "payload": payload}, "synthetic", 1), 15, 3)


class QualityWorkbenchTests(unittest.TestCase):
    def project(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        root = base / "project"
        root.mkdir()
        (root / "README.md").write_text("# Setup\n\nPython 3.8+\n\nload_config does not override existing variables.\n\n```python\nfrom pathlib import Path\nPath('/path/to/result.txt').write_text('result')\n```\n")
        (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10"\n')
        (root / "config.py").write_text("def load_config(override=False):\n    return override\n")
        (root / "LICENSE").write_text("Synthetic fixture license")
        return base, root

    def test_version_and_placeholder_are_narrow_source_observations(self):
        _, root = self.project()
        snapshot = prepare_project(root, {})
        rules = {f.get("rule"): f for f in snapshot.static_observations}
        self.assertEqual(rules["python-minimum-conflict"]["claim_type"], "source_conflict")
        self.assertEqual(rules["placeholder-path"]["claim_type"], "experience_suggestion")
        (root / "README.md").write_text("Python 3.10+\n")
        self.assertFalse(prepare_project(root, {}).static_observations)

    def test_default_check_compares_explicit_function_default_only(self):
        _, root = self.project()
        (root / "README.md").write_text("By default, load_config(override=True) replaces variables.\n")
        observations = prepare_project(root, {}).static_observations
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["rule"], "literal-default-conflict")
        (root / "README.md").write_text("Example: load_config(override=True).\n")
        self.assertFalse(prepare_project(root, {}).static_observations)

    def test_absence_claim_is_unconfirmed_even_when_search_finds_no_support(self):
        _, root = self.project()
        snapshot = prepare_project(root, {})
        chunk = snapshot.chunks[0]
        finding = {"title": "缺少 load_config 优先级说明", "impact": "读者可能困惑", "suggestion": "补充说明",
                   "category": "explanation", "origin": "synthetic_fixture", "evidence": [asdict(chunk)]}
        result = enrich_findings(snapshot, [finding])[0]
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertFalse(result["source_search"]["absence_established"])
        self.assertFalse(result["source_search"]["counterevidence_confirmed"])
        self.assertIn("does not override", json.dumps(result["source_search"]))
        self.assertEqual(enrich_findings(snapshot, [finding, finding])[0]["id"], result["id"])
        self.assertEqual(len(enrich_findings(snapshot, [finding, finding])), 1)

    def test_direct_matches_lexical_input_and_document_ablation_excludes_source(self):
        _, root = self.project()
        snapshot = prepare_project(root, {}, task="Load configuration")
        clients = [SyntheticClient() for _ in range(3)]
        reports = [analyze_snapshot(snapshot, client=c, strategy=s, task_comparison=True)
                   for c, s in zip(clients, ("direct", "lexical", "documentation_only"))]
        self.assertEqual(clients[0].requests[0][1], clients[1].requests[0][1])
        self.assertNotEqual(clients[0].requests[0][0], clients[1].requests[0][0])
        self.assertTrue(all(c["kind"] == "document" for c in clients[2].requests[0][1]["evidence"]))
        self.assertFalse(reports[0]["findings"])
        self.assertTrue(reports[1]["findings"])

    def test_template_does_not_invent_a_passing_oracle(self):
        base, root = self.project()
        create_template(root, "README.md", 1, "Write result", base / "draft")
        with self.assertRaisesRegex(ValueError, "frozen task oracle"):
            prepare_task_inputs(root, base / "draft/task.json")

    def test_source_root_mapping_keeps_original_paths_read_only(self):
        contract = {"source_files": ["src/package/__init__.py"], "import_root": "src"}
        self.assertEqual(runtime_sources(contract, {"src/package/__init__.py": b"x=1"}), {"package/__init__.py": "x=1"})
        for bad in ("../src", "/src", "src/../src"):
            with self.assertRaises(ValueError):
                runtime_sources(contract | {"import_root": bad}, {})

    def test_rst_options_alias_and_literal_repl_preserve_outputs(self):
        text = ".. code:: pycon\n    :linenos:\n    :caption: Example\n\n    >>> x = 1\n    >>> x\n    1\n\nNext::\n\n    >>> print('ok')\n    ok\n"
        blocks = extract_task_blocks(text, "doc.rst")
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0][1], ("1\n",))
        self.assertEqual(blocks[1][1], ("ok\n",))
        self.assertNotIn(":caption", blocks[0][0])

    def test_existing_environment_assignment_is_preserved_but_new_mutations_rejected(self):
        original = 'from pathlib import Path\nos.environ["KEY"] = "value"\n'
        fixed = "import os\n" + original
        self.assertIsNotNone(validate_candidate(original, fixed))  # Existing repair policy remains strict.
        self.assertIsNone(validate_candidate(original, fixed, preserve_existing_mutations=True))
        self.assertIsNotNone(validate_candidate(original, fixed.replace('"value"', '"other"'), preserve_existing_mutations=True))

    def test_preview_escapes_html_and_never_interprets_rst_directives(self):
        html = render_preview("<script>alert(1)</script>\n\n.. include:: /etc/passwd\n", "README.rst")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("不是 Sphinx", html)

    def test_rst_prose_keeps_roles_and_rejects_directive_injection(self):
        _, root = self.project()
        text = "Read :func:`load_config` before saving configuration."
        (root / "guide.rst").write_text(text + "\n\n.. code-block:: python\n\n    assert True\n")
        snapshot = prepare_project(root, {})
        chunk = next(c for c in snapshot.chunks if c.path == "guide.rst")
        proposal = {"evidence_id": chunk.id, "original": text,
                    "replacement": "Read :func:`load_config` to understand configuration precedence before saving."}
        self.assertEqual(len(review_edits(snapshot, [chunk], [proposal])["accepted"]), 1)
        for bad in (".. raw:: html", "Read :class:`load_config` before saving.", "Read configuration::"):
            self.assertTrue(review_edits(snapshot, [chunk], [proposal | {"replacement": bad}])["rejected"])

    def test_reader_observations_require_real_fields_and_stay_separate(self):
        protocol = {"cases": [{"id": "load"}]}
        self.assertEqual(tutorial_eval.reader_metrics(protocol, "seal")["status"], "not_observed")
        row = {"case": "load", "participant": "synthetic-test", "condition": "original", "completed": False,
               "elapsed_seconds": 20.0, "help_count": 1, "notes": "test only", "observed_at": "2026-10-21T00:00:00Z"}
        record = {"schema_version": "reader-observations-1", "seal": "seal", "origin": "human_observation", "observations": [row]}
        result = tutorial_eval.reader_metrics(protocol, "seal", record)
        self.assertEqual(result["by_condition"]["original"]["completion_rate"], 0)
        self.assertNotIn("candidate", result["by_condition"])
        for invalid in (row | {"elapsed_seconds": float("nan")}, row | {"case": "unknown"}, row | {"help_count": -1}):
            with self.assertRaises(ValueError):
                tutorial_eval.reader_metrics(protocol, "seal", record | {"observations": [invalid]})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            tutorial_eval.reader_metrics(protocol, "seal", record | {"observations": [row, row]})

    def test_missing_documentation_cannot_be_supported_when_already_documented(self):
        base, root = self.project()
        frozen, review = self.freeze(base, root)
        class MissingClient(SyntheticClient):
            def complete(self, system, payload):
                reply = super().complete(system, payload)
                reply.value["findings"] = [{"title": "缺少配置说明", "category": "explanation", "impact": "配置不明",
                    "suggestion": "补充配置说明", "evidence_ids": [payload["evidence"][0]["id"]]}]
                return reply
        tutorial_eval.run(frozen, base / "run", review, lambda *args: MissingClient())
        quality = json.loads((base / "run/quality-review-template.json").read_text())
        quality.update(reviewer="synthetic test only", independent_human=True)
        for row in quality["rows"]:
            for finding in row["findings"]:
                finding.update(judgment="supported", reason="test reason", factual_relation="already_documented")
        with self.assertRaisesRegex(ValueError, "cannot be supported"):
            tutorial_eval.summarize(frozen, base / "run", quality)

    def freeze(self, base, root, version=1):
        spec = {"schema_version": "tutorial-task-evaluation-1", "projects": {"demo": {"root": str(root), "provenance": {}}},
                "review_schema": version, "strategies": ["direct", "lexical", "iterative", "documentation_only"],
                "model": {"provider": "synthetic_fixture", "name": "fixture"},
                "cases": [{"id": "load", "project": "demo", "task": "Load config", "acceptance": "Keeps variables",
                           "required_evidence": [{"path": "README.md", "start_line": 1, "end_line": 3}], "gold_issues": []}]}
        frozen = base / "frozen"
        result = tutorial_eval.freeze(spec, frozen)
        review = {"seal": result["seal"], "reviewer": "synthetic fixture; no real human review", "approved": True,
                  "independent_human": True, "authored_candidates_or_annotations": False, "complete_gold_inventory": True}
        return frozen, review

    def test_per_task_review_gate_cannot_be_replaced_by_a_global_yes(self):
        base, root = self.project()
        frozen, review = self.freeze(base, root, version=2)
        with self.assertRaisesRegex(ValueError, "every task"):
            tutorial_eval.run(frozen, base / "run", review, lambda *args: SyntheticClient())
        self.assertFalse((base / "run").exists())

    def test_costs_are_reported_without_inventing_quality(self):
        base, root = self.project()
        frozen, review = self.freeze(base, root)
        tutorial_eval.run(frozen, base / "run", review, lambda *args: SyntheticClient())
        result = tutorial_eval.summarize(frozen, base / "run")
        self.assertIsNone(result["support_rate"])
        self.assertEqual(result["operational_metrics"]["direct"]["total_tokens"], 18)
        self.assertIsNone(result["operational_metrics"]["direct"]["reader_task_completion_rate"])

    def test_generated_report_size_does_not_change_input_file_bound(self):
        from exampleproof.config import safe_path
        base, root = self.project()
        large = root / "analysis.json"
        large.write_text(" " * 300000)
        with self.assertRaisesRegex(ValueError, "exceeds 256000"):
            safe_path(root, "analysis.json")
        self.assertEqual(safe_path(root, "analysis.json", max_bytes=16_000_000), large)
        (root / "linked.json").symlink_to(large)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            safe_path(root, "linked.json", max_bytes=16_000_000)

    def test_workbench_binds_real_source_seal_and_does_not_mutate_evidence(self):
        base, root = self.project()
        frozen, review = self.freeze(base, root)
        result = export_workbench(frozen, base / "ui")
        self.assertEqual(result["seal"], tutorial_eval.verify(frozen))
        html = (base / "ui/index.html").read_text()
        self.assertIn("原文", html)
        self.assertIn("frozen_tasks_pending_human_review", html)
        self.assertNotIn("__EVIDENCE_DATA__", html)
        self.assertTrue((base / "ui/licenses/demo/LICENSE").is_file())
        javascript = (base / "ui/workbench.js").read_text()
        for removed in ("export-preflight", "export-quality", "localStorage", "<textarea", 'type="checkbox"'):
            self.assertNotIn(removed, javascript)


@unittest.skipUnless(os.environ.get("EXAMPLEPROOF_SANDBOX_TESTS") == "1", "Requires real Bubblewrap")
class EnvironmentProbeTests(unittest.TestCase):
    def test_missing_generated_version_is_environment_failure_not_task_defect(self):
        result = prerequisite_check("from package import value", {"package/__init__.py": "from .version import value"})
        self.assertEqual(result["status"], "environment_unprepared")
        self.assertEqual(result["diagnostic"], "possible_missing_generated_file")

    def test_standard_library_import_probe_runs_only_in_sandbox(self):
        self.assertEqual(prerequisite_check("from pathlib import Path", {})["status"], "ready")
