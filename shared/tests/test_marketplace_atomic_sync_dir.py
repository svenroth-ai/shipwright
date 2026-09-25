"""Behavioral tests for update-marketplace.sh's ``_atomic_sync_dir`` helper.

Lock acquisition and staleness reclamation live in the sibling
``test_marketplace_sync_lock.py``, and orphaned-backup recovery lives in
``test_marketplace_orphan_recovery.py`` (split out when this file crossed the
300-line guideline, round 22) — this file covers the general sync/swap
behavior: pycache/venv preservation and pruning.

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
    `_lock_is_owned_by`, `_new_claim_token`, and `_find0_to_file` (its lock's
    liveness, leftover liveness, ownership, per-claim-identity, and
    enumeration-checking helpers), separate top-level functions — without
    extracting them too, every fixture run would fail on "command not found"
    instead of exercising the lock."""
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


def test_noprune_preserves_a_dst_file_the_copy_loop_excludes_by_name_even_when_src_also_has_it(tmp_path):
    """Tier-3 review, PR #796 round 3: the noprune preservation step checked
    `[ ! -f "$src/$rel" ]` — true only when $src altogether lacks the file.
    A `.python-version` present in BOTH trees is never copied (the copy
    loop's own `-not -name` exclusion refuses it), so it was never staged
    either, yet that check saw it as "present in src" and skipped preserving
    it too — silently dropping a file the old pure-copy mirror always kept.
    noprune has no distribution policy to justify that; only prune mode does."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "keep.py").write_text("a", encoding="utf-8")
    (src / ".python-version").write_text("3.11.15", encoding="utf-8")
    dst.mkdir()
    (dst / ".python-version").write_text("3.11.15", encoding="utf-8")

    res = _run(f'sync_dir_from_to "{_p(src)}" "{_p(dst)}"')

    assert res.returncode == 0, res.stderr
    assert (dst / "keep.py").exists()
    assert (dst / ".python-version").exists(), (
        "excluded-by-name file present in both trees was dropped instead of preserved")


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


def test_source_enumeration_failure_aborts_before_the_swap(tmp_path):
    """Tier-3 review, PR #796 round 17: `while read < <(find ...)` never
    surfaces find's own exit status — the process substitution runs in a
    background subshell the calling command's `$?` (and `set -e`) know
    nothing about, so a `find` that dies partway through a scan (permission
    error, interrupted read) was silently indistinguishable from one that
    legitimately enumerated everything, and the swap below would still
    replace $dst with an INCOMPLETE staging tree. Reproduced with a stubbed
    `find` that always fails, simulating a scan that dies immediately: the
    sync must report failure and abort before ever touching $dst, leaving
    its original content untouched and never publishing $src's own file."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "new_file.py").write_text("new", encoding="utf-8")
    dst.mkdir()
    (dst / "original.py").write_text("original", encoding="utf-8")

    script = ("set -euo pipefail\n"
              + _extract("_pid_is_alive") + "\n"
              + _extract("_leftover_pid_is_alive") + "\n"
              + _extract("_lock_is_owned_by") + "\n"
              + _extract("_new_claim_token") + "\n"
              + _extract("_find0_to_file") + "\n"
              + _extract("_atomic_sync_dir") + "\n"
              + 'find() { return 1; }\n'  # simulate an enumeration scan that dies
              + f'if _atomic_sync_dir "{_p(src)}" "{_p(dst)}" label; then\n'
              + '    echo "SYNC_RESULT=succeeded"\n'
              + 'else\n'
              + '    echo "SYNC_RESULT=failed"\n'
              + 'fi\n'
              + f'echo "ORIGINAL_SURVIVED=$([ -f "{_p(dst)}/original.py" ] && echo yes || echo no)"\n'
              + f'echo "NEW_FILE_LEAKED=$([ -f "{_p(dst)}/new_file.py" ] && echo yes || echo no)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "SYNC_RESULT=failed" in res.stdout, (
        "an enumeration failure must make _atomic_sync_dir report failure, not silently "
        "succeed with an incomplete result — " + res.stdout)
    assert "ORIGINAL_SURVIVED=yes" in res.stdout, (
        "the original destination content was lost even though enumeration failed before "
        "any swap should have happened — " + res.stdout)
    assert "NEW_FILE_LEAKED=no" in res.stdout, (
        "the swap ran despite a failed enumeration, publishing an incomplete destination — "
        + res.stdout)


def test_source_file_matching_the_internal_listing_name_survives_the_sync(tmp_path):
    """Tier-3 review, PR #796 round 20: the enumeration listing used to live
    at "$staging/.find-files" -- inside the tree being published -- so a
    legitimate source file happening to share that exact name would collide
    with it (lost content, or a hard failure on Windows, where overwriting a
    file another handle still has open for reading is refused outright). The
    listing now lives at "${dst}.find-list.$$", a sibling of $dst never
    reachable by anything under $src, so a source file using that literal
    old name is just an ordinary file to sync."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / ".find-files").write_text("legitimate source content", encoding="utf-8")
    (src / "other.py").write_text("other", encoding="utf-8")

    res = _run(f'_atomic_sync_dir "{_p(src)}" "{_p(dst)}" label')

    assert res.returncode == 0, res.stderr
    assert (dst / "other.py").exists()
    assert (dst / ".find-files").exists(), (
        "a source file sharing the old internal listing name was lost")
    assert (dst / ".find-files").read_text(encoding="utf-8") == "legitimate source content", (
        "the source file's content was overwritten by the sync's own internal "
        "enumeration listing")
