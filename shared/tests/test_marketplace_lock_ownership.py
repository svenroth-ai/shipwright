"""Behavioral tests for update-marketplace.sh's lock OWNERSHIP verification.

Split out of ``test_marketplace_sync_lock.py`` (which crossed the 300-line
guideline) along the seam the round-8/9 review findings drew: this file
covers verifying a lock's ownership before ever deleting it — the ABA-race
fix (claim-then-recheck) and the release-site guard (`_lock_is_owned_by`)
used at both the normal completion path and the script-wide EXIT trap.
Acquisition and staleness reclamation stay in the sibling file.

Extracts functions out of the real script and drives them against fixture
trees under ``bash``, rather than sourcing the whole script (which would
immediately try to fetch the real marketplace). The closing brace of a
top-level function sits at column 0; an inner loop/if's closing brace is
indented — that is what lets a non-greedy ``^\\}`` anchor find the right one
without a real bash parser.
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

_RELEASE_GUARD_RE = r'_lock_is_owned_by "\$lock" "\$\$" && rm -rf "\$lock" 2>/dev/null \|\| true'


def _extract(name: str) -> str:
    m = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", _SRC, flags=re.DOTALL | re.MULTILINE)
    assert m, f"could not find {name}() in update-marketplace.sh — has it been renamed?"
    return f"{name}() {{\n{m.group(1)}}}"


def _require_bash() -> None:
    if not shutil.which("bash"):
        pytest.fail("bash ships on every CI runner; install Git Bash locally")


def _run_script(script: str, **kwargs) -> subprocess.CompletedProcess:
    """Writes the script to a temp file and runs `bash <file>` instead of
    `bash -c <script>` — extracted function text can run well past 8000
    characters, and Windows' classic ~8191-char command-line limit truncated
    it mid-function when passed inline, producing a baffling "unexpected end
    of file" bash syntax error with no size hint anywhere in it."""
    _require_bash()
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name
    try:
        return subprocess.run(["bash", script_path], capture_output=True, text=True, **kwargs)
    finally:
        Path(script_path).unlink(missing_ok=True)


def _p(path: Path) -> str:
    """Windows backslash paths break bash's own string ops (rel_path
    stripping, dirname); Git Bash/MSYS accepts the forward-slash form."""
    return path.as_posix()


def test_reclaimed_lock_is_verified_before_deletion_not_trusted_by_path(tmp_path):
    """Tier-3 review, PR #796 round 8: `mv "$lock" "$discard"` claims
    WHATEVER currently sits at "$lock", not verifiably the specific stale
    instance a reclaimer just read the pid of — an ABA race. Another
    reclaimer can remove the stale lock and a genuinely fresh, live one can
    install at the same path in the gap between that read and this mv, and
    the mv would then silently steal (and, before this fix, delete) the live
    replacement instead. Checked structurally: reproducing the actual
    four-process interleaving needs real OS thread scheduling a unit test
    can't reliably force. The fix must read the claimed instance's own pid
    back and compare it to what was expected before deciding to discard it,
    and restore (not delete) on a mismatch."""
    body = _extract("_atomic_sync_dir")
    mv_idx = body.index('if mv "$lock" "$discard" 2>/dev/null; then')
    tail = body[mv_idx:]
    assert re.search(r'claimed_pid=\$\(cat "\$discard/pid"', tail), (
        "expected the claimed instance's pid to be re-read after the mv, "
        "before deciding whether it is safe to discard")
    assert re.search(r'\[ "\$claimed_pid" = "\$holder_pid" \]', tail), (
        "expected the re-read pid to be compared against the one observed before the mv")
    assert re.search(r'mv "\$discard" "\$lock"', tail), (
        "expected a mismatched (live, replacement) claim to be restored, not deleted outright")


def test_release_guard_does_not_delete_a_lock_it_does_not_own(tmp_path):
    """Tier-3 review, PR #796 round 9 (10th round): the round-8 fix's own
    restore-failure fallback only ever discarded the privately-named
    `$discard` path, but never addressed the deeper flaw — the ORIGINAL lock
    owner's own eventual release (both the normal completion path and the
    EXIT trap) has never verified ownership before deleting, since round 1.
    If a restore race (round 8) orphans this process's own lock and a
    genuinely different, live process installs its own lock at the same
    path, this process's later unconditional `rm -rf "$lock"` would delete
    THAT live lock out from under its rightful owner, cascading the exact
    corruption locking exists to prevent. Extracts the actual release line
    used at the normal completion site (verbatim, so a future edit that
    silently drops the guard fails this test) and runs it directly against a
    lock this process demonstrably does not own — it must survive."""
    m = re.search(_RELEASE_GUARD_RE, _SRC)
    assert m, "release guard line not found verbatim in update-marketplace.sh — has it changed shape?"
    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()
    (lock / "pid").write_text("99999999", encoding="utf-8")

    script = ("set -euo pipefail\n" + _extract("_lock_is_owned_by") + "\n"
              + f'lock="{_p(lock)}"\n' + m.group(0) + "\n")
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert lock.exists(), "the release guard deleted a lock it does not own"


def test_release_guard_deletes_a_lock_it_does_own(tmp_path):
    """Companion to the test above: confirms the guard isn't just trivially
    inert (never deleting anything) — a lock genuinely stamped with this
    process's own pid must still be released as before."""
    m = re.search(_RELEASE_GUARD_RE, _SRC)
    assert m, "release guard line not found verbatim in update-marketplace.sh — has it changed shape?"
    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()

    script = ("set -euo pipefail\n" + _extract("_lock_is_owned_by") + "\n"
              + f'lock="{_p(lock)}"\n' + 'echo "$$" > "' + _p(lock) + '/pid"\n' + m.group(0) + "\n")
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert not lock.exists(), "the release guard failed to delete a lock this process genuinely owns"


def test_exit_trap_verifies_ownership_before_deleting():
    """The script-wide EXIT trap is the OTHER unconditional-release site the
    round-9 review flagged — it must go through the same ownership check as
    the normal completion path, not just trust `_CURRENT_SYNC_LOCK` by path."""
    trap_line = re.search(r"^trap '.*' EXIT$", _SRC, flags=re.MULTILINE)
    assert trap_line, "EXIT trap registration not found — has it moved or changed shape?"
    assert "_lock_is_owned_by" in trap_line.group(0), (
        "the EXIT trap must verify ownership via _lock_is_owned_by before deleting "
        "_CURRENT_SYNC_LOCK, not delete it by path alone")
