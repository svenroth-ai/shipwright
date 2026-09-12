"""Shared fixtures for the project-phase verifier test modules.

Split out of ``test_verifiers_project.py`` (shared bloat gate, 300-line
limit) so ``seed_canon_project``/``_write_grill_trace``/``_write_splits_config``
have one home instead of being duplicated across the files that now cover
``project_checks.py`` and ``_project_gate_wiring.py`` separately.
"""

from __future__ import annotations

import json
from pathlib import Path


def seed_canon_project(
    root: Path,
    *,
    splits: list[str] | None = None,
    run_id: str = "project-20260414-test",
    write_canon_artifacts: bool = True,
) -> None:
    """Produce a minimally-valid project that passes every check in
    ``run_project_checks`` when ``write_canon_artifacts=True``.

    Callers selectively tear down individual artifacts in failure-path
    tests so we don't pay the seed cost every time.
    """
    splits = splits or ["01-auth", "02-dashboard"]

    # Project config — status=complete, splits populated. scope="extension"
    # so `check_starting_guidance_present` (FR-01.02 #11) is skipped here —
    # this fixture never modeled CLAUDE.md/agent_docs scaffolding, which is
    # a Full Application-only concern this generic canon fixture is not
    # about; dedicated tests below exercise that check directly.
    (root / "shipwright_project_config.json").write_text(
        json.dumps({
            "status": "complete",
            "scope": "extension",
            "splits": [{"name": s, "status": "complete"} for s in splits],
        }),
        encoding="utf-8",
    )

    # Planning dirs matching splits — each spec.md carries one clean, minimal
    # FR row so `check_no_empty_split` (FR-01.02 #10) doesn't itself turn the
    # happy path red: a split with a bare "# spec" heading and no FR table is
    # exactly the empty-split defect that check exists to catch.
    for i, s in enumerate(splits, start=1):
        split_dir = root / ".shipwright" / "planning" / s
        split_dir.mkdir(parents=True)
        (split_dir / "spec.md").write_text(
            "# spec\n\n"
            "| ID | Name | Priority | Description | Basis |\n"
            "|---|---|---|---|---|\n"
            f"| FR-{i:02d}.01 | some capability | Must | "
            "a plain-language capability description | interview |\n",
            encoding="utf-8",
        )

    if not write_canon_artifacts:
        return

    # C1 — phase_completed event
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "phase_completed",
            "phase": "project",
            "timestamp": "2026-04-14T10:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )

    # C2 — build_dashboard mentions project
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "## Phases\n\n- project: complete\n"
    )

    # C3 — fresh session_handoff
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")

    # C4 — ADR referencing project
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Project decomposition decision\n"
        "- **Status:** accepted\n"
    )

    # C5 — CHANGELOG [Unreleased] Added bullet (root CHANGELOG)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n"
        "- Project initialized: demo (2 splits)\n"
    )

    # phase_history — seed via run_config
    (root / "shipwright_run_config.json").write_text(
        json.dumps({
            "phase_history": {
                "project": [{"run_id": run_id, "date": "2026-04-14"}]
            },
        }),
        encoding="utf-8",
    )


def _write_grill_trace(root: Path, *, requirement_key: str, **dimension_overrides: str) -> None:
    """Write one valid-shaped grill-trace record, applying dimension
    overrides so an individual test can push exactly one dimension into
    STOP territory while keeping the other six/seven fields shape-valid."""
    dimensions = {
        "outcome": "answered",
        "purpose": "answered",
        "boundaries": "answered",
        "failure": "answered",
        "glossary": "answered",
        "rationale": "answered",
        "out_of_scope": "answered",
    }
    dimensions.update(dimension_overrides)
    trace_dir = root / ".shipwright" / "planning" / "grill-traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / f"{requirement_key}.json").write_text(
        json.dumps({
            "requirement_key": requirement_key,
            "requirement_text": "Users can export their data",
            "surface": "project",
            "evidence": ["interview transcript line 42"],
            "dimensions": dimensions,
            "fit_criterion": "export completes in < 5s for a 10k-row account",
            "glossary_delta": [],
            "confirmed_by": "user",
            "terms_used": [],
        }),
        encoding="utf-8",
    )


def _write_splits_config(root: Path, names: list[str]) -> None:
    """Declares ``names`` as this project's splits manifest — the
    authoritative source ``_read_spec_texts`` now enumerates from (round 2
    fix: config-driven, not directory-enumeration; see
    ``_project_gate_manifest._declared_split_names``)."""
    (root / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": n, "status": "not_started"} for n in names]}),
        encoding="utf-8",
    )
