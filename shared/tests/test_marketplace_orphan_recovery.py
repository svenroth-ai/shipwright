"""Behavioral tests for update-marketplace.sh's orphaned-backup recovery.

Split out of ``test_marketplace_atomic_sync_dir.py`` when it crossed the
300-line guideline (round 22) — general sync/swap/prune behavior stays there;
this file covers only recovering ``$dst`` from a crashed process's leftover
``.sync-old.*`` backup.

Extracts the function (and its ``sync_dir_from_to`` wrapper) out of the real
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
    """`_atomic_sync_dir` calls `_pid_is_alive`, `_leftover_pid_is_alive`,
    `_lock_is_owned_by`, `_new_claim_token`, and `_find0_to_file`, separate
    top-level functions — without extracting them too, every fixture run
    would fail on "command not found" instead of exercising the lock."""
    script = ("set -euo pipefail\n" + _extract("_pid_is_alive") + "\n"
              + _extract("_leftover_pid_is_alive") + "\n"
              + _extract("_lock_is_owned_by") + "\n"
              + _extract("_new_claim_token") + "\n"
              + _extract("_find0_to_file") + "\n"
              + _extract("_atomic_sync_dir") + "\n" + _extract("sync_dir_from_to") + "\n" + body)
    return _run_script(script)


def _p(path: Path) -> str:
    """Windows backslash paths break bash's own string ops (rel_path
    stripping, dirname); Git Bash/MSYS accepts the forward-slash form."""
    return path.as_posix()


def test_orphaned_backup_is_recovered_before_the_sweep_would_discard_it(tmp_path):
    """Tier-3 review, PR #796 round 2: a crash between the swap's two `mv`s
    leaves $dst MISSING with its only backup sitting in a dead process's
    $old. Simulate exactly that and confirm noprune's dst-only preservation
    still sees the old content — provable only if it was recovered into
    $dst before that step runs, not discarded by the leftover sweep."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep.py").write_text("a", encoding="utf-8")
    # No dst/ at all — simulates dst having already been renamed away.
    orphan = dst.parent / (dst.name + ".sync-old.99999999")
    orphan.mkdir()
    (orphan / "mirror_owned.py").write_text("b", encoding="utf-8")

    res = _run(f'sync_dir_from_to "{_p(src)}" "{_p(dst)}"')

    assert res.returncode == 0, res.stderr
    assert (dst / "keep.py").exists()
    assert (dst / "mirror_owned.py").exists(), "the orphaned backup's content was lost, not recovered"


def test_orphan_backup_survives_when_its_pid_suffix_matches_our_own_pid(tmp_path):
    """Tier-3 review, PR #796 round 22, data-loss finding: `_pid_is_alive("$$")`
    is trivially true (it asks whether we ourselves are alive), so a leftover
    `.sync-old.<PID>` whose PID happens to equal our OWN "$$" -- exactly what
    the OS produces whenever a dead process's PID gets recycled onto us --
    used to be treated as "still live" and skipped by both the missing-$dst
    recovery loop and the dead-leftover sweep. $dst then stayed missing, and
    the swap's own unguarded `rm -rf "$old"` -- computed as that SAME
    "${dst}.sync-old.$$" path -- deleted the leftover outright before ever
    reaching the `mv "$staging" "$dst"` that would have replaced it,
    permanently destroying the only remaining copy of the previous
    destination. Creates the orphan from INSIDE the generated script, after
    "$$" is known, so its PID suffix is guaranteed to match what
    `_atomic_sync_dir` sees -- a real fixed PID like the other orphan test
    uses can't reproduce a same-PID collision at all."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep.py").write_text("a", encoding="utf-8")
    # No dst/ at all -- simulates dst having already been renamed away by a
    # process that then crashed before the final `mv "$staging" "$dst"`.

    script = ("set -euo pipefail\n"
              + _extract("_pid_is_alive") + "\n"
              + _extract("_leftover_pid_is_alive") + "\n"
              + _extract("_lock_is_owned_by") + "\n"
              + _extract("_new_claim_token") + "\n"
              + _extract("_find0_to_file") + "\n"
              + _extract("_atomic_sync_dir") + "\n" + _extract("sync_dir_from_to") + "\n"
              + f'orphan="{_p(dst)}.sync-old.$$"\n'
              + 'mkdir -p "$orphan"\n'
              + 'echo b > "$orphan/mirror_owned.py"\n'
              + f'sync_dir_from_to "{_p(src)}" "{_p(dst)}"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert (dst / "keep.py").exists()
    assert (dst / "mirror_owned.py").exists(), (
        "the orphaned backup was destroyed instead of recovered when its PID "
        "suffix coincided with this process's own $$")


def test_orphan_backup_is_recovered_when_its_pid_suffix_belongs_to_an_unrelated_live_process(tmp_path):
    """Tier-3 review, PR #796 round 26, data-loss finding: PID reuse cuts the
    other way from round 22's same-PID case too -- an orphan's PID suffix can
    coincidentally match some OTHER, completely unrelated process that is
    genuinely alive right now, with no connection to this sync at all.
    `_leftover_pid_is_alive` used to read that as "still owned" and skip
    recovering the orphan, even though holding "$lock" for this exact $dst
    already rules out any legitimate CONCURRENT owner of its ".sync-old.*" --
    a raw pid-liveness check can never distinguish that from an unrelated
    coincidence, so recovery must not depend on it at all. Simulate the
    unrelated live process with a real background `sleep` and confirm the
    orphan is still recovered."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep.py").write_text("a", encoding="utf-8")
    # No dst/ at all -- simulates dst having already been renamed away by a
    # process that then crashed before the final `mv "$staging" "$dst"`.

    script = ("set -euo pipefail\n"
              + _extract("_pid_is_alive") + "\n"
              + _extract("_leftover_pid_is_alive") + "\n"
              + _extract("_lock_is_owned_by") + "\n"
              + _extract("_new_claim_token") + "\n"
              + _extract("_find0_to_file") + "\n"
              + _extract("_atomic_sync_dir") + "\n" + _extract("sync_dir_from_to") + "\n"
              + "sleep 30 & unrelated=$!\n"
              + f'orphan="{_p(dst)}.sync-old.$unrelated"\n'
              + 'mkdir -p "$orphan"\n'
              + 'echo b > "$orphan/mirror_owned.py"\n'
              + f'sync_dir_from_to "{_p(src)}" "{_p(dst)}"\n'
              + 'kill "$unrelated" 2>/dev/null || true\n')
    res = _run_script(script, timeout=30)

    assert res.returncode == 0, res.stderr
    assert (dst / "keep.py").exists()
    assert (dst / "mirror_owned.py").exists(), (
        "the orphaned backup was skipped instead of recovered because its "
        "PID suffix coincidentally belonged to an unrelated, currently-alive "
        "process")
