"""AC-3/AC-4/AC-5 — churn-conflict resolver.

Pure-logic unit tests (allowlist / classify / dedup / validate) plus git
integration tests in real merge-conflict repos. Regeneration is tested with the
canonical ``finalize_iterate`` producers monkeypatched (the real regeneration is
exercised end-to-end by the iterate's own dogfood, AC-10).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import (  # noqa: E402
    CHURN_ALLOWLIST,
    classify,
    dedup_event_lines,
    validate_events_text,
)
from tools import resolve_churn_conflicts as rcc  # noqa: E402


# --------------------------------------------------------------------------- #
# pure logic                                                                  #
# --------------------------------------------------------------------------- #

def test_classify_blocks_source_allows_churn() -> None:
    resolvable, blocking = classify(
        [
            ".shipwright/compliance/dashboard.md",
            "shipwright_events.jsonl",
            "shipwright_test_results.json",
            "src/app.py",
            "shared/scripts/tools/foo.py",
        ]
    )
    assert "src/app.py" in blocking and "shared/scripts/tools/foo.py" in blocking
    assert ".shipwright/compliance/dashboard.md" in resolvable
    assert "shipwright_events.jsonl" in resolvable


def test_architecture_md_is_NOT_allowlisted_so_it_blocks() -> None:
    # Curated prose must reach a human (folds external-review G4/O1).
    assert ".shipwright/agent_docs/architecture.md" not in CHURN_ALLOWLIST
    resolvable, blocking = classify([".shipwright/agent_docs/architecture.md"])
    assert blocking == [".shipwright/agent_docs/architecture.md"]
    assert resolvable == []


def test_classify_normalises_backslash_paths() -> None:
    resolvable, blocking = classify([r".shipwright\compliance\sbom.md"])
    assert resolvable == [".shipwright/compliance/sbom.md"]
    assert blocking == []


def test_dedup_collapses_byte_identical_lines_only() -> None:
    out, warn = dedup_event_lines(['{"id":"a"}', '{"id":"a"}', '{"id":"b"}', ""])
    assert out == ['{"id":"a"}', '{"id":"b"}']
    assert warn == []


def test_dedup_keeps_both_on_id_collision_and_warns() -> None:
    # Two DISTINCT lines sharing an evt id: never drop, but warn (G2/O6).
    out, warn = dedup_event_lines(['{"id":"x","ts":1}', '{"id":"x","ts":2}'])
    assert len(out) == 2
    assert warn and "x" in warn[0]


def test_validate_flags_non_json_line() -> None:
    errs = validate_events_text('{"ok":1}\nNOT JSON\n')
    assert any("not valid JSON" in e for e in errs)


def test_validate_requires_run_event_when_run_id_given() -> None:
    present = '{"type":"work_completed","adr_id":"iterate-x","id":"e1"}\n'
    assert validate_events_text(present, require_run_id="iterate-x") == []
    absent = '{"type":"phase_completed","id":"e2"}\n'
    assert validate_events_text(absent, require_run_id="iterate-x")


# --------------------------------------------------------------------------- #
# git integration                                                             #
# --------------------------------------------------------------------------- #

def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="Churn Test",
        GIT_AUTHOR_EMAIL="churn@test.invalid",
        GIT_COMMITTER_NAME="Churn Test",
        GIT_COMMITTER_EMAIL="churn@test.invalid",
    )
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=_env(), capture_output=True, text=True, check=check
    )


def _make_conflict_repo(root: Path, files: dict[str, tuple[str, str, str]]) -> subprocess.CompletedProcess[str]:
    """``files``: relpath -> (base, ours, theirs). Returns the (conflicting) merge."""
    _git(root, "init", "-b", "main")
    for rel, (base, _o, _t) in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(base, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    _git(root, "checkout", "-b", "theirs")
    for rel, (_b, _o, theirs) in files.items():
        (root / rel).write_text(theirs, encoding="utf-8")
    _git(root, "commit", "-am", "theirs")
    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "ours")
    for rel, (_b, ours, _t) in files.items():
        (root / rel).write_text(ours, encoding="utf-8")
    _git(root, "commit", "-am", "ours")
    return _git(root, "merge", "theirs", "-m", "merge theirs", check=False)


def test_preflight_aborts_on_source_conflict_touching_nothing(tmp_path: Path) -> None:
    merge = _make_conflict_repo(
        tmp_path,
        {
            "src/app.py": ("base\n", "ours\n", "theirs\n"),
            ".shipwright/compliance/dashboard.md": ("b\n", "o\n", "t\n"),
        },
    )
    assert merge.returncode != 0
    before = set(rcc.conflicted_paths(tmp_path))

    result = rcc.complete_merge(tmp_path, run_id="iterate-x")

    assert result.status == "blocked"
    assert result.exit_code == 2
    assert "src/app.py" in result.blocking
    # Hard invariant: nothing resolved/staged — every conflict still unmerged.
    assert set(rcc.conflicted_paths(tmp_path)) == before
    assert result.resolved == []


def test_resolves_churn_only_merge(tmp_path: Path) -> None:
    merge = _make_conflict_repo(
        tmp_path,
        {
            ".shipwright/compliance/dashboard.md": ("b\n", "ours-md\n", "theirs-md\n"),
            "shipwright_test_results.json": ('{"r":0}\n', '{"r":1}\n', '{"r":2}\n'),
        },
    )
    assert merge.returncode != 0

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []  # merge is now committable
    # test_results.json resolved to OURS (PR-owned snapshot).
    assert (tmp_path / "shipwright_test_results.json").read_text(encoding="utf-8") == '{"r":1}\n'
    # derived MD cleared to THEIRS as a placeholder (regenerated in follow-up).
    assert (tmp_path / ".shipwright/compliance/dashboard.md").read_text(encoding="utf-8") == "theirs-md\n"


def test_events_deduped_and_validated_even_without_conflict(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    run_evt = '{"type":"work_completed","adr_id":"iterate-x","id":"evt-run","v":1}'
    dup = '{"type":"phase_completed","id":"evt-dup","v":1}'
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text(f"{dup}\n{run_evt}\n{dup}\n", encoding="utf-8")  # dup appears twice
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "log")

    result = rcc.complete_merge(tmp_path, run_id="iterate-x")

    text = log.read_text(encoding="utf-8")
    assert text.count("evt-dup") == 1  # exact-line dedup ran
    assert "evt-run" in text
    assert result.status in ("resolved", "clean")


def test_events_invalid_when_run_event_missing(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text('{"type":"phase_completed","id":"evt-1","v":1}\n', encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "log")

    result = rcc.complete_merge(tmp_path, run_id="iterate-missing")

    assert result.status == "events_invalid"
    assert result.exit_code == 4
    assert any("absent" in e for e in result.errors)


def test_regenerate_invokes_canonical_producers_and_stages(tmp_path: Path, monkeypatch) -> None:
    _git(tmp_path, "init", "-b", "main")
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")

    from tools import finalize_iterate

    calls: list[str] = []

    def fake_compliance(project_root: Path) -> list[str]:
        calls.append("compliance")
        rels = []
        for name in ("dashboard", "sbom", "test-evidence", "traceability-matrix", "change-history"):
            rel = f".shipwright/compliance/{name}.md"
            (project_root / rel).write_text(f"# {name}\n", encoding="utf-8")
            rels.append(rel)
        return rels

    monkeypatch.setattr(finalize_iterate, "_update_compliance", fake_compliance)

    outcomes = rcc.regenerate_tracked_snapshots(
        tmp_path, "iterate-x", session_id="s", only=set(rcc.COMPLIANCE_MDS)
    )

    assert calls == ["compliance"]
    assert all(v == "regenerated" for v in outcomes.values())
    # the 5 compliance MDs are now staged
    staged = _git(tmp_path, "diff", "--name-only", "--cached").stdout.split()
    assert ".shipwright/compliance/dashboard.md" in staged
    assert len([s for s in staged if s.startswith(".shipwright/compliance/")]) == 5
