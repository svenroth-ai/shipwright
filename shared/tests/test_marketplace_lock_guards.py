"""Behavioral tests for update-marketplace.sh's WRITE-time lock guards.

Split out of ``test_marketplace_lock_ownership.py`` (which crossed the
300-line guideline again) along the seam the round-9/12 review findings
drew: this file covers guarding a WRITE against an ownership mistake —
the release-site guard (`_lock_is_owned_by`, round 9) used at both the
normal completion path and the script-wide EXIT trap, the noclobber
pid-write guard (round 12) that protects the initial claim against a
paused installer, and the round-24 cleanup that applies that same
release-site guard to a claim abandoned mid-write. The ABA-claim-and-restore
mismatch-handling mechanism (rounds 8/11/13) stays in the sibling file.

Extracts functions/lines out of the real script and drives them against
fixture trees under ``bash``, rather than sourcing the whole script (which
would immediately try to fetch the real marketplace). The closing brace of
a top-level function sits at column 0; an inner loop/if's closing brace is
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


def test_partial_claim_with_a_failed_token_write_cleans_up_its_own_pid_stamped_lock(tmp_path):
    """Tier-3 review, PR #796 round 24: once the pid write inside a fresh
    claim succeeds, a failure on the very next token write used to just
    reset `_CURRENT_SYNC_LOCK` and retry, ABANDONING "$lock" -- but it can
    already be stamped with THIS process's own live pid by then. A THIRD
    process can have read this same "$lock" as empty-pid BEFORE our write
    landed, reached its own grace-period reclaim, and completed its
    claiming `mv` -- stealing the directory, pid file and all -- before our
    token write runs; finding our now-nonempty pid a mismatch against what
    it originally observed, it treats ours as a live claim worth protecting
    and restores it via a fresh `mkdir "$lock"`, which can already carry an
    (empty) token file by the time our own noclobber token write reaches
    it, failing it even though our pid write genuinely succeeded. Left
    abandoned, a lock bearing our own pid reads as "live" to every future
    check -- including this same process's own very next acquisition
    attempt -- so nothing would recognize it as reclaimable short of the
    full 120s timeout. Reproduced by stubbing the token generator to fail
    on the first call only (the precise cause doesn't matter to this fix;
    only that the pid write succeeded and the token write then failed) and
    confirming the claim attempt cleans up its own stamped lock instead of
    leaving it behind."""
    lock = tmp_path / "dst.sync.lock"
    body = _extract("_atomic_sync_dir")
    start = body.index('if mkdir "$lock" 2>/dev/null; then')
    end = body.index('_CURRENT_SYNC_LOCK=""\n            continue\n        fi') + len(
        '_CURRENT_SYNC_LOCK=""\n            continue\n        fi')
    claim_snippet = body[start:end]

    call_count_file = tmp_path / "call_count"
    # `$(_new_claim_token)` (well, its redirection form) runs inside the
    # `(set -C; ...)` SUBSHELL the real code wraps it in — a plain variable
    # increment inside the stub never reaches the parent script, so the
    # counter has to live in a file instead (same trap round 16's own test
    # hit for the same reason).
    script = (
        "set -uo pipefail\n"  # no -e: the snippet's bare `continue` outside
        # a loop "fails" here on purpose, matching the sibling reclaim-path
        # tests that extract the same kind of loop-body snippet.
        + _extract("_lock_is_owned_by") + "\n"
        + f'call_count_file="{_p(call_count_file)}"\n'
        + 'echo 0 > "$call_count_file"\n'
        + '_new_claim_token() {\n'
        + '    local n\n'
        + '    n=$(($(cat "$call_count_file") + 1))\n'
        + '    echo "$n" > "$call_count_file"\n'
        + '    [ "$n" -eq 1 ] && return 1\n'
        + '    printf "tok-%s" "$n"\n'
        + '}\n'
        + f'lock="{_p(lock)}"\n'
        + '_CURRENT_SYNC_LOCK=""\n'
        + claim_snippet + "\n"
        + 'echo "ABANDONED_LOCK_SURVIVED=$([ -d "$lock" ] && echo yes || echo no)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "ABANDONED_LOCK_SURVIVED=no" in res.stdout, (
        "a lock this process's own pid write landed in, but whose token write then failed, "
        "was abandoned instead of cleaned up — " + res.stdout)
