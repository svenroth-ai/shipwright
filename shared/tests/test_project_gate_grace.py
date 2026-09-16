"""Tests for ``shared/scripts/tools/verifiers/_project_gate_grace.py`` — the
pure comparator helpers behind the FR-01.02 #5/#10 rollout-transition grace
(`trg-9583d3a8`). Constructs ``FrTableRow`` fixtures directly rather than
parsing markdown, since these functions' own contract (identity matching,
membership) is what's under test, not the table reader.
"""

from __future__ import annotations

from tools.verifiers import _project_gate_grace as grace


def _row(id_: str = "FR-01.01", name: str = "", text: str = "a capability"):
    from lib.fr_table_reader import FrTableRow
    return FrTableRow(
        id=id_, name=name, text=text, priority="Must",
        text_from_named_col=True, layers_cell="", layers_from_named_col=False,
        status="active", cells=(), lineno=0,
    )


class _FakeSnapshot:
    def __init__(self, texts: dict[str, str] | None = None, splits: frozenset[str] | None = None):
        self._texts = texts or {}
        self._splits = splits if splits is not None else frozenset()
        self.resolved = True

    def spec_text(self, rel_path: str) -> str | None:
        return self._texts.get(rel_path)

    def declared_split_names(self) -> frozenset[str]:
        return self._splits


# --------------------------------------------------------------------------- #
# norm_title
# --------------------------------------------------------------------------- #


def test_norm_title_ignores_whitespace_and_case_differences():
    assert grace.norm_title("Widget  Export") == grace.norm_title("widget export")
    assert grace.norm_title("  Widget Export  ") == grace.norm_title("Widget Export")


def test_norm_title_distinguishes_genuinely_different_titles():
    assert grace.norm_title("Widget Export") != grace.norm_title("Gadget Import")


# --------------------------------------------------------------------------- #
# graced_criteria_for_row (exercises _row_identity_matches internally)
# --------------------------------------------------------------------------- #

_SPEC_TEXT = (
    "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
    "| FR-01.01 | widget export | Must | export widgets | interview |\n\n"
    "### FR-01.01\n"
    "- (E) Given the handler in export_service.py runs, then a file is written.\n"
    "- (E) Given a signed-in user, then export begins.\n"
)


def test_graced_criteria_for_row_returns_empty_set_when_rollout_is_none():
    row = _row(name="widget export", text="export widgets")
    assert grace.graced_criteria_for_row(None, "spec.md", row) == frozenset()


def test_graced_criteria_for_row_returns_empty_set_when_path_absent_from_rollout():
    row = _row(name="widget export", text="export widgets")
    rollout = _FakeSnapshot({})
    assert grace.graced_criteria_for_row(rollout, "spec.md", row) == frozenset()


def test_graced_criteria_for_row_returns_empty_set_when_row_id_absent_at_rollout():
    row = _row(id_="FR-99.99", name="widget export", text="export widgets")
    rollout = _FakeSnapshot({"spec.md": _SPEC_TEXT})
    assert grace.graced_criteria_for_row(rollout, "spec.md", row) == frozenset()


def test_graced_criteria_for_row_returns_the_rollout_criteria_when_identity_matches():
    row = _row(name="widget export", text="export widgets")
    rollout = _FakeSnapshot({"spec.md": _SPEC_TEXT})
    graced = grace.graced_criteria_for_row(rollout, "spec.md", row)
    assert any("export_service.py" in c for c in graced)
    assert any("signed-in user" in c for c in graced)


def test_graced_criteria_for_row_ignores_cosmetic_title_rewording():
    row = _row(name="  Widget  EXPORT ", text="export widgets")
    rollout = _FakeSnapshot({"spec.md": _SPEC_TEXT})
    graced = grace.graced_criteria_for_row(rollout, "spec.md", row)
    assert graced  # cosmetic whitespace/case difference must not forfeit the match


def test_graced_criteria_for_row_refuses_a_repurposed_id_with_a_different_title():
    row = _row(name="totally different capability", text="something else entirely")
    rollout = _FakeSnapshot({"spec.md": _SPEC_TEXT})
    assert grace.graced_criteria_for_row(rollout, "spec.md", row) == frozenset()


def test_graced_criteria_for_row_refuses_when_both_sides_have_no_name_and_no_text():
    """Identity must never default to 'matches' when it is unverifiable —
    both name and text empty on either side refuses the match outright."""
    unnamed_spec = (
        "| ID | Priority | Description | Basis |\n|---|---|---|---|\n"
        "| FR-01.01 | Must |  | interview |\n\n"
        "### FR-01.01\n- (E) Given export_service.py runs, then done.\n"
    )
    row = _row(name="", text="")
    rollout = _FakeSnapshot({"spec.md": unnamed_spec})
    assert grace.graced_criteria_for_row(rollout, "spec.md", row) == frozenset()


# --------------------------------------------------------------------------- #
# split_name_from_path
# --------------------------------------------------------------------------- #


def test_split_name_from_path_extracts_the_split_directory():
    assert grace.split_name_from_path(".shipwright/planning/01-a/spec.md") == "01-a"


def test_split_name_from_path_is_os_separator_agnostic():
    assert grace.split_name_from_path(".shipwright\\planning\\01-a\\spec.md") == "01-a"


def test_split_name_from_path_returns_none_for_an_unrelated_path():
    assert grace.split_name_from_path("some/other/path/spec.md") is None


def test_split_name_from_path_returns_none_for_a_too_short_path():
    assert grace.split_name_from_path(".shipwright/planning") is None


# --------------------------------------------------------------------------- #
# split_predates_rollout
# --------------------------------------------------------------------------- #


def test_split_predates_rollout_false_when_rollout_is_none():
    assert grace.split_predates_rollout(None, "path", "01-a") is False


def test_split_predates_rollout_false_when_name_is_none():
    rollout = _FakeSnapshot(splits=frozenset({"01-a"}))
    assert grace.split_predates_rollout(rollout, "path", None) is False


def test_split_predates_rollout_false_when_not_declared_at_rollout():
    rollout = _FakeSnapshot({"path": "# spec\n"}, splits=frozenset())
    assert grace.split_predates_rollout(rollout, "path", "01-a") is False


def test_split_predates_rollout_true_when_declared_and_never_written_yet():
    """Declared at rollout, but no spec.md text there yet — vacuously empty."""
    rollout = _FakeSnapshot({}, splits=frozenset({"01-a"}))
    assert grace.split_predates_rollout(rollout, "path", "01-a") is True


def test_split_predates_rollout_true_when_declared_and_empty_at_rollout():
    rollout = _FakeSnapshot({"path": "# spec\n\nNothing here yet.\n"}, splits=frozenset({"01-a"}))
    assert grace.split_predates_rollout(rollout, "path", "01-a") is True


def test_split_predates_rollout_false_when_declared_but_had_rows_at_rollout():
    text = (
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n"
    )
    rollout = _FakeSnapshot({"path": text}, splits=frozenset({"01-a"}))
    assert grace.split_predates_rollout(rollout, "path", "01-a") is False
