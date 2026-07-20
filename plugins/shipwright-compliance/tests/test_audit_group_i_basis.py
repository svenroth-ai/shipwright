"""I5 — the ``Basis`` vocabulary check (campaign S5, SPEC §3.2).

Asymmetric by design: a value outside the vocabulary FAILS (a typo is not a
special case), ``other`` never fails (an escape hatch that blocks is not one),
and a spec with no ``Basis`` column is skipped rather than scored — so adopting
the column is not a breaking change for the specs that predate it.

@FR-01.10
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit import group_i

HEADER = "| ID | Area | Name | Priority | Description | Basis | Layers |"
SEP = "|---|---|---|---|---|---|---|"
LEGACY_HEADER = "| ID | Name | Priority | Description | Source |"


def _spec(root: Path, body: str) -> None:
    d = root / ".shipwright" / "planning" / "01-adopted"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")


def _i5(root: Path):
    return next(f for f in group_i.run(root, None, None) if f.check_id == "I5")


def _row(fr_id: str, basis: str) -> str:
    return f"| {fr_id} | Adopted | Login | Must | Users sign in | {basis} | unit (inferred) |"


def test_known_values_pass(tmp_path: Path) -> None:
    _spec(tmp_path, "\n".join([HEADER, SEP, _row("FR-01.01", "code"),
                               _row("FR-01.02", "interview")]) + "\n")
    finding = _i5(tmp_path)
    assert finding.status == "pass"
    assert "no malformed" in finding.detail


def test_a_malformed_value_fails_and_names_the_requirement(tmp_path: Path) -> None:
    _spec(tmp_path, "\n".join([HEADER, SEP, _row("FR-01.01", "enrichment.json")]) + "\n")
    finding = _i5(tmp_path)
    assert finding.status == "fail"
    assert "FR-01.01" in finding.detail
    assert finding.suggested_iterate_cmd


def test_other_is_advisory_and_never_fails(tmp_path: Path) -> None:
    _spec(tmp_path, "\n".join([HEADER, SEP,
                               _row("FR-01.01", "other: vendor questionnaire")]) + "\n")
    finding = _i5(tmp_path)
    assert finding.status == "pass"
    assert "advisory" in finding.detail
    assert "FR-01.01" in finding.detail


def test_a_bare_other_is_still_only_advisory_but_says_so(tmp_path: Path) -> None:
    _spec(tmp_path, "\n".join([HEADER, SEP, _row("FR-01.01", "other")]) + "\n")
    finding = _i5(tmp_path)
    assert finding.status == "pass"
    assert "no reason given" in finding.detail


def test_a_blank_cell_under_a_declared_column_fails(tmp_path: Path) -> None:
    """Declaring the column is opting in; every row then answers.

    `assumed` is always available as the honest answer, so a blank cell is a row
    that declined to answer a required question rather than a row with nothing
    to say. Note the asymmetry with the test below: a spec with NO Basis column
    is skipped entirely — it is the declaration that creates the obligation.
    """
    _spec(tmp_path, "\n".join([HEADER, SEP, _row("FR-01.01", "  ")]) + "\n")
    finding = _i5(tmp_path)
    assert finding.status == "fail"
    assert "FR-01.01" in finding.detail
    assert "assumed" in finding.detail


def test_a_spec_without_a_basis_column_is_skipped_not_scored(tmp_path: Path) -> None:
    """The legacy `Source` cell holds a file path and never claimed to be a
    basis. Scoring it would fail every already-adopted repo on its own history."""
    _spec(tmp_path, "\n".join([
        LEGACY_HEADER, "|---|---|---|---|---|",
        "| FR-01.01 | Login | Must | Users sign in | enrichment.json |",
    ]) + "\n")
    finding = _i5(tmp_path)
    assert finding.status == "skip"
    assert "no Basis column" in finding.detail


def test_a_malformed_value_does_not_redden_the_other_checks(tmp_path: Path) -> None:
    """I5 is its own verdict; the advisory prose checks stay advisory."""
    _spec(tmp_path, "\n".join([HEADER, SEP, _row("FR-01.01", "nonsense")]) + "\n")
    findings = {f.check_id: f for f in group_i.run(tmp_path, None, None)}
    assert findings["I5"].status == "fail"
    assert findings["I1"].status != "fail"
    assert findings["I2"].status != "fail"
    assert findings["I3"].status != "fail"
