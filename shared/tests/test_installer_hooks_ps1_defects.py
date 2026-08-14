"""Premise/fix regressions for the three install-hooks.ps1 fail-open defects
fixed for trg-d17b2a22 (ported from svenroth-ai/leadwright):

[1] An unchecked ``git config`` write fell through to a success message and
    exit 0 even when the write failed.
[2] ``--default ''`` errors on git <2.18; the try/catch swallowed that and
    made an actually-set foreign ``core.hooksPath`` read as unset, silently
    overwriting it.
[3] ``Write-Error`` under ``$ErrorActionPreference='Stop'`` raises a
    terminating error, so the following ``exit 1`` never runs — a caller
    that dot-sources the script wrapped in try/catch reads a stale,
    likely-zero, ``$LASTEXITCODE``.

Each pair proves the premise with a small inline OLD-shape snippet (the
codebase's own idiom — see test_f33_raw_post_increment_from_zero_aborts in
test_installer_shell_scripts.py) before proving the fix against the real
file. Source-level pins and end-to-end lifecycle tests live in
test_installer_hooks_scripts.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

PS1 = REPO_ROOT / "scripts" / "install-hooks.ps1"


def _require_pwsh() -> None:
    skip_or_fail_on_missing_binary(
        "pwsh", "pwsh ships preinstalled on ubuntu-latest GitHub runners; install PowerShell 7 locally (https://aka.ms/pwsh)"
    )


def _pwsh(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(["pwsh", "-NoProfile", "-Command", script], capture_output=True, text=True, env=full_env)


# A PowerShell `git` stand-in, parametrized via env vars, that logs every
# invocation. Real git is not exercised here — these three defects need
# conditions (a failing write, an old git rejecting a flag) that are
# impractical to reproduce with the real binary.
_GIT_STUB = """
function git {
    $callArgs = $args
    if ($env:GIT_STUB_LOG) { Add-Content -Path $env:GIT_STUB_LOG -Value ($callArgs -join ' ') }
    if ($callArgs[0] -eq 'rev-parse') {
        Write-Output $env:GIT_STUB_TOPLEVEL
        $global:LASTEXITCODE = 0
        return
    }
    if ($callArgs[0] -eq 'config') {
        if ($callArgs -contains '--default') {
            if ($env:GIT_STUB_OLD_GIT -eq '1') {
                [Console]::Error.WriteLine('git: error: unknown option --default')
                $global:LASTEXITCODE = 129
                return
            }
            Write-Output $env:GIT_STUB_CURRENT
            $global:LASTEXITCODE = 0
            return
        }
        if ($callArgs -contains '--get') {
            if ($env:GIT_STUB_CURRENT) {
                Write-Output $env:GIT_STUB_CURRENT
                $global:LASTEXITCODE = 0
            } else {
                $global:LASTEXITCODE = 1
            }
            return
        }
        if ($env:GIT_STUB_WRITE_FAILS -eq '1') {
            [Console]::Error.WriteLine('git: error: could not lock config file')
            $global:LASTEXITCODE = 255
            return
        }
        $global:LASTEXITCODE = 0
        return
    }
    $global:LASTEXITCODE = 0
}
"""


# --------------------------------------------------------------------------- #
# Defect [1] — unchecked write must not report success
# --------------------------------------------------------------------------- #
def test_premise_unchecked_write_reports_false_success():
    """Guard the premise: an unchecked write really does fall through to 'success'."""
    _require_pwsh()
    old_snippet = """
& git config --local core.hooksPath scripts/hooks
Write-Host "install-hooks: core.hooksPath -> scripts/hooks"
"""
    res = _pwsh(_GIT_STUB + old_snippet, env={"GIT_STUB_WRITE_FAILS": "1"})
    assert res.returncode == 0, "premise broken: unchecked write no longer exits 0"
    assert "core.hooksPath ->" in res.stdout


def test_ps1_write_failure_exits_nonzero_not_false_success(tmp_path):
    _require_pwsh()
    log = tmp_path / "calls.log"
    body = f"{_GIT_STUB}\n& '{PS1}'\nexit $LASTEXITCODE\n"
    res = _pwsh(
        body,
        env={"GIT_STUB_TOPLEVEL": str(tmp_path), "GIT_STUB_WRITE_FAILS": "1", "GIT_STUB_LOG": str(log)},
    )
    assert res.returncode != 0, "a failed git config write must not exit 0"
    assert "core.hooksPath ->" not in res.stdout, "must not print the success message on a failed write"


# --------------------------------------------------------------------------- #
# Defect [2] — an old-git error on an unset flag must not read as "unset"
# --------------------------------------------------------------------------- #
def test_premise_default_flag_misreads_foreign_value_as_unset():
    """Guard the premise: --default on a git that rejects it loses a real foreign value."""
    _require_pwsh()
    old_snippet = """
$current = ''
try {
    $current = (& git config --local --default '' core.hooksPath).Trim()
} catch {
    $current = ''
}
Write-Output "CURRENT=[$current]"
"""
    res = _pwsh(_GIT_STUB + old_snippet, env={"GIT_STUB_OLD_GIT": "1", "GIT_STUB_CURRENT": "some/other/path"})
    assert "CURRENT=[]" in res.stdout, (
        f"premise broken: --default no longer loses a foreign value on an old git: {res.stdout!r}"
    )


def test_ps1_get_flag_survives_old_git_and_refuses_to_clobber(tmp_path):
    _require_pwsh()
    log = tmp_path / "calls.log"
    body = f"{_GIT_STUB}\n& '{PS1}'\nexit $LASTEXITCODE\n"
    res = _pwsh(
        body,
        env={
            "GIT_STUB_TOPLEVEL": str(tmp_path),
            "GIT_STUB_OLD_GIT": "1",
            "GIT_STUB_CURRENT": "some/other/path",
            "GIT_STUB_LOG": str(log),
        },
    )
    assert res.returncode != 0, "must refuse to clobber even when --default is unsupported by git"
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "--default" not in calls, "install-hooks.ps1 must never call --default"
    assert "core.hooksPath scripts/hooks" not in calls, "must never reach the write call when refusing"


# --------------------------------------------------------------------------- #
# Defect [3] — a terminating write must not leave a dot-sourcing caller
# with a stale, successful-looking $LASTEXITCODE
# --------------------------------------------------------------------------- #
def test_premise_write_error_leaves_stale_last_exit_code():
    """Guard the premise: Write-Error under Stop skips the following exit 1,
    so a caller that catches it sees a stale (here: successful) $LASTEXITCODE."""
    _require_pwsh()
    snippet = """
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
try {
    Write-Error "install-hooks: refused"
    exit 1
} catch {
    # a caller defensively swallowing the terminating error
}
Write-Output "REACHED_AFTER=$LASTEXITCODE"
"""
    res = _pwsh(snippet)
    assert "REACHED_AFTER=0" in res.stdout, (
        f"premise broken: Write-Error no longer leaves a stale $LASTEXITCODE: {res.stdout!r}"
    )


def test_console_error_writeline_exit_is_not_swallowed_by_caller_catch():
    _require_pwsh()
    snippet = """
$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
try {
    [Console]::Error.WriteLine("install-hooks: refused")
    exit 1
} catch {
    Write-Output "SHOULD_NOT_REACH"
}
Write-Output "REACHED_AFTER=$LASTEXITCODE"
"""
    res = _pwsh(snippet)
    assert res.returncode == 1, "exit 1 must terminate the process, not be caught by a wrapping try/catch"
    assert "SHOULD_NOT_REACH" not in res.stdout
    assert "REACHED_AFTER" not in res.stdout
