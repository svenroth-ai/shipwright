"""AC-3/AC-4/AC-5 — churn-conflict resolver (git integration).

Real merge-conflict repos exercise ``complete_merge`` end-to-end (events +
triage reconcile, allowlist gate, --ours/--theirs resolution). The pure
allowlist/classify/dedup/validate unit tests live in ``test_churn_merge.py``.
Regeneration is tested with the canonical ``finalize_iterate`` producers
monkeypatched (the real regeneration is dogfooded end-to-end, AC-10).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

from tools import resolve_churn_conflicts as rcc  # noqa: E402

from _churn_conflicts_helpers import git as _git, make_conflict_repo as _make_conflict_repo  # noqa: E402

# Pure allowlist/classify/dedup/validate unit tests live in test_churn_merge.py.
# Campaign status.json conflict + regenerate (S3) live in
# test_resolve_churn_campaign_status.py (reuses _make_conflict_repo / _git here
# via THIS module — a re-export of the helpers below, kept for that cross-file
# import). Triage-specific conflict/dedup/validate tests split into
# test_resolve_churn_conflicts_triage.py when this file crossed the 300-LOC
# guideline (iterate-2026-08-08-triage-amend-event).


# --------------------------------------------------------------------------- #
# git integration                                                             #
# --------------------------------------------------------------------------- #


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

    def fake_compliance(project_root: Path, run_id=None) -> list[str]:
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
