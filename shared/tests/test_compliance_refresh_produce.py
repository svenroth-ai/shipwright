"""Recompute, verify, refuse — the producing half of the compliance refresh.

Subject: ``shared/scripts/tools/compliance_refresh_produce.py``
(iterate-2026-07-31-derived-docs-at-release, AC-3 / AC-4 / AC-5 / AC-6 / AC-9).

The generators are injected throughout. What is under test is the LOOP and the
refusals — every one of which exists because a refresh that reports green while
shipping frozen or emptied documents is worse than not refreshing at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Order matters and the inserts are UNCONDITIONAL. `shared/tests` carries its own
# `tools/` package, so it must never sit ahead of `shared/scripts` on the path —
# a `if p not in sys.path` guard would skip the second insert whenever conftest
# had already added it, leaving the tests dir in front and resolving
# `from tools import ...` to the wrong package (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import (  # noqa: E402
    BASE, DASHBOARD, RUN, all_ok, head_sha, seed_repo,
)
from lib.churn_merge import CI_SECURITY_SUMMARY  # noqa: E402
from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from tools import compliance_refresh_produce as produce_mod  # noqa: E402


@pytest.fixture
def compliance_refresh_repo(tmp_path: Path) -> Path:
    """:func:`seed_repo` as a fixture — see that module for why it is declared
    here rather than shared."""
    return seed_repo(tmp_path / "repo")


def _stable(_root, _run_id):
    """A producer that writes nothing — every pass is byte-identical."""
    return all_ok()


# --- AC-3: the fixpoint ------------------------------------------------------


def test_a_stable_producer_converges_on_the_second_pass(compliance_refresh_repo):
    reached, passes, _ = produce_mod.converge(compliance_refresh_repo, RUN, regenerate=_stable)
    assert reached is True
    assert passes == 2, "one pass cannot establish a fixpoint; two identical ones can"


def test_a_producer_that_never_settles_fails_rather_than_committing_a_pass(compliance_refresh_repo):
    """AC-3. Whichever pass happened to run last is not an answer."""
    counter = {"n": 0}

    def churn(root, run_id):
        counter["n"] += 1
        (root / DASHBOARD).write_text(f"# d\n\n{'row' * 40}\n{counter['n']}\n",
                                      encoding="utf-8")
        return all_ok()

    reached, passes, _ = produce_mod.converge(compliance_refresh_repo, RUN, regenerate=churn)
    assert reached is False
    assert passes == produce_mod.MAX_PASSES


def test_convergence_ignores_a_moving_ci_security(compliance_refresh_repo):
    """AC-6. It reads the latest completed CI run, not the tree, so two passes may
    legitimately differ there. Demanding byte-equality would make an honest
    refresh flake."""
    counter = {"n": 0}

    def moving_ci(root, run_id):
        counter["n"] += 1
        (root / CI_SECURITY_SUMMARY).write_text(
            json.dumps({"rows": ["x"] * 40, "n": counter["n"]}), encoding="utf-8")
        return all_ok()

    reached, _, _ = produce_mod.converge(compliance_refresh_repo, RUN, regenerate=moving_ci)
    assert reached is True


# --- AC-4: a failed pass is not a pass that found nothing --------------------


def test_an_all_error_pass_is_reported_as_a_failure_not_a_fixpoint(compliance_refresh_repo, monkeypatch):
    """AC-4. The regression this exists for: an all-error pass writes nothing, so
    its digest is unchanged, so it converges IMMEDIATELY — green, frozen forever,
    no card. The outcomes must be consulted BEFORE the convergence verdict."""
    monkeypatch.setattr(
        produce_mod, "converge",
        lambda *a, **k: (True, 2, {rel: "error" for rel in sorted(REFRESH_SET)}),
    )
    result, payload = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "producer_failed"
    assert result["converged"] is True, "it DID converge — that is exactly the trap"
    assert payload == {}


def test_one_unknown_outcome_word_is_enough_to_refuse(compliance_refresh_repo, monkeypatch):
    outcomes = all_ok()
    outcomes[DASHBOARD] = "skipped (symlink)"
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (True, 2, outcomes))
    result, _ = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "producer_failed"
    assert result["failed"] == [DASHBOARD]


def test_a_failure_in_an_EARLIER_pass_still_fails_the_run(compliance_refresh_repo):
    """AC-4 is about *a* pass that failed, not the pass that happened to be last.

    An errored leg writes nothing, so the pass after it can succeed, move the
    digest, and the pass after THAT can converge — leaving a caller that keeps
    only the final outcomes holding an all-green report over a real producer
    failure (external code review, openai/high).
    """
    passes = {"n": 0}

    def fails_first_then_settles(root, run_id):
        passes["n"] += 1
        if passes["n"] == 1:
            return {**all_ok(), DASHBOARD: "error"}
        (root / DASHBOARD).write_text("# d\n\n" + "row\n" * 60, encoding="utf-8")
        return all_ok()

    _, _, outcomes = produce_mod.converge(
        compliance_refresh_repo, RUN, regenerate=fails_first_then_settles)
    assert passes["n"] >= 3, "the fixture must really converge on a LATER pass"
    assert outcomes[DASHBOARD] == "error", (
        "the earlier pass's failure was overwritten by the later pass's success"
    )


def test_a_non_converging_run_refuses_after_the_producer_check(compliance_refresh_repo, monkeypatch):
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (False, 4, all_ok()))
    result, payload = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "not_converged"
    assert payload == {}


# --- AC-5: the content floor -------------------------------------------------


def test_an_emptied_document_blocks_the_refresh(compliance_refresh_repo, monkeypatch):
    """AC-5. The measured shape: a collector times out, returns [] and renders a
    well-formed document with no rows. It converges perfectly."""
    def empty_one(root, run_id):
        (root / DASHBOARD).write_text("", encoding="utf-8")
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge",
                        lambda root, *a, **k: (empty_one(root, RUN), (True, 2, all_ok()))[1])
    result, payload = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "content_floor"
    assert DASHBOARD in result["violations"]
    assert payload == {}


def test_allow_shrink_waives_the_ratio_floor_and_records_that_it_did(compliance_refresh_repo, monkeypatch):
    def shrink(root, run_id):
        (root / DASHBOARD).write_text("# d\n\nrow\n", encoding="utf-8")
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge",
                        lambda root, *a, **k: (shrink(root, RUN), (True, 2, all_ok()))[1])
    blocked, _ = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert blocked["status"] == "content_floor"

    allowed, payload = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None, allow_shrink=True)
    assert allowed["status"] == "ok"
    assert payload
    # AC-5 / Stage-1 HIGH-2: WHICH documents, not merely that the flag was passed.
    assert allowed["allow_shrink"] == {"waived": [DASHBOARD]}


def test_allow_shrink_records_an_empty_waiver_when_nothing_shrank(
    compliance_refresh_repo, monkeypatch,
):
    """The flag passed and never mattered is a different fact from a document
    halving, and only the second is worth anyone's attention."""
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (True, 2, all_ok()))
    result, _ = produce_mod.produce(
        compliance_refresh_repo, RUN, BASE, None, allow_shrink=True)
    assert result["status"] == "ok"
    assert result["allow_shrink"] == {"waived": []}


def test_allow_shrink_never_waives_an_emptied_document(compliance_refresh_repo, monkeypatch):
    """No legitimate change turns a document with content into a blank one, and
    that is the shape a timed-out collector produces."""
    def empty_one(root, run_id):
        (root / DASHBOARD).write_text("", encoding="utf-8")
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge",
                        lambda root, *a, **k: (empty_one(root, RUN), (True, 2, all_ok()))[1])
    result, payload = produce_mod.produce(
        compliance_refresh_repo, RUN, BASE, None, allow_shrink=True)
    assert result["status"] == "content_floor"
    assert DASHBOARD in result["violations"]
    assert payload == {}


def test_a_ci_security_producer_failure_never_fails_the_run(
    compliance_refresh_repo, monkeypatch,
):
    """AC-6, made true by construction rather than by the producer's coupling.

    Today one `_update_compliance` call decides all seven together, so
    `ci-security.json` cannot fail alone — which is exactly why this must be
    stated: a producer that ever reported per-path outcomes would otherwise start
    failing releases over a scan, silently (external code review, openai/high).
    """
    outcomes = {**all_ok(), CI_SECURITY_SUMMARY: "error"}
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (True, 2, outcomes))
    result, payload = produce_mod.produce(
        compliance_refresh_repo, RUN, head_sha(compliance_refresh_repo), None)
    assert result["status"] == "ok", "a scan must never hold a release"
    assert payload
    assert result["ci_security"]["producer_outcome"] == "error"
    assert result["ci_security"]["stale"] is None, "unknown, not fresh"
    assert "committed copy stands" in result["ci_security"]["note"]


def test_a_tree_derived_failure_alongside_ci_security_still_refuses(
    compliance_refresh_repo, monkeypatch,
):
    """The carve-out is for that ONE path, not a hole in the refusal."""
    outcomes = {**all_ok(), CI_SECURITY_SUMMARY: "error", DASHBOARD: "error"}
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (True, 2, outcomes))
    result, _ = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "producer_failed"
    assert result["failed"] == [DASHBOARD]
