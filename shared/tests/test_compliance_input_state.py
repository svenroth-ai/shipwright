"""What the refresh is allowed to UNDO, and what it must put back.

Subject: ``shared/scripts/tools/compliance_input_state.py`` and ``produce``'s
own refusal cleanup (iterate-2026-07-31-derived-docs-at-release). Split from
``test_compliance_refresh_produce.py``, which owns the loop and its refusals;
this owns the state protocol around them — because both defects Stage 3 found
here were invisible to a test that only watched the loop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Order matters and the inserts are UNCONDITIONAL. `shared/tests` carries its own
# `tools/` package, so it must never sit ahead of `shared/scripts` on the path —
# a `if p not in sys.path` guard would skip the second insert whenever conftest
# had already added it, leaving the tests dir in front and resolving
# `from tools import ...` to the wrong package (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import (  # noqa: E402
    BASE, DASHBOARD, RUN, all_ok, git, head_sha, seed_repo,
)
from tools import compliance_refresh_produce as produce_mod  # noqa: E402


@pytest.fixture
def compliance_refresh_repo(tmp_path: Path) -> Path:
    """:func:`seed_repo` as a fixture — see that module for why it is declared
    here rather than shared."""
    return seed_repo(tmp_path / "repo")

# --- a refusal rewinds the DOCUMENTS too, to what it found --------------------


def test_a_refusal_restores_an_operator_edit_rather_than_resetting_to_head(
    compliance_refresh_repo, monkeypatch,
):
    """External code review, openai/medium. `--stage` has no clean-tree preflight,
    so an operator may legitimately be holding an edit to one of these documents.
    Cleaning up after a refusal that was not their fault must not discard it."""
    mine = "# dashboard\n\nmy own uncommitted edit\n" + "row\n" * 60
    (compliance_refresh_repo / DASHBOARD).write_text(mine, encoding="utf-8")

    def empties_it(root, run_id):
        (root / DASHBOARD).write_text("", encoding="utf-8")
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge",
                        lambda root, *a, **k: (empties_it(root, RUN), (True, 2, all_ok()))[1])
    result, _ = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "content_floor"
    assert (compliance_refresh_repo / DASHBOARD).read_text(encoding="utf-8") == mine


# --- the producer's INPUTS are rewound, never discarded ----------------------


def test_uncommitted_appends_to_the_event_log_survive_the_run(
    compliance_refresh_repo, monkeypatch,
):
    """Stage-1 spec review, MEDIUM-4.

    Between passes the producer inputs must be rewound so pass N and pass N+1 see
    the same tree. Rewinding to ``HEAD`` cannot tell this run's throwaway appends
    from appends that were already there — and on the ``--stage`` path, which has
    no clean-tree preflight, a dirty event log is the normal mid-session state.
    Discarding it is trg-ad29a709's defect wearing a different hat.
    """
    # TRACKED and then dirtied — the exact shape of the finding. Left untracked
    # this test would pass against the OLD `git checkout HEAD --` code too (the
    # checkout would simply fail and leave the file alone), so only the second
    # assertion would discriminate (Stage-1 re-review, note 1).
    log = compliance_refresh_repo / "shipwright_events.jsonl"
    log.write_text('{"id":"evt-committed"}\n', encoding="utf-8")
    git(compliance_refresh_repo, "add", "--", "shipwright_events.jsonl")
    git(compliance_refresh_repo, "commit", "-m", "seed the event log")
    log.write_text('{"id":"evt-committed"}\n{"id":"evt-operator"}\n', encoding="utf-8")

    def appends_then_regenerates(root, run_id):
        with (root / "shipwright_events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"id":"evt-throwaway","type":"grade_snapshot"}\n')
        return all_ok()

    produce_mod.converge(compliance_refresh_repo, RUN,
                         regenerate=appends_then_regenerates)

    text = log.read_text(encoding="utf-8")
    assert "evt-committed" in text
    assert "evt-operator" in text, "the operator's uncommitted append was discarded"


def test_a_CONCURRENT_append_during_a_pass_is_never_destroyed(compliance_refresh_repo):
    """Stage-3 doubt D1 — the defect the first fix had exactly backwards.

    A concurrent append LEAVES the entry-time snapshot as a prefix, so a
    "restore only while it is still a prefix" guard passed and wrote the snapshot
    back over it. The guard only fired on a rewrite, which was never the reported
    case. The rule is now the safe direction: an append-only log that grew is left
    alone, whoever grew it, and the path is recorded.
    """
    log = compliance_refresh_repo / "shipwright_events.jsonl"
    log.write_text('{"id":"evt-before"}\n', encoding="utf-8")

    def another_writer_appends(root, run_id):
        # Stands in for a background producer — the documented stray-event class.
        with (root / "shipwright_events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"id":"evt-concurrent"}\n')
        return all_ok()

    produce_mod.converge(compliance_refresh_repo, RUN,
                         regenerate=another_writer_appends)

    text = log.read_text(encoding="utf-8")
    assert "evt-before" in text
    assert "evt-concurrent" in text, "a concurrent append was destroyed"
    assert "shipwright_events.jsonl" in produce_mod.converge.left_alone, (
        "the rewind declined to touch it and said nothing"
    )


def test_a_left_alone_input_reaches_the_operator(compliance_refresh_repo):
    """Recording it on the function and never reporting it is how the first
    version of this guard went unnoticed."""
    log = compliance_refresh_repo / "shipwright_events.jsonl"
    log.write_text('{"id":"evt-before"}\n', encoding="utf-8")

    def appends(root, run_id):
        with (root / "shipwright_events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"id":"evt-mid-run"}\n')
        return all_ok()

    produce_mod.converge(compliance_refresh_repo, RUN, regenerate=appends)
    result, _ = produce_mod.produce(
        compliance_refresh_repo, RUN, head_sha(compliance_refresh_repo), None)
    assert "shipwright_events.jsonl" in result.get("inputs_left_alone", [])


def test_a_rewritten_producer_config_IS_rewound(compliance_refresh_repo):
    """Stage-3 doubt D6. The compliance config is REWRITTEN, not appended to, so
    lumping it in with the logs left it dirty after every run — including every
    refusal — and the next `--pr` then refused preflight on a change the operator
    never made."""
    config = compliance_refresh_repo / "shipwright_compliance_config.json"
    config.write_text('{"phases_covered": []}', encoding="utf-8")

    def rewrites_the_config(root, run_id):
        (root / "shipwright_compliance_config.json").write_text(
            '{"phases_covered": ["iterate"], "extra": 1}', encoding="utf-8")
        return all_ok()

    produce_mod.converge(compliance_refresh_repo, RUN, regenerate=rewrites_the_config)
    assert config.read_text(encoding="utf-8") == '{"phases_covered": []}'
    assert "shipwright_compliance_config.json" not in produce_mod.converge.left_alone


def test_the_inputs_are_rewound_even_when_a_pass_raises(compliance_refresh_repo):
    """A producer that blows up must not leave its throwaway appends in the
    operator's event log."""
    log = compliance_refresh_repo / "shipwright_events.jsonl"
    log.write_text('{"id":"evt-operator"}\n', encoding="utf-8")
    config = compliance_refresh_repo / "shipwright_compliance_config.json"
    config.write_text('{"phases_covered": []}', encoding="utf-8")

    def explodes(root, run_id):
        with (root / "shipwright_events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"id":"evt-throwaway"}\n')
        (root / "shipwright_compliance_config.json").write_text(
            '{"phases_covered": ["iterate"]}', encoding="utf-8")
        raise RuntimeError("collector died")

    with pytest.raises(RuntimeError):
        produce_mod.converge(compliance_refresh_repo, RUN, regenerate=explodes)

    # The log is append-only, so its content survives whoever wrote it; what a
    # raise must not do is leave the REWRITTEN config behind.
    assert "evt-operator" in log.read_text(encoding="utf-8")
    assert config.read_text(encoding="utf-8") == '{"phases_covered": []}'


def test_a_path_missing_from_the_payload_is_blocked_not_skipped(compliance_refresh_repo, monkeypatch):
    """Capture omits a symlink rather than reading through it, so the path is
    simply ABSENT from the payload. The floor must read that gap as a violation —
    a delivery that quietly drops one of the seven is the fail-open shape."""
    real_capture = produce_mod.capture

    def capture_without_dashboard(root):
        payload = real_capture(root)
        payload.pop(DASHBOARD, None)
        return payload

    monkeypatch.setattr(produce_mod, "capture", capture_without_dashboard)
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (True, 2, all_ok()))
    result, payload = produce_mod.produce(compliance_refresh_repo, RUN, BASE, None)
    assert result["status"] == "content_floor"
    assert DASHBOARD in result["violations"]
    assert payload == {}


def test_capture_skips_a_symlink_rather_than_reading_through_it(compliance_refresh_repo):
    """Reading through one would commit the TARGET's bytes to a public branch."""
    target = compliance_refresh_repo / "outside.md"
    target.write_text("secret\n" * 40, encoding="utf-8")
    link = compliance_refresh_repo / DASHBOARD
    link.unlink()
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        # Silent-skip CI-discipline rule: a developer on Windows without
        # SeCreateSymbolicLinkPrivilege may skip this; CI (Linux) has no excuse,
        # and a leak of a symlink TARGET onto a public branch is exactly what
        # this test exists to catch.
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                f"CI cannot create a symlink ({exc}) — this must not silently skip. "
                "On Linux runners no privilege is needed; check the workspace "
                "filesystem rather than deleting the test."
            )
        pytest.skip("this platform/user cannot create symlinks")
    payload = produce_mod.capture(compliance_refresh_repo)
    assert DASHBOARD not in payload
    assert b"secret" not in b"".join(payload.values())
