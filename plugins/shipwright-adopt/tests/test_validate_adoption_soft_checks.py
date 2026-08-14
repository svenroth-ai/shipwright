"""Verify validate_adoption emits soft-check warnings (3.3).

Hard errors still hard-fail validation. Soft-check warnings are
informational — surfaced but non-blocking — and meant to flag
plausibility issues like "200 commits, only 1 ADR" that an adoption
artifact-presence check otherwise misses.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

import checks.validate_adoption as validate_adoption_module
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


def test_hollow_adr_entry_warns_regardless_of_commit_count(tmp_path: Path) -> None:
    """trg-6b59524b: a hollow entry is a correctness defect, not a density
    signal — it must warn even under the 50-commit density-check floor,
    and the message must name the specific missing field(s)."""
    hollow_log = (
        "# Decision Log\n\n"
        "### ADR-001: (no subject)\n\n"
        "- **Status**: accepted (retroactive, llm-inferred)\n"
        "- **Commit**: ``\n\n"
        "#### Context\nA full multi-paragraph body the LLM did produce.\n\n"
        "#### Decision\nAlso real.\n\n"
        "#### Consequences\n—\n\n---\n"
    )
    _make_minimum_valid(tmp_path, decision_log_body=hollow_log)
    result = validate(tmp_path)
    assert result["errors"] == []
    assert any(
        "hollow entry" in w and "ADR-001" in w and "subject" in w and "commit" in w
        for w in result["warnings"]
    ), result


def test_healthy_adr_entry_does_not_warn(tmp_path: Path) -> None:
    healthy_log = (
        "# Decision Log\n\n"
        "### ADR-001: Adopt this repository into the Shipwright SDLC\n\n"
        "- **Commit**: `abc1234`\n\n"
        "#### Context\nReal context.\n\n"
        "#### Decision\nReal decision.\n\n---\n"
    )
    _make_minimum_valid(tmp_path, decision_log_body=healthy_log)
    result = validate(tmp_path)
    assert not any("hollow entry" in w for w in result["warnings"])


def test_hollow_adrs_excluded_from_density_count(tmp_path: Path) -> None:
    """trg-6b59524b: the density check must not be MISLED by a hollow entry
    counting the same as a real one — 1 substantive ADR of 3 total on a
    200-commit repo must still trip the historical-data warning."""
    log = (
        "# Decision Log\n\n"
        "### ADR-001: Real one\n\n- **Commit**: `abc1234`\n\n"
        "#### Context\nctx\n\n#### Decision\ndec\n\n---\n\n"
        "### ADR-002: (no subject)\n\n- **Commit**: ``\n\n"
        "#### Context\nctx\n\n#### Decision\ndec\n\n---\n\n"
        "### ADR-003: (no subject)\n\n- **Commit**: ``\n\n"
        "#### Context\nctx\n\n#### Decision\ndec\n\n---\n"
    )
    _make_minimum_valid(tmp_path, decision_log_body=log)
    _write_snapshot(tmp_path, commits_total=200)
    result = validate(tmp_path)
    assert any("historical" in w and "1 substantive" in w for w in result["warnings"]), result


def test_hollow_adr_detection_loader_does_not_poison_cache_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doubt-reviewer (round 4): `_hollow_adr_detection()`'s loader can't
    reuse `lib/shared_loader.py` (it targets plugin-local `lib/`, not
    `shared/`) — this pins that its own copy of the same two guards holds:
    a failing exec must not memoise a half-initialised module under the
    sentinel, so a later retry re-raises rather than returning it broken."""
    sentinel = "_shipwright_adopt_hollow_adr_detection"
    sys.modules.pop(sentinel, None)
    real_spec_from_file_location = importlib.util.spec_from_file_location

    def bad_spec(*args, **kwargs):
        spec = real_spec_from_file_location(*args, **kwargs)
        spec.loader.exec_module = lambda module: (_ for _ in ()).throw(RuntimeError("boom"))
        return spec

    with monkeypatch.context() as m:
        m.setattr(importlib.util, "spec_from_file_location", bad_spec)
        with pytest.raises(RuntimeError, match="boom"):
            validate_adoption_module._hollow_adr_detection()
    assert sentinel not in sys.modules

    mod = validate_adoption_module._hollow_adr_detection()
    assert hasattr(mod, "find_hollow_adrs")


def test_missing_adr_seed_folder_warns(tmp_path: Path) -> None:
    """Doubt-reviewer (round 4): the ADR-folder seed is best-effort by
    design, so nothing else notices if it silently degraded. Surface it."""
    _make_minimum_valid(tmp_path)
    result = validate(tmp_path)
    assert result["errors"] == []
    assert any("no seeded ADR files" in w for w in result["warnings"]), result


def test_missing_adr_index_warns(tmp_path: Path) -> None:
    """The folder can exist with real ADRs while INDEX.md's own refresh
    still failed (best-effort subprocess) — that must warn too."""
    _make_minimum_valid(tmp_path)
    adr_dir = tmp_path / ".shipwright" / "planning" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "001-adopt-this-repository.md").write_text("# ADR-001 — x\n", encoding="utf-8")
    result = validate(tmp_path)
    assert any("INDEX.md is missing" in w for w in result["warnings"]), result


def test_seeded_adr_folder_with_index_does_not_warn(tmp_path: Path) -> None:
    _make_minimum_valid(tmp_path)
    adr_dir = tmp_path / ".shipwright" / "planning" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "001-adopt-this-repository.md").write_text("# ADR-001 — x\n", encoding="utf-8")
    (adr_dir / "INDEX.md").write_text("# ADR Index\n", encoding="utf-8")
    result = validate(tmp_path)
    assert not any("seeded ADR" in w or "INDEX.md is missing" in w for w in result["warnings"])


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
