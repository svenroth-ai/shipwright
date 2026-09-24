"""Behavioral tests for update-marketplace.sh's ``_atomic_sync_dir`` helper.

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
    """`_atomic_sync_dir` calls `_pid_is_alive` (its lock's liveness check),
    a separate top-level function — without extracting it too, every fixture
    run would fail on "command not found" instead of exercising the lock."""
    script = ("set -euo pipefail\n" + _extract("_pid_is_alive") + "\n"
              + _extract("_atomic_sync_dir") + "\n" + _extract("sync_dir_from_to") + "\n" + body)
    return _run_script(script)


def _p(path: Path) -> str:
    """Windows backslash paths break bash's own string ops (rel_path
    stripping, dirname); Git Bash/MSYS accepts the forward-slash form."""
    return path.as_posix()


def test_pycache_venv_and_pytest_cache_survive_the_swap(tmp_path):
    """iterate-2026-09-24-stop-hook-cache-race review round 2: an earlier
    revision excluded these from the SEED loop, so the wholesale directory
    replacement silently deleted a plugin's own built .venv on every sync."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "a.py").write_text("a", encoding="utf-8")
    for d in ("__pycache__", ".venv/lib/__pycache__", ".pytest_cache"):
        (dst / d).mkdir(parents=True)
    (dst / "__pycache__" / "a.pyc").write_text("x", encoding="utf-8")
    (dst / ".venv" / "lib" / "site.py").write_text("x", encoding="utf-8")
    # A __pycache__ NESTED inside .venv must not be double-copied (both
    # matching find's prune pattern independently) nor missed (pruned away
    # entirely) — the outer .venv copy alone must carry it.
    (dst / ".venv" / "lib" / "__pycache__" / "site.pyc").write_text("x", encoding="utf-8")
    (dst / ".pytest_cache" / "v").write_text("x", encoding="utf-8")

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    assert (dst / "sub" / "a.py").exists()
    assert (dst / "__pycache__" / "a.pyc").exists(), "the plugin's own bytecode cache was deleted"
    assert (dst / ".venv" / "lib" / "site.py").exists(), "the plugin's own .venv was deleted"
    assert (dst / ".venv" / "lib" / "__pycache__" / "site.pyc").exists(), "nested __pycache__ inside .venv was lost"
    assert (dst / ".pytest_cache" / "v").exists()


def test_github_directory_is_not_mistaken_for_git(tmp_path):
    """A directory-skeleton exclusion of `*/.git*` (no trailing slash) also
    matches `.github` — leaving it uncreated in staging while the file-copy
    loop, whose own exclusion correctly ends `.git/*`, still tries to copy
    into it (`cp: ... No such file or directory`). Reproduced live via a
    plugin's `.github/workflows/` test fixture (round 4 of this fix)."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / ".github" / "workflows").mkdir(parents=True)
    (src / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    assert (dst / ".github" / "workflows" / "ci.yml").exists()


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


def test_lock_is_installed_atomically_not_mkdir_then_stamped():
    """Tier-3 review, PR #796 round 2: a bare `mkdir "$lock"` immediately
    followed by writing its PID left a window where a concurrent reader saw
    the lock with no PID yet, called it stale, and stole it out from under a
    process that still believed it held it. The PID must be written into a
    PRIVATE candidate dir BEFORE the one atomic rename that installs it —
    checked structurally since reproducing the actual race needs real OS
    thread interleaving a unit test can't reliably force."""
    body = _extract("_atomic_sync_dir")
    code_lines = [line for line in body.splitlines() if not line.strip().startswith("#")]
    assert not any('mkdir "$lock"' in line for line in code_lines), (
        'a bare `mkdir "$lock"` reintroduces the pid-less window this guards against')
    assert re.search(r'mv -T "\$candidate" "\$lock"', body), (
        "expected the lock to be installed via one atomic rename of a fully-formed candidate")


def test_source_root_is_not_mkdirred_as_a_bogus_nested_path(tmp_path):
    """`${dir#$src/}` doesn't strip $src itself (no trailing slash on $src to
    match against), so without `-mindepth 1` on the directory-skeleton scan,
    every sync mkdir'd the whole absolute source path as a junk empty
    directory tree inside staging (Tier-3 review, PR #796 round 2)."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "a.py").write_text("a", encoding="utf-8")

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    top_level = sorted(p.name for p in dst.iterdir())
    assert top_level == ["sub"], (
        f"expected only 'sub' at the destination root, found {top_level} — "
        "the source root itself was likely mkdir'd as a bogus nested path")


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


def test_default_prune_removes_files_absent_from_source(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep.py").write_text("a", encoding="utf-8")
    dst.mkdir()
    (dst / "stale.py").write_text("b", encoding="utf-8")

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    assert (dst / "keep.py").exists()
    assert not (dst / "stale.py").exists()


def test_sync_dir_from_to_does_not_prune_unrelated_files(tmp_path):
    """The Windows real-dir plugin-symlink fallback only ever copied; giving
    it the cache-sync's prune semantics would newly delete mirror-owned or
    user-added files it previously left alone."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep.py").write_text("a", encoding="utf-8")
    dst.mkdir()
    (dst / "user_added.py").write_text("b", encoding="utf-8")

    res = _run(f'sync_dir_from_to "{_p(src)}" "{_p(dst)}"')

    assert res.returncode == 0, res.stderr
    assert (dst / "keep.py").exists()
    assert (dst / "user_added.py").exists(), "sync_dir_from_to must not prune"
