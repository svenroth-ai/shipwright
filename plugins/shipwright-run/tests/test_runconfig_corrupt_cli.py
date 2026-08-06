"""The CLI half, plus AC12: the recovery path stays open, by category.

An unusable config exits non-zero instead of mutating a run.

Two paths reach the same payload, deliberately, and exactly one fires per
invocation so it is never printed twice:

* ``get-next-step`` — ``get_next_step`` CATCHES the exception (it is a reporter
  and must not crash), so it can never reach ``main()``'s handler; the arm's own
  branch is what turns a blocked read into exit 2.
* everything that mutates — propagates to ``main()``'s ``except``.

Run as a SUBPROCESS because the process exit code is the contract a caller
actually sees. Subprocess tests are invisible to diff-coverage, so the same
logic is also covered in-process in ``test_runconfig_corrupt_fail_closed.py``.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parent.parent
_LIB = _PLUGIN / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import config_factory, config_io  # noqa: E402
from orchestrator_pkg.config_io import RunConfigUnreadable  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402
from runconfig_corrupt_shapes import (  # noqa: E402
    UNUSABLE_CONTENT,
    raiser,
    truncated,
    write,
)

_ORCHESTRATOR = _LIB / "orchestrator.py"


def _run(*args, cwd):
    return subprocess.run(
        [sys.executable, str(_ORCHESTRATOR), *args, "--project-root", str(cwd)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def test_update_step_exits_two_and_changes_nothing(tmp_path):
    path = write(tmp_path, truncated())
    before = path.read_bytes()

    result = _run("update-step", "--step", "plan", "--status", "complete", cwd=tmp_path)

    assert result.returncode == 2, result.stderr
    assert path.read_bytes() == before
    assert "config_unreadable" in result.stderr


def test_get_next_step_exits_two(tmp_path):
    write(tmp_path, truncated())
    result = _run("get-next-step", cwd=tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["blocked"] is True


def test_get_next_step_emits_the_payload_on_one_stream_only(tmp_path):
    """One diagnostic, one stream. It was printed to stdout AND stderr, so
    anything aggregating both saw it twice (external code review).

    stdout is the right stream here: a blocked read is still this command's
    RESULT, every other arm prints its result there, and the exit code is what
    carries the failure. `update-step`, which propagates instead of returning,
    is the arm that legitimately uses stderr."""
    write(tmp_path, truncated())
    result = _run("get-next-step", cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert combined.count('"reason": "config_unreadable"') == 1, combined
    assert result.stderr.strip() == "", "the result belongs on stdout"


def test_all_steps_complete_still_exits_zero(tmp_path):
    """The blocked case must not be confused with a finished run — both carry
    ``next_step: null``."""
    write(tmp_path, json.dumps({
        "pipeline": ["plan"], "completed_steps": ["plan"], "standalone": True,
    }))
    result = _run("get-next-step", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["next_step"] is None
    assert "blocked" not in payload


def test_absent_config_still_exits_zero(tmp_path):
    result = _run("get-next-step", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["next_step"] == "project"


def test_the_payload_is_not_printed_twice(tmp_path):
    """Both the arm's branch and main()'s handler can emit; only one may."""
    write(tmp_path, truncated())
    result = _run("update-step", "--step", "plan", "--status", "complete", cwd=tmp_path)
    assert result.stderr.count('"reason": "config_unreadable"') == 1, result.stderr


def test_write_config_recovers_an_unusable_config(tmp_path):
    """AC12 — the recovery the error message tells the operator to perform. It
    must NOT be caught by the strict guard."""
    path = write(tmp_path, truncated())
    result = _run(
        "write-config", "--scope", "full_app", "--profile", "nextjs-supabase",
        "--autonomy", "guided", "--deploy-target", "none", "--mode", "single_session",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "config_unreadable" not in result.stderr
    assert json.loads(path.read_text(encoding="utf-8"))["schemaVersion"] == 2


@pytest.mark.parametrize("content", ["null", "[]", "{oops", ""])
def test_write_config_recovers_from_every_bad_content_shape(tmp_path, content):
    write(tmp_path, content)
    result = _run(
        "write-config", "--scope", "full_app", "--profile", "nextjs-supabase",
        "--autonomy", "guided", "--deploy-target", "none", "--mode", "single_session",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_driven_run_guard_is_not_bypassed_by_an_unusable_config(tmp_path):
    """The guard reads the config to decide whether ``update-step`` is inert. An
    unusable config used to read as ``{}`` — falsy — so the guard silently
    switched off and the command went on to mutate a driven run."""
    path = write(tmp_path, truncated())
    before = path.read_bytes()
    result = _run("update-step", "--step", "plan", "--status", "in_progress", cwd=tmp_path)
    assert result.returncode == 2
    assert path.read_bytes() == before


# --------------------------------------------------------------------------- #
# AC12 (library half) — create_config is the recovery, so bad CONTENT must not
# stop it. `io` still propagates: it defeats the write anyway.
# --------------------------------------------------------------------------- #

def _create(project_root):
    return config_factory.create_config(
        "full_app", "nextjs-supabase", "guided", "none", project_root,
        mode="single_session",
    )


@pytest.mark.parametrize("name", sorted(UNUSABLE_CONTENT))
def test_create_config_recovers_from_bad_content(tmp_path, name):
    """'Delete it and re-run' has to actually work. ``create_config`` reads the
    old file only to merge ``completed_steps``; bad content is precisely what it
    is here to replace."""
    write(tmp_path, UNUSABLE_CONTENT[name])
    config = _create(tmp_path)
    assert config["schemaVersion"] == 2
    assert config["completed_steps"] == []


def test_create_config_recovers_from_non_utf8(tmp_path):
    """The category the external plan review caught: the TOLERANT reader
    propagates UnicodeDecodeError, so leaving ``create_config`` on it would have
    made the advertised recovery crash."""
    (tmp_path / CONFIG_NAME).write_bytes(b'{"standalone": fa\xff\xfelse}')
    assert _create(tmp_path)["schemaVersion"] == 2


def test_create_config_stays_loud_on_a_filesystem_fault(tmp_path, monkeypatch):
    """An ``io`` failure defeats the write anyway, and 'delete the file' is the
    wrong advice for it.

    Asserts the EXACT type and category, not a tuple of either: accepting
    ``PermissionError`` too would let this pass against a ``create_config``
    reverted to the tolerant reader (which propagates it), so the `io` arm —
    the one branch this test exists for — would be pinned by nothing.
    """
    write(tmp_path, "{}")
    monkeypatch.setattr(config_io, "durable_read_text", raiser(PermissionError(13, "denied")))
    with pytest.raises(RunConfigUnreadable) as excinfo:
        _create(tmp_path)
    assert excinfo.value.category == "io"


def test_create_config_still_merges_a_healthy_standalone_config(tmp_path):
    """The recovery change must not cost the normal merge."""
    write(tmp_path, json.dumps({
        "standalone": True, "completed_steps": ["project"], "pipeline": ["project", "plan"],
    }))
    assert "project" in _create(tmp_path)["completed_steps"]


def test_create_config_says_the_prior_steps_were_not_merged(tmp_path, capsys):
    """AC12 requires the recovery to be ANNOUNCED, not silent: a run that quietly
    forgets its completed phases looks like one that never had any."""
    write(tmp_path, truncated())
    _create(tmp_path)
    warning = capsys.readouterr().err
    assert "completed_steps" in warning
    assert "NOT merged" in warning or "not merged" in warning.lower()


def test_create_config_does_not_warn_on_a_healthy_config(tmp_path):
    """The warning must mean something — it cannot fire on the normal path."""
    write(tmp_path, json.dumps({"standalone": True, "completed_steps": ["project"]}))
    result = _run(
        "write-config", "--scope", "full_app", "--profile", "nextjs-supabase",
        "--autonomy", "guided", "--deploy-target", "none", "--mode", "single_session",
        cwd=tmp_path,
    )
    # Both strings are ones config_factory ACTUALLY emits on the recovery path
    # (`Replacing an unusable orchestrator config` / `were NOT merged`), so each
    # line can genuinely fail. An earlier draft asserted a paraphrase that the
    # code never produces — a line that pins nothing (Stage-1 review).
    assert "Replacing an unusable" not in result.stderr
    assert "NOT merged" not in result.stderr
