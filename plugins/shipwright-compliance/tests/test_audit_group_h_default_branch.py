"""H2 default-branch guard (webui incident 2026-09-09, PRs #450/#453/#456).

A Group-H2 ratchet-suggestion tightened ``shipwright_bloat_baseline.json``
to a value measured on one tree at one instant while a concurrent,
already-in-flight branch landed the same file bigger; after both merged,
trunk's own anti-ratchet broke on every later zero-diff PR. H2 must not
suggest a tightening the shared trunk (``origin/<default>``) already
exceeds — see ``scripts.audit._group_h_default_branch``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_h  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args],
                   check=True, capture_output=True)


def _mktree(root: Path, entries: bytes) -> str:
    # Raw bytes, NOT text=True: on Windows a text-mode stdin pipe translates
    # "\n" to "\r\n", which corrupts mktree's "<mode> <type> <sha>\t<name>\n"
    # line format (the stray \r lands inside the entry name) and silently
    # produces a tree that doesn't contain the path we asked for.
    return subprocess.run(
        ["git", "-C", str(root), "mktree"],
        input=entries, capture_output=True, check=True,
    ).stdout.decode().strip()


def _build_tree(root: Path, rel: str, blob: str) -> str:
    """Build a (possibly nested) tree containing ``blob`` at ``rel``.

    ``git mktree`` only builds one flat level per call, so a nested path
    (``src/foo.py``) is built bottom-up: innermost directory first, then
    each parent wraps the previous tree as a ``040000 tree`` entry.
    """
    parts = rel.split("/")
    tree = _mktree(root, f"100644 blob {blob}\t{parts[-1]}\n".encode())
    for name in reversed(parts[:-1]):
        tree = _mktree(root, f"040000 tree {tree}\t{name}\n".encode())
    return tree


def _seed_origin_main(root: Path, rel: str, n_lines: int) -> None:
    """Simulate a shared trunk: commit ``rel`` at ``n_lines`` on a throwaway
    commit and point ``refs/remotes/origin/main`` at it, WITHOUT touching the
    caller's own on-disk working-tree copy of ``rel`` or HEAD/any branch."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    content = ("x = 1\n" * n_lines).encode()
    blob = subprocess.run(
        ["git", "-C", str(root), "hash-object", "-w", "--stdin"],
        input=content, capture_output=True, check=True,
    ).stdout.decode().strip()
    tree = _build_tree(root, rel, blob)
    commit = subprocess.run(
        ["git", "-C", str(root), "commit-tree", tree, "-m", "trunk"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    _git(root, "update-ref", "refs/remotes/origin/main", commit)


def _write_py(root: Path, rel: str, n_lines: int) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x = 1\n" * n_lines, encoding="utf-8")
    return p


def _write_baseline(root: Path, entries: list[dict]) -> None:
    (root / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": entries}, indent=2),
        encoding="utf-8",
    )


def _findings_by(findings, check_id: str):
    return [f for f in findings if f.check_id == check_id]


def test_h2_suppressed_when_default_branch_already_at_or_above_proposed(tmp_path):
    # recorded=447, on-disk actual=445 (would normally suggest tightening to
    # 445) — but origin/main already carries the file at 446, i.e. >= the
    # proposed value. The entry isn't stale, it's larger elsewhere: no H2
    # finding for this path.
    _seed_origin_main(tmp_path, "src/foo.py", 446)
    _write_py(tmp_path, "src/foo.py", 445)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 447,
        "state": "grandfathered", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h2 = _findings_by(findings, "H2")
    assert h2 and h2[0].status == "pass", \
        f"expected H2 pass (suppressed); got {h2[0].detail if h2 else None!r}"
    assert "src/foo.py" not in "".join(h2[0].evidence)


def test_h2_still_suggests_when_default_branch_is_smaller_still(tmp_path):
    # origin/main is genuinely smaller than the proposed value everywhere —
    # nothing is racing ahead of the audited tree, so the suggestion still
    # fires normally.
    _seed_origin_main(tmp_path, "src/foo.py", 300)
    _write_py(tmp_path, "src/foo.py", 380)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 500,
        "state": "grandfathered", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h2 = _findings_by(findings, "H2")
    assert h2 and h2[0].status == "fail", \
        f"expected H2 fail (still suggested); got {h2[0].status if h2 else None!r}"
    assert "src/foo.py" in h2[0].detail
    assert "380" in h2[0].detail


def test_h2_suggests_normally_when_no_git_repo_present(tmp_path):
    # No ``.git`` at all — default_branch_lines() must fail closed to
    # "unknown" and NOT suppress, matching pre-fix behavior exactly (this
    # is the shape every other Group-H test's tmp_path fixture already is).
    _write_py(tmp_path, "src/foo.py", 380)
    _write_baseline(tmp_path, entries=[{
        "path": "src/foo.py", "limit": 300, "current": 500,
        "state": "grandfathered", "adr": None,
    }])

    findings = group_h.run(tmp_path, None, None)
    h2 = _findings_by(findings, "H2")
    assert h2 and h2[0].status == "fail"
    assert "src/foo.py" in h2[0].detail
