"""Tests for ``shared/scripts/tools/verifiers/_project_gate_extras_rollout.py``
— FR-01.02 #5 (``criteria_free_of_implementation_detail``) and #10
(``no_empty_split``), split out of ``test_project_gate_extras.py`` on
2026-09-12 alongside their own module split (`trg-9583d3a8`).

Rollout-unaware behaviour (no ``rollout=`` argument) is unchanged from the
pre-split module and its tests are carried over verbatim. The grace-path
tests below use a hand-built fake snapshot rather than a real git repo —
``criteria_free_of_implementation_detail``/``no_empty_split`` only ever call
``.spec_text(path)`` and ``.declared_split_names()`` on whatever they're
given (duck-typed, no ``isinstance`` check anywhere in the call chain), so a
plain fake exercises the exact same code path a real
``_project_gate_rollout_snapshot.RolloutSnapshot`` would, without paying for
a git repo per test. The git-backed resolution itself (which commit, what it
actually said) is covered separately in ``test_project_gate_rollout.py`` and
``test_project_gate_rollout_snapshot.py``.
"""

from __future__ import annotations

from tools.verifiers import _project_gate_extras_rollout as ext_rollout

_HEADER = "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"


def _row(fr_id: str, basis: str, *, name: str = "widget export", desc: str = "export widgets") -> str:
    return f"| {fr_id} | {name} | Must | {desc} | {basis} |\n"


class _FakeSnapshot:
    """Duck-types ``RolloutSnapshot``: a fixed mapping of path -> historical
    spec.md text, plus a fixed set of declared split names."""

    def __init__(self, texts: dict[str, str] | None = None, splits: frozenset[str] | None = None):
        self._texts = texts or {}
        self._splits = splits if splits is not None else frozenset()
        self.resolved = True

    def spec_text(self, rel_path: str) -> str | None:
        return self._texts.get(rel_path)

    def declared_split_names(self) -> frozenset[str]:
        return self._splits


# --------------------------------------------------------------------------- #
# criteria_free_of_implementation_detail — #5, rollout-unaware
# --------------------------------------------------------------------------- #


def test_criteria_free_of_implementation_detail_passes_on_clean_criteria():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given a signed-in customer, when they request an export, "
        "then a file download begins within five seconds.\n"
    )
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is True


def test_criteria_free_of_implementation_detail_fails_on_a_file_path():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given the handler in export_service.py, when it runs, "
        "then a file is written.\n"
    )
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "FR-01.01" in result.detail
    assert "file-path" in result.detail


def test_criteria_free_of_implementation_detail_fails_on_an_adr_reference():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given ADR-042 was accepted, when export runs, then it uses "
        "the chosen queue.\n"
    )
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "adr-number" in result.detail


def test_criteria_free_of_implementation_detail_fails_on_a_code_symbol():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given export_widget_batch runs, when it completes, then a "
        "receipt is written.\n"
    )
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "code-symbol" in result.detail


def test_criteria_free_of_implementation_detail_passes_when_no_criteria_anchored():
    """A row with no ``### FR-xx.yy`` criteria block at all yields no
    criteria to score — this check is not I6 (does an FR have criteria)."""
    text = _HEADER + _row("FR-01.01", "interview")
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is True


def test_criteria_free_of_implementation_detail_reads_the_real_bold_anchor_shape():
    """Round-trip probe (ADR-024): ``spec-generation.md``'s ACTUAL template
    anchors criteria with ``**FR-XX.YY: Name**`` + ``- [ ]`` checkboxes, not
    the ``### FR-xx.yy`` + ``- (E)`` shape every other fixture in this file
    uses — both are supported by ``fr_criteria``'s own regexes, but only this
    test pins the format the real producer emits, with a real ``Area`` column
    too."""
    text = (
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Auth | Password reset | Must | Let a user reset a "
        "forgotten password. | interview | unit |\n\n"
        "### Acceptance Criteria\n\n"
        "**FR-01.01: Password reset**\n"
        "- [ ] Given a user requests a reset, when they submit a valid "
        "email, then a reset link is sent.\n"
        "- [ ] Given the handler in reset_service.py runs, when it "
        "completes, then a token record is written.\n"
    )
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "FR-01.01" in result.detail
    assert "file-path" in result.detail


# --------------------------------------------------------------------------- #
# criteria_free_of_implementation_detail — #5, rollout-transition grace
# --------------------------------------------------------------------------- #


def test_criteria_free_of_implementation_detail_grants_grace_for_an_unchanged_pre_existing_criterion():
    """The exact criterion string already existed on the same row (same
    Name/body) at rollout — graced to a WARNING, ``strict_exempt``."""
    bad_criterion = (
        "- (E) Given the handler in export_service.py, when it runs, "
        "then a file is written.\n"
    )
    text = _HEADER + _row("FR-01.01", "interview") + "\n### FR-01.01\n" + bad_criterion
    rollout = _FakeSnapshot({"spec.md": text})
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text}, rollout=rollout)
    assert result.ok is False
    assert result.severity == "warning"
    assert result.strict_exempt is True
    assert "FR-01.01" in result.detail


def test_criteria_free_of_implementation_detail_new_violation_on_an_already_graced_row_stays_hard():
    """Per-criterion membership, not whole-row equality: an UNTOUCHED
    pre-existing violation on a row is graced, but a NEW violating criterion
    added to that same row since rollout is not — the row's identity
    matching must not blanket-grace every criterion on it."""
    old_bad = "- (E) Given the handler in export_service.py, when it runs, then a file is written.\n"
    new_bad = "- (E) Given ADR-042 was accepted, when export runs, then it uses the chosen queue.\n"
    rollout_text = _HEADER + _row("FR-01.01", "interview") + "\n### FR-01.01\n" + old_bad
    head_text = _HEADER + _row("FR-01.01", "interview") + "\n### FR-01.01\n" + old_bad + new_bad
    rollout = _FakeSnapshot({"spec.md": rollout_text})
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": head_text}, rollout=rollout)
    assert result.ok is False
    assert result.severity is None  # a hard hit remains, so no advisory downgrade
    assert "adr-number" in result.detail
    assert "granted transition grace" in result.detail  # the OLD hit is still disclosed
    # External code review (glm, low): the mixed branch used to summarize graced
    # hits as a bare COUNT, unlike no_empty_split's mixed branch which lists the
    # graced locations — the actual graced hit ("spec.md:FR-01.01 (...)") must be
    # named, not just counted, so a graced hit is never hidden behind a hard one.
    assert "spec.md:FR-01.01" in result.detail.split("granted transition grace")[1]


def test_criteria_free_of_implementation_detail_no_grace_for_a_repurposed_fr_id():
    """A row whose Name/body differ from the rollout row sharing the same id
    is a repurposed id, not the same requirement — no grace."""
    old_row = _row("FR-01.01", "interview", name="widget export", desc="export widgets")
    new_row = _row("FR-01.01", "interview", name="totally different capability", desc="something else")
    bad = "- (E) Given the handler in export_service.py, when it runs, then a file is written.\n"
    rollout_text = _HEADER + old_row + "\n### FR-01.01\n" + bad
    head_text = _HEADER + new_row + "\n### FR-01.01\n" + bad
    rollout = _FakeSnapshot({"spec.md": rollout_text})
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": head_text}, rollout=rollout)
    assert result.ok is False
    assert result.severity is None


def test_criteria_free_of_implementation_detail_no_grace_when_rollout_has_no_snapshot_for_the_path():
    text = _HEADER + _row("FR-01.01", "interview") + "\n### FR-01.01\n" + (
        "- (E) Given the handler in export_service.py, when it runs, then a file is written.\n"
    )
    rollout = _FakeSnapshot({})  # nothing at this path in the rollout snapshot
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text}, rollout=rollout)
    assert result.ok is False
    assert result.severity is None


def test_criteria_free_of_implementation_detail_no_grace_when_rollout_is_none():
    text = _HEADER + _row("FR-01.01", "interview") + "\n### FR-01.01\n" + (
        "- (E) Given the handler in export_service.py, when it runs, then a file is written.\n"
    )
    result = ext_rollout.criteria_free_of_implementation_detail({"spec.md": text}, rollout=None)
    assert result.ok is False
    assert result.severity is None


# --------------------------------------------------------------------------- #
# no_empty_split — #10, rollout-unaware
# --------------------------------------------------------------------------- #


def test_no_empty_split_passes_when_every_spec_has_a_row():
    texts = {
        "01-a/spec.md": _HEADER + _row("FR-01.01", "interview"),
        "02-b/spec.md": _HEADER + _row("FR-02.01", "code"),
    }
    result = ext_rollout.no_empty_split(texts)
    assert result.ok is True


def test_no_empty_split_fails_when_one_split_has_no_active_fr_row():
    texts = {
        "01-a/spec.md": _HEADER + _row("FR-01.01", "interview"),
        "02-b/spec.md": "# spec\n\nNothing here yet.\n",
    }
    result = ext_rollout.no_empty_split(texts)
    assert result.ok is False
    assert "02-b/spec.md" in result.detail
    assert "01-a/spec.md" not in result.detail


def test_no_empty_split_treats_a_removed_only_row_as_empty():
    text = (
        "## Removed Requirements\n\n" + _HEADER + _row("FR-01.01", "interview")
    )
    result = ext_rollout.no_empty_split({"01-a/spec.md": text})
    assert result.ok is False


# --------------------------------------------------------------------------- #
# no_empty_split — #10, rollout-transition grace
# --------------------------------------------------------------------------- #


def test_no_empty_split_grants_grace_for_a_split_declared_and_empty_at_rollout():
    texts = {".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n"}
    rollout = _FakeSnapshot(
        {".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n"},
        splits=frozenset({"01-a"}),
    )
    result = ext_rollout.no_empty_split(texts, rollout=rollout)
    assert result.ok is False
    assert result.severity == "warning"
    assert result.strict_exempt is True
    assert "01-a" in result.detail


def test_no_empty_split_no_grace_when_split_was_never_declared_at_rollout():
    """A split reusing an old, unrelated path must not inherit a stranger's
    grace merely because SOME file sat empty at that path historically —
    grace requires manifest DECLARATION, not path content."""
    texts = {".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n"}
    rollout = _FakeSnapshot(
        {".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n"},
        splits=frozenset(),  # NOT declared at rollout
    )
    result = ext_rollout.no_empty_split(texts, rollout=rollout)
    assert result.ok is False
    assert result.severity is None


def test_no_empty_split_no_grace_when_declared_split_had_rows_at_rollout():
    """Declared at rollout, but NOT empty then — the split went empty
    later, which is a regression, not a pre-existing condition to grandfather."""
    texts = {".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n"}
    rollout = _FakeSnapshot(
        {".shipwright/planning/01-a/spec.md": _HEADER + _row("FR-01.01", "interview")},
        splits=frozenset({"01-a"}),
    )
    result = ext_rollout.no_empty_split(texts, rollout=rollout)
    assert result.ok is False
    assert result.severity is None


def test_no_empty_split_mixed_hard_and_graced_reports_both():
    texts = {
        ".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n",  # declared+empty at rollout
        ".shipwright/planning/02-b/spec.md": "# spec\n\nNothing here yet.\n",  # never declared
    }
    rollout = _FakeSnapshot(
        {".shipwright/planning/01-a/spec.md": "# spec\n\nNothing here yet.\n"},
        splits=frozenset({"01-a"}),
    )
    result = ext_rollout.no_empty_split(texts, rollout=rollout)
    assert result.ok is False
    assert result.severity is None  # a hard hit (02-b) remains
    assert "02-b" in result.detail
    assert "granted transition grace" in result.detail
    assert "01-a" in result.detail
