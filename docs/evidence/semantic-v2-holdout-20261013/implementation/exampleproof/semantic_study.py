"""Predeclared v2 method comparison; keep development and holdout runs separate."""

import json

from .providers import SYSTEM, SYSTEM_V2


def validate_project_splits(projects, design):
    split = design.get("split")
    if split not in {"development", "holdout"}:
        raise ValueError("A semantic study requires an explicit development/holdout split")
    for project in projects:
        metadata = json.loads((project / "metadata.json").read_text(encoding="utf-8"))
        if metadata.get("split") != split + "_v2":
            raise ValueError(f"Project split does not match declared study split: {project.name}")
        if split == "holdout":
            provenance = metadata.get("provenance", {})
            if (metadata.get("selection", {}).get("held_out_from_method_optimization") is not True
                    or provenance.get("held_out") is False
                    or provenance.get("previous_cases_and_live_results_seen") is True
                    or provenance.get("live_model_evaluation") is True):
                raise ValueError(f"Holdout declaration conflicts with project provenance: {project.name}")


def study_design(split):
    if split not in {"development", "holdout"}:
        raise ValueError("Split must be development or holdout")
    return {
        "name": "semantic-v2-method-comparison",
        "method_revision": 2,
        "split": split,
        "seeds": [17] if split == "development" else [17, 29, 43],
        "source_context_character_limit": 6000,
        "retrieval_policy": {
            "project_sources": "AST receiver scope and lexical ranking; exclude unreferenced private APIs.",
            "stdlib_trigger": "Original missing-import exception matches a from-import in the example and the selected project package.",
            "stdlib_corpus": "Fixed public top-level Python standard-library function signatures/docstrings; static AST extraction, no candidate module imports.",
            "triggered_character_budget": {"project": 4000, "stdlib": 2000},
            "untriggered_project_character_budget": 6000,
            "causal_scope": "The v2 method combines retrieval, additional standard-library evidence and a revised generic prompt.",
        },
        "arms": {
            "legacy_source": {"context": "legacy", "feedback": "none", "system_prompt": SYSTEM},
            "legacy_feedback": {"context": "legacy", "feedback": "generic", "system_prompt": SYSTEM},
            "source_v2": {"context": "v2", "feedback": "none", "system_prompt": SYSTEM_V2},
            "generic_feedback_v2": {"context": "v2", "feedback": "generic", "system_prompt": SYSTEM_V2},
            "feedback_v2": {"context": "v2", "feedback": "categorized", "system_prompt": SYSTEM_V2},
        },
        "held_out_scope": (
            "Development: known v1 failure modes and evaluator-authored extended semantic contracts. "
            "May inform optimization; never an independent generalization score."
            if split == "development" else
            "Held out from application method/prompt optimization. Independently collected new projects; "
            "method locked before implementation owner inspects case details, then inputs and checks frozen "
            "before first live call. Public upstream content may occur in model pretraining. Not double-blind."
        ),
        "comparisons": {
            "legacy_source_vs_source_v2": "Combined retrieval and generic prompt revision, not isolated retrieval causality.",
            "source_v2_vs_generic_feedback_v2": "History feedback effect with identical first-call prompt/context.",
            "generic_feedback_v2_vs_feedback_v2": "Additional fixed host failure categories; same first-call data and all other v2 settings.",
            "legacy_feedback_vs_feedback_v2": "Complete method upgrade under equal maximum calls and output-token budgets.",
        },
        "selection": "All predeclared cases and seeds; failed, declined, rejected and malformed generations retained.",
    }
