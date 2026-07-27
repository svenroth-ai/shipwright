"""Git-evidence tests for ``record_requirement_impact``.

Split from ``test_record_requirement_impact.py`` along the same seam as the
modules: this file is about where the touch evidence COMES FROM. The design's
central claim is that git — not the caller — supplies it, so the ways that claim
can be undermined (a degenerate range, a bad ref quietly reading as "skipped", an
unborn HEAD) all live here.

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))

from lib.requirement_impact_store import (  # noqa: E402
    declaration_dir,
    read_declarations,
)
from record_requirement_impact import main  # noqa: E402

SPEC = ".shipwright/planning/01-adopted/spec.md"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one commit and a requirements spec on disk."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, SPEC, "# Spec\n\n| FR-01.04 | ... |\n")
    _write(tmp_path, "src/app.py", "print('hi')\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _run(repo: Path, *extra: str) -> int:
    return main(["--project-root", str(repo), "--run-id", "run-a", *extra])


def _decls(repo: Path) -> list[dict]:
    records, problems = read_declarations(declaration_dir(repo))
    assert problems == [], problems
    return records


def test_unknown_ref_is_an_error_not_a_skip(repo, capsys):
    """A typo'd ref must not silently degrade the check to 'skipped'."""
    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "modify", "--fr", "FR-01.04",
              "--base-ref", "no-such-ref", "--head-ref", "HEAD")

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "requirement_impact_evidence_unusable"
    assert "no-such-ref" in payload["detail"]


def test_missing_comparison_boundary_is_an_error(repo):
    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "none", "--reason", "ok")
    assert rc == 1


def test_worktree_and_range_together_are_rejected(repo, capsys):
    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "none", "--reason", "ok",
              "--worktree", "--base-ref", "HEAD~1", "--head-ref", "HEAD")
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_ambiguous_evidence"


def test_degenerate_range_is_rejected(repo, capsys):
    """base == head yields an empty diff, which would pass ANY declaration.

    The caller cannot hand in a path list, but it does choose the range — so a
    range that can prove nothing has to be refused, or the evidence rule is
    decorative.
    """
    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "modify", "--fr", "FR-01.04",
              "--base-ref", "HEAD", "--head-ref", "HEAD")

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "requirement_impact_evidence_unusable"
    assert "empty range" in payload["detail"]


def test_resolved_shas_are_recorded_for_a_committed_range(repo):
    """A symbolic 'HEAD~1..HEAD' is unauditable later; the SHAs are not."""
    _write(repo, SPEC, "# Spec\n\n| FR-01.05 | corrected |\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section")

    _run(repo, "--phase", "build", "--scope", "01-auth",
         "--impact", "modify", "--fr", "FR-01.05",
         "--base-ref", "HEAD~1", "--head-ref", "HEAD")

    touch = _decls(repo)[0]["touch_check"]
    assert len(touch["base_sha"]) == 40 and len(touch["head_sha"]) == 40
    assert touch["base_sha"] != touch["head_sha"]


def _snapshot(repo: Path, scope: str = "round-1") -> None:
    main(["--project-root", str(repo), "--run-id", "run-a", "--phase", "design",
          "--scope", scope, "--snapshot-baseline"])


def test_a_worktree_modify_without_a_baseline_is_refused(repo, capsys):
    """Fail-closed: no baseline means 'this round corrected it' cannot be checked."""
    rc = _run(repo, "--phase", "design", "--scope", "round-1",
              "--impact", "modify", "--fr", "FR-01.04", "--worktree")

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_no_baseline"


def test_an_untouched_spec_no_longer_satisfies_a_worktree_modify(repo, capsys):
    """THE design-side bug: nothing commits before build, so every untracked spec
    was listed by `ls-files --others` and satisfied any --impact modify."""
    _snapshot(repo)
    capsys.readouterr()

    rc = _run(repo, "--phase", "design", "--scope", "round-1",
              "--impact", "modify", "--fr", "FR-01.04", "--worktree")

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_no_spec_touched"


def test_a_genuinely_corrected_spec_satisfies_a_worktree_modify(repo, capsys):
    _snapshot(repo)
    capsys.readouterr()
    _write(repo, SPEC, "# Spec\n\n| FR-01.04 | corrected this round |\n")

    rc = _run(repo, "--phase", "design", "--scope", "round-1",
              "--impact", "modify", "--fr", "FR-01.04", "--worktree")

    assert rc == 0
    record = _decls(repo)[0]
    assert record["touch_check"]["baselined"] is True
    assert record["touch_check"]["spec_files"] == [SPEC]


def test_an_untracked_spec_created_this_round_does_count(repo, capsys):
    """A round that adds a split's requirements genuinely changed them."""
    _snapshot(repo)
    capsys.readouterr()
    _write(repo, ".shipwright/planning/02-new/spec.md",
           "# New split\n\n| FR-02.01 | x |\n")

    rc = _run(repo, "--phase", "design", "--scope", "round-1",
              "--impact", "add", "--fr", "FR-02.01", "--worktree")

    assert rc == 0


def test_design_round_works_before_the_first_commit(tmp_path, capsys):
    """A greenfield project designs before anything is committed (unborn HEAD).

    Without this, `git diff HEAD` fails, every round is rejected as
    evidence_unusable, and the design phase can never be finished.
    """
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, SPEC, "# Spec\n\n| FR-01.04 | new |\n")

    main(["--project-root", str(tmp_path), "--run-id", "run-a", "--phase", "design",
          "--scope", "round-1", "--snapshot-baseline"])
    _write(tmp_path, SPEC, "# Spec\n\n| FR-01.04 | corrected |\n")

    rc = main(["--project-root", str(tmp_path), "--run-id", "run-a",
               "--phase", "design", "--scope", "round-1",
               "--impact", "modify", "--fr", "FR-01.04", "--worktree"])

    assert rc == 0
    record = _decls(tmp_path)[0]
    assert record["touch_check"]["spec_files"] == [SPEC]


@pytest.mark.parametrize("flag,value", [
    ("--reason", "line one\nline two"),
    ("--contradiction", "who\ndecided"),
    ("--scope", "round\n2"),
])
def test_free_text_fields_must_stay_one_line(repo, capsys, flag, value):
    """A record meant to be one-line greppable must not accept a wall of text."""
    args = ["--phase", "design", "--impact", "none", "--reason", "ok",
            "--worktree", "--scope", "round-1"]
    # Replace the default for whichever flag this case is exercising.
    if flag in args:
        args[args.index(flag) + 1] = value
    else:
        args += [flag, value]

    rc = _run(repo, *args)

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_invalid_text"


def test_non_repository_skips_the_touch_check_but_still_records(tmp_path, capsys):
    """Fail-open on unavailable — and the record says the check did not run."""
    rc = main(["--project-root", str(tmp_path), "--run-id", "run-a",
               "--phase", "design", "--scope", "round-1",
               "--impact", "none", "--reason", "appearance only", "--worktree"])

    assert rc == 0
    (record,) = _decls(tmp_path)
    assert record["touch_check"]["source"] == "skipped"
    assert "WARNING" in capsys.readouterr().err


def test_vocabulary_is_enforced_even_without_git(tmp_path):
    """Fail-open on *unavailable* is not fail-open on *unknown*."""
    rc = main(["--project-root", str(tmp_path), "--run-id", "run-a",
               "--phase", "design", "--scope", "round-1",
               "--impact", "none", "--worktree"])
    assert rc == 1
    assert not declaration_dir(tmp_path).exists()
