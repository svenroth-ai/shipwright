"""Rendering tests for the "when did the cross-check last run?" disclosure.

``format_note`` is the one-line suffix every evidence-document header carries;
``render_consistency_audit`` is the dashboard's block. Both render from the
durable record only — never from the gitignored ``audit-report.*`` transients,
so a tracked document reads the same on every machine.

Four states must stay distinguishable: never run, unknown (damaged record),
partial-only, and checked. Collapsing any pair of them produces exactly the
false confidence this feature exists to remove.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lib._audit_disclosure_render import (
    format_note,
    freshness_note,
    render_consistency_audit,
)
from scripts.lib.audit_disclosure import (
    ABSENT,
    CONFIG_FILE,
    INVALID,
    LAST_AUDIT_KEY,
    VALID,
    AuditFreshness,
    AuditRecord,
    record_audit_run,
)

_AS_OF = "2026-07-27T12:00:00+00:00"


@pytest.fixture
def bare_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _rec(ran_at="2026-07-15T00:00:00+00:00", verdict="pass", scope="full",
         checks=None) -> AuditRecord:
    return AuditRecord(ran_at, verdict, scope, checks or {})


def _record(root: Path, **kw) -> None:
    kw.setdefault("statuses", ["pass"])
    kw.setdefault("any_fail", False)
    kw.setdefault("ran_at", "2026-07-15T00:00:00+00:00")
    record_audit_run(root, **kw)


class TestFormatNote:
    """AC-1/2/3/5 — the one-line disclosure carried by every document header."""

    def test_never_run_says_so_explicitly(self):
        note = format_note(AuditFreshness(ABSENT), as_of=_AS_OF)
        assert note.startswith("Consistency-audit: ")
        assert "never run" in note

    def test_unreadable_record_is_unknown_not_never(self):
        """A damaged record must not assert something the project cannot know."""
        note = format_note(AuditFreshness(INVALID), as_of=_AS_OF)
        assert "unknown" in note
        assert "never run" not in note

    def test_records_the_date_and_the_age(self):
        note = format_note(
            AuditFreshness(VALID, _rec(), _rec()), as_of=_AS_OF,
        )
        assert "2026-07-15" in note
        assert "12 days earlier" in note
        assert "PASS" in note

    def test_same_day_reads_as_same_day(self):
        r = _rec(ran_at="2026-07-27T09:00:00+00:00")
        note = format_note(AuditFreshness(VALID, r, r), as_of=_AS_OF)
        assert "same day" in note
        assert "0 days" not in note

    def test_one_day_is_singular(self):
        r = _rec(ran_at="2026-07-26T09:00:00+00:00")
        note = format_note(AuditFreshness(VALID, r, r), as_of=_AS_OF)
        assert "1 day earlier" in note
        assert "1 days" not in note

    def test_audit_newer_than_the_render_reference_clamps(self):
        """The reference is event-pinned, so it can trail a fresh audit run."""
        r = _rec(ran_at="2026-08-02T00:00:00+00:00")
        note = format_note(AuditFreshness(VALID, r, r), as_of=_AS_OF)
        assert "same day" in note
        assert "-6" not in note

    def test_failing_audit_is_disclosed_as_failing(self):
        r = _rec(verdict="fail")
        note = format_note(AuditFreshness(VALID, r, r), as_of=_AS_OF)
        assert "FAIL" in note

    def test_partial_run_does_not_displace_the_last_full_check(self):
        """The reader's question is "when was the WHOLE thing checked?"."""
        partial = _rec(ran_at="2026-07-25T00:00:00+00:00", scope="A,B")
        full = _rec(ran_at="2026-07-01T00:00:00+00:00")
        note = format_note(AuditFreshness(VALID, partial, full), as_of=_AS_OF)
        assert "last full run 2026-07-01" in note
        assert "26 days earlier" in note
        assert "partial" in note
        assert "A,B" in note

    def test_partial_only_project_says_never_fully_run(self):
        partial = _rec(scope="A,B")
        note = format_note(AuditFreshness(VALID, partial, None), as_of=_AS_OF)
        assert "never fully run" in note
        assert "A,B" in note

    def test_unparseable_reference_still_discloses_the_run(self):
        note = format_note(AuditFreshness(VALID, _rec(), _rec()), as_of="")
        assert "2026-07-15" in note

    def test_note_is_a_single_line(self):
        states = [
            AuditFreshness(ABSENT),
            AuditFreshness(INVALID),
            AuditFreshness(VALID, _rec(), _rec()),
            AuditFreshness(VALID, _rec(scope="A"), None),
        ]
        for freshness in states:
            assert "\n" not in format_note(freshness, as_of=_AS_OF)

    def test_freshness_note_reads_the_durable_record(self, bare_root: Path):
        _record(bare_root)
        assert "2026-07-15" in freshness_note(bare_root, as_of=_AS_OF)

    def test_freshness_note_on_a_bare_project_says_never(self, bare_root: Path):
        assert "never run" in freshness_note(bare_root, as_of=_AS_OF)

    def test_freshness_note_on_a_damaged_record_says_unknown(self, bare_root: Path):
        (bare_root / CONFIG_FILE).write_text(
            json.dumps({LAST_AUDIT_KEY: {"ran_at": "not-a-date"}}),
            encoding="utf-8",
        )
        note = freshness_note(bare_root, as_of=_AS_OF)
        assert "unknown" in note
        assert "not-a-date" not in note  # never interpolated verbatim


class TestRenderConsistencyAudit:
    """AC-6 — the dashboard section, from the durable record only."""

    def test_never_run_is_stated_plainly(self, bare_root: Path):
        block = "\n".join(render_consistency_audit(bare_root, as_of=_AS_OF))
        assert "## 🔎 Consistency Audit" in block
        assert "Never run" in block
        # ...and why nothing will produce this check on its own.
        assert "on demand" in block.lower()

    def test_damaged_record_renders_as_unknown(self, bare_root: Path):
        (bare_root / CONFIG_FILE).write_text("{oops", encoding="utf-8")
        block = "\n".join(render_consistency_audit(bare_root, as_of=_AS_OF))
        assert "Unknown" in block
        assert "Never run" not in block

    def test_recorded_run_shows_date_age_verdict_and_counts(self, bare_root: Path):
        _record(bare_root, statuses=["pass"] * 45 + ["skip"] * 3)
        block = "\n".join(render_consistency_audit(bare_root, as_of=_AS_OF))
        assert "2026-07-15" in block
        assert "12 days earlier" in block
        assert "PASS" in block
        assert "48 checks" in block
        assert "45 pass" in block

    def test_failing_run_names_the_drift(self, bare_root: Path):
        _record(bare_root, statuses=["fail"], any_fail=True)
        block = "\n".join(render_consistency_audit(bare_root, as_of=_AS_OF))
        assert "FAIL" in block

    def test_partial_since_the_last_full_run_is_spelled_out(self, bare_root: Path):
        _record(bare_root, ran_at="2026-07-01T00:00:00+00:00")
        _record(bare_root, ran_at="2026-07-25T00:00:00+00:00", scope="A,B")
        block = "\n".join(render_consistency_audit(bare_root, as_of=_AS_OF))
        assert "Last full run 2026-07-01" in block
        assert "partial" in block
        assert "does not re-check the rest of the project" in block

    def test_partial_only_project_says_never_fully_run(self, bare_root: Path):
        _record(bare_root, scope="A,B")
        block = "\n".join(render_consistency_audit(bare_root, as_of=_AS_OF))
        assert "Never fully run" in block
        assert "A,B" in block

    def test_gitignored_transient_does_not_change_the_render(self, bare_root: Path):
        """The tracked document must read the same on every machine."""
        _record(bare_root)
        before = render_consistency_audit(bare_root, as_of=_AS_OF)

        compliance = bare_root / ".shipwright" / "compliance"
        compliance.mkdir(parents=True)
        (compliance / "audit-report.md").write_text(
            "# Shipwright Detective Audit\n\nGenerated: 1999-01-01 00:00:00 UTC\n",
            encoding="utf-8",
        )
        (compliance / "audit-report.json").write_text(
            json.dumps({"findings": [{"status": "fail"}], "any_fail": True}),
            encoding="utf-8",
        )
        assert render_consistency_audit(bare_root, as_of=_AS_OF) == before

    def test_render_is_deterministic(self, bare_root: Path):
        _record(bare_root)
        assert (
            render_consistency_audit(bare_root, as_of=_AS_OF)
            == render_consistency_audit(bare_root, as_of=_AS_OF)
        )

    def test_block_ends_with_a_blank_line(self, bare_root: Path):
        """Section contract: the dashboard concatenates blocks verbatim."""
        for setup in (lambda r: None, _record):
            setup(bare_root)
            assert render_consistency_audit(bare_root, as_of=_AS_OF)[-1] == ""
