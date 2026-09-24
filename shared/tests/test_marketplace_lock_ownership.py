"""Behavioral tests for update-marketplace.sh's ABA claim-and-restore
mismatch handling.

Split out of ``test_marketplace_sync_lock.py`` (which crossed the 300-line
guideline) along the seam the round-8/9 review findings drew, then split
again into ``test_marketplace_lock_guards.py`` (release-site and pid-write
ownership guards, rounds 9/12) when this file itself crossed the guideline
a second time, and a third time into ``test_marketplace_lock_reclaim_paths.py``
(discard-path naming and uniqueness, rounds 14/16) when it crossed the
guideline yet again. This file covers only the mismatch-handling mechanism
itself: discovering a mismatch (round 8's ABA race) after a discard path is
already claimed, and either restoring or safely preserving what was
mistakenly claimed (rounds 11/13/15). Acquisition and staleness reclamation
stay in the ``test_marketplace_sync_lock.py`` sibling file; the discard
path's own naming and collision handling live in
``test_marketplace_lock_reclaim_paths.py``.

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
              + 'holder_token=""\n'  # unused here: the pid alone already mismatches
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


def test_mismatch_restore_failure_preserves_discard_instead_of_deleting_it(tmp_path):
    """Tier-3 review, PR #796 round 13: when a mismatched (live, replacement)
    claim's restore cannot complete — here because "$lock" is already
    occupied again by the time this restore's own `mkdir` runs, the same
    end-state the round-11 nesting test above constructs — $discard may
    still hold a live replacement lock this process's earlier claiming `mv`
    accidentally stole from its rightful owner. The pre-fix code
    unconditionally `rm -rf`'d $discard in this branch, destroying that
    owner's only remaining trace with no way to recover it. The fix leaves
    $discard in place for the existing leftover sweep to reap once THIS
    process (never the stolen claim's own owner) is confirmed dead."""
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
              + 'holder_pid="99999999"\n'
              + 'holder_token=""\n'  # unused here: the pid alone already mismatches
              + "_reclaim() {\n" + mismatch_block + "\n}\n_reclaim\n"
              + f'echo "DISCARD_SURVIVED=$([ -d "{_p(discard)}" ] && echo yes || echo no)"\n'
              + f'echo "DISCARD_PID=$(cat "{_p(discard)}/pid" 2>/dev/null || echo MISSING)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "DISCARD_SURVIVED=yes" in res.stdout, (
        "the mismatched claim's stolen pid was deleted instead of preserved — " + res.stdout)
    assert "DISCARD_PID=live_replacement_pid" in res.stdout, (
        "the mismatched claim's content was lost — " + res.stdout)


def test_pid_reuse_does_not_defeat_the_mismatch_check(tmp_path):
    """Tier-3 review, PR #796 round 15: comparing only the re-read pid
    against the pid originally observed is not a reliable "same instance"
    check — the OS recycles pid numbers, so a genuinely different live
    replacement can coincidentally carry the SAME numeric pid the stale
    instance had. Under a pid-only comparison this looks identical to
    "nothing changed, safe to discard", and the live replacement would be
    deleted exactly like the round-8 ABA race this mechanism already
    defends against — just via pid coincidence instead of a stale-lock
    removal race. Reproduced directly: a discard whose claimed pid matches
    what was originally observed, but whose token (a random per-claim
    identity paired with every pid write, effectively never repeated across
    genuinely different claims) does not — the mismatch must still be
    detected and the claim restored, never discarded."""
    body = _extract("_atomic_sync_dir")
    start = body.index("local claimed_pid")
    end = body.index('\n                fi\n', start) + len('\n                fi\n')
    mismatch_block = body[start:end]

    lock = tmp_path / "dst.sync.lock"  # deliberately absent: the restore's own mkdir must succeed
    discard = tmp_path / "dst.sync.lock.stale.12345"
    discard.mkdir()
    (discard / "pid").write_text("99999999", encoding="utf-8")
    (discard / "token").write_text("live_replacement_token", encoding="utf-8")

    script = ("set -euo pipefail\n"
              + f'lock="{_p(lock)}"\n' + f'discard="{_p(discard)}"\n'
              + 'holder_pid="99999999"\n'  # coincidentally the SAME pid, via reuse
              + 'holder_token="original_stale_token"\n'  # but NOT the same claim
              + "_reclaim() {\n" + mismatch_block + "\n}\n_reclaim\n"
              + f'echo "LOCK_PID=$(cat "{_p(lock)}/pid" 2>/dev/null || echo MISSING)"\n'
              + f'echo "LOCK_TOKEN=$(cat "{_p(lock)}/token" 2>/dev/null || echo MISSING)"\n'
              + f'echo "DISCARD_SURVIVED=$([ -d "{_p(discard)}" ] && echo yes || echo no)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "LOCK_PID=99999999" in res.stdout, (
        "the live replacement (matched on pid alone, via reuse) was deleted instead of "
        "restored — " + res.stdout)
    assert "LOCK_TOKEN=live_replacement_token" in res.stdout, (
        "the live replacement's token was not restored alongside its pid — " + res.stdout)
    assert "DISCARD_SURVIVED=no" in res.stdout, (
        "expected the restore to complete and clean up $discard, not fall into the "
        "leave-it-behind failure path — " + res.stdout)
