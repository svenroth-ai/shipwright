"""Behavioral tests for update-marketplace.sh's ``_atomic_sync_dir`` lock.

Split out of ``test_marketplace_atomic_sync_dir.py`` (which crossed the
300-line guideline) along an existing seam: this file covers only lock
acquisition, staleness reclamation, and the pre-lock parent-directory
creation it depends on. General sync/swap behavior (pycache preservation,
pruning, orphan recovery) stays in the sibling file.

Extracts the function (and its ``_pid_is_alive`` helper) out of the real
script and drives it against fixture trees under ``bash``, rather than
sourcing the whole script (which would immediately try to fetch the real
marketplace). The closing brace of a top-level function sits at column 0;
an inner loop/if's closing brace is indented — that is what lets a
non-greedy ``^\\}`` anchor find the right one without a real bash parser.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"
_SRC = UPDATE_SH.read_text(encoding="utf-8")


def _extract(name: str) -> str:
    m = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", _SRC, flags=re.DOTALL | re.MULTILINE)
    assert m, f"could not find {name}() in update-marketplace.sh — has it been renamed?"
    return f"{name}() {{\n{m.group(1)}}}"


def _require_bash() -> None:
    if not shutil.which("bash"):
        pytest.fail("bash ships on every CI runner; install Git Bash locally")


def _run_script(script: str, **kwargs) -> subprocess.CompletedProcess:
    """Writes the script to a temp file and runs `bash <file>` instead of
    `bash -c <script>` — `_atomic_sync_dir`'s own extracted text now runs well
    past 8000 characters, and Windows' classic ~8191-char command-line limit
    truncated it mid-function when passed inline, producing a baffling
    "unexpected end of file" bash syntax error with no size hint anywhere in
    it. A file has no such ceiling."""
    _require_bash()
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name
    try:
        return subprocess.run(["bash", script_path], capture_output=True, text=True, **kwargs)
    finally:
        Path(script_path).unlink(missing_ok=True)


def _run(body: str) -> subprocess.CompletedProcess:
    """`_atomic_sync_dir` calls `_pid_is_alive` (its lock's liveness check),
    a separate top-level function — without extracting it too, every fixture
    run would fail on "command not found" instead of exercising the lock."""
    script = ("set -euo pipefail\n" + _extract("_pid_is_alive") + "\n"
              + _extract("_atomic_sync_dir") + "\n" + body)
    return _run_script(script)


def _p(path: Path) -> str:
    """Windows backslash paths break bash's own string ops (rel_path
    stripping, dirname); Git Bash/MSYS accepts the forward-slash form."""
    return path.as_posix()


def test_live_pid_leftover_survives_the_sweep(tmp_path):
    """Tier-3 review, PR #796: a name-only sweep of `.sync-new.*`/`.sync-old.*`
    cannot tell a dead process's leftover apart from a CONCURRENT, still-running
    sync's own staging dir — it would delete both. Simulate the latter with a
    real background process's PID and confirm its leftover survives, while a
    leftover under an unused PID (nothing on the system has it) is swept."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.py").write_text("a", encoding="utf-8")
    dst.mkdir()

    script = (
        "set -euo pipefail\n"
        + _extract("_pid_is_alive") + "\n"
        + _extract("_atomic_sync_dir") + "\n"
        + f'live_leftover="{_p(dst)}.sync-new.live_holder"\n'
        + f'dead_leftover="{_p(dst)}.sync-new.99999999"\n'
        + 'mkdir -p "$live_leftover" "$dead_leftover"\n'
        + 'sleep 30 & holder=$!\n'
        + 'mv "$live_leftover" "' + _p(dst) + '.sync-new.$holder"\n'
        + f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label\n'
        + 'kill "$holder" 2>/dev/null || true\n'
        + 'echo "LIVE_SURVIVED=$([ -d "' + _p(dst) + '.sync-new.$holder" ] && echo yes || echo no)"\n'
        + 'echo "DEAD_SWEPT=$([ -d "$dead_leftover" ] && echo no || echo yes)"\n'
    )
    res = _run_script(script, timeout=30)

    assert res.returncode == 0, res.stderr
    assert "LIVE_SURVIVED=yes" in res.stdout, res.stdout
    assert "DEAD_SWEPT=yes" in res.stdout, res.stdout


def test_stale_lock_with_dead_holder_is_reclaimed(tmp_path):
    """A lock left behind by a crashed process (killed, OOM) must not
    deadlock every future sync of this $dst forever."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.py").write_text("a", encoding="utf-8")
    dst.mkdir()
    lock = dst.parent / (dst.name + ".sync.lock")
    lock.mkdir()
    (lock / "pid").write_text("99999999", encoding="utf-8")

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    assert (dst / "a.py").exists()
    assert not lock.exists(), "the reclaimed (and then re-released) lock should not survive a clean run"


def test_stale_lock_is_claimed_atomically_not_deleted_by_name(tmp_path):
    """Tier-3 review, PR #796 round 3: two contenders can both read the same
    dead PID; a bare `rm -rf "$lock"` deletes by name only, so if the other
    contender wins the race and installs its own live lock first, THIS
    process's rm then deletes that live lock out from under it. Reclaiming
    must `mv "$lock"` away first — a rename that only one contender's attempt
    can ever win for a given lock instance — checked structurally since
    reproducing the actual race needs real OS thread interleaving."""
    body = _extract("_atomic_sync_dir")
    assert re.search(r'mv "\$lock" "\$discard"', body), (
        "expected the stale lock to be claimed via `mv` (atomic) before being discarded — "
        "a bare `rm -rf \"$lock\"` here would delete by name only, racing a concurrent winner")


def test_lock_with_unwritten_pid_is_not_stolen_as_stale(tmp_path):
    """Tier-3 review, PR #796 round 2 found this window under an earlier
    `mkdir "$lock"`-then-stamp design: a concurrent reader saw the lock with
    no PID yet, called it stale, and stole it out from under a process that
    still believed it held it. That design was replaced in round 6 (`mv -T`,
    used to install the lock in one atomic rename instead, is a GNU
    extension BSD's `mv` lacks, breaking every sync on macOS) with a plain
    `mkdir "$lock"` again — which reopens the exact same window. The fix is
    now behavioral instead of structural: an unreadable (missing/empty) pid
    must never be treated as stale, only a pid that reads back as a
    genuinely dead process may be reclaimed. Simulate the window directly:
    pre-create the lock with no pid file, confirm the sync does not proceed
    while it stays empty, then populate it with a dead pid and confirm the
    sync reclaims it and completes."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.py").write_text("a", encoding="utf-8")
    lock = dst.parent / (dst.name + ".sync.lock")
    lock.mkdir(parents=True)
    # No pid file: simulates the window between another process's own
    # `mkdir "$lock"` and its `echo "$$" > "$lock/pid"`.

    script = (
        "set -euo pipefail\n"
        + _extract("_pid_is_alive") + "\n"
        + _extract("_atomic_sync_dir") + "\n"
        + f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label &\n'
        + "bg=$!\n"
        + "sleep 0.3\n"
        + f'echo "SYNCED_WHILE_EMPTY=$([ -d "{_p(dst)}" ] && echo yes || echo no)"\n'
        + f'echo "99999999" > "{_p(lock)}/pid"\n'
        + 'wait "$bg"\n'
        + f'echo "SYNCED_AFTER_DEAD_PID=$([ -d "{_p(dst)}" ] && echo yes || echo no)"\n'
    )
    res = _run_script(script, timeout=30)

    assert res.returncode == 0, res.stderr
    assert "SYNCED_WHILE_EMPTY=no" in res.stdout, res.stdout
    assert "SYNCED_AFTER_DEAD_PID=yes" in res.stdout, res.stdout


def test_dst_parent_directory_is_created_before_lock_acquisition(tmp_path):
    """Tier-3 review, PR #796 round 4: the lock is a SIBLING of $dst (built
    as `${dst}.sync.lock`), so `mkdir "$lock"` needs $dst's parent to already
    exist. A first-ever sync into a not-yet-existing cache root (or a plugin
    mirror directory before its first copy) has no such parent, so this
    exited under `set -e` before ever reaching the `mkdir -p "$staging"`
    that would otherwise have created the whole tree."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("a", encoding="utf-8")
    dst = tmp_path / "not_yet_created" / "nested" / "dst"

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    assert (dst / "a.py").exists()
