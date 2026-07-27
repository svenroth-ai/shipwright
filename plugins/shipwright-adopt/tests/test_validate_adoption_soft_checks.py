"""Verify validate_adoption emits soft-check warnings (3.3).

Hard errors still hard-fail validation. Soft-check warnings are
informational — surfaced but non-blocking — and meant to flag
plausibility issues like "200 commits, only 1 ADR" that an adoption
artifact-presence check otherwise misses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from checks.validate_adoption import validate
from lib.derived_catalogue import summarize
from lib.derived_catalogue_doc import to_document, write_summary


def _make_minimum_valid(root: Path, *, decision_log_body: str | None = None) -> None:
    """Lay down all artifacts validate_adoption requires for ok=True."""
    for name in (
        "shipwright_run_config.json",
        "shipwright_project_config.json",
        "shipwright_plan_config.json",
        "shipwright_build_config.json",
        "shipwright_compliance_config.json",
    ):
        (root / name).write_text("{}", encoding="utf-8")
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "architecture.md").write_text("# arch\n", encoding="utf-8")
    (root / ".shipwright" / "agent_docs" / "conventions.md").write_text("# conv\n", encoding="utf-8")
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("# dash\n", encoding="utf-8")
    body = decision_log_body if decision_log_body is not None else "# log\n\n## ADR-0001: x\n"
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(body, encoding="utf-8")
    (root / ".shipwright" / "planning" / "01-adopted").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "planning" / "01-adopted" / "spec.md").write_text(
        "# spec\n\nFR-01.01 placeholder.\n", encoding="utf-8",
    )
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "adopted"}) + "\n", encoding="utf-8"
    )
    # The honesty artifact (trg-1aa5a8ab): what onboarding derived and nobody
    # confirmed. Built through the REAL writer — a hand-rolled stub would be a
    # fixture the production reader rejects, and the test would then be asserting
    # against something adopt never emits (external code review).
    (root / ".shipwright" / "adopt").mkdir(parents=True, exist_ok=True)
    write_summary(root, summarize(
        [{"fr_id": "FR-01.01", "label": "Sign in", "source_file": "src/auth.ts"}],
        split_name="01-adopted"))
    (root / "shipwright_known_failures.json").write_text(
        json.dumps({"known_failures": [], "baseline_failure_count": 0}), encoding="utf-8",
    )
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"UserPromptSubmit": [{"command": "uv run suggest_iterate.py"}]}}),
        encoding="utf-8",
    )
    (root / ".shipwright" / "adopt").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "adopt" / "review.md").write_text("status: skipped", encoding="utf-8")


def _write_snapshot(root: Path, *, commits_total: int) -> None:
    snap_dir = root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / "snapshot.json"
    snap.write_text(json.dumps({"git": {"commits_total": commits_total}}), encoding="utf-8")


def test_validate_returns_dict_with_errors_and_warnings(tmp_path: Path) -> None:
    """validate() now returns a dict (was list[str]) with both errors and warnings."""
    _make_minimum_valid(tmp_path)
    result = validate(tmp_path)
    assert isinstance(result, dict)
    assert "errors" in result
    assert "warnings" in result
    assert result["errors"] == []


def test_few_adrs_for_large_repo_warns(tmp_path: Path) -> None:
    """200 commits + 1 ADR triggers the historical-data-missing warning."""
    _make_minimum_valid(tmp_path)
    _write_snapshot(tmp_path, commits_total=200)
    result = validate(tmp_path)
    assert result["errors"] == []
    assert any("ADRs" in w or "historical" in w for w in result["warnings"]), result


def test_few_adrs_for_small_repo_no_warning(tmp_path: Path) -> None:
    """Under 50 commits, the few-ADRs check is silent."""
    _make_minimum_valid(tmp_path)
    _write_snapshot(tmp_path, commits_total=10)
    result = validate(tmp_path)
    assert not any("historical" in w for w in result["warnings"])


def test_many_adrs_for_large_repo_no_warning(tmp_path: Path) -> None:
    """The check fires only on count<3 — a 4-ADR log on a 200-commit repo is fine."""
    rich = "# log\n\n" + "\n\n".join(f"## ADR-{i:04d}: x\n" for i in range(1, 5))
    _make_minimum_valid(tmp_path, decision_log_body=rich)
    _write_snapshot(tmp_path, commits_total=200)
    result = validate(tmp_path)
    assert not any("historical" in w for w in result["warnings"])


def test_no_snapshot_does_not_crash(tmp_path: Path) -> None:
    """Snapshot may legitimately be absent (e.g. analyze_codebase didn't run);
    validate must not error out — it just skips the soft-check."""
    _make_minimum_valid(tmp_path)
    result = validate(tmp_path)
    assert result["errors"] == []
    # No "historical" warning since we have no commit count to compare against
    assert not any("historical" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# The honesty artifacts are HARD requirements (trg-1aa5a8ab)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", [
    ".shipwright/adopt/derived-catalogue.json",
    "shipwright_known_failures.json",
])
def test_a_missing_honesty_artifact_blocks_the_handover(tmp_path: Path, rel: str) -> None:
    """Errors, not warnings, and Step H hard-stops on errors.

    Without them the handover presents a derived catalogue as if someone had
    confirmed it, and an inherited red suite as this project's own failure.
    A warning would be surfaced and then walked past — which is how both gaps
    survived to be found years later.
    """
    _make_minimum_valid(tmp_path)
    (tmp_path / rel).unlink()
    result = validate(tmp_path)
    assert any(rel in e for e in result["errors"]), result


def test_the_error_names_the_step_that_writes_the_missing_file(tmp_path: Path) -> None:
    """A repo adopted before this rule existed will fail re-validation. That is
    correct — it genuinely lacks the artifacts — so the message must say what to
    run rather than only that something is absent."""
    _make_minimum_valid(tmp_path)
    (tmp_path / "shipwright_known_failures.json").unlink()
    (errmsg,) = [e for e in validate(tmp_path)["errors"] if "known_failures" in e]
    assert "record_inherited_baseline.py" in errmsg


def test_a_catalogue_that_contradicts_itself_blocks_the_handover(tmp_path: Path) -> None:
    """Present is not the same as trustworthy. The count in this file is what the
    adoption commit publishes, so a forged document must not pass the one gate
    meant to stop it."""
    _make_minimum_valid(tmp_path)
    doc = to_document(summarize(
        [{"fr_id": "FR-01.01", "label": "x", "source_file": "a.ts"}],
        split_name="01-adopted"))
    doc["unconfirmed"] = 0                      # a lie the entries do not support
    (tmp_path / ".shipwright" / "adopt" / "derived-catalogue.json").write_text(
        json.dumps(doc), encoding="utf-8")

    (err,) = [e for e in validate(tmp_path)["errors"] if "derived-catalogue" in e]
    assert "unusable" in err and "contradicts itself" in err


def test_a_catalogue_claiming_unearned_confirmation_blocks_the_handover(
    tmp_path: Path,
) -> None:
    _make_minimum_valid(tmp_path)
    doc = to_document(summarize(
        [{"fr_id": "FR-01.01", "label": "x", "source_file": "a.ts"}],
        split_name="01-adopted"))
    doc["requirements"][0]["confirmed"] = True
    doc["confirmed"], doc["unconfirmed"] = 1, 0   # counts kept self-consistent
    (tmp_path / ".shipwright" / "adopt" / "derived-catalogue.json").write_text(
        json.dumps(doc), encoding="utf-8")

    (err,) = [e for e in validate(tmp_path)["errors"] if "derived-catalogue" in e]
    assert "contradicts `basis`" in err
