"""How often the required-checks producer is allowed to reach the network.

@FR-01.17

Split from `test_check_required_checks_hook.py` (the fail-soft contract, the
invocation shape, the F7 guard and `main()`) so both stay under the 300-line
budget — the same split `_required_checks_fakes.py` serves for the producer.

**Why a throttle is part of the contract and not a nicety.** The placement of
this hook was justified by `import_github_findings.py`, the network producer it
sits beside in `shipwright-iterate`'s SessionStart chain. That hook is throttled
(6 h by default), and the throttle is precisely what makes a network call
acceptable in a chain that runs *before the session opens*. The first version of
this wrapper copied the placement and not the throttle, which would have billed a
developer who runs `/clear` fifteen times a day forty-five `gh` calls for an
answer the spec itself says only moves when a workflow is added, renamed or
deleted, or when someone edits the host's rules.

There is also no mechanism protecting it: `run_if_cache_ready.py` does **not**
dedupe per event — its `session_event_key` machinery gates cache-repair
readiness, and in the monorepo dev model that block is skipped entirely. The hook
runs once per session because exactly one `hooks.json` lists it. The throttle is
the only thing that bounds the cost if that ever stops being true.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _required_checks_hook_fakes import (  # noqa: E402
    Recorder,
    completed,
    load_hook,
    make_project,
)

hook = load_hook()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path)


def test_the_first_run_in_a_window_compares(project) -> None:
    """Non-vacuity for every suppression assertion below."""
    runner = Recorder()
    assert hook.run(project, runner=runner) == 0
    assert len(runner.calls) == 1


def test_a_second_session_inside_the_window_does_not_call_out(project) -> None:
    """The finding this file exists for."""
    assert hook.run(project, runner=Recorder()) == 0
    second = Recorder()
    assert hook.run(project, runner=second) == 0
    assert second.calls == [], "the throttle did not suppress the second run"


def test_the_window_expires(project) -> None:
    """A throttle that never lets go is just a disabled producer."""
    assert hook.run(project, runner=Recorder()) == 0
    later = datetime.now(timezone.utc) + timedelta(
        hours=hook.DEFAULT_THROTTLE_HOURS + 1
    )
    runner = Recorder()
    assert hook.run(project, runner=runner, now=later) == 0
    assert len(runner.calls) == 1, "the producer never ran again after the window"


def test_the_interval_is_configurable_by_env(project, monkeypatch) -> None:
    """An operator who wants it hourly, or effectively off, must not edit code.

    Driven with an explicit `now=` rather than a sub-millisecond real interval:
    the first version set 0.0000001 hours (360 us) and asserted the second call
    got through, which is a wall-clock race against a few filesystem operations
    and would flake on a fast host with a warm cache.
    """
    monkeypatch.setenv("SHIPWRIGHT_REQUIRED_CHECKS_THROTTLE_HOURS", "1")
    assert hook.run(project, runner=Recorder()) == 0

    # Still inside the one-hour override, but well past nothing at all.
    soon = datetime.now(timezone.utc) + timedelta(minutes=30)
    blocked = Recorder()
    assert hook.run(project, runner=blocked, now=soon) == 0
    assert blocked.calls == [], "the 1h override did not hold for 30 minutes"

    # …and past it. The default is 6h, so this ALSO proves the override is what
    # is being honoured rather than the default.
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    runner = Recorder()
    assert hook.run(project, runner=runner, now=later) == 0
    assert len(runner.calls) == 1, "the env override did not shorten the window"


def test_run_config_outranks_the_env_var(project, monkeypatch) -> None:
    """Same resolution order as `github_triage/state.py`, the sibling producer.

    An operator who sets background cadence in the durable, checked-in place must
    not find that one of the two network producers honours it and the other
    silently does not.
    """
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete",
                    "triage": {"required_checks_throttle_hours": 24}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SHIPWRIGHT_REQUIRED_CHECKS_THROTTLE_HOURS", "1")
    assert hook.throttle_hours(project) == 24.0

    assert hook.run(project, runner=Recorder()) == 0
    blocked = Recorder()
    # Past the env's 1h and the 6h default, still inside run-config's 24h.
    assert hook.run(project, runner=blocked,
                    now=datetime.now(timezone.utc) + timedelta(hours=8)) == 0
    assert blocked.calls == [], "run-config did not outrank the env var"


@pytest.mark.parametrize("garbage", ["", "not-a-number", "0", "-3"])
def test_an_unusable_interval_falls_back_to_the_default(
    project, monkeypatch, garbage
) -> None:
    """A zero or negative window would mean "every session", silently undoing the
    throttle for whoever mistyped it."""
    monkeypatch.setenv("SHIPWRIGHT_REQUIRED_CHECKS_THROTTLE_HOURS", garbage)
    assert hook.throttle_hours() == hook.DEFAULT_THROTTLE_HOURS


def test_a_stamp_from_the_future_does_not_mean_permanent_silence(project) -> None:
    """A restored VM snapshot, a corrected clock, a state file copied between
    machines — a `lastRun` ahead of now parses cleanly, so it misses the
    malformed-state branch, and the elapsed comparison stays negative until
    wall-clock catches up. That is permanent silence, which is the one outcome
    this throttle's contract rules out.
    """
    hook.record(project, succeeded=True)
    ahead = datetime.now(timezone.utc) - timedelta(days=400)  # clock moved back
    runner = Recorder()
    assert hook.run(project, runner=runner, now=ahead) == 0
    assert len(runner.calls) == 1, "a future stamp silenced the producer"


def test_unreadable_state_reads_as_due(project) -> None:
    """Losing the stamp costs one extra comparison, never permanent silence."""
    state = hook.state_path(project)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{ not json", encoding="utf-8")
    runner = Recorder()
    assert hook.run(project, runner=runner) == 0
    assert len(runner.calls) == 1, "malformed state silenced the producer"


# --------------------------------------------------------------------------- #
# Staleness — the fail-open the rest of the design would otherwise have
# --------------------------------------------------------------------------- #

def test_a_check_that_never_succeeds_eventually_says_so(project, capsys) -> None:
    """The scenario: a `gh` token expires.

    `exit 2` covers "not authenticated"; the wrapper is silent on that path by
    contract; and the attempt still consumes its window. Without staleness there
    is no state anywhere distinguishing "compared, in sync" from "has not
    succeeded since March" — and the failure correlates with the event being
    watched, since whoever rotates credentials is often whoever edits the rules.
    """
    assert hook.run(project, runner=Recorder(completed(2))) == 0
    assert capsys.readouterr().err == "", "one failure is routine and must be quiet"

    overdue = datetime.now(timezone.utc) + timedelta(
        hours=hook.DEFAULT_THROTTLE_HOURS * (hook.STALE_WINDOWS + 1)
    )
    assert hook.run(project, runner=Recorder(completed(2)), now=overdue) == 0
    err = capsys.readouterr().err
    assert "has not been verified" in err, (
        f"a check that has not succeeded for {hook.STALE_WINDOWS} windows stayed "
        f"silent — an expired token would end it permanently with no trace: {err!r}"
    )


def test_a_succeeding_check_never_nags(project, capsys) -> None:
    """The other half: exit 0 records success, so staleness never accrues."""
    assert hook.run(project, runner=Recorder(completed(0))) == 0
    capsys.readouterr()
    much_later = datetime.now(timezone.utc) + timedelta(
        hours=hook.DEFAULT_THROTTLE_HOURS * (hook.STALE_WINDOWS + 1)
    )
    assert hook.run(project, runner=Recorder(completed(0)), now=much_later) == 0
    assert capsys.readouterr().err == "", "a healthy check spoke anyway"


def test_a_fresh_project_is_not_greeted_with_a_staleness_warning(project, capsys):
    """A tree that has never run has not failed to succeed — it has not been asked."""
    assert hook.run(project, runner=Recorder(completed(2))) == 0
    assert capsys.readouterr().err == ""


def test_an_unwritable_state_file_skips_rather_than_running_unthrottled(
    project, monkeypatch
) -> None:
    """A window that cannot be RECORDED cannot be bounded.

    Running anyway would mean three `gh` calls every session forever — both halves
    of what the throttle exists to prevent — so this fails safe and stays silent,
    matching the timeout's reasoning rather than contradicting it.
    """
    monkeypatch.setattr(hook, "record", lambda *a, **k: False)
    runner = Recorder()
    assert hook.run(project, runner=runner) == 0
    assert runner.calls == [], "an unrecordable window ran the producer unthrottled"


def test_a_timed_out_producer_still_stamps(project) -> None:
    """Otherwise a host that always times out pays the full wait EVERY session.

    Bounding that is the whole point of the window, so a timeout counts as an
    attempt. The operator keeps `uv run …/check_required_checks.py` for an
    answer they want now.
    """
    import subprocess as sp
    assert hook.run(
        project, runner=Recorder(raises=sp.TimeoutExpired(cmd="gh", timeout=1))
    ) == 0
    runner = Recorder()
    assert hook.run(project, runner=runner) == 0
    assert runner.calls == [], "a timeout did not consume its window"


def test_a_producer_that_could_not_start_does_NOT_stamp(project) -> None:
    """The other side of that trade.

    Failing to launch is usually fixable — a broken interpreter path, a partially
    written file — and suppressing the retry for six hours would hide the fix
    rather than the fault.
    """
    assert hook.run(project, runner=Recorder(raises=OSError("boom"))) == 0
    runner = Recorder()
    assert hook.run(project, runner=runner) == 0
    assert len(runner.calls) == 1, "an unstartable producer consumed its window"
