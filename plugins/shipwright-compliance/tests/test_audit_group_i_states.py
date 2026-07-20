"""Group I says WHICH of the six no-rows states it hit (campaign S5).

Group I used to report one `skip` — "no FR rows found" — for every reason it
might have found none. That conflation is the shape of FV-2: zero rows read as
green, so a spec the reader could not understand was indistinguishable from a
repo that simply has no spec yet.

The state these tests exist for is ``no_canonical_ids``. S4's strict id rule
creates it, and ADR-107, S4's own mini-plan and ``frozen_bugs.py`` FV-1 each
cited S5's acceptance criterion as the mitigation for it — which it was not, as
originally written: in that route the spec IS on disk and the header IS
recognised, and only the ids fail, so a two-state check reports the benign answer
for the dangerous case.

@FR-01.10
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.audit import group_i
from scripts.audit.group_i_scan import (
    STATE_NO_CANONICAL_IDS,
    STATE_NO_FR_ROWS,
    STATE_NO_GOVERNING_HEADER,
    STATE_NO_SPEC,
    STATE_ROWS,
    STATE_ALL_ROWS_RETIRED,
    STATE_ROWS_TOO_NARROW,
)

HEADER = "| ID | Area | Name | Priority | Description | Basis | Layers |"
SEP = "|---|---|---|---|---|---|---|"


def _spec(root: Path, body: str, split: str = "01-adopted") -> Path:
    # Canonical fixture root: `.shipwright/planning/<split>/spec.md`. A bare
    # `tmp_path / "planning"` trips the artifact-path canon gate.
    d = root / ".shipwright" / "planning" / split
    d.mkdir(parents=True, exist_ok=True)
    path = d / "spec.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_no_spec_on_disk(tmp_path: Path) -> None:
    (tmp_path / ".shipwright" / "planning").mkdir(parents=True)
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_SPEC
    assert "no spec.md found" in scan.detail


def test_spec_present_but_nothing_fr_shaped(tmp_path: Path) -> None:
    _spec(tmp_path, "# Spec\n\nProse only, no table at all.\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_FR_ROWS
    assert "no FR-shaped rows" in scan.detail


def test_fr_ids_present_but_no_header_names_a_priority_column(tmp_path: Path) -> None:
    """The reader has no table to read the rows under, so it declines them all."""
    _spec(tmp_path, "| ID | Name |\n|---|---|\n| FR-01.01 | Login |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_GOVERNING_HEADER
    assert "no table header naming a Priority column" in scan.detail
    assert "FR-01.01" in scan.detail


def test_header_recognised_but_no_id_is_canonical(tmp_path: Path) -> None:
    """THE state this AC was amended for.

    ``generate_adoption_artifacts`` emits ``FR-01.{i:02d}`` uncapped, so an
    adopted repo with more than 99 detected routes emits ``FR-01.100`` — a
    well-formed table whose every row is declined. Reported as "no requirements"
    before S5.
    """
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.100 | Adopted | A | Must | x | code | unit (inferred) |\n"
          "| FR-1.1 | Adopted | B | Must | y | code | unit (inferred) |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_CANONICAL_IDS
    assert "no row id is canonical FR-XX.YY" in scan.detail
    assert "FR-01.100" in scan.detail


def test_canonical_ids_in_rows_too_narrow_for_their_header(tmp_path: Path) -> None:
    """A width problem must not be reported as an id problem.

    Both `non_canonical_id` and `row_narrower_than_header` carry
    `header_seen=True`, so an earlier cut that branched on that flag alone told
    the operator "fix the ids (two digits either side)" about `FR-01.01` — an id
    that is already canonical. Naming the wrong cause is the same defect class
    as naming none, which is what this module exists to remove.
    """
    _spec(tmp_path, f"{HEADER}\n{SEP}\n| FR-01.01 | Adopted | Login |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_ROWS_TOO_NARROW
    assert "wide enough to reach the Priority column" in scan.detail
    assert "FR-01.01" in scan.detail
    # The misdiagnosis this test exists to prevent.
    assert "canonical FR-XX.YY" not in scan.detail


def test_a_noncanonical_id_with_no_header_is_a_header_problem(tmp_path: Path) -> None:
    """Rule 3 checks the reason AND the header together, so this falls to rule 5.

    Characterization pin, not a regression test: this input classified the same
    way before the reason-based branch, because there was no header to see. It
    is here to stop the pairing being "simplified" away, not because it ever
    misbehaved.
    """
    _spec(tmp_path, "| ID | Name |\n|---|---|\n| FR-1.1 | Login |\n")
    assert group_i.scan_specs(tmp_path).state == STATE_NO_GOVERNING_HEADER


def test_an_all_retired_spec_is_not_reported_as_having_no_rows(tmp_path: Path) -> None:
    """`no_fr_rows` says "contains no FR-shaped rows" — false about this file.

    The rows exist and parse; they are simply all retired. Nothing is broken, so
    the repair is different from every other no-rows state, and reporting the
    generic one is the wrong-cause defect again.
    """
    _spec(tmp_path, "# Spec\n\n### Removed Requirements\n\n"
          f"{HEADER}\n{SEP}\n"
          "| FR-01.01 | Adopted | Login | Must | Users sign in | code | unit (inferred) |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_ALL_ROWS_RETIRED
    assert scan.retired_count == 1
    assert "every FR row sits under" in scan.detail
    assert "no FR-shaped rows" not in scan.detail


def test_a_live_row_beside_retired_ones_is_the_normal_state(tmp_path: Path) -> None:
    """Only an ENTIRELY retired spec is special; one live row is business as usual."""
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.01 | Adopted | Login | Must | Users sign in | code | unit (inferred) |\n"
          "\n### Removed Requirements\n\n"
          f"{HEADER}\n{SEP}\n"
          "| FR-01.02 | Adopted | Old | Must | Retired thing | code | unit (inferred) |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_ROWS
    assert [r.id for r in scan.rows] == ["FR-01.01"]
    assert scan.retired_count == 1


def test_a_broken_table_outranks_an_all_retired_one(tmp_path: Path) -> None:
    """A parse failure is a repair; a retirement is not, so rules 3-5 win."""
    _spec(tmp_path, "# Spec\n\n### Removed Requirements\n\n"
          f"{HEADER}\n{SEP}\n"
          "| FR-01.01 | Adopted | Old | Must | Retired | code | unit (inferred) |\n",
          split="01-a")
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.100 | A | B | Must | x | code | unit (inferred) |\n", split="02-b")
    assert group_i.scan_specs(tmp_path).state == STATE_NO_CANONICAL_IDS


def test_the_declined_list_quotes_only_the_ids_of_the_deciding_reason(tmp_path: Path) -> None:
    """Mixed reject reasons must not pool into one explanation.

    A spec with BOTH a non-canonical id and a too-narrow canonical row used to
    emit "no row id is canonical FR-XX.YY ... fix the ids; declined: FR-01.01,
    FR-01.100" — and FR-01.01 is canonical, its problem is width. Same
    wrong-cause defect the state machine exists to remove, one field over.
    """
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.100 | A | B | Must | x | code | unit (inferred) |\n"
          "| FR-01.01 | Adopted | Login |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_CANONICAL_IDS
    assert "FR-01.100" in scan.detail          # the id that DID decide the state
    assert "FR-01.01" not in scan.detail       # canonical; its problem is width
    # "every row was declined" is false here, and must not be claimed.
    assert "every row was declined" not in scan.detail
    assert "other rows were declined for other reasons" in scan.detail
    # Nor may the SURVIVING clause make the same universal claim in other words:
    # "no row id is canonical" is equally false when some rows failed on width.
    assert "no row id is canonical" not in scan.detail
    assert "some row ids are not canonical" in scan.detail


def test_the_catch_all_state_still_names_the_rows_it_declined(tmp_path: Path) -> None:
    """Narrowing attribution must not COST attribution.

    `no_governing_header` is the rule-5 catch-all, reached by any leftover
    reject — including a `non_canonical_id` one whose `header_seen` was False.
    Filtering its ids to the single like-named reason matched nothing, so the
    state silently stopped naming any id, in the module whose entire purpose is
    naming the cause.
    """
    _spec(tmp_path, "| ID | Name |\n|---|---|\n| FR-1.1 | Login |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_GOVERNING_HEADER
    assert "declined: FR-1.1" in scan.detail


def test_the_catch_all_never_claims_rows_it_did_not_list(tmp_path: Path) -> None:
    """For the catch-all, the id list is COMPLETE, so the "others" suffix lies.

    `_STATE_REASON[no_governing_header] is None` means every reject is quoted.
    The suffix is gated on `mixed`, which is True here because the two rows fail
    for different reasons — so the detail listed both and then promised further
    rows that do not exist. The previous test cannot see this: its fixture has
    ONE reject reason, so `mixed` is False and the suffix never renders.
    """
    _spec(tmp_path, "| ID | Name |\n|---|---|\n"
                    "| FR-1.1 | Login |\n| FR-01.02 | Logout |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_NO_GOVERNING_HEADER
    # Both are named -- the list really is complete...
    assert "FR-1.1" in scan.detail
    assert "FR-01.02" in scan.detail
    # ...so it must not claim there are others.
    assert "other rows were declined for other reasons" not in scan.detail


def test_a_recognised_header_outranks_a_missing_one(tmp_path: Path) -> None:
    """Precedence, decided from raw parse facts so one input cannot classify two
    ways: the well-formed table with unusable ids is the more specific and more
    actionable finding, and the one that would otherwise stay hidden."""
    _spec(tmp_path, "| ID | Name |\n|---|---|\n| FR-01.01 | Login |\n", split="01-a")
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.100 | A | B | Must | x | code | unit (inferred) |\n", split="02-b")
    assert group_i.scan_specs(tmp_path).state == STATE_NO_CANONICAL_IDS


def test_a_readable_table_is_the_normal_state(tmp_path: Path) -> None:
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.01 | Adopted | Login | Must | Users sign in | code | unit (inferred) |\n")
    scan = group_i.scan_specs(tmp_path)
    assert scan.state == STATE_ROWS
    assert [r.id for r in scan.rows] == ["FR-01.01"]


@pytest.mark.parametrize("body,fragment", [
    ("# Spec\n\nProse only.\n", "no FR-shaped rows"),
    ("| ID | Name |\n|---|---|\n| FR-01.01 | Login |\n", "Priority column"),
    (f"{HEADER}\n{SEP}\n| FR-01.100 | A | B | Must | x | code | unit (inferred) |\n",
     "canonical FR-XX.YY"),
])
def test_every_state_still_skips_but_says_which(tmp_path: Path, body: str, fragment: str) -> None:
    """Detective-only: a repo without requirements must not redden CI. What
    changed is the detail, never the verdict."""
    _spec(tmp_path, body)
    findings = group_i.run(tmp_path, None, None)
    assert {f.status for f in findings} == {"skip"}
    assert all(fragment in f.detail for f in findings)


def test_scan_fr_rows_keeps_its_pre_s5_signature(tmp_path: Path) -> None:
    """The projection existing callers use is unchanged."""
    _spec(tmp_path, f"{HEADER}\n{SEP}\n"
          "| FR-01.01 | Adopted | Login | Must | Users sign in | code | unit (inferred) |\n")
    rows = group_i.scan_fr_rows(tmp_path)
    assert [r.id for r in rows] == ["FR-01.01"]
