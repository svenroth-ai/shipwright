"""What the required-check producer DECIDES once the host has answered.

@FR-01.17

``test_required_checks_drift.py`` covers the pure set comparison and
``test_check_required_checks_io.py`` the host-call primitives. The decisions in
between are what made the first draft wrong:

- **An unprotected repo is a finding, not an error.** Requiring nothing is the
  loudest thing this tool can report: every check runs and gates nothing. The
  first draft raised on it, so the producer was blind exactly where it mattered
  most — found independently by both external reviewers.
- **A 404 only means "no such policy" once the repo is known readable.** A
  typo'd slug 404s on every endpoint too, and reading that as "protects nothing"
  would report every check as unenforced: a producer crying wolf at full volume.
- **Exit 2 is reserved for "I could not look."** It must never be reachable by a
  repository that simply has no policy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _required_checks_fakes import (  # noqa: E402
    FORBIDDEN,
    NOT_FOUND,
    REPO_OK,
    REPO_ROOT,
    Resp,
    gh_router,
    load_producer,
)

crc = load_producer()


# ---------------------------------------------------------------------------
# fetch_configured_contexts — readable vs empty
# ---------------------------------------------------------------------------


def test_a_repo_that_requires_nothing_reads_as_empty_not_unreadable(monkeypatch) -> None:
    """The regression both external reviewers caught. THE test in this file."""
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": Resp(0, "[]"),
        "/branches/main/protection": NOT_FOUND,  # "Branch not protected"
    }))
    assert crc.fetch_configured_contexts("o/r", "main") == []


def test_empty_configured_set_makes_every_check_unenforced() -> None:
    """...and that empty set must read as total drift, never as 'in sync'."""
    result = crc.compare_required_checks(["Build", "Test"], [])
    assert not result["in_sync"]
    assert result["unenforced"] == ["Build", "Test"]
    assert result["phantom"] == []


def test_contexts_come_from_rulesets(monkeypatch) -> None:
    rules = [
        {"type": "pull_request", "parameters": {}},
        {"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "Build"}, {"context": "Scan"}]}},
    ]
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": Resp(0, json.dumps(rules)),
        "/branches/main/protection": NOT_FOUND,
    }))
    assert sorted(crc.fetch_configured_contexts("o/r", "main")) == ["Build", "Scan"]


def test_classic_branch_protection_is_still_read(monkeypatch) -> None:
    prot = {"required_status_checks": {"contexts": ["Legacy gate"]}}
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": Resp(0, "[]"),
        "/branches/main/protection": Resp(0, json.dumps(prot)),
    }))
    assert crc.fetch_configured_contexts("o/r", "main") == ["Legacy gate"]


def test_both_mechanisms_union(monkeypatch) -> None:
    rules = [{"type": "required_status_checks",
              "parameters": {"required_status_checks": [{"context": "Build"}]}}]
    prot = {"required_status_checks": {"contexts": ["Legacy gate"]}}
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": Resp(0, json.dumps(rules)),
        "/branches/main/protection": Resp(0, json.dumps(prot)),
    }))
    assert sorted(crc.fetch_configured_contexts("o/r", "main")) == ["Build", "Legacy gate"]


def test_neither_mechanism_readable_raises(monkeypatch) -> None:
    """403 on both is 'I could not ask' — never compared against."""
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": FORBIDDEN,
        "/branches/main/protection": FORBIDDEN,
    }))
    with pytest.raises(RuntimeError, match="could not read"):
        crc.fetch_configured_contexts("o/r", "main")


def test_one_mechanism_unreadable_does_not_sink_the_other(monkeypatch) -> None:
    rules = [{"type": "required_status_checks",
              "parameters": {"required_status_checks": [{"context": "Build"}]}}]
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": Resp(0, json.dumps(rules)),
        "/branches/main/protection": FORBIDDEN,
    }))
    assert crc.fetch_configured_contexts("o/r", "main") == ["Build"]


def test_unparseable_response_is_not_read_as_empty(monkeypatch) -> None:
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/main": Resp(0, "<html>proxy error</html>"),
        "/branches/main/protection": Resp(0, "<html>proxy error</html>"),
    }))
    with pytest.raises(RuntimeError, match="could not read"):
        crc.fetch_configured_contexts("o/r", "main")


def test_the_policy_is_read_for_the_named_branch(monkeypatch) -> None:
    """Ref scoping: a release-branch ruleset must not be compared against main.

    The evaluation is delegated to the host — `/rules/branches/<ref>` returns
    only the rules GitHub itself applies to that ref — so what this pins is that
    the branch really reaches the URL.
    """
    seen: list[str] = []
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "/rules/branches/release/v2": Resp(0, "[]"),
        "/branches/release/v2/protection": NOT_FOUND,
    }, recorder=seen))
    crc.fetch_configured_contexts("o/r", "release/v2")
    assert any(e.endswith("/rules/branches/release/v2") for e in seen), seen
    assert not any("branches/main" in e for e in seen), seen


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


def test_unreachable_repo_exits_2_before_any_policy_lookup(monkeypatch, capsys) -> None:
    """A typo'd slug must not be read as 'this repo protects nothing'."""
    seen: list[str] = []
    monkeypatch.setattr(crc.subprocess, "run",
                        gh_router({"repos/o/r": NOT_FOUND}, recorder=seen))
    assert crc.main(["--project-root", str(REPO_ROOT), "--repo", "o/r", "--no-file"]) == 2
    assert "[required-checks]" in capsys.readouterr().err
    assert not any("/rules/branches" in e for e in seen), (
        "policy was queried for a repo we could not even read"
    )


def test_missing_gh_exits_2_without_a_traceback(monkeypatch, capsys) -> None:
    def _run(argv, **kwargs):
        if argv and argv[0] == "git":
            return Resp(0, "https://github.com/o/r.git\n")
        raise FileNotFoundError("gh")

    monkeypatch.setattr(crc.subprocess, "run", _run)
    assert crc.main(["--project-root", str(REPO_ROOT), "--no-file"]) == 2
    assert "not installed" in capsys.readouterr().err


def test_one_divergence_files_one_card_across_repeated_invocations(
    tmp_path, monkeypatch
) -> None:
    """Repeated runs against unchanged drift must leave exactly one card.

    Idempotency was always the design — `append_triage_item_idempotent` keyed on
    the exact divergence — but it only became load-bearing when
    iterate-2026-08-05-wire-local-guard-scripts wired this producer to a
    SessionStart hook, so it now runs unattended instead of when a human types it.

    This is also the suite's first exercise of the REAL triage store: every other
    test here stubs the append out, which cannot show accumulation.
    """
    from triage import read_all_items

    (tmp_path / "shipwright_run_config.json").write_text('{"status": "complete"}',
                                                         encoding="utf-8")
    (tmp_path / ".shipwright").mkdir()
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: CI\non:\n  pull_request:\n    branches: [main]\njobs:\n"
        "  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "repos/o/r": REPO_OK,
        "/rules/branches/main": Resp(0, "[]"),      # no ruleset …
        "/branches/main/protection": NOT_FOUND,     # … and not protected → drift
    }))

    for _ in range(3):
        assert crc.main(["--project-root", str(tmp_path)]) == 0

    cards = [i for i in read_all_items(tmp_path)
             if (i.get("source") or "") == "required-checks"]
    assert len(cards) == 1, (
        f"three invocations filed {len(cards)} cards for one unchanged divergence — "
        f"the inbox would grow by one card per session opened."
    )

    # WHERE it landed, not merely that `read_all_items` can see it — that function
    # unions the tracked log with the gitignored outbox, so it cannot tell them
    # apart. On a non-iterate tree the routing decision is the tracked log, which
    # F6 stages and which therefore reaches origin.
    assert (tmp_path / ".shipwright" / "triage.jsonl").is_file(), (
        "the card went to the gitignored outbox. `to_outbox` was hardcoded True "
        "until iterate-2026-08-05-wire-local-guard-scripts; wiring this producer "
        "to SessionStart made that load-bearing, because a session opened inside "
        "`.worktrees/<slug>` resolves the WORKTREE, whose outbox no sweep reads "
        "and which is deleted with the tree — the finding would be written to a "
        "buffer nothing drains and then destroyed."
    )


def test_in_sync_repo_exits_0_and_files_nothing(monkeypatch, capsys) -> None:
    derived = crc.all_workflow_check_names(REPO_ROOT)
    rules = [{"type": "required_status_checks", "parameters": {
        "required_status_checks": [{"context": c} for c in derived]}}]
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "repos/o/r": REPO_OK,
        "/rules/branches/main": Resp(0, json.dumps(rules)),
        "/branches/main/protection": NOT_FOUND,
    }))
    filed: list[dict] = []
    monkeypatch.setattr(crc, "append_triage_item_idempotent",
                        lambda *a, **k: filed.append(k) or "trg-test")
    rc = crc.main(["--project-root", str(REPO_ROOT), "--repo", "o/r", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["in_sync"] is True
    assert filed == [], "an in-sync repo must file nothing"


def test_drift_files_one_item_keyed_on_repo_and_branch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(crc.subprocess, "run", gh_router({
        "repos/o/r": REPO_OK,
        "/rules/branches/main": Resp(0, "[]"),      # requires nothing
        "/branches/main/protection": NOT_FOUND,
    }))
    filed: list[dict] = []
    monkeypatch.setattr(crc, "append_triage_item_idempotent",
                        lambda *a, **k: filed.append(k) or "trg-test")
    assert crc.main(["--project-root", str(REPO_ROOT), "--repo", "o/r"]) == 0
    capsys.readouterr()
    assert len(filed) == 1
    assert filed[0]["source"] == "required-checks"
    # ROUTED, not hardcoded. This asserted `is True` until
    # iterate-2026-08-05-wire-local-guard-scripts, which is what pinned the bug:
    # `to_outbox=True` was harmless while a human typed this on main, but wiring
    # the producer to a SessionStart hook made it load-bearing — a session opened
    # inside `.worktrees/<slug>` resolves the WORKTREE, whose outbox no sweep
    # reads and which is deleted with the tree. Every sibling producer routes
    # conditionally; the value is now whatever `should_route_to_outbox` decides
    # for the tree in hand, which is what this asserts.
    assert filed[0]["to_outbox"] == crc.should_route_to_outbox(REPO_ROOT)
    assert "o/r@main" in filed[0]["dedup_key"], filed[0]["dedup_key"]
