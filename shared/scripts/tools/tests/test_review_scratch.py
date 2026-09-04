"""Unit tests for scripts.lib.review_scratch, plus one cross-process
contract test pinning the actual regression this module exists to close —
see iterate-2026-09-03-review-scratch-path."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.lib import review_scratch as rs  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI = _REPO_ROOT / "shared" / "scripts" / "tools" / "review_scratch.py"


def _bash() -> str:
    """Find the Bash paired with Git when Windows exposes only git.exe."""
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            candidate = Path(os.environ.get(variable, "")) / "Git" / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    resolved = shutil.which("bash")
    if resolved:
        return resolved
    pytest.skip("bash is required to exercise the shell trap pattern")
    raise AssertionError("pytest.skip() must not return")


def _patch_base(monkeypatch, tmp_path, *, subdir="base"):
    base = tmp_path / subdir
    monkeypatch.setattr(rs, "_private_shipwright_base", lambda: (base, tmp_path, False))
    return base


def _plant_reparse_point(path: Path, target: Path, *, dangling: bool = False) -> None:
    """Create a real symlink (POSIX) or directory junction (Windows) at
    `path` pointing at `target`. Junctions need no elevated privilege on
    Windows, unlike symlinks (SeCreateSymbolicLinkPrivilege) — this is what
    lets the reparse-point tests below run unconditionally on every host
    instead of skipping, and faithfully exercises the junction-specific gap
    (IO_REPARSE_TAG_MOUNT_POINT, which `Path.is_symlink()` never catches).
    `dangling=True` removes the target after linking."""
    target.mkdir(exist_ok=True)
    if sys.platform == "win32":
        subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["cmd", "/c", "mklink", "/J", str(path), str(target)],
            capture_output=True, text=True, check=True, timeout=30,
        )
    else:
        path.symlink_to(target, target_is_directory=True)
    if dangling:
        target.rmdir()


def test_resolve_is_deterministic(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    first = rs.resolve("iterate-x", "diff.txt")
    second = rs.resolve("iterate-x", "diff.txt")
    assert first == second
    assert first.parent.is_dir()


def test_resolve_disjoint_across_run_ids(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    a = rs.resolve("iterate-a", "diff.txt")
    b = rs.resolve("iterate-b", "diff.txt")
    assert a != b
    assert a.parent != b.parent


def test_resolve_round_trips_content(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    path = rs.resolve("iterate-x", "diff.txt")
    path.write_text("hello", encoding="utf-8")
    assert rs.resolve("iterate-x", "diff.txt").read_text(encoding="utf-8") == "hello"


def test_cleanup_removes_run_directory(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    path = rs.resolve("iterate-x", "diff.txt")
    path.write_text("x", encoding="utf-8")
    rs.cleanup("iterate-x")
    assert not path.exists()
    assert not path.parent.exists()


def test_cleanup_on_missing_run_id_is_a_noop(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    rs.cleanup("never-existed")  # must not raise


@pytest.mark.parametrize(
    "bad", ["..", ".", "", "a/b", "a\\b", "/etc/passwd", "C:\\x", "a" * 101,
            "con", "CON", "nul", "aux.txt", "com1", "COM9.log", "lpt5",
            "run1.", "RUN1.", "run1.."])
def test_resolve_rejects_unsafe_run_id(monkeypatch, tmp_path, bad):
    _patch_base(monkeypatch, tmp_path)
    with pytest.raises(rs.ReviewScratchError):
        rs.resolve(bad, "diff.txt")


@pytest.mark.parametrize(
    "bad", ["..", ".", "", "a/b", "../../etc", "nul", "COM3", "prn.json",
            "diff.txt.", "diff."])
def test_resolve_rejects_unsafe_name(monkeypatch, tmp_path, bad):
    _patch_base(monkeypatch, tmp_path)
    with pytest.raises(rs.ReviewScratchError):
        rs.resolve("iterate-x", bad)


def test_resolve_rejects_trailing_dot_run_id_alias(monkeypatch, tmp_path):
    """Windows silently strips a trailing dot when a path component is
    created/opened, so "run1." and "run1" would resolve to the SAME
    directory there even though both pass the charset check — a distinct
    run_id must never be allowed to alias another run's scratch dir
    (external-review finding, PR #676)."""
    _patch_base(monkeypatch, tmp_path)
    rs.resolve("run1", "diff.txt")
    with pytest.raises(rs.ReviewScratchError):
        rs.resolve("run1.", "diff.txt")


def test_resolve_rejects_trailing_dot_name_alias(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    rs.resolve("iterate-x", "diff.txt")
    with pytest.raises(rs.ReviewScratchError):
        rs.resolve("iterate-x", "diff.txt.")


def test_resolve_canonicalizes_case(monkeypatch, tmp_path):
    """Two run_ids/names differing only by case must resolve to the SAME
    path everywhere — not silently collide only on a case-insensitive
    filesystem (Windows/macOS), where a cleanup of one could otherwise
    remove the other's live snapshot (external-review finding)."""
    _patch_base(monkeypatch, tmp_path)
    assert rs.resolve("Iterate-X", "Diff.TXT") == rs.resolve("iterate-x", "diff.txt")


def test_cleanup_rejects_unsafe_run_id(monkeypatch, tmp_path):
    _patch_base(monkeypatch, tmp_path)
    with pytest.raises(rs.ReviewScratchError):
        rs.cleanup("../escape")


def test_cleanup_rejects_a_reparse_point_planted_at_run_root(monkeypatch, tmp_path):
    """A symlink swapped in for the run's own directory must not be silently
    treated as absent (dangling) or silently followed by rmtree — doubt-
    reviewer finding, iterate-2026-09-03-review-scratch-path. Exercises the
    real reparse-point path: os.path.lexists (not is_symlink()/exists())
    catches it even when dangling, and _reject_linked_components rejects it
    before any rmtree."""
    base = _patch_base(monkeypatch, tmp_path)
    namespace = base / rs._NAMESPACE
    namespace.mkdir(parents=True)
    run_root = namespace / "iterate-x"
    decoy_target = tmp_path / "decoy-outside-namespace"
    _plant_reparse_point(run_root, decoy_target)

    with pytest.raises(rs.ReviewScratchError):
        rs.cleanup("iterate-x")
    assert decoy_target.exists(), "cleanup must never follow the link into another directory"


def test_cleanup_rejects_a_dangling_reparse_point_at_run_root(monkeypatch, tmp_path):
    """Same as above but the link's target no longer exists — exists()
    alone would read this as 'missing' and silently no-op past it."""
    base = _patch_base(monkeypatch, tmp_path)
    namespace = base / rs._NAMESPACE
    namespace.mkdir(parents=True)
    run_root = namespace / "iterate-x"
    _plant_reparse_point(run_root, tmp_path / "vanishing-target", dangling=True)

    with pytest.raises(rs.ReviewScratchError):
        rs.cleanup("iterate-x")


def test_resolve_survives_a_space_in_the_temp_root(monkeypatch, tmp_path):
    (tmp_path / "Program Files").mkdir()
    spaced_base = tmp_path / "Program Files" / "base"
    monkeypatch.setattr(rs, "_private_shipwright_base", lambda: (spaced_base, tmp_path, False))

    path = rs.resolve("iterate-x", "diff.txt")
    path.write_text("ok", encoding="utf-8")

    assert " " in str(path)
    assert path.read_text(encoding="utf-8") == "ok"


# --- cross-process contract test (the actual regression pin) ---------------
#
# The bug this module closes only reproduces when a bash-tool write and a
# native-Python read independently reinterpret a bare `/tmp/...` string. CI
# runs Linux, where that specific divergence cannot occur, so this pins the
# *contract* instead: two independent `uv run` processes resolving the same
# (run_id, name) land on the identical path, and a write from one is visible
# to the other — the property the fix actually depends on, platform-agnostic.


def test_cli_resolve_is_stable_and_content_survives_across_two_processes():
    if not _CLI.exists():
        raise AssertionError(f"review_scratch.py CLI not found at {_CLI}")
    run_id = f"iterate-cli-contract-{uuid4().hex[:12]}"
    try:
        first = subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "resolve", "--run-id", run_id, "--name", "diff.txt"],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )
        assert first.returncode == 0, first.stderr
        path_a = first.stdout.strip()
        assert path_a, "resolve printed an empty path"

        Path(path_a).write_text("cross-process payload", encoding="utf-8")

        second = subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "resolve", "--run-id", run_id, "--name", "diff.txt"],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )
        assert second.returncode == 0, second.stderr
        path_b = second.stdout.strip()

        assert path_a == path_b
        assert Path(path_b).read_text(encoding="utf-8") == "cross-process payload"
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )


def _run_trap_pattern(run_id: str, *, review_exit: int) -> subprocess.CompletedProcess:
    """Exercise the exact `trap 'ec=$?; ... cleanup ...; exit "$ec"' EXIT`
    idiom used by `code-review.md` Step 6c, `iteration-reviews.md` Branch A,
    and `sub-iterate-runner.md` Step 2 — a fake "review command" with a
    controlled exit code stands in for `external_review.py`."""
    script = (
        f'DIFF_FILE="$(uv run "{_CLI}" resolve --run-id "{run_id}" --name diff.txt)"\n'
        f'trap \'ec=$?; uv run "{_CLI}" cleanup --run-id "{run_id}"; exit "$ec"\' EXIT\n'
        f"echo payload > \"$DIFF_FILE\"\n"
        f"exit {review_exit}\n"
    )
    return subprocess.run(  # nosec B603 - fixed argv, shell=False
        [_bash(), "-c", script],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
    )


def test_trap_preserves_a_failed_review_commands_exit_status():
    # PR #676 round-4 external-review finding: a trap whose own cleanup
    # command succeeds becomes bash's new "last command run", so without
    # `ec=$?` ... `exit "$ec"` the trap silently turns a failed review into
    # an apparent success.
    run_id = f"iterate-trap-fail-{uuid4().hex[:12]}"
    try:
        result = _run_trap_pattern(run_id, review_exit=17)
        assert result.returncode == 17, result.stderr
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )


def test_trap_cleans_up_the_scratch_diff_on_a_failed_review():
    run_id = f"iterate-trap-cleanup-{uuid4().hex[:12]}"
    result = _run_trap_pattern(run_id, review_exit=1)
    assert result.returncode == 1, result.stderr
    check = subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "run", str(_CLI), "resolve", "--run-id", run_id, "--name", "diff.txt"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
    )
    try:
        assert check.returncode == 0, check.stderr
        assert not Path(check.stdout.strip()).exists(), (
            "trap must remove the scratch diff even when the review command failed"
        )
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )


def test_trap_preserves_a_successful_review_commands_exit_status():
    run_id = f"iterate-trap-ok-{uuid4().hex[:12]}"
    try:
        result = _run_trap_pattern(run_id, review_exit=0)
        assert result.returncode == 0, result.stderr
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )
