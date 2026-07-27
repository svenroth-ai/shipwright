"""Inherited failures are recorded as inherited (FR-01.13, trg-1aa5a8ab).

An onboarded codebase is not required to arrive perfect, only to arrive
honestly described. Two things must therefore be recorded at onboarding, and
kept apart:

* **failures that predate onboarding** — the accepted-baseline list the audit
  phase already reads (`shipwright_known_failures.json`), so a red test is
  attributable to the inherited codebase rather than to this project's work;
* **capabilities no test covers** — recorded beside it, and *never inside it*.

The separation is the load-bearing rule. `baseline_failure_count` is what
`rtm_generator` uses to turn a `passed < total` gap into `COVERED (baseline)`;
folding untested requirements or disabled tests into that number would let a
genuine future failure read as green. That is laundering, and it is exactly the
dishonesty this card exists to remove.

The observed-baseline INPUT (its validation, and the round-trip through the real
compliance consumer) lives in the sibling
``test_inherited_baseline_input.py`` — split only to keep both files under the
300-LOC cap.

@FR-01.13
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest  # noqa: E402

from lib.inherited_baseline import (  # noqa: E402
    REGISTER_REL,
    BaselineInputError,
    build_register,
    coverage_gaps,
    gap_triage,
    parse_observed_failures,
    write_register,
)

BACKFILL = {
    "auto_written": [{"test": "t1", "fr": "FR-01.01", "layer": "unit"}],
    "already_tagged": [{"test": "t2", "frs": ["FR-01.02"], "layer": "unit"}],
}
SKIPS = [
    {"file": "tests/test_a.py", "line": 4, "pattern": "pytest.mark.skip",
     "reason": "disabled", "language": "python"},
]


def make_register(**kw):
    """A register over three requirements, two of them covered by a tagged test."""
    base = dict(
        fr_ids=["FR-01.01", "FR-01.02", "FR-01.03"],
        backfill_report=BACKFILL,
        skip_inventory=SKIPS,
        observed=None,
        adopted_at="2026-07-27T00:00:00+00:00",
    )
    base.update(kw)
    return build_register(**base)


# --------------------------------------------------------------------------- #
# Coverage gaps — what has no test
# --------------------------------------------------------------------------- #

def test_a_requirement_with_no_tagged_test_is_an_inherited_gap() -> None:
    gaps = coverage_gaps(["FR-01.01", "FR-01.02", "FR-01.03"], BACKFILL, SKIPS)
    assert gaps["requirements_without_tests"] == ["FR-01.03"]


def test_both_tag_origins_count_as_coverage() -> None:
    """A tag the backfill wrote and a tag that was already there are equally
    real evidence — reading only one of them would invent gaps."""
    gaps = coverage_gaps(["FR-01.01", "FR-01.02"], BACKFILL, [])
    assert gaps["requirements_without_tests"] == []


def test_a_tag_pointing_at_an_unknown_requirement_is_not_coverage() -> None:
    """External review O6: a stale or mistyped `@FR` tag must not silently
    count as evidence for a requirement that does not exist in this catalogue."""
    stale = {"auto_written": [{"test": "t", "fr": "FR-99.99"}], "already_tagged": []}
    gaps = coverage_gaps(["FR-01.01"], stale, [])
    assert gaps["requirements_without_tests"] == ["FR-01.01"]


def test_disabled_tests_are_carried_verbatim() -> None:
    gaps = coverage_gaps(["FR-01.01"], BACKFILL, SKIPS)
    assert gaps["disabled_tests"] == SKIPS
    assert gaps["counts"]["disabled_tests"] == 1


def test_a_clean_repo_has_empty_gaps_not_a_crash() -> None:
    """External review G2: a repo with no backfill report and no skips is the
    normal zero-test case, not an error."""
    gaps = coverage_gaps([], {}, [])
    assert gaps == {"requirements_without_tests": [], "disabled_tests": [],
                    "counts": {"requirements_without_tests": 0, "disabled_tests": 0}}


# --------------------------------------------------------------------------- #
# The register — the shape the audit phase already reads
# --------------------------------------------------------------------------- #

def test_register_carries_the_two_keys_the_audit_phase_reads() -> None:
    reg = make_register()
    assert reg["known_failures"] == []
    assert reg["baseline_failure_count"] == 0


def test_an_unobserved_baseline_says_so_rather_than_claiming_clean() -> None:
    reg = make_register()
    assert reg["baseline_observed"] is False
    assert reg["baseline_source"] == "not_run"


def test_gaps_never_feed_the_number_that_excuses_failures() -> None:
    """The rule this module exists for. Three untested requirements and three
    disabled tests must leave `baseline_failure_count` at zero — that number
    buys forgiveness for a red run, and nothing unobserved may buy it."""
    reg = build_register(
        fr_ids=["FR-01.01", "FR-01.02", "FR-01.03"],
        backfill_report={}, skip_inventory=SKIPS * 3, observed=None,
        adopted_at="2026-07-27T00:00:00+00:00",
    )
    assert reg["inherited_coverage_gaps"]["counts"]["requirements_without_tests"] == 3
    assert reg["inherited_coverage_gaps"]["counts"]["disabled_tests"] == 3
    assert reg["baseline_failure_count"] == 0
    assert reg["known_failures"] == []


def test_an_observed_red_baseline_is_recorded_as_inherited() -> None:
    observed = parse_observed_failures({
        "source": "adopt baseline run",
        "command": "npx vitest run",
        "failing_tests": [
            {"test": "auth.spec.ts::login", "description": "pre-existing"},
            {"test": "cart.spec.ts::total", "count": 2},
        ],
    })
    reg = make_register(observed=observed)
    assert reg["baseline_observed"] is True
    assert reg["baseline_source"] == "adopt baseline run"   # the LABEL, not the command
    assert reg["baseline_failure_count"] == 3
    assert [f["test"] for f in reg["known_failures"]] == [
        "auth.spec.ts::login", "cart.spec.ts::total",
    ]


def test_an_observed_green_baseline_is_observed_and_empty() -> None:
    """A run that happened and found nothing is a different fact from a run that
    never happened — and the register must be able to say which."""
    observed = parse_observed_failures({
        "source": "adopt baseline run", "command": "pytest -q", "failing_tests": [],
    })
    reg = make_register(observed=observed)
    assert reg["baseline_observed"] is True
    assert reg["baseline_failure_count"] == 0


def test_register_is_schema_versioned_and_attributed() -> None:
    reg = make_register()
    assert reg["schema_version"] == 1
    assert reg["generated_by"] == "shipwright-adopt"
    assert reg["adopted_at"] == "2026-07-27T00:00:00+00:00"


def test_write_register_lands_at_the_path_the_consumer_looks_at(tmp_path: Path) -> None:
    path = write_register(tmp_path, make_register())
    assert path == tmp_path / REGISTER_REL
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_write_register_is_idempotent(tmp_path: Path) -> None:
    reg = make_register()
    first = write_register(tmp_path, reg).read_text(encoding="utf-8")
    assert write_register(tmp_path, reg).read_text(encoding="utf-8") == first


# --------------------------------------------------------------------------- #
# Gap follow-ups
# --------------------------------------------------------------------------- #

def test_each_non_empty_gap_class_leaves_a_follow_up() -> None:
    cards = gap_triage(make_register())
    keys = {c["dedup_key"] for c in cards}
    assert keys == {
        "adopt-inherited-gaps::requirements_without_tests",
        "adopt-inherited-gaps::disabled_tests",
    }
    assert all(c["kind"] == "maintenance" for c in cards)


def test_an_empty_gap_class_leaves_nothing_behind() -> None:
    reg = build_register(fr_ids=["FR-01.01"], backfill_report=BACKFILL,
                         skip_inventory=[], observed=None,
                         adopted_at="2026-07-27T00:00:00+00:00")
    assert gap_triage(reg) == []


def test_gap_card_dedup_keys_do_not_vary_with_the_count() -> None:
    """External review O5 — a re-adopt that finds one more disabled test must
    update nothing and duplicate nothing."""
    few = gap_triage(make_register())
    many = gap_triage(make_register(skip_inventory=SKIPS * 7))
    assert {c["dedup_key"] for c in few} == {c["dedup_key"] for c in many}


def test_gap_cards_describe_the_gap_without_pointing_at_a_failure() -> None:
    """A missing test is not a failing test. The card must not read as one, or
    the operator learns to treat inherited absence as inherited breakage."""
    for card in gap_triage(make_register()):
        assert "inherited" in card["detail"].lower()
        assert "fail" not in card["title"].lower()


# --------------------------------------------------------------------------- #
# The command is evidence, not payload (external code review, high)
# --------------------------------------------------------------------------- #

def test_the_command_never_reaches_the_committed_register() -> None:
    """A command line is exactly where a token or a home path rides along, and
    this register is committed at Step H. Whitelisting the failure entries while
    persisting the raw command beside them would have left the boundary open at
    the one field nobody was looking at."""
    observed = parse_observed_failures({
        "source": "adopt baseline run",
        "command": "TOKEN=hunter2 pytest --root /home/me/.ssh -q",
        "failing_tests": [{"test": "a::b"}],
    })
    blob = json.dumps(make_register(observed=observed))
    assert "hunter2" not in blob
    assert "/home/me/.ssh" not in blob
    assert "TOKEN" not in blob
    assert "adopt baseline run" in blob


@pytest.mark.parametrize("declared", [True, False, 1.0, "1", -1])
def test_a_declared_count_of_the_wrong_type_is_rejected(declared) -> None:
    """`True == 1` and `1.0 == 1` in Python, so a bare equality check accepts a
    boolean or a float as a declared count."""
    with pytest.raises(BaselineInputError, match="non-negative integer"):
        parse_observed_failures({
            "source": "s", "command": "c", "baseline_failure_count": declared,
            "failing_tests": [{"test": "a"}],
        })
