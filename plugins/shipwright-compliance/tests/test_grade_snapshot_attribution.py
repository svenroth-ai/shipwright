"""The grade_snapshot emitter names the tree it measured
(iterate-2026-07-28-grade-snapshot-honest-subject).

Split out of ``test_grade_snapshot_regen.py`` when that file crossed the
300-line guideline. The seam is the subject: that file asks whether the emitter
EMITS (one per grade CHANGE, matching the dashboard); this one asks
whether what it emits says WHICH TREE it measured — the property the union-merged
event log needs so snapshots from many worktrees stop reading as one timeline.

Fixtures build real repositories: attribution is resolved from git, so a mocked
fixture would prove nothing about the producer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.lib.data_collector import ComplianceData, DependencyInfo
from scripts.lib._grade_snapshot import emit_grade_snapshot

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

import scripts.tools.update_compliance as update_compliance  # noqa: E402


def _read_events(root: Path) -> list[dict]:
    path = root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(ln)
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _gradeable_data(root: Path) -> ComplianceData:
    """ComplianceData whose report is gradeable: one declared dependency makes
    the dependency-hygiene dimension measurable -> a letter + score to trend."""
    return ComplianceData(
        project_root=root,
        dependencies=[DependencyInfo("left-pad", "1.0.0", "runtime", "MIT")],
        timestamp="2026-07-28T00:00:00Z",
    )


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_commit(root: Path, name: str) -> None:
    (root / name).write_text(name, encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-m", f"add {name}")


def _git_repo(root: Path) -> Path:
    """A real repo on ``main`` with one commit — attribution is resolved from
    git, so a fixture that fakes it would prove nothing about the producer."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "config", "commit.gpgsign", "false")
    _git_commit(root, "one.txt")
    return root




class TestEmitterAttributesTheTree:
    """Every emitted snapshot names the tree it measured
    (iterate-2026-07-28-grade-snapshot-lineage).

    Without this, snapshots from many worktrees union-merge onto ``main`` as one
    indistinguishable timeline, and the Ship's-Log sparkline plots a mixture of
    subjects as if it were one project's trend.
    """

    def test_snapshot_from_a_real_repo_names_its_branch_and_base(self, tmp_path):
        root = _git_repo(tmp_path / "repo")
        _git(root, "checkout", "-b", "iterate/x")
        _git_commit(root, "two.txt")

        result = emit_grade_snapshot(_gradeable_data(root))

        event = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "branch"
        assert event["branch"] == "iterate/x"
        assert event["base"] == _git(root, "rev-parse", "main")
        # The caller's payload reports it too, so a regen's own output says
        # which tree it just measured.
        assert result["lineage"] == "branch"

    def test_snapshot_on_the_default_branch_is_main_lineage(self, tmp_path):
        root = _git_repo(tmp_path / "repo")

        emit_grade_snapshot(_gradeable_data(root))

        event = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "main"
        assert event["branch"] == "main"

    def test_a_worktree_at_the_fork_point_is_not_called_main(self, tmp_path):
        """The production shape that used to be mislabelled.

        An iterate worktree is created AT the fork point and F5b emits before
        the only mandated commit, so HEAD is still that fork point while the
        working tree holds the whole change set. This must read as a branch
        measurement over uncommitted content, not as the default branch's own.
        """
        root = _git_repo(tmp_path / "repo")
        _git(root, "checkout", "-b", "iterate/at-fork")
        (root / "uncommitted.py").write_text("work in progress", encoding="utf-8")
        (root / "one.txt").write_text("edited", encoding="utf-8")

        emit_grade_snapshot(_gradeable_data(root))

        event = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "branch"
        assert event["branch"] == "iterate/at-fork"

    def test_unresolvable_tree_still_emits_an_explicitly_unknown_snapshot(self, tmp_path):
        # tmp_path is not a git repo. The snapshot must still land — attribution
        # is metadata, not a precondition — and must say "unknown" out loud,
        # because an ABSENT lineage is reserved for events written before
        # attribution existed.
        result = emit_grade_snapshot(_gradeable_data(tmp_path))
        assert result["appended"] == 1

        event = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "unknown"
        assert "branch" not in event

    def test_a_raising_resolver_never_costs_us_the_snapshot(self, tmp_path, monkeypatch):
        # The regen must survive a broken git the same way it survives every
        # other degraded input: with a recorded, honest gap.
        import grade_snapshot_shape

        def _boom(_root):
            raise RuntimeError("git exploded")

        monkeypatch.setattr(grade_snapshot_shape, "resolve_tree_lineage", _boom)

        assert emit_grade_snapshot(_gradeable_data(tmp_path))["appended"] == 1
        event = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "unknown"
        assert event["grade"]


class TestComplianceRegenAttributesTheTree:
    """category: integration — the whole chain, in a tree that is NOT main."""

    def test_regen_in_a_branch_tree_lands_an_attributed_snapshot(
        self, tmp_path, monkeypatch, capsys,
    ):
        """category: integration — the whole chain, in a tree that is NOT main.

        This is the defect's actual shape: a compliance regen running inside an
        iterate worktree, on a branch, whose event then union-merges onto
        ``main``. Three components have to compose for the fix to hold — the
        update_compliance dashboard branch, the emitter, and the git resolver —
        and each of them passes its own unit tests while still producing an
        unattributed event if the wiring between them is wrong.
        """
        root = _git_repo(tmp_path / "repo")
        (root / ".shipwright" / "compliance").mkdir(parents=True)
        _git(root, "checkout", "-b", "iterate/lineage-demo")
        _git_commit(root, "two.txt")
        branch_point = _git(root, "rev-parse", "main")

        data = _gradeable_data(root)
        monkeypatch.setattr(update_compliance, "collect_all", lambda pr: data)
        monkeypatch.setattr(sys, "argv", [
            "update_compliance.py", "--project-root", str(root), "--phase", "design",
        ])
        assert update_compliance.main() == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["grade_snapshot"]["lineage"] == "branch"

        snaps = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 1
        assert snaps[0]["lineage"] == "branch"
        assert snaps[0]["branch"] == "iterate/lineage-demo"
        # `base` names the main commit this tree extends — NOT its own HEAD,
        # which is the whole reason `commit` was unusable here.
        assert snaps[0]["base"] == branch_point
        assert snaps[0]["base"] != _git(root, "rev-parse", "HEAD")
