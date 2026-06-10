"""Campaign status.json concurrent-sibling regenerate through ``integrate_main``
(campaign 2026-06-07-tracked-campaign-status, S3).

Two sibling sub-iterates each complete a different sub; the second's
``integrate origin/main`` textually conflicts on the campaign ``status.json``,
which the resolver glob-admits + placeholder-resolves, then re-projects from the
UNION event log in the follow-up regenerate. ``events_invalid`` must still abort
BEFORE any campaign-status regenerate. Uses the ``git_origin_repo`` /
``make_worktree`` conftest fixtures + the helpers from ``test_integrate_main``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import integrate_main  # noqa: E402

_CAMP_DIR = ".shipwright/planning/iterate/campaigns/demo"
_CAMP_STATUS = f"{_CAMP_DIR}/status.json"
_CAMP_MD = """---
campaign: demo
status: active
---

# Campaign: demo

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| S1 | alpha | First | pending |
| S2 | bravo | Second | pending |
"""


def _status_line(s1: str, s2: str) -> str:
    """A compact single-line status.json so any two-sided edit textually conflicts."""
    return (
        '{"campaign": "demo", "status": "active", "sub_iterates": ['
        f'{{"id": "S1", "slug": "alpha", "status": "{s1}"}}, '
        f'{{"id": "S2", "slug": "bravo", "status": "{s2}"}}]}}\n'
    )


def _status_ml(s1: str, s2: str) -> str:
    """The REAL production multi-line (indent=2) format: each sub on its own lines,
    so two siblings editing DIFFERENT subs auto-merge textually (non-overlapping)."""
    return json.dumps({
        "campaign": "demo", "status": "active",
        "sub_iterates": [
            {"id": "S1", "slug": "alpha", "status": s1, "commit": None},
            {"id": "S2", "slug": "bravo", "status": s2, "commit": None},
        ],
    }, indent=2, ensure_ascii=False) + "\n"


def _event(sid: str, *, adr: str | None = None) -> str:
    ev = {"type": "work_completed", "ts": f"2026-06-10T07:0{sid[-1]}:00+00:00",
          "commit": "", "campaign": "demo", "sub_iterate_id": sid,
          "tests": {"passed": 2, "total": 2}}
    if adr:
        ev["adr_id"] = adr
    return json.dumps(ev)


def _seed_main(work: Path) -> None:
    _set_repo_identity(work)
    _write(work, ".gitattributes", "shipwright_events.jsonl merge=union\n")
    _write(work, f"{_CAMP_DIR}/campaign.md", _CAMP_MD)
    _write(work, _CAMP_STATUS, _status_line("pending", "pending"))
    _write(work, "shipwright_events.jsonl", '{"type":"phase_completed","id":"e0","v":1}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed campaign")
    _git(work, "push", "origin", "main")


def _append(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _stub_derived_md_producers(monkeypatch) -> None:
    """Let the REAL regenerate_tracked_snapshots run (so the campaign-status leg
    fires) but stub the heavy derived-MD producers to harmless non-error values
    (truthy relpaths that don't exist → not staged, never classified 'error')."""
    from tools import finalize_iterate
    monkeypatch.setattr(finalize_iterate, "_update_compliance", lambda pr: ["ok"])
    monkeypatch.setattr(finalize_iterate, "_update_dashboard",
                        lambda *a, **k: ".shipwright/agent_docs/build_dashboard.md")
    monkeypatch.setattr(finalize_iterate, "_generate_handoff",
                        lambda *a, **k: ".shipwright/agent_docs/session_handoff.md")
    monkeypatch.setattr(finalize_iterate, "_snapshot_triage_runtime", lambda pr: "skipped")


def test_integrate_concurrent_sibling_status_regenerate(git_origin_repo, make_worktree, monkeypatch) -> None:
    work, _origin = git_origin_repo
    _seed_main(work)

    # sibling B (this run, S2): completes S2 in its worktree.
    wt = make_worktree(work, "camp-s2")
    _write(wt, _CAMP_STATUS, _status_line("pending", "complete"))
    _append(wt / "shipwright_events.jsonl", _event("S2", adr="iterate-s2"))
    _git(wt, "commit", "-am", "S2 complete")

    # origin/main advances: sibling A merged S1 first (different sub → textual conflict).
    _write(work, _CAMP_STATUS, _status_line("complete", "pending"))
    _append(work / "shipwright_events.jsonl", _event("S1"))
    _git(work, "commit", "-am", "S1 complete")
    _git(work, "push", "origin", "main")

    _stub_derived_md_producers(monkeypatch)
    result = integrate_main.integrate(wt, "iterate-s2", do_fetch=True)

    assert result["status"] == "ok", result
    assert "regenerated-followup" in result["steps"]
    status = json.loads((wt / _CAMP_STATUS).read_text(encoding="utf-8"))
    by = {s["id"]: s["status"] for s in status["sub_iterates"]}
    assert by == {"S1": "complete", "S2": "complete"}  # union projection: both done
    # the re-projected board is staged in the follow-up commit (HEAD).
    assert _CAMP_STATUS in _git(wt, "show", "--name-only", "--format=", "HEAD").stdout


def test_integrate_status_regen_skipped_when_events_invalid(git_origin_repo, make_worktree, monkeypatch) -> None:
    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "camp-bad")
    _append(wt / "shipwright_events.jsonl", _event("S2", adr="iterate-s2"))
    _git(wt, "commit", "-am", "S2 event")

    _write(work, "shipwright_events.jsonl",
           '{"type":"phase_completed","id":"e0","v":1}\nthis is NOT json\n')
    _git(work, "commit", "-am", "main corrupts log")
    _git(work, "push", "origin", "main")

    called = {"regen": False}
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: called.__setitem__("regen", True) or {},
    )
    result = integrate_main.integrate(wt, "iterate-s2", do_fetch=True)

    assert result["status"] == "events_invalid", result
    assert called["regen"] is False  # campaign regen lives inside regen — never reached
    # campaign board untouched (still the committed all-pending baseline).
    assert "pending" in (wt / _CAMP_STATUS).read_text(encoding="utf-8")


def test_integrate_multiline_nonoverlapping_subs_merge_clean(git_origin_repo, make_worktree, monkeypatch) -> None:
    """M2: the PRODUCTION multi-line status.json — two siblings completing DIFFERENT
    subs auto-merge textually with no conflict, yielding a correct S1+S2 board WITHOUT
    a regen (only OVERLAPPING edits conflict → scoped regen; non-overlapping are
    git-correct). Proves the format isn't silently corrupted."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, ".gitattributes", "shipwright_events.jsonl merge=union\n")
    _write(work, f"{_CAMP_DIR}/campaign.md", _CAMP_MD)
    _write(work, _CAMP_STATUS, _status_ml("pending", "pending"))
    _write(work, "shipwright_events.jsonl", '{"type":"phase_completed","id":"e0","v":1}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed multiline board")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "camp-ml")
    _write(wt, _CAMP_STATUS, _status_ml("pending", "complete"))   # this run completes S2
    _append(wt / "shipwright_events.jsonl", _event("S2", adr="iterate-ml"))
    _git(wt, "commit", "-am", "S2 complete")

    _write(work, _CAMP_STATUS, _status_ml("complete", "pending"))  # sibling completed S1
    _append(work / "shipwright_events.jsonl", _event("S1"))
    _git(work, "commit", "-am", "S1 complete")
    _git(work, "push", "origin", "main")

    _stub_derived_md_producers(monkeypatch)
    result = integrate_main.integrate(wt, "iterate-ml", do_fetch=True)

    assert result["status"] == "ok", result
    status = json.loads((wt / _CAMP_STATUS).read_text(encoding="utf-8"))
    by = {s["id"]: s["status"] for s in status["sub_iterates"]}
    assert by == {"S1": "complete", "S2": "complete"}  # git's line-merge is correct


def test_integrate_rolls_back_campaign_status_on_regenerate_failure(git_origin_repo, make_worktree, monkeypatch) -> None:
    """Transactional rollback (S3): when the follow-up regenerate reports a
    campaign status.json 'error', integrate restores it to the merge commit so a
    partial write never leaves a dirty board."""
    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "camp-rb")
    _append(wt / "shipwright_events.jsonl", _event("S2", adr="iterate-rb"))
    _write(wt, "README2.md", "wt\n")           # divergent change → a real merge commit
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "wt change + S2 event")
    _write(work, "README3.md", "main\n")       # main advances on a DIFFERENT file (no conflict)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main change")
    _git(work, "push", "origin", "main")

    def bad_regen(project_root, run_id, **kw):
        # simulate a partial regenerate: corrupt the board, then report it failed.
        (Path(project_root) / _CAMP_STATUS).write_text("CORRUPT", encoding="utf-8")
        return {_CAMP_STATUS: "error"}

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", bad_regen)
    result = integrate_main.integrate(wt, "iterate-rb", do_fetch=True)

    assert result["status"] == "regenerate_failed", result
    text = (wt / _CAMP_STATUS).read_text(encoding="utf-8")
    assert "CORRUPT" not in text                # rolled back to the merge commit
    assert "pending" in text                    # the committed all-pending baseline restored
