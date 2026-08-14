"""Source-level pins and end-to-end lifecycle tests for
scripts/install-hooks.{sh,ps1} — trg-d17b2a22.

Ported from svenroth-ai/leadwright's scripts/install-hooks.ps1, which fixed
fail-open defects the canonical .ps1 here still carried. Defect-specific
premise/fix regressions (the unchecked write, the --default flag, and the
Write-Error terminating-error trap) live in
test_installer_hooks_ps1_defects.py — split out to stay under the 300 LOC
guideline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402
from test_installer_hooks_ps1_defects import _pwsh, _require_pwsh  # noqa: E402

PS1 = REPO_ROOT / "scripts" / "install-hooks.ps1"
SH = REPO_ROOT / "scripts" / "install-hooks.sh"


def _require_bash() -> None:
    skip_or_fail_on_missing_binary("bash", "bash ships on every CI runner; install Git Bash locally")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """Strip full-line `#` comments, leaving executable lines. Both scripts
    only use `#` as a comment marker and never start a code line with it, so
    this distinguishes an explanatory mention (e.g. "not --default") from an
    actual invocation."""
    return "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))


# --------------------------------------------------------------------------- #
# Source-level pins — cheap, no subprocess needed
# --------------------------------------------------------------------------- #
def test_ps1_uses_get_not_default_flag():
    code = _code_only(_read(PS1))
    assert "--default" not in code, "install-hooks.ps1 still uses the git<2.18-unsafe --default flag"
    assert "--get" in code, "install-hooks.ps1 does not use --get to read core.hooksPath"


def test_sh_uses_get_not_default_flag():
    code = _code_only(_read(SH))
    assert "--default" not in code, "install-hooks.sh still uses the git<2.18-unsafe --default flag"
    assert "--get" in code, "install-hooks.sh does not use --get to read core.hooksPath"


def test_ps1_uses_literal_path_for_set_location():
    src = _read(PS1)
    assert "-LiteralPath" in src, "Set-Location without -LiteralPath misresolves [ ] in a clone path as a wildcard"


def test_ps1_refuse_branch_does_not_use_write_error():
    src = _read(PS1)
    code = _code_only(src)
    assert "Write-Error" not in code, (
        "Write-Error under $ErrorActionPreference='Stop' raises a terminating error that skips the "
        "following exit 1, leaving a dot-sourcing caller's $LASTEXITCODE stale"
    )
    assert src.count("[Console]::Error.WriteLine(") >= 2, (
        "expected both the refuse-to-clobber branch and the write-failure branch to use "
        "[Console]::Error.WriteLine instead of a terminating write"
    )


def test_ps1_checks_last_exit_code_after_write():
    src = _read(PS1)
    write_idx = src.index("& git config --local core.hooksPath $targetPath")
    tail = src[write_idx:]
    assert "$LASTEXITCODE -ne 0" in tail, (
        "the git config write is not followed by a $LASTEXITCODE check — a failed write "
        "falls through to the success message"
    )


# --------------------------------------------------------------------------- #
# End-to-end behavior against the real scripts + real git
# --------------------------------------------------------------------------- #
def test_sh_lifecycle_install_idempotent_refuse_force(tmp_path):
    _require_bash()
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "install-hooks.sh").write_text(_read(SH), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    r1 = subprocess.run(["bash", "scripts/install-hooks.sh"], cwd=repo, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    got = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert got == "scripts/hooks"

    r2 = subprocess.run(["bash", "scripts/install-hooks.sh"], cwd=repo, capture_output=True, text=True)
    assert r2.returncode == 0, "second run (idempotent) must not fail"

    subprocess.run(["git", "config", "--local", "core.hooksPath", "some/other/path"], cwd=repo, check=True)
    r3 = subprocess.run(["bash", "scripts/install-hooks.sh"], cwd=repo, capture_output=True, text=True)
    assert r3.returncode != 0, "must refuse to clobber a foreign core.hooksPath"
    got = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert got == "some/other/path", "foreign value must survive the refused install"

    r4 = subprocess.run(["bash", "scripts/install-hooks.sh", "--force"], cwd=repo, capture_output=True, text=True)
    assert r4.returncode == 0, r4.stderr
    got = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert got == "scripts/hooks"


def test_sh_write_failure_exits_nonzero_not_false_success(tmp_path):
    """Defect [1] does not apply to bash (set -e already covers a failed
    native write), but the acceptance criteria still ask for both scripts to
    exit non-zero on a failed config write. A `git` shim earlier on PATH
    fails only the write invocation and delegates everything else to the
    real binary — mirrors test_f39's PATH-shim pattern in
    test_installer_shell_scripts.py."""
    _require_bash()
    real_git = shutil.which("git")
    assert real_git, "git not found on PATH"
    shim_dir = tmp_path / "shimbin"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "config" ] && [ "$2" = "--local" ] && [ "$3" = "core.hooksPath" ] && [ "$4" = "scripts/hooks" ]; then\n'
        '    echo "error: could not lock config file" >&2\n'
        "    exit 255\n"
        "fi\n"
        f'exec "{real_git.replace(chr(92), "/")}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)

    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "install-hooks.sh").write_text(_read(SH), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    env = {**os.environ, "PATH": f"{shim_dir.as_posix()}:{os.environ.get('PATH', '')}"}
    res = subprocess.run(["bash", "scripts/install-hooks.sh"], cwd=repo, capture_output=True, text=True, env=env)
    assert res.returncode != 0, "a failed git config write must not exit 0"
    assert "core.hooksPath ->" not in res.stdout, "must not print the success message on a failed write"


def test_ps1_lifecycle_install_idempotent_refuse_force(tmp_path):
    _require_pwsh()
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "install-hooks.ps1").write_text(_read(PS1), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    r1 = _pwsh(f"Set-Location -LiteralPath '{repo}'; pwsh -NoProfile -File scripts/install-hooks.ps1; exit $LASTEXITCODE")
    assert r1.returncode == 0, r1.stderr
    got = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert got == "scripts/hooks"

    r2 = _pwsh(f"Set-Location -LiteralPath '{repo}'; pwsh -NoProfile -File scripts/install-hooks.ps1; exit $LASTEXITCODE")
    assert r2.returncode == 0, "second run (idempotent) must not fail"

    subprocess.run(["git", "config", "--local", "core.hooksPath", "some/other/path"], cwd=repo, check=True)
    r3 = _pwsh(f"Set-Location -LiteralPath '{repo}'; pwsh -NoProfile -File scripts/install-hooks.ps1; exit $LASTEXITCODE")
    assert r3.returncode != 0, "must refuse to clobber a foreign core.hooksPath"
    got = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert got == "some/other/path", "foreign value must survive the refused install"

    r4 = _pwsh(f"Set-Location -LiteralPath '{repo}'; pwsh -NoProfile -File scripts/install-hooks.ps1 -Force; exit $LASTEXITCODE")
    assert r4.returncode == 0, r4.stderr
    got = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert got == "scripts/hooks"
