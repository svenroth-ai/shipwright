"""Write-boundary tests for ``record_requirement_impact``.

The rule is unit-tested in ``test_requirement_impact.py``. What matters here is
the boundary itself: that git — not the caller — supplies the touch evidence,
that the three git outcome classes are kept apart, and that a rejected
declaration leaves **nothing** on disk.

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


def _snapshot(repo: Path, phase: str, scope: str) -> None:
    """A worktree-mode behaviour declaration is judged against this snapshot."""
    main(["--project-root", str(repo), "--run-id", "run-a",
          "--phase", phase, "--scope", scope, "--snapshot-baseline"])


def _decls(repo: Path) -> list[dict]:
    records, problems = read_declarations(declaration_dir(repo))
    assert problems == [], problems
    return records


# --------------------------------------------------------------------------
# The happy paths
# --------------------------------------------------------------------------

def test_appearance_only_round_records_none_with_reason(repo, capsys):
    rc = _run(repo, "--phase", "design", "--scope", "round-2",
              "--impact", "none", "--reason", "spacing and colour only",
              "--worktree")
    assert rc == 0

    (record,) = _decls(repo)
    assert record["impact"] == "none"
    assert record["reason"] == "spacing and colour only"
    assert record["scope"] == "round-2"
    assert record["touch_check"]["source"] == "git"
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_behaviour_change_with_spec_touch_is_accepted(repo):
    """A round that changed what a flow does, and corrected the requirement."""
    _snapshot(repo, "design", "round-3")
    _write(repo, SPEC, "# Spec\n\n| FR-01.04 | corrected |\n")

    rc = _run(repo, "--phase", "design", "--scope", "round-3",
              "--impact", "modify", "--fr", "FR-01.04", "--worktree")

    assert rc == 0
    (record,) = _decls(repo)
    assert record["frs"] == ["FR-01.04"]
    assert record["touch_check"]["spec_files"] == [SPEC]


def test_build_section_uses_a_committed_range(repo):
    _write(repo, SPEC, "# Spec\n\n| FR-01.05 | corrected to match the mockup |\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section 01-auth")

    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "modify", "--fr", "FR-01.05",
              "--base-ref", "HEAD~1", "--head-ref", "HEAD")

    assert rc == 0
    assert _decls(repo)[0]["touch_check"]["detail"] == "HEAD~1..HEAD"


def test_attributed_extra_is_recorded_against_the_section(repo):
    _write(repo, "src/lib/http.py", "def get(): return 'retried'\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section 01-auth")

    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "none", "--reason", "section matched spec and mockup",
              "--base-ref", "HEAD~1", "--head-ref", "HEAD",
              "--extra", "src/lib/http.py=section needed a shared retry helper")

    assert rc == 0
    assert _decls(repo)[0]["extras"] == [
        {"path": "src/lib/http.py", "reason": "section needed a shared retry helper"}
    ]


def test_contradiction_decision_is_recorded(repo):
    """Part (2): stopping is only useful if the decision is written down."""
    _write(repo, SPEC, "# Spec\n\n| FR-01.05 | matches the mockup now |\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section 01-auth")

    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "modify", "--fr", "FR-01.05",
              "--base-ref", "HEAD~1", "--head-ref", "HEAD",
              "--contradiction", "operator chose the mockup; requirement corrected")

    assert rc == 0
    assert "mockup" in _decls(repo)[0]["contradiction"]


# --------------------------------------------------------------------------
# Fail-closed — a rejected declaration leaves nothing behind
# --------------------------------------------------------------------------

def test_none_without_reason_is_rejected_and_writes_nothing(repo, capsys):
    rc = _run(repo, "--phase", "design", "--scope", "round-2",
              "--impact", "none", "--worktree")

    assert rc == 1
    assert not declaration_dir(repo).exists()
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_none_requires_reason"


def test_behaviour_change_without_spec_touch_is_rejected(repo, capsys):
    """The core of the mechanism: claiming a requirement changed, but not changing it."""
    _snapshot(repo, "design", "round-3")
    capsys.readouterr()
    _write(repo, "src/app.py", "print('changed the behaviour but not the spec')\n")

    rc = _run(repo, "--phase", "design", "--scope", "round-3",
              "--impact", "modify", "--fr", "FR-01.04", "--worktree")

    assert rc == 1
    # The baseline directory exists (the round snapshotted one); what must NOT
    # exist is a declaration — the rejection wrote nothing.
    assert _decls(repo) == []
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_no_spec_touched"


def test_behaviour_change_without_fr_is_rejected(repo):
    _snapshot(repo, "design", "round-3")
    _write(repo, SPEC, "# Spec\n\n| FR-01.04 | touched |\n")
    rc = _run(repo, "--phase", "design", "--scope", "round-3",
              "--impact", "modify", "--worktree")
    assert rc == 1
    assert _decls(repo) == []


@pytest.mark.parametrize("flag,value,expected", [
    ("--impact", "tweak", "requirement_impact_invalid_impact"),
    ("--phase", "deploy", "requirement_impact_invalid_phase"),
])
def test_bad_vocabulary_exits_1_with_structured_json(repo, capsys, flag, value, expected):
    """argparse `choices` would exit 2 with plain text, bypassing fail-closed."""
    args = ["--phase", "design", "--scope", "round-1", "--impact", "none",
            "--reason", "ok", "--worktree"]
    args[args.index(flag) + 1] = value

    rc = _run(repo, *args)

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == expected
    assert not declaration_dir(repo).exists()


def test_extra_escaping_project_root_is_rejected(repo, capsys):
    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "none", "--reason", "ok",
              "--base-ref", "HEAD~1", "--head-ref", "HEAD",
              "--extra", "../../../etc/passwd=nope")

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_invalid_extra"


# --------------------------------------------------------------------------
# Round-trip + identity
# --------------------------------------------------------------------------

def test_record_round_trips_through_the_reader(repo):
    _write(repo, "src/app.py", "print('section work')\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section 01-auth")

    _run(repo, "--phase", "design", "--scope", "round-1",
         "--impact", "none", "--reason", "colour only", "--worktree")
    _run(repo, "--phase", "build", "--scope", "01-auth",
         "--impact", "none", "--reason", "matched",
         "--base-ref", "HEAD~1", "--head-ref", "HEAD")

    records = _decls(repo)
    assert {(r["phase"], r["scope"]) for r in records} == \
        {("design", "round-1"), ("build", "01-auth")}


def test_same_scope_under_two_runs_produces_two_records(repo):
    main(["--project-root", str(repo), "--run-id", "run-a", "--phase", "design",
          "--scope", "round-1", "--impact", "none", "--reason", "a", "--worktree"])
    main(["--project-root", str(repo), "--run-id", "run-b", "--phase", "design",
          "--scope", "round-1", "--impact", "none", "--reason", "b", "--worktree"])

    assert sorted(r["run_id"] for r in _decls(repo)) == ["run-a", "run-b"]


def test_rerecording_the_same_identity_overwrites_in_place(repo):
    _run(repo, "--phase", "design", "--scope", "round-1",
         "--impact", "none", "--reason", "first", "--worktree")
    _run(repo, "--phase", "design", "--scope", "round-1",
         "--impact", "none", "--reason", "corrected", "--worktree")

    (record,) = _decls(repo)
    assert record["reason"] == "corrected"


# --------------------------------------------------------------------------
# The evidence mode belongs to the PHASE, not to the caller's argv
# --------------------------------------------------------------------------

def test_a_design_declaration_may_not_use_a_committed_range(repo, capsys):
    """Otherwise any historical spec edit satisfies this round's declaration."""
    rc = _run(repo, "--phase", "design", "--scope", "round-1",
              "--impact", "none", "--reason", "ok",
              "--base-ref", "HEAD~1", "--head-ref", "HEAD")

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_wrong_evidence_mode"


def test_a_build_declaration_may_not_use_the_worktree(repo, capsys):
    """A section HAS a commit; judging it against uncommitted state is not it."""
    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "none", "--reason", "ok", "--worktree")

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_wrong_evidence_mode"


def test_a_build_range_wider_than_one_commit_is_rejected(repo, capsys):
    """An older/broader range containing some spec edit must not satisfy modify."""
    _write(repo, SPEC, "# Spec\n\n| FR-01.05 | v2 |\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "an earlier commit touching the spec")
    _write(repo, "src/app.py", "print('section work only')\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section 01-auth")

    rc = _run(repo, "--phase", "build", "--scope", "01-auth",
              "--impact", "modify", "--fr", "FR-01.05",
              "--base-ref", "HEAD~2", "--head-ref", "HEAD")

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "requirement_impact_evidence_unusable"
    assert "more than one commit" in payload["detail"]
