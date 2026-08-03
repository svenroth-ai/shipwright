"""Each producer's refusal arm actually RUNS, and reports a kept item.

The behavioural caller half of iterate-2026-07-31-it1-s2-expected-status. The
source-level registry pins live in `test_triage_precondition_registry.py`, the
store mechanism in `test_triage_expected_status.py`, the drift-hook composition
in `test_triage_operator_decision_integration.py`, and the ninth arm in
`test_triage_precondition_converge_arm.py`.

A source-level pin can only prove an arm EXISTS. These prove it is reached —
which matters because the three arms that shipped reporting less than the others
were caught by review, not by the AST test that was watching them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
# Module scope, guarded, once — the same idiom as this run's sibling test
# files. Repeating an unguarded insert inside test bodies grows `sys.path` on
# every call and can bind one file as two module objects in one session.
for _p in (str(_SHARED_SCRIPTS), str(_SHARED_SCRIPTS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import triage  # noqa: E402
from triage import append_triage_item, mark_status, read_all_items  # noqa: E402

# --------------------------------------------------------------------------
# Behaviour — a refusal is KEPT, not resolved and not a failure
# --------------------------------------------------------------------------

def _decided_item(root: Path) -> str:
    """An item a person already dismissed, with their own reason."""
    item_id = append_triage_item(
        root, source="github", severity="low", kind="bug",
        title="t", detail="d", dedup_key="gh-pr-ci:1",
    )
    mark_status(root, item_id, new_status="dismissed", by="operator",
                reason="a person decided this")
    return item_id


def test_github_resolver_keeps_a_decided_item_and_does_not_count_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Executes `_dismiss_if_open`'s `except StatusPreconditionError` arm.

    `resolve_stale` filtered on `status == "triage"` from its own unlocked read,
    so it is handed an id it believes is open. It must return 0, not 1.
    """
    from github_triage import resolve as gh_resolve

    item_id = _decided_item(tmp_path)
    landed = gh_resolve._dismiss_if_open(
        tmp_path, item_id, reason="githubResolved", label="resolve",
    )
    assert landed == 0
    assert "kept" in capsys.readouterr().err

    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert (item["statusBy"], item["statusReason"]) == (
        "operator", "a person decided this",
    )


def test_github_resolver_still_counts_a_landed_dismiss(tmp_path: Path) -> None:
    """The positive half — the helper must not have become a no-op."""
    from github_triage import resolve as gh_resolve

    item_id = append_triage_item(
        tmp_path, source="github", severity="low", kind="bug",
        title="t", detail="d", dedup_key="gh-pr-ci:2",
    )
    assert gh_resolve._dismiss_if_open(
        tmp_path, item_id, reason="githubResolved", label="resolve",
    ) == 1
    assert next(
        i for i in read_all_items(tmp_path) if i["id"] == item_id
    )["statusBy"] == "githubImporter"


def _phase_quality_race(tmp_path: Path, monkeypatch, decision: str, **extra):
    """Run the phase-quality resolver with a decision landing mid-flight.

    The decision must land AFTER the producer built `open_backlog` and BEFORE
    its write. Deciding up front would instead filter the item out of
    `open_backlog` entirely, so `_dismiss` would never be called and the test
    would pass with the fix reverted — which is exactly how a ledger row comes
    to say "tested" about a line no test executes.
    """
    from lib.phase_quality import _triage_bundle as bundle

    item_id = append_triage_item(
        tmp_path, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d", dedup_key=bundle.BACKLOG_PREFIX + "deadbeef",
    )
    real_mark_status = triage.mark_status
    fired = []

    def barrier(*args, **kwargs):
        if not fired:
            fired.append(True)
            real_mark_status(tmp_path, item_id, new_status=decision,
                             by="operator", reason="a person decided this",
                             **extra)
        return real_mark_status(*args, **kwargs)

    monkeypatch.setattr(triage, "mark_status", barrier)
    # No fails in scope → the resolver wants to close every open backlog item.
    result = bundle.emit_phase_quality_backlog(tmp_path, run_id=None, commit=None)
    assert fired, "the producer never attempted a write — barrier never fired"
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    return result, item


def test_phase_quality_dismiss_keeps_an_item_a_person_dismissed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Executes `_triage_bundle._dismiss`'s `except StatusPreconditionError` arm.

    The `trg-93ceb2b0` guarantee, intact: a decision that ENDS an entry's life
    is never overwritten by a producer's machine reason, and the refusal is
    reported as KEPT rather than counted or filed as an error.
    """
    result, item = _phase_quality_race(tmp_path, monkeypatch, "dismissed")
    assert result["dismissed"] == 0
    assert (item["statusBy"], item["statusReason"]) == (
        "operator", "a person decided this",
    )


def test_phase_quality_still_closes_an_item_a_person_parked_mid_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PARK in the race window does NOT stop the close — and that is decided.

    This test asserted the opposite until iterate-2026-08-01-triage-defer-
    lifecycle. The operator decision of 2026-07-27 is that a parked entry closes
    automatically when its underlying finding disappears, exactly like an open
    one; the producer here knows something the parker did not, namely that the
    finding is gone. So `AUTO_RESOLVABLE_STATUSES` deliberately narrows what
    `expected_status` protects to the two decisions that END an entry's life,
    and the sibling test above pins that half.
    """
    result, item = _phase_quality_race(
        tmp_path, monkeypatch, "snoozed", revisit_at="2099-01-01",
    )
    assert result["dismissed"] == 1
    assert (item["status"], item["statusBy"]) == ("dismissed", "phaseQualityBacklog")


# --------------------------------------------------------------------------
# AC-5 — the CLI's contract survives the RACE path, not just its pre-check
# --------------------------------------------------------------------------

def test_cli_race_path_reports_the_same_message_and_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Executes `triage_promote._not_triage_error` from the `except` arm.

    The decision is forced to land BETWEEN the CLI's unlocked pre-check and the
    write — the window the pre-check cannot cover — by making the pre-check read
    a stale snapshot while the real store already holds the decision. Without
    the mapping the operator would get the raw store wording instead of the
    CLI's own.
    """
    import triage_promote

    item_id = _decided_item(tmp_path)
    stale = [{"id": item_id, "status": "triage"}]
    monkeypatch.setattr(triage_promote, "read_all_items", lambda _root: stale)

    with pytest.raises(ValueError, match="only `triage` is dismissable") as exc:
        triage_promote.dismiss(tmp_path, item_id=item_id, reason="auto")
    # The wording quotes the status the STORE holds, not the stale snapshot.
    assert "'dismissed'" in str(exc.value)
    # And nothing was written: the person's reason still stands.
    assert next(
        i for i in read_all_items(tmp_path) if i["id"] == item_id
    )["statusReason"] == "a person decided this"


def test_cli_pre_check_and_race_path_share_one_wording() -> None:
    """Both paths route through the same helper, so they cannot drift apart."""
    import triage_promote

    for new_status, adjective in (
        ("dismissed", "dismissable"), ("snoozed", "deferrable"),
        ("promoted", "promotable"),
    ):
        msg = str(triage_promote._not_triage_error("trg-1", "dismissed", new_status))
        assert f"only `triage` is {adjective} from this CLI" in msg


def test_cli_still_promotes_and_defers_a_still_open_item(tmp_path: Path) -> None:
    """The precondition must not break either ordinary operator path.

    Both verbs, because they take different routes into the store: `defer`
    goes through the shared `_transition`, `promote` has its own body that
    also writes `promotedTaskId`.
    """
    import triage_promote

    def _seed() -> str:
        return append_triage_item(
            tmp_path, source="manual", severity="low", kind="bug",
            title="t", detail="d",
        )

    deferred = triage_promote.defer(tmp_path, item_id=_seed(), reason="later",
                                    revisit_at="2099-01-01")
    assert deferred["newStatus"] == "snoozed"

    promoted_id = _seed()
    promoted = triage_promote.promote(
        tmp_path, item_id=promoted_id, task_ref="EXT:linear-ENG-1",
    )
    assert promoted["newStatus"] == "promoted"
    item = next(i for i in read_all_items(tmp_path) if i["id"] == promoted_id)
    assert (item["status"], item["promotedTaskId"]) == (
        "promoted", "EXT:linear-ENG-1",
    )


def test_cli_race_path_keeps_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-5 says "exit code", so drive a real CLI entry point, not a helper.

    What this pins, stated honestly: a refusal reaches the operator as the
    CLI's ordinary "not open" outcome — exit 2 with the CLI's own wording — and
    NOT as a crash. It does not pin the `_not_triage_error` conversion by
    itself: `StatusPreconditionError` subclasses `ValueError`, which
    `main` already maps to 2, so deleting the conversion would still exit 2.
    The conversion is load-bearing for the MESSAGE, and that is what the
    stderr assertion below covers (doubt review, doubt 4).
    """
    import triage_promote

    item_id = _decided_item(tmp_path)
    stale = [{"id": item_id, "status": "triage"}]
    monkeypatch.setattr(triage_promote, "read_all_items", lambda _root: stale)

    code = triage_promote.main([
        "--project-root", str(tmp_path), "--id", item_id,
        "--task-ref", "EXT:linear-ENG-1",
    ])
    assert code == 2
    err = capsys.readouterr().err
    assert "only `triage` is promotable from this CLI" in err, (
        "the operator got a raw store error instead of the CLI's own wording"
    )
    assert "'dismissed'" in err  # the status the STORE holds, not the snapshot
