"""The dashboard's OWN ignore-file parser, and its agreement with the gate's.

Split out of ``test_accepted_risk_view.py`` when that file crossed the 300-line
cap. That file owns correlation, degradation and rendering; this one owns
reading ``.trivyignore*`` — the same division the shared side makes between
``test_accepted_risks_register.py`` (the gate) and ``test_accepted_risk_scan.py``
(discovery).

The subject here is a deliberate duplication. ``accepted_risk_view`` keeps its
own copy of the flat-form parser because it must stay importable with no
``shared/scripts`` on ``sys.path`` (ADR-045), so nothing but a test can hold the
two copies equal. They drifted exactly once — this parser took the whole line as
the id while the shared reader took the first field — and the dashboard rendered
two rows for one suppression until
``iterate-2026-07-31-accepted-risk-gate-holes`` caught it.

The two answer deliberately DIFFERENT questions about expiry, which is why the
pin is a subset relation rather than equality:

* the gate asks *"what is Trivy suppressing right now?"* — a lapsed entry is gone;
* the dashboard asks *"what acceptances exist, and in what state?"* — a lapsed
  entry stays, flagged ``EXPIRED - re-review``.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.lib.accepted_risk_view import accepted_risk_rows, parse_trivyignore

_NOW = date(2026, 6, 28)


def _shared_reader():
    """The gate's own reader, or skip — this test exists to compare the two."""
    import scripts.lib.accepted_risk_view as view

    shared = view._load_shared()
    assert shared is not None, (
        "the shared reader must be importable here; without it this file "
        "silently stops comparing anything"
    )
    return shared[1]


# ---------------------------------------------------------------------------
# The anti-drift pin
# ---------------------------------------------------------------------------

#: (line, id this parser must yield, expiry it must read).  ``None`` id means
#: "no entry at all". Every row is fed to BOTH parsers below.
_FLAT_CASES = [
    ("CVE-A exp:2099-01-01", "CVE-A", "2099-01-01"),
    ("CVE-B", "CVE-B", None),
    ("CVE-C exp:2020-01-01", "CVE-C", "2020-01-01"),
    ("CVE-D\texp:2099-01-01", "CVE-D", "2099-01-01"),      # tab-separated
    ("CVE-E exp:", "CVE-E", ""),                            # exp: with no date
    ("CVE-F exp:2099-01-01 exp:2020-01-01", "CVE-F", "2099-01-01"),  # first wins
    ("CVE-G  # trailing comment", "CVE-G", None),
    ("# a whole-line comment", None, None),
    ("", None, None),
    ("   ", None, None),
]


@pytest.mark.parametrize("line,expected_id,expected_expiry", _FLAT_CASES)
def test_flat_line_parses_to_its_id_and_expiry(
        tmp_path, line, expected_id, expected_expiry):
    (tmp_path / ".trivyignore").write_text(line + "\n", encoding="utf-8")
    entries = parse_trivyignore(tmp_path)
    if expected_id is None:
        assert entries == [], f"{line!r} is not an entry"
        return
    assert [e["id"] for e in entries] == [expected_id]
    assert entries[0]["expired_at"] == expected_expiry


@pytest.mark.parametrize("line,expected_id,_expiry", _FLAT_CASES)
def test_both_parsers_agree_on_the_id(tmp_path, line, expected_id, _expiry):
    """Same input, same id — the invariant that stops the copies drifting.

    Compared at a date before every fixture expiry, so expiry semantics (where
    the two intentionally differ) cannot mask an id-spelling disagreement.
    """
    (tmp_path / ".trivyignore").write_text(line + "\n", encoding="utf-8")
    early = date(2019, 1, 1)
    mine = {e["id"] for e in parse_trivyignore(tmp_path)}
    theirs = _shared_reader().read_trivyignore_ids(tmp_path, now=early)
    assert mine == theirs == (set() if expected_id is None else {expected_id})


def test_the_two_differ_only_by_dropping_lapsed_entries(tmp_path):
    """The one intended divergence, stated as a subset relation plus its cause."""
    (tmp_path / ".trivyignore").write_text(
        "CVE-A exp:2099-01-01\nCVE-B\nCVE-C exp:2020-01-01\n", encoding="utf-8")
    mine = {e["id"] for e in parse_trivyignore(tmp_path)}
    theirs = _shared_reader().read_trivyignore_ids(tmp_path, now=_NOW)
    assert theirs == {"CVE-A", "CVE-B"}, "the gate drops the lapsed entry"
    assert mine == {"CVE-A", "CVE-B", "CVE-C"}, "the dashboard keeps it"
    assert mine - theirs == {"CVE-C"}, (
        "the ONLY permitted difference is a lapsed entry; anything else is drift")


# ---------------------------------------------------------------------------
# Rendering consequences of the above
# ---------------------------------------------------------------------------


def test_a_flat_entry_with_an_expiry_renders_exactly_one_row(tmp_path):
    (tmp_path / ".trivyignore").write_text("CVE-X exp:2099-01-01\n", encoding="utf-8")
    rows, _ = accepted_risk_rows(tmp_path, now=_NOW)
    assert [r["id"] for r in rows] == ["CVE-X"]


def test_a_lapsed_flat_entry_is_flagged_expired(tmp_path):
    (tmp_path / ".trivyignore").write_text("CVE-Y exp:2020-01-01\n", encoding="utf-8")
    rows, _ = accepted_risk_rows(tmp_path, now=_NOW)
    assert [(r["id"], r["expires"], r["expired"]) for r in rows] == [
        ("CVE-Y", "2020-01-01", True)]


def test_on_its_lapse_date_the_dashboard_agrees_with_the_gate(tmp_path):
    """A Trivy date takes Trivy's boundary rule, not the register's.

    The gate stops counting the suppression FROM ``expired_at`` (Trivy parses
    the date to midnight). Rendering ``expired`` with the register's ``<`` rule
    made the dashboard say "not expired" for exactly the one day the gate had
    already dropped it — the day the flag matters most.
    """
    (tmp_path / ".trivyignore.yaml").write_text(
        "vulnerabilities:\n  - id: CVE-Z\n    expired_at: 2026-06-22\n",
        encoding="utf-8")
    on_the_day, _ = accepted_risk_rows(tmp_path, now=date(2026, 6, 22))
    day_before, _ = accepted_risk_rows(tmp_path, now=date(2026, 6, 21))
    assert on_the_day[0]["expired"] is True
    assert day_before[0]["expired"] is False


# ---------------------------------------------------------------------------
# Forms and precedence
# ---------------------------------------------------------------------------


def test_classic_flat_file_is_read(tmp_path):
    (tmp_path / ".trivyignore").write_text(
        "# comment\nCVE-2026-1\n\nCVE-2026-2\n", encoding="utf-8")
    assert {e["id"] for e in parse_trivyignore(tmp_path)} == {
        "CVE-2026-1", "CVE-2026-2"}


def test_yaml_form_carries_scope(tmp_path):
    (tmp_path / ".trivyignore.yaml").write_text(
        'vulnerabilities:\n  - id: CVE-2026-54285\n    paths: ["a/b"]\n'
        "    expired_at: 2026-12-22\n    statement: x\n", encoding="utf-8")
    assert parse_trivyignore(tmp_path)[0]["scope"] == ["a/b"]


def test_missing_file_is_empty(tmp_path):
    assert parse_trivyignore(tmp_path) == []


# ---------------------------------------------------------------------------
# The YAML branch is duplicated too — and it is the form this repo actually uses
# ---------------------------------------------------------------------------

_YAML_FIXTURE = (
    "vulnerabilities:\n"
    "  - id: CVE-LIVE\n    paths: [\"a/b\"]\n    expired_at: 2099-01-01\n"
    "  - id: CVE-LAPSED\n    expired_at: 2020-01-01\n"
    "  - id: CVE-FOREVER\n"
    "  - paths: [\"no-id\"]\n"
)


def test_yaml_form_ids_agree_with_the_shared_reader(tmp_path):
    """The flat pin above covers only half the duplication.

    Both modules parse the YAML form independently as well, and that is the
    form this repo, the docs and every example use. Compared at a date before
    every fixture expiry so the intended expiry divergence cannot mask an
    id-level disagreement (e.g. an added section, or a changed id-truthiness
    guard on one side only).
    """
    (tmp_path / ".trivyignore.yaml").write_text(_YAML_FIXTURE, encoding="utf-8")
    early = date(2019, 1, 1)
    mine = {e["id"] for e in parse_trivyignore(tmp_path)}
    theirs = _shared_reader().read_trivyignore_ids(tmp_path, now=early)
    assert mine == theirs == {"CVE-LIVE", "CVE-LAPSED", "CVE-FOREVER"}, (
        "an entry without an id must be skipped by BOTH, and no other id may "
        "appear in one parser and not the other")


def test_yaml_form_expiries_agree_with_the_shared_readers_filter(tmp_path):
    (tmp_path / ".trivyignore.yaml").write_text(_YAML_FIXTURE, encoding="utf-8")
    mine = {e["id"]: e["expired_at"] for e in parse_trivyignore(tmp_path)}
    assert mine["CVE-FOREVER"] is None
    theirs = _shared_reader().read_trivyignore_ids(tmp_path, now=_NOW)
    assert theirs == {"CVE-LIVE", "CVE-FOREVER"}, "only the lapsed one is dropped"


def test_a_duplicate_id_folds_onto_the_latest_expiry(tmp_path):
    """Trivy repeats an id to scope it per path; the row must not lapse early.

    Last-wins let a narrow, already-lapsed entry render the whole id as EXPIRED
    while a sibling was still suppressing — the dashboard asserting a
    suppression had expired while it was in force.
    """
    (tmp_path / ".trivyignore.yaml").write_text(
        "vulnerabilities:\n"
        "  - id: CVE-DUP\n    paths: [\"a\"]\n    expired_at: 2099-01-01\n"
        "  - id: CVE-DUP\n    paths: [\"b\"]\n    expired_at: 2020-01-01\n",
        encoding="utf-8")
    rows, _ = accepted_risk_rows(tmp_path, now=_NOW)
    assert [r["id"] for r in rows] == ["CVE-DUP"], "one id, one row"
    assert rows[0]["expires"] == "2099-01-01"
    assert rows[0]["expired"] is False, (
        "a sibling entry still suppresses this id; calling it expired "
        "contradicts the gate, which still counts it as live")


def test_an_undated_duplicate_never_lapses(tmp_path):
    (tmp_path / ".trivyignore.yaml").write_text(
        "vulnerabilities:\n"
        "  - id: CVE-DUP\n    expired_at: 2020-01-01\n"
        "  - id: CVE-DUP\n",
        encoding="utf-8")
    rows, _ = accepted_risk_rows(tmp_path, now=_NOW)
    assert rows[0]["expired"] is False and rows[0]["expires"] == ""


def test_the_views_date_parser_matches_the_shared_one(tmp_path):
    """The third copy. ``_coerce_date`` is duplicated here for the same ADR-045
    reason as the parsers, and it is load-bearing for the new ``<=`` boundary —
    so it needs the same pin."""
    from datetime import datetime

    import scripts.lib.accepted_risk_view as view
    from scripts.lib.accepted_risk_view import _coerce_date

    accepted_risks = view._load_shared()[0]
    for value in (
        date(2026, 12, 22), datetime(2026, 12, 22, 8, 30), "2026-12-22",
        "2026-12-22T00:00:00Z", "not-a-date", None, 12345, "",
    ):
        assert _coerce_date(value) == accepted_risks.coerce_date(value), value
