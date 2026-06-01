"""AC-1/AC-2 — `shipwright_events.jsonl merge=union` via repo `.gitattributes`.

Two layers:

1. **Drift protection** — the repo-root `.gitattributes` MUST declare the union
   merge driver for the append-only event log. If a future edit drops the line,
   the recurring per-PR `events.jsonl` merge conflict (session
   `10dff198`, PR #121) silently returns.

2. **Empirical round-trip probe** — prove that, *with* the union attribute, two
   branches that each append a distinct event line merge cleanly (no conflict
   markers, both lines preserved, every line still valid JSON), and *without*
   it the same history conflicts. This is the boundary probe required by the
   `touches_io_boundary` risk flag (round-trip producer→file→consumer).

See `.shipwright/planning/iterate/2026-05-31-churn-merge-resolver.md` AC-1/AC-2.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GITATTRIBUTES = REPO_ROOT / ".gitattributes"

_BASE = '{"v":1,"id":"evt-00000000","type":"phase_completed","ts":"2026-05-31T00:00:00+00:00"}\n'
_OURS = '{"v":1,"id":"evt-0a0a0a0a","type":"work_completed","ts":"2026-05-31T01:00:00+00:00"}\n'
_THEIRS = '{"v":1,"id":"evt-0b0b0b0b","type":"work_completed","ts":"2026-05-31T02:00:00+00:00"}\n'


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Union Test",
            "GIT_AUTHOR_EMAIL": "union@test.invalid",
            "GIT_COMMITTER_NAME": "Union Test",
            "GIT_COMMITTER_EMAIL": "union@test.invalid",
        }
    )
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_env(),
        capture_output=True,
        text=True,
        check=check,
    )


def _build_divergent_appends(repo: Path, *, with_union: bool) -> subprocess.CompletedProcess[str]:
    """Init a repo whose `main` has a base event log, branch `theirs` appends one
    event, `ours` appends another, then merge `theirs` into `ours`. Returns the
    merge CompletedProcess (check=False so callers can inspect the return code).
    """
    _git(repo, "init", "-b", "main")
    log = repo / "shipwright_events.jsonl"
    log.write_text(_BASE, encoding="utf-8")
    if with_union:
        (repo / ".gitattributes").write_text(
            "shipwright_events.jsonl merge=union\n", encoding="utf-8"
        )
        _git(repo, "add", ".gitattributes")
    _git(repo, "add", "shipwright_events.jsonl")
    _git(repo, "commit", "-m", "base log")

    # theirs (= origin/main advancing): append a different event.
    _git(repo, "checkout", "-b", "theirs")
    log.write_text(_BASE + _THEIRS, encoding="utf-8")
    _git(repo, "commit", "-am", "main appends event")

    # ours (= the iterate branch): append our own event off the base.
    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "ours")
    log.write_text(_BASE + _OURS, encoding="utf-8")
    _git(repo, "commit", "-am", "iterate appends work_completed")

    return _git(repo, "merge", "theirs", "-m", "merge theirs into ours", check=False)


def test_repo_gitattributes_declares_events_union() -> None:
    """Drift protection: the repo ships the union driver for the event log."""
    assert GITATTRIBUTES.exists(), (
        f"{GITATTRIBUTES} is missing — the events.jsonl union merge strategy "
        "(iterate-2026-05-31-churn-merge-resolver AC-1) was dropped."
    )
    lines = [
        ln.strip()
        for ln in GITATTRIBUTES.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert any(
        ln.split()[0] == "shipwright_events.jsonl" and "merge=union" in ln.split()[1:]
        for ln in lines
    ), f"`shipwright_events.jsonl merge=union` not found among: {lines}"


def test_union_merge_roundtrip_preserves_both_events(tmp_path: Path) -> None:
    """AC-1/AC-2: with the union attribute, divergent appends merge with no
    markers, both events survive, and every line stays valid JSON."""
    merge = _build_divergent_appends(tmp_path, with_union=True)
    assert merge.returncode == 0, (
        f"union merge should not conflict; stderr={merge.stderr}\nstdout={merge.stdout}"
    )

    text = (tmp_path / "shipwright_events.jsonl").read_text(encoding="utf-8")
    assert "<<<<<<<" not in text and ">>>>>>>" not in text, "conflict markers leaked"

    ids = []
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)  # AC-2: every line parses as JSON
        ids.append(obj["id"])

    # AC-2: both the iterate's event and main's event are present in HEAD.
    assert "evt-0a0a0a0a" in ids, "the iterate's own work_completed event was lost"
    assert "evt-0b0b0b0b" in ids, "main's event was lost"
    assert "evt-00000000" in ids, "the shared base event was lost"


def test_without_union_attr_the_same_history_conflicts(tmp_path: Path) -> None:
    """Control probe: absent the attribute, the identical history conflicts —
    proving the `.gitattributes` line is what removes the recurring conflict."""
    merge = _build_divergent_appends(tmp_path, with_union=False)
    conflicted = merge.returncode != 0 or "CONFLICT" in (merge.stdout + merge.stderr)
    assert conflicted, (
        "expected a merge conflict without merge=union, but the merge succeeded — "
        "the control probe is no longer meaningful"
    )
