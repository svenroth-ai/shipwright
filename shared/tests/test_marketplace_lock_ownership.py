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
_INITIAL_PID_WRITE_RE = r'\(set -C; echo "\$\$" > "\$lock/pid"\) 2>/dev/null'


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
    and restore (not delete) on a mismatch — via `mkdir`, not a
    directory-to-directory `mv` (round 11: see the test below for why)."""
    body = _extract("_atomic_sync_dir")
    mv_idx = body.index('if mv "$lock" "$discard" 2>/dev/null; then')
    tail = body[mv_idx:]
    assert re.search(r'claimed_pid=\$\(cat "\$discard/pid"', tail), (
        "expected the claimed instance's pid to be re-read after the mv, "
        "before deciding whether it is safe to discard")
    assert re.search(r'\[ "\$claimed_pid" = "\$holder_pid" \]', tail), (
        "expected the re-read pid to be compared against the one observed before the mv")
    assert re.search(r'elif mkdir "\$lock" 2>/dev/null; then', tail), (
        "expected a mismatched (live, replacement) claim to be restored via a fresh "
        "`mkdir \"$lock\"` claim, not deleted outright")
    assert re.search(r'set -C; cat "\$discard/pid" > "\$lock/pid"', tail), (
        "expected only the pid FILE's content to be noclobber-written into the "
        "freshly mkdir'd lock, not the whole $discard directory nor an unprotected mv")


def test_restore_never_uses_a_directory_to_directory_mv(tmp_path):
    """Tier-3 review, PR #796 round 11 (11th round): a plain (non `-T`) `mv`
    onto an existing directory target does not fail — it moves the source
    INSIDE the target instead. `mv "$discard" "$lock"` therefore does not
    reliably signal "restore failed" when "$lock" has been re-claimed by yet
    another process in the gap since our own claiming mv: it silently nests
    the mismatched claim under the new live lock rather than restoring it to
    the top level or failing loudly, and the round-8/9 code's own `elif !
    mv ...` assumed a failure signal this never reliably gives for a
    directory target. `-T` (which prevents that "move into" behavior) is the
    GNU-only flag round 6 already rejected for breaking every lock attempt
    on BSD/macOS, so the fix must not reintroduce a bare directory `mv` as
    the restore mechanism at all."""
    body = _extract("_atomic_sync_dir")
    mv_idx = body.index('if mv "$lock" "$discard" 2>/dev/null; then')
    tail = body[mv_idx:]
    # Comments are allowed to mention the rejected pattern as prose (this
    # file's own fix comment does, explaining what NOT to do) — only actual
    # code lines matter here.
    code_lines = "\n".join(line for line in tail.splitlines() if not line.strip().startswith("#"))
    assert not re.search(r'mv "\$discard" "\$lock"(?!/)', code_lines), (
        'restore must never use a bare directory-to-directory `mv "$discard" "$lock"` — '
        'it does not reliably fail when "$lock" already exists again, silently nesting '
        "the claim instead of restoring or failing loudly")


def test_restore_does_not_nest_a_mismatched_claim_under_a_reclaimed_lock(tmp_path):
    """Behavioral reproduction of the round-11 interleaving the review asked
    for a test of. The full reclaim block's OWN first statement is `mv
    "$lock" "$discard"`, which itself vacates "$lock" — so a THIRD process
    can only ever install a fresh lock there in the gap AFTER that mv and
    BEFORE the restore attempt, a window real concurrency can't be forced
    into on demand. Reproduced deterministically instead by constructing
    that exact post-race state directly: `$discard` pre-populated as
    already-claimed-and-mismatched, and a fresh lock already sitting at
    "$lock" as if a third process had won that gap — then running only the
    mismatch-handling code that follows the initial claim, unmodified from
    the real script. The third process's own live pid must survive
    untouched at the top level, and the mismatched claim must never end up
    nested as a subdirectory inside it."""
    body = _extract("_atomic_sync_dir")
    start = body.index("local claimed_pid")
    end = body.index('\n                fi\n', start) + len('\n                fi\n')
    mismatch_block = body[start:end]

    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()
    (lock / "pid").write_text("third_process_pid", encoding="utf-8")
    discard = tmp_path / "dst.sync.lock.stale.12345"
    discard.mkdir()
    (discard / "pid").write_text("live_replacement_pid", encoding="utf-8")

    script = ("set -euo pipefail\n"
              + f'lock="{_p(lock)}"\n' + f'discard="{_p(discard)}"\n'
              + 'holder_pid="99999999"\n'  # what this process originally observed, now stale
              + "_reclaim() {\n" + mismatch_block + "\n}\n_reclaim\n"
              + f'echo "LIVE_PID=$(cat "{_p(lock)}/pid" 2>/dev/null || echo MISSING)"\n'
              + f'echo "NESTED_COUNT=$(find "{_p(lock)}" -mindepth 1 -maxdepth 1 -type d | wc -l)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "LIVE_PID=third_process_pid" in res.stdout, (
        "the third process's own live lock pid was overwritten or lost — " + res.stdout)
    assert "NESTED_COUNT=0" in res.stdout, (
        "the mismatched claim ended up nested as a subdirectory inside the live lock "
        "instead of being safely discarded — " + res.stdout)


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


def test_initial_pid_write_does_not_overwrite_a_replacement_lock(tmp_path):
    """Tier-3 review, PR #796 round 12: the grace-period reclamation (sibling
    file's test_persistently_empty_lock_is_reclaimed_after_grace_period)
    treats an empty "$lock" as abandoned after a bounded silence — but a
    merely PAUSED (not dead) installer can resume AFTER another process has
    already reclaimed and repopulated that same path with its own live
    claim. A plain `echo "$$" > "$lock/pid"` would then silently overwrite
    the new owner's pid with the paused process's own, letting both believe
    they hold the lock and sync the same $dst concurrently. Extracts the
    actual pid-write line verbatim (so a future edit that drops the
    noclobber guard fails this test) and runs it directly against a lock
    already populated by someone else — it must fail, leaving the existing
    owner's pid untouched."""
    m = re.search(_INITIAL_PID_WRITE_RE, _SRC)
    assert m, "noclobber pid-write line not found verbatim in update-marketplace.sh — has it changed shape?"
    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()
    (lock / "pid").write_text("replacement_owner_pid", encoding="utf-8")

    script = "set -euo pipefail\n" + f'lock="{_p(lock)}"\n' + m.group(0) + "\n"
    res = _run_script(script)

    assert res.returncode != 0, "the noclobber pid-write must fail when the lock is already owned"
    assert (lock / "pid").read_text(encoding="utf-8") == "replacement_owner_pid", (
        "the replacement owner's pid was overwritten by the paused process's own write")


def test_initial_pid_write_succeeds_on_a_freshly_claimed_lock(tmp_path):
    """Companion to the test above: confirms the noclobber guard isn't just
    trivially inert (never succeeding) — the normal, uncontested fast path
    (nobody else has touched the lock since this process's own `mkdir`)
    must still write the pid as before."""
    m = re.search(_INITIAL_PID_WRITE_RE, _SRC)
    assert m, "noclobber pid-write line not found verbatim in update-marketplace.sh — has it changed shape?"
    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()

    script = "set -euo pipefail\n" + f'lock="{_p(lock)}"\n' + m.group(0) + "\n"
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert (lock / "pid").read_text(encoding="utf-8").strip() != "", (
        "the pid was not written on the uncontested fast path")


def test_failed_pid_write_resets_current_sync_lock_and_retries():
    """A process that loses the noclobber race above must not proceed as if
    it holds the lock — `_CURRENT_SYNC_LOCK` (which the EXIT trap uses to
    decide what to clean up) must be reset, and acquisition must retry from
    scratch (`continue`), never fall through to the sync body as if it had
    `break`-en out with a genuine claim."""
    body = _extract("_atomic_sync_dir")
    mkdir_idx = body.index('if mkdir "$lock" 2>/dev/null; then')
    write_idx = body.index('(set -C; echo "$$" > "$lock/pid")', mkdir_idx)
    tail = body[write_idx:]
    reset_idx = tail.index('_CURRENT_SYNC_LOCK=""')
    continue_idx = tail.index("continue")
    assert reset_idx < continue_idx, (
        "expected _CURRENT_SYNC_LOCK to be reset before retrying acquisition "
        "after losing the noclobber race")
