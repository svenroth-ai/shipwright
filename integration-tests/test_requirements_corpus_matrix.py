"""The golden matrix: every target x every fixture, pinned against ``golden.json``.

Campaign "Requirements Catalog" sub-iterate S1. Steps S2-S4 rewrite the
discovery and parsing machinery and claim to be behaviour-preserving. This test
is what makes that claim falsifiable: when S2 lands, the reviewer reads a git
diff of ONE file and every changed line is a behaviour change that must be
explained.

**There is deliberately no ``--update-golden`` flag.** Regeneration is
``uv run integration-tests/requirements_corpus/regen_golden.py``. A pytest flag
would let anyone rerun-to-green the moment this harness goes red, which would
make S2 self-certifying and destroy the only guarantee the corpus provides.

@FR-01.10
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from requirements_corpus.collect import SCHEMA_VERSION, collect_all, dumps  # noqa: E402
from requirements_corpus.corpus_data import FIXTURE_NAMES  # noqa: E402
from requirements_corpus.frozen_bugs import as_json_block  # noqa: E402
from requirements_corpus.registry import TARGETS  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parent / "requirements_corpus" / "golden.json"
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def golden() -> dict:
    if not GOLDEN_PATH.exists():
        pytest.fail(
            "golden.json is missing. Generate it with:\n"
            "  uv run integration-tests/requirements_corpus/regen_golden.py"
        )
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh() -> dict:
    """Collect the live behaviour once -- one subprocess per realm."""
    return collect_all()


# ---------------------------------------------------------------------------
# The matrix itself
# ---------------------------------------------------------------------------

def test_golden_schema_version_matches():
    """A schema bump must be deliberate -- it invalidates every cell below."""
    golden_doc = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert golden_doc["schema_version"] == SCHEMA_VERSION


def test_every_target_and_fixture_has_a_cell(fresh):
    """No target may quietly drop out of the matrix."""
    collected = fresh["targets"]
    assert set(collected) == {t["id"] for t in TARGETS}
    for tid, entry in collected.items():
        if entry["kind"] != "invoked":
            continue
        assert set(entry["fixtures"]) == set(FIXTURE_NAMES), tid


def test_no_target_failed_to_import(fresh):
    """An import error must never read as 'no findings'.

    A realm that fails to load would produce an empty result set, and empty
    reads as green almost everywhere in this plane (that is FV-2). Fail loudly.
    """
    broken = {
        tid: entry for tid, entry in fresh["targets"].items()
        if entry["kind"] == "import_error"
    }
    assert not broken, f"targets failed to import: {json.dumps(broken, indent=2)}"


@pytest.mark.parametrize("target_id", [t["id"] for t in TARGETS])
def test_target_behaviour_matches_the_frozen_baseline(target_id, golden, fresh):
    """One assertion per target, so a failure names the target that moved.

    If this fails you have changed the requirements machinery. That may be
    correct -- but it is a BEHAVIOUR CHANGE and must be declared, not
    regenerated away. Do not reach for regen_golden.py to make it green unless
    you can say which change caused each diff line and why it is intended.
    """
    expected = golden["targets"].get(target_id)
    actual = fresh["targets"].get(target_id)
    assert expected is not None, (
        f"{target_id} is new -- add it to the baseline deliberately"
    )
    assert actual == expected, (
        f"BEHAVIOUR CHANGE in {target_id}.\n"
        f"expected (frozen): {json.dumps(expected, indent=2, sort_keys=True)[:1800]}\n"
        f"actual   (live):   {json.dumps(actual, indent=2, sort_keys=True)[:1800]}"
    )


def test_golden_file_is_byte_current(fresh):
    """Whole-file check, so nothing drifts outside the per-target assertions.

    ``frozen_bugs`` is REBUILT from ``as_json_block()`` rather than copied out
    of the file being checked. Copying it made the assertion circular: an edit
    to ``frozen_bugs.py`` -- a new bug, a corrected flip step -- would leave
    golden.json stale while this "whole-file currency" test still passed.
    Caught in external code review of this iterate.
    """
    committed = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    payload = dict(fresh)
    payload["frozen_bugs"] = as_json_block()
    # `regenerated_for` IS carried forward from the committed file, unlike
    # frozen_bugs. It is a human annotation recording why the baseline was last
    # rewritten — it has no live source to rebuild from, so self-sourcing it is
    # correct rather than circular. frozen_bugs is code-derived and must be
    # rebuilt, which is the distinction that made the earlier version a bug.
    if "regenerated_for" in committed:
        payload["regenerated_for"] = committed["regenerated_for"]
    assert dumps(payload) == GOLDEN_PATH.read_text(encoding="utf-8"), (
        "golden.json is stale. Inspect the diff with:\n"
        "  uv run integration-tests/requirements_corpus/regen_golden.py --check"
    )


# ---------------------------------------------------------------------------
# Properties the corpus must keep in order to be worth anything
# ---------------------------------------------------------------------------

def test_corpus_discriminates_between_targets(golden):
    """The corpus must actually separate the implementations.

    The floors below are per-FIXTURE. An earlier version asserted only that at
    least two of twenty signatures differed across the whole matrix — which,
    across heterogeneous return types (dataclass lists, Path lists, a raw str,
    a generator), cannot fail. It would still have passed if 19 of 20 targets
    returned `[]` on every fixture: a decorative assertion dressed as a safety
    net. (Caught in adversarial review.)
    """
    populated = [f for f in FIXTURE_NAMES if f not in ("absent", "empty")]
    for fixture in populated:
        sigs = {
            json.dumps(entry["fixtures"][fixture], sort_keys=True)
            for entry in golden["targets"].values()
            if entry["kind"] == "invoked"
        }
        assert len(sigs) >= 5, (
            f"fixture {fixture!r} produced only {len(sigs)} distinct results "
            f"across the target set — it is not discriminating between the "
            f"implementations, so it proves nothing S2 could break"
        )

    columns = {
        fixture: json.dumps(
            [entry["fixtures"][fixture] for entry in golden["targets"].values()
             if entry["kind"] == "invoked"],
            sort_keys=True,
        )
        for fixture in FIXTURE_NAMES
    }
    dupes = len(columns) - len(set(columns.values()))
    assert dupes == 0, f"{dupes} fixture(s) produce an identical matrix column"


def test_planning_as_a_file_still_splits_the_targets(golden):
    """The divergence that justified the `planning-file` fixture is real.

    Some targets raise NotADirectoryError where others degrade. If that split
    ever collapses to all-raise or all-degrade, it is a behaviour change.
    """
    outcomes = {
        tid: entry["fixtures"]["planning-file"]["outcome"]
        for tid, entry in golden["targets"].items()
        if entry["kind"] == "invoked" and tid.startswith("disc.")
    }
    assert set(outcomes.values()) == {"raised", "returned"}, (
        f"planning-as-a-file stopped splitting the targets: {outcomes}"
    )
