"""Tests for shared/scripts/tools/aggregate_decisions.py."""

from __future__ import annotations

import json

from tools.aggregate_decisions import aggregate, drop_dir, rebuild_adr_index
from tools.write_decision_drop import write_decision_drop


def _drop(tmp_path, run_id, **over):
    fields = dict(
        run_id=run_id,
        section=f"Iterate — change: {run_id}",
        title=f"Title {run_id}",
        context="ctx",
        decision="dec",
        consequences="cons",
    )
    fields.update(over)
    return write_decision_drop(tmp_path, **fields)


def _log(tmp_path):
    return tmp_path / ".shipwright" / "agent_docs" / "decision_log.md"


def _seed_log(tmp_path, content):
    log = _log(tmp_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(content, encoding="utf-8")


def test_no_drops_is_noop(tmp_path):
    result = aggregate(tmp_path)
    assert result["aggregated"] == 0
    assert result["adr_numbers"] == []


def test_aggregates_drops_into_decision_log(tmp_path):
    _seed_log(
        tmp_path,
        "# Decision Log\n\n### ADR-005: prior\n- **Date:** 2026-01-01\n",
    )
    _drop(tmp_path, "iterate-20260515-aaa")
    _drop(tmp_path, "iterate-20260515-bbb")
    result = aggregate(tmp_path)
    assert result["aggregated"] == 2
    assert result["adr_numbers"] == [6, 7]
    log_text = _log(tmp_path).read_text(encoding="utf-8")
    assert "### ADR-006:" in log_text
    assert "### ADR-007:" in log_text
    # run-id traceability line linking run-id ↔ ADR-NNN
    assert "**Run-ID:** iterate-20260515-aaa" in log_text
    assert "**Run-ID:** iterate-20260515-bbb" in log_text


def test_drops_deleted_after_aggregation(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    d1 = _drop(tmp_path, "iterate-20260515-aaa")
    aggregate(tmp_path)
    assert not d1.exists()


def test_dry_run_changes_nothing(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    d1 = _drop(tmp_path, "iterate-20260515-aaa")
    before = _log(tmp_path).read_text(encoding="utf-8")
    result = aggregate(tmp_path, dry_run=True)
    assert result["aggregated"] == 1
    assert result["dry_run"] is True
    assert d1.exists()  # drop NOT deleted under dry-run
    assert _log(tmp_path).read_text(encoding="utf-8") == before


def test_numbering_starts_at_one_for_empty_log(tmp_path):
    # No decision_log.md on disk at all.
    _drop(tmp_path, "iterate-20260515-aaa")
    result = aggregate(tmp_path)
    assert result["adr_numbers"] == [1]
    assert _log(tmp_path).exists()


def test_malformed_drop_recorded_but_others_processed(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    _drop(tmp_path, "iterate-20260515-good")
    bad = (
        tmp_path / ".shipwright" / "agent_docs" / "decision-drops" / "bad_001.json"
    )
    bad.write_text("{not json", encoding="utf-8")
    result = aggregate(tmp_path)
    assert result["aggregated"] == 1
    assert any("bad_001" in e for e in result["errors"])
    assert bad.exists()  # malformed drop left in place for the operator


def test_authoring_date_preserved(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    drop = _drop(tmp_path, "iterate-20260515-aaa")
    data = json.loads(drop.read_text(encoding="utf-8"))
    data["date"] = "2025-01-02"  # distinct from today
    drop.write_text(json.dumps(data), encoding="utf-8")
    aggregate(tmp_path)
    assert "**Date:** 2025-01-02" in _log(tmp_path).read_text(encoding="utf-8")


def test_architecture_impact_updates_architecture_md(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    arch = tmp_path / ".shipwright" / "agent_docs" / "architecture.md"
    arch.write_text("# Architecture\n", encoding="utf-8")
    _drop(tmp_path, "iterate-20260515-aaa", architecture_impact="component")
    aggregate(tmp_path)
    assert "ADR-001" in arch.read_text(encoding="utf-8")


def test_drop_dir_resolves_main_repo_from_worktree(git_origin_repo, make_worktree):
    """aggregate_decisions.drop_dir is worktree-aware — symmetric with
    write_decision_drop.drop_dir, so the producer and the consumer never
    disagree on where the drop files live."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "agg-wt")
    assert drop_dir(wt).resolve() == (
        work / ".shipwright" / "agent_docs" / "decision-drops"
    ).resolve()


# ---------------------------------------------------------------------------
# Iterate A.3 — spec_ref pass-through + INDEX.md regeneration
# ---------------------------------------------------------------------------


def _seed_adr_spec(tmp_path, filename: str, body: str = "spec body\n") -> None:
    folder = tmp_path / ".shipwright" / "planning" / "adr"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(body, encoding="utf-8")


def test_spec_ref_renders_details_link_in_log(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    _drop(
        tmp_path, "iterate-20260520-spec",
        spec_ref=".shipwright/planning/adr/099-spec.md",
    )
    result = aggregate(tmp_path)
    assert result["aggregated"] == 1
    log_text = _log(tmp_path).read_text(encoding="utf-8")
    assert "**Details:**" in log_text
    assert "../planning/adr/099-spec.md" in log_text


def test_spec_ref_missing_in_drop_does_not_emit_details_bullet(tmp_path):
    """Backwards-compat: drops without spec_ref must render exactly as before
    (no stray empty Details bullet)."""
    _seed_log(tmp_path, "# Decision Log\n")
    _drop(tmp_path, "iterate-20260520-nospec")
    aggregate(tmp_path)
    log_text = _log(tmp_path).read_text(encoding="utf-8")
    assert "**Details:**" not in log_text


def test_aggregation_regenerates_adr_index(tmp_path):
    """After a non-dry-run aggregate, INDEX.md must list every numbered spec."""
    _seed_log(tmp_path, "# Decision Log\n")
    _seed_adr_spec(tmp_path, "001-alpha.md")
    _seed_adr_spec(tmp_path, "002-beta.md")
    _drop(tmp_path, "iterate-20260520-x")
    aggregate(tmp_path)
    index = (
        tmp_path / ".shipwright" / "planning" / "adr" / "INDEX.md"
    ).read_text(encoding="utf-8")
    # Sorted by ADR number prefix; index does not link itself
    assert "ADR-001 — alpha" in index
    assert "ADR-002 — beta" in index
    assert "INDEX.md" not in index.split("\n", 4)[-1]  # only the title may mention INDEX
    # Numeric prefix is preserved in the link href
    assert "(001-alpha.md)" in index
    assert "(002-beta.md)" in index


def test_dry_run_does_not_touch_index(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    _seed_adr_spec(tmp_path, "001-alpha.md")
    _drop(tmp_path, "iterate-20260520-x")
    aggregate(tmp_path, dry_run=True)
    index_path = tmp_path / ".shipwright" / "planning" / "adr" / "INDEX.md"
    assert not index_path.exists()


def test_rebuild_adr_index_handles_empty_folder(tmp_path):
    """An ADR folder with no specs still produces a usable INDEX (placeholder)."""
    folder = tmp_path / ".shipwright" / "planning" / "adr"
    folder.mkdir(parents=True)
    out = rebuild_adr_index(tmp_path)
    assert out == folder / "INDEX.md"
    text = out.read_text(encoding="utf-8")
    assert "ADR Spec Folder" in text
    assert "No ADR specs yet" in text


def test_rebuild_adr_index_returns_none_when_folder_missing(tmp_path):
    """No-op when the folder doesn't exist — keeps the aggregator fail-soft."""
    assert rebuild_adr_index(tmp_path) is None


def test_rebuild_adr_index_sorts_freeform_after_numbered(tmp_path):
    _seed_adr_spec(tmp_path, "010-zzz.md")
    _seed_adr_spec(tmp_path, "free-form-note.md")
    _seed_adr_spec(tmp_path, "001-alpha.md")
    rebuild_adr_index(tmp_path)
    index = (
        tmp_path / ".shipwright" / "planning" / "adr" / "INDEX.md"
    ).read_text(encoding="utf-8")
    # Order: 001, 010, freeform
    first = index.index("001-alpha.md")
    second = index.index("010-zzz.md")
    third = index.index("free-form-note.md")
    assert first < second < third
