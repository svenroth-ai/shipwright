"""Does the repair-safety gate actually REFUSE, through real git?

@FR-01.19

`test_assertion_weakening.py` feeds the detector hand-written `FileChange`
objects. That proves the comparison logic and nothing about the plumbing in
front of it — the `--name-status --find-renames` parsing, reading the *before*
out of the base tree, a deleted file having no `after` to parse, and the exit
code the CI step keys on. Every one of those sits between a lazy repair and the
refusal, and every one of them is where a silent pass would hide.

So this drives the REAL CLI against a REAL throwaway repository, once per
weakening a repair might reach for — plus the honest repair, which must be
*allowed*. A gate that blocks updating a pinned count would block the commonest
correct fix and be turned off within a week.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "shared" / "scripts" / "tools" / "check_repair_safety.py"

if shutil.which("git") is None:  # pragma: no cover - environment guard
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("git is required for the repair-gate probe — install git")
    pytest.skip("git not on PATH", allow_module_level=True)

BASE = (
    'def test_counts():\n'
    '    assert len(REGISTRY) == 5\n'
    '    assert REGISTRY[0] == "a"\n'
    '\n'
    '\n'
    'def test_other():\n'
    '    assert 1 == 1\n'
)

_KEEP_OTHER = '\n\ndef test_other():\n    assert 1 == 1\n'

ASSERTION_REMOVED = 'def test_counts():\n    assert len(REGISTRY) == 5\n' + _KEEP_OTHER
TEST_DELETED = 'def test_counts():\n    assert len(REGISTRY) == 5\n    assert REGISTRY[0] == "a"\n'
SKIP_ADDED = (
    'import pytest\n\n\n@pytest.mark.skip\ndef test_counts():\n'
    '    assert len(REGISTRY) == 5\n    assert REGISTRY[0] == "a"\n' + _KEEP_OTHER
)
PIN_UPDATED = (
    'def test_counts():\n    assert len(REGISTRY) == 6\n'
    '    assert REGISTRY[0] == "a"\n' + _KEEP_OTHER
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


def _drive(tmp_path: Path, after: str | None) -> tuple[int, dict]:
    """Commit BASE, apply `after` (None = delete the file), run the real CLI."""
    root = tmp_path
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "probe@example.com")
    _git(root, "config", "user.name", "probe")
    tests = root / "tests"
    tests.mkdir()
    target = tests / "test_registry.py"
    target.write_text(BASE, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    _git(root, "branch", "base-ref")

    if after is None:
        target.unlink()
    else:
        target.write_text(after, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "repair")

    proc = subprocess.run(
        [sys.executable, str(TOOL), "--project-root", str(root), "--base", "base-ref"],
        capture_output=True, text=True,
    )
    return proc.returncode, json.loads(proc.stdout or "{}")


@pytest.mark.parametrize(
    ("label", "after", "kind"),
    [
        ("an assertion quietly dropped", ASSERTION_REMOVED, "assertions_removed"),
        ("a whole test deleted", TEST_DELETED, "test_removed"),
        ("the test switched off", SKIP_ADDED, "skip_added"),
        ("the test file deleted", None, "file_removed"),
    ],
)
def test_the_gate_refuses_every_way_of_making_the_suite_prove_less(
    tmp_path, label, after, kind
):
    code, payload = _drive(tmp_path, after)
    assert code == 2, f"{label}: exit {code} — the CI step keys on this"
    assert payload["verdict"] == "blocked"
    assert kind in [f["kind"] for f in payload["findings"]]


def test_the_honest_repair_is_allowed_and_still_asked_to_explain_itself(tmp_path):
    """Updating a count another change legitimately moved IS the repair. It
    passes — and it is surfaced, so the pull request has to say why the new
    number is the truth."""
    code, payload = _drive(tmp_path, PIN_UPDATED)
    assert code == 0
    assert payload["verdict"] == "review"
    assert [f["kind"] for f in payload["findings"]] == ["assertion_changed"]


@pytest.mark.parametrize("bad", ["--upload-pack=evil", "a ref; rm -rf /", ""])
def test_a_base_that_is_not_ref_shaped_is_refused_before_any_git_call(tmp_path, bad):
    """Every git call already uses an argv list, so there is no shell to inject
    into — this is the second fence. A leading `-` in particular would be read
    by git as an OPTION rather than a revision (Tier-3 review).

    Passed as `--base=<value>` so argparse hands the value through instead of
    rejecting a leading dash itself: the point is to exercise OUR guard, not
    argparse's.
    """
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--project-root", str(tmp_path), f"--base={bad}"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3, proc.stderr
    assert json.loads(proc.stdout)["verdict"] == "unreadable"


def test_an_unreadable_base_fails_closed_rather_than_reporting_clean(tmp_path):
    """An unreadable diff is not a clean one."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "p@e.com")
    _git(tmp_path, "config", "user.name", "p")
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "only")

    proc = subprocess.run(
        [sys.executable, str(TOOL), "--project-root", str(tmp_path),
         "--base", "no-such-ref"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3
    assert json.loads(proc.stdout)["verdict"] == "unreadable"
