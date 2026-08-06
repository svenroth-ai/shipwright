"""The SessionStart wrapper around the required-check drift producer.

@FR-01.17

`shared/scripts/tools/check_required_checks.py` answers "does the host's must-pass
check set match the checks that exist?" — and until P3.03 (`trg-304c764b`) nothing
invoked it. It is a **producer**, not a gate: it returns 0 on drift and files one
tracked follow-up. That is why it is wired to the SessionStart chain rather than to a
push-time gate, and why every test here is about being *harmless*, not about a verdict.

Two hard constraints shape the wrapper, both discovered by reading the chain rather
than assumed:

1. `run_if_cache_ready.py` forwards each child's **stderr verbatim** to the user and
   parses its **stdout** as SessionStart JSON. The producer prints a human-readable
   drift paragraph, so an unwrapped registration would spill into the session and fail
   `test_hook_output_schema_compliance.py`, which executes every registered hook.
2. The chain runs children with `check=False` but propagates the FIRST non-zero code.
   The producer's documented `exit 2` (no `gh`, no auth, unreachable repo) is the
   normal case on many machines, so it must never surface as a chain failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _required_checks_hook_fakes import (  # noqa: E402
    ITERATE_HOOKS as _ITERATE_HOOKS,
    PRODUCER as _PRODUCER,
    Recorder as _Recorder,
    completed as _completed,
    load_hook,
    make_project,
)

hook = load_hook()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A minimally Shipwright-managed tree, so the F7 guard lets the call through."""
    return make_project(tmp_path)


# --------------------------------------------------------------------------- #
# Fail-soft: the chain must never go red because of this producer
# --------------------------------------------------------------------------- #

def test_the_producers_documented_exit_2_is_not_a_failure(project, capsys) -> None:
    """`gh` missing / unauthed / repo unreachable — the normal case, not an error.

    The producer's own docstring makes this distinction load-bearing ("an empty
    must-pass set is a finding, not an error"); the wrapper must not undo it by
    letting the chain report failure on a machine without `gh`.
    """
    runner = _Recorder(_completed(2))
    assert hook.run(project, runner=runner) == 0
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout must stay empty, got {captured.out!r}"
    assert captured.err == "", f"exit 2 is routine — no operator noise, got {captured.err!r}"


def test_a_hang_is_bounded_and_fail_soft(project, capsys) -> None:
    """An unreachable `gh` must not hold session start open indefinitely."""
    runner = _Recorder(raises=subprocess.TimeoutExpired(cmd="gh", timeout=1))
    assert hook.run(project, runner=runner) == 0
    assert capsys.readouterr().out == ""
    assert runner.calls[0]["timeout"] == hook.TIMEOUT_SECONDS
    # The constraint that actually binds, and the one nothing else states:
    # `test_hook_output_schema_compliance` runs the WHOLE registered chain under a
    # 30s cap, so a single hook whose own allowance exceeded it could only ever
    # fail that gate. `> 0` — the first version of this line — was a tautology
    # about a module-level literal and pinned nothing.
    assert 0 < hook.TIMEOUT_SECONDS <= 30, (
        "test_hook_output_schema_compliance caps the entire SessionStart chain at "
        "30s; this hook's own budget must fit inside that."
    )


def test_an_unexpected_failure_still_exits_zero_but_reaches_the_operator(
    project, capsys
) -> None:
    """Total silence would make a permanently broken wrapper indistinguishable from a
    healthy one. stdout stays schema-clean; the signal goes to stderr, which
    `run_if_cache_ready.py` forwards verbatim — so no log file has to be invented."""
    runner = _Recorder(raises=OSError("boom"))
    assert hook.run(project, runner=runner) == 0
    captured = capsys.readouterr()
    assert captured.out == "", "stdout must stay parseable as SessionStart JSON"
    assert "boom" in captured.err, "an unexpected failure left no trace at all"


def test_a_producer_crash_is_reported_but_not_fatal(project, capsys) -> None:
    """The producer documents exit 0 and exit 2. Anything else is a defect in it, and
    the operator is the only one who can act on that."""
    assert hook.run(project, runner=_Recorder(_completed(1))) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip(), "an undocumented exit code was swallowed silently"


def test_control_flow_exceptions_are_not_swallowed(project) -> None:
    """`except Exception`, never `except BaseException`: swallowing KeyboardInterrupt
    makes the hook un-interruptible and hides shutdown from the runtime."""
    with pytest.raises(KeyboardInterrupt):
        hook.run(project, runner=_Recorder(raises=KeyboardInterrupt()))


# --------------------------------------------------------------------------- #
# Invocation contract
# --------------------------------------------------------------------------- #

def test_the_producer_is_driven_as_an_argv_list_never_a_shell_string(project) -> None:
    """No shell, and no interpolation of project/repo values into a command string."""
    runner = _Recorder()
    hook.run(project, runner=runner)
    call = runner.calls[0]
    assert isinstance(call["argv"], list), "argv must be a list, not a shell string"
    assert call.get("shell", False) is False, "shell=True would be injectable"


def test_the_producer_path_is_absolute_and_the_root_is_explicit(project) -> None:
    """A hook process inherits an arbitrary cwd, so nothing may be relative.

    The producer is also reached from an installed plugin cache, where a
    relative path resolves somewhere else entirely.
    """
    runner = _Recorder()
    hook.run(project, runner=runner)
    call = runner.calls[0]
    argv = call["argv"]
    assert argv[0] == sys.executable, "must run on this interpreter"
    assert Path(argv[1]).is_absolute(), f"producer path is relative: {argv[1]}"
    assert Path(argv[1]) == _PRODUCER.resolve(), f"wrong producer: {argv[1]}"
    assert "--project-root" in argv, "the producer would default to an arbitrary cwd"
    assert argv[argv.index("--project-root") + 1] == str(project)
    assert Path(call["cwd"]) == project, "child cwd must be the resolved project root"


def test_child_output_is_captured_not_forwarded(project) -> None:
    """The producer's drift paragraph and any `gh` diagnostics must not reach the
    session. `run_if_cache_ready.py` re-emits child stderr verbatim and parses child
    stdout as SessionStart JSON, so anything not captured here lands in the user's
    session — and `gh` error text is exactly where credentials would surface."""
    runner = _Recorder()
    hook.run(project, runner=runner)
    assert runner.calls[0].get("capture_output") is True, (
        "uncaptured child output is forwarded verbatim by the chain"
    )


# --------------------------------------------------------------------------- #
# Scope guard
# --------------------------------------------------------------------------- #

def test_it_does_nothing_outside_a_shipwright_project(tmp_path) -> None:
    """Opening an unrelated repository must not spend `gh` calls on it, nor write
    triage state into a tree the framework is not installed in — the same F7 boundary
    `check_drift.py` respects."""
    runner = _Recorder()
    assert hook.run(tmp_path, runner=runner) == 0
    assert runner.calls == [], "the producer ran in a non-Shipwright tree"


def test_a_bare_shipwright_directory_is_not_a_shipwright_project(tmp_path) -> None:
    """The degraded fallback must never be WIDER than the canonical predicate.

    It fires only when `from lib.project_root import …` collides, so it is the
    branch nobody exercises — and the first version admitted a bare `.shipwright/`,
    which satisfies neither `CONFIG_MARKER` nor `.shipwright/agent_docs/`. A stray
    directory left by a removed install (or a fixture that creates `.shipwright/`
    holding one `.gitkeep`) would then have spent three authenticated `gh` calls on
    a stranger's repository and written triage state into it — the exact F7
    violation the docstring claims to respect.
    """
    (tmp_path / ".shipwright").mkdir()
    runner = _Recorder()

    assert hook.run(tmp_path, runner=runner) == 0
    assert runner.calls == [], "canonical predicate admitted a bare .shipwright/"


def test_the_degraded_fallback_agrees_with_the_canonical_predicate(
    tmp_path, monkeypatch
) -> None:
    """Exercise the branch that only fires when the import collides.

    Asserting `_is_shipwright_project` directly does NOT reach it: `conftest.py`
    already puts `shared/scripts` on `sys.path`, so `from lib.project_root import
    …` succeeds and the canonical branch answers — the same side, asserted twice.
    Forcing the ImportError is the only way to test the fallback, and the fallback
    is precisely the code nobody exercises in normal operation, which is why it
    must not be able to say "yes" where canonical says "no".
    """
    monkeypatch.setitem(sys.modules, "lib.project_root", None)

    bare = tmp_path / "bare"
    (bare / ".shipwright").mkdir(parents=True)
    assert hook._is_shipwright_project(bare) is False, (
        "the degraded fallback admitted a bare .shipwright/ — it would spend "
        "three authenticated `gh` calls on a stranger's repository"
    )

    # …and it must not be NARROWER either, or a degraded import would silently
    # switch the producer off in a project that legitimately has it.
    for marker in ("shipwright_run_config.json", "shipwright_build_config.json"):
        managed = tmp_path / marker.replace(".json", "")
        managed.mkdir()
        (managed / marker).write_text("{}", encoding="utf-8")
        assert hook._is_shipwright_project(managed) is True, (
            f"the degraded fallback rejected a tree carrying {marker}"
        )


# --------------------------------------------------------------------------- #
# main() — the entry point the chain actually executes
# --------------------------------------------------------------------------- #

def test_main_survives_a_project_root_that_cannot_be_resolved(monkeypatch, capsys):
    """`resolve_project_root()` runs OUTSIDE `run()`'s guard.

    Its canonical resolver calls `Path.cwd()` / `cwd.iterdir()`, which raise
    `FileNotFoundError` when the working directory has been deleted and
    `PermissionError` when it cannot be listed — neither of which is `ImportError`
    or `ValueError`. Unguarded, the traceback goes to stderr (forwarded verbatim by
    the chain) and exits 1 (propagated as the chain's first non-zero code): a failed
    session, which is the one outcome this hook exists to prevent.
    """
    def boom() -> Path:
        raise PermissionError("cwd is not listable")

    monkeypatch.setattr(hook, "resolve_project_root", boom)
    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "", "stdout must stay parseable as SessionStart JSON"
    assert "PermissionError" in captured.err, "the failure left no trace"


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #

def test_the_hook_is_registered_on_session_start() -> None:
    """The whole point of the card: built, tested, and invoked by nothing."""
    raw = json.loads(_ITERATE_HOOKS.read_text(encoding="utf-8"))
    events = raw.get("hooks", raw)
    commands = [
        h.get("command", "")
        for entry in events.get("SessionStart", [])
        for h in entry.get("hooks", [])
    ]
    assert any("check_required_checks_hook.py" in c for c in commands), (
        "shipwright-iterate does not register the required-checks producer, so it "
        "still runs only when a human types it (trg-304c764b)."
    )
