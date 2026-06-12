"""END-TO-END parallel-merge cascade integration test
(iterate-2026-06-12-cascade-integration-test).

The auto-merge churn cascade had THREE artifact classes that conflict when
parallel iterate branches merge serially, each fixed by a different mechanism —
proven INDIVIDUALLY by unit tests. This proves they all resolve TOGETHER, on real
git, across N serially-drained branches, with NO conflict markers and NO stale:

  - curated agent-docs (`architecture.md` `## …Updates` bullet-prepends) → `merge=union`
    (iterate-2026-06-12-union-curated-agent-docs), honored at the git merge
  - regenerated churn snapshots (`.shipwright/compliance/dashboard.md`) → the
    `integrate_main` regenerate-at-merge resolver (iterate-2026-05-31)
  - append-log JSONL (`shipwright_events.jsonl`) → `merge=union`

Two scenarios, both via the REAL `integrate_main.integrate` (the engine behind
the F11 `ensure_current` guard AND the campaign serial drain):

  A. THREE concurrent NON-campaign iterates drained one-by-one.
  B. A CAMPAIGN of three sub-iterates drained one-by-one (adds the per-tree
     campaign `status.json` projection from the union'd event log).

Real-git via the `git_origin_repo` / `make_worktree` conftest fixtures + the
helpers from `test_integrate_main`. NOT marked `slow` so it gates in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_campaign_status import (  # noqa: E402  (campaign event + producer stub)
    _CAMP_STATUS,
    _event,
    _stub_derived_md_producers,
)
from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from lib import gitattributes_union as gu  # noqa: E402
from tools import integrate_main  # noqa: E402

_ARCH = ".shipwright/agent_docs/architecture.md"
_DASH = ".shipwright/compliance/dashboard.md"
_ARCH_BASE = "# Architecture\n\n## Architecture Updates\n\n- **base** (2026-06-01): base entry\n"
_ANCHOR = "## Architecture Updates\n\n"

_CAMP_MD = ".shipwright/planning/iterate/campaigns/demo/campaign.md"
_CAMP_MD3 = (
    "---\ncampaign: demo\nstatus: active\n---\n\n# Campaign: demo\n\n## Sub-Iterates\n\n"
    "| ID | Slug | Title | Status |\n|---|---|---|---|\n"
    "| S1 | alpha | First | pending |\n| S2 | bravo | Second | pending |\n"
    "| S3 | charlie | Third | pending |\n"
)
_SLUG = {"S1": "alpha", "S2": "bravo", "S3": "charlie"}


def _status3(states: dict) -> str:
    """Single-line campaign status.json (so any two-sided edit textually conflicts,
    exercising the regenerate-from-events leg)."""
    subs = ", ".join(
        f'{{"id": "{sid}", "slug": "{_SLUG[sid]}", "status": "{states.get(sid, "pending")}"}}'
        for sid in ("S1", "S2", "S3")
    )
    return f'{{"campaign": "demo", "status": "active", "sub_iterates": [{subs}]}}\n'


def _prepend_arch(root: Path, bullet: str) -> None:
    p = root / _ARCH
    text = p.read_text(encoding="utf-8")
    assert _ANCHOR in text
    p.write_text(text.replace(_ANCHOR, _ANCHOR + bullet + "\n", 1), encoding="utf-8")


def _append(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _show(work: Path, ref_path: str) -> str:
    return _git(work, "show", ref_path).stdout


def _fake_regen(project_root, run_id, **kw):
    """Stand in for the heavy MD producers: deterministically 'regenerate' the
    churn dashboard from the merged tree (the unit-test pattern)."""
    p = Path(project_root) / _DASH
    p.write_text(f"regenerated from merged tree ({run_id})\n", encoding="utf-8")
    _git(Path(project_root), "add", "--", _DASH)
    return {_DASH: "regenerated"}


def test_three_concurrent_iterates_drain_without_cascade(git_origin_repo, make_worktree, monkeypatch):
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    # Seed main with the REAL union fragment (curated docs + JSONL), a curated
    # architecture.md, a churn dashboard, and an events log.
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _write(work, _ARCH, _ARCH_BASE)
    _write(work, _DASH, "base dashboard\n")
    _write(work, "shipwright_events.jsonl", '{"type":"phase_completed","id":"e0"}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", _fake_regen)

    tags = ("aaaa", "bbbb", "cccc")
    worktrees = []
    for tag in tags:
        wt = make_worktree(work, f"iter-{tag}")
        _prepend_arch(wt, f"- **iterate-{tag}** (2026-06-12): {tag} change")
        _write(wt, _DASH, f"{tag} dashboard\n")  # each regenerates the churn MD differently
        # adr_id == run_id: integrate validates THIS run's work_completed event
        # survives the union merge (else F11 would fail) — a real guard we honor.
        _append(wt / "shipwright_events.jsonl",
                f'{{"type":"work_completed","adr_id":"iterate-{tag}","id":"evt-{tag}","commit":""}}')
        _git(wt, "commit", "-am", f"iterate {tag}")
        worktrees.append((tag, wt))

    # Serial drain: branch 0 is current → push; each later branch integrates the
    # now-advanced origin/main FIRST (the F11 ensure_current guard / serial drain),
    # then advances origin/main.
    for i, (tag, wt) in enumerate(worktrees):
        if i:
            result = integrate_main.integrate(wt, f"iterate-{tag}", do_fetch=True)
            assert result["status"] == "ok", (tag, result)
            assert "regenerated-followup" in result["steps"], (tag, result)
        _git(wt, "push", "origin", "HEAD:main")

    # Final origin/main: ALL curated bullets survived (union), no markers, churn
    # regenerated, JSONL union'd — the cascade is fully resolved.
    _git(work, "fetch", "origin", "main")
    arch = _show(work, "origin/main:" + _ARCH)
    assert "<<<<<<<" not in arch
    for tag in tags:
        assert f"iterate-{tag}" in arch, tag
    assert "base entry" in arch
    assert arch.count("## Architecture Updates") == 1
    assert "regenerated from merged tree" in _show(work, "origin/main:" + _DASH)
    events = _show(work, "origin/main:shipwright_events.jsonl")
    assert "<<<<<<<" not in events
    for tag in tags:
        assert f"evt-{tag}" in events, tag


def test_campaign_three_subiterates_drain_without_cascade(git_origin_repo, make_worktree, monkeypatch):
    # A 3-sub campaign drained S1->S2->S3 serially via integrate_main. Each merge
    # textually conflicts on the single-line status.json, which the resolver
    # glob-admits + re-projects from the UNION'd event log (campaign S3,
    # never-downgrade), while the curated architecture.md unions and the churn
    # dashboard regenerates — three artifact classes, one drain, no cascade.
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, ".gitattributes", gu.merge_into(None)[0])  # union: events/triage + curated docs
    _write(work, _CAMP_MD, _CAMP_MD3)
    _write(work, _CAMP_STATUS, _status3({}))
    _write(work, _ARCH, _ARCH_BASE)
    _write(work, "shipwright_events.jsonl", '{"type":"phase_completed","id":"e0"}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed campaign (3 subs) + curated arch")
    _git(work, "push", "origin", "main")
    _stub_derived_md_producers(monkeypatch)

    subs = ("S1", "S2", "S3")
    for i, sid in enumerate(subs):
        wt = make_worktree(work, f"camp-{sid}")
        adr = f"iterate-{sid.lower()}"
        _write(wt, _CAMP_STATUS, _status3({sid: "complete"}))
        _append(wt / "shipwright_events.jsonl", _event(sid, adr=adr))
        _prepend_arch(wt, f"- **{adr}** (2026-06-12): {sid} done")
        _git(wt, "commit", "-am", f"{sid} complete")
        if i:
            result = integrate_main.integrate(wt, adr, do_fetch=True)
            assert result["status"] == "ok", (sid, result)
        _git(wt, "push", "origin", "HEAD:main")

    _git(work, "fetch", "origin", "main")
    # Campaign status.json: every sub projected complete from the union'd events.
    status = json.loads(_show(work, "origin/main:" + _CAMP_STATUS))
    by_id = {s["id"]: s["status"] for s in status["sub_iterates"]}
    assert by_id == {"S1": "complete", "S2": "complete", "S3": "complete"}, by_id
    # Curated architecture.md unioned all three sub bullets, no markers.
    arch = _show(work, "origin/main:" + _ARCH)
    assert "<<<<<<<" not in arch
    for sid in subs:
        assert f"iterate-{sid.lower()}" in arch, sid
