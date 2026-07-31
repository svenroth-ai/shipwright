"""The enforcement seam for the accepted-risk register — SYNTHETIC controls.

These prove each guard actually fires. A gate is only real once you have watched
it go red on the bug it is meant to catch (conventions.md,
iterate-2026-07-14-phase-invocation-mode).

The **live guards** — the ones that run against the REAL repo and are what
actually fails the build — live in ``test_accepted_risks_repo_guards.py``. They
were split out when this file crossed the 300-line cap; the seam is the one this
file's own docstring already drew.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import accepted_risks as ar  # noqa: E402
from tools import accepted_risks_cli as cli  # noqa: E402


# ---------------------------------------------------------------------------
# Negative controls — prove each guard fires
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path, *, register: str | None, workflow_env: str = "",
          trivy: str | None = None) -> Path:
    if register is not None:
        (tmp_path / ar.REGISTER_NAME).write_text(register, encoding="utf-8")
    if trivy is not None:
        (tmp_path / ".trivyignore.yaml").write_text(trivy, encoding="utf-8")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "security.yml").write_text(
        "jobs:\n  scan:\n    steps:\n      - env:\n" + workflow_env, encoding="utf-8"
    )
    return tmp_path


def _register(rule: str, target: str, expires: str = "2099-01-01") -> str:
    return (
        "schema: 1\nacceptances:\n"
        f"  - id: ar-test-entry\n    target: {target}\n    rule: {rule}\n"
        f"    expires: {expires}\n    rationale_ref: ADR-271\n"
        "    statement: >-\n      A sufficiently long justification for the test.\n"
    )


def test_unrecorded_suppression_fails(tmp_path):
    """A suppression with no register entry must be caught."""
    root = _repo(
        tmp_path,
        register="schema: 1\nacceptances: []\n",
        workflow_env="          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n",
    )
    result = cli.reconcile(root)
    assert not result["ok"]
    assert result["unrecorded"] == [(ar.TARGET_SEMGREP_RULE, "some.rule.id")]


def test_stale_register_entry_fails(tmp_path):
    """A register entry with no matching suppression must be caught."""
    root = _repo(tmp_path, register=_register("gone.rule.id", ar.TARGET_SEMGREP_RULE))
    result = cli.reconcile(root)
    assert not result["ok"]
    assert result["stale"] == [(ar.TARGET_SEMGREP_RULE, "gone.rule.id")]


def test_matching_pair_is_clean(tmp_path):
    root = _repo(
        tmp_path,
        register=_register("some.rule.id", ar.TARGET_SEMGREP_RULE),
        workflow_env="          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n",
    )
    assert cli.reconcile(root)["ok"]


def test_expired_entry_is_reported(tmp_path):
    yesterday = ar.today_utc() - timedelta(days=1)
    root = _repo(
        tmp_path,
        register=_register("some.rule.id", ar.TARGET_SEMGREP_RULE,
                           expires=yesterday.isoformat()),
        workflow_env="          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n",
    )
    assert ar.expired(ar.load_register(root), ar.today_utc())


def test_github_dismissal_is_reported_unchecked_not_silently_skipped(tmp_path):
    root = _repo(tmp_path, register=_register("py/some-query",
                                              ar.TARGET_GITHUB_DISMISSAL))
    result = cli.reconcile(root)
    assert result["ok"], "a non-static target must not count as drift"
    assert [e.rule for e in result["unchecked"]] == ["py/some-query"]


# ---------------------------------------------------------------------------
# Deleting the record must not delete the gate
# (iterate-2026-07-31-accepted-risk-gate-holes, hole 1)
# ---------------------------------------------------------------------------


def test_absent_register_does_not_silence_live_suppressions(tmp_path):
    """No register at all is the loudest drift, not a reason to skip the check.

    The gate used to return success on a missing FILE before discovering
    anything, so removing `shipwright_accepted_risks.yaml` silenced it while
    every suppression stayed live.
    """
    root = _repo(
        tmp_path, register=None,
        workflow_env="          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.live.rule\n",
    )
    result = cli.reconcile(root)
    assert not result["ok"]
    assert result["unrecorded"] == [(ar.TARGET_SEMGREP_RULE, "some.live.rule")]


def test_absent_register_without_suppressions_is_still_clean(tmp_path):
    """A genuinely fresh/legacy repo is not made red — nothing is suppressed."""
    result = cli.reconcile(_repo(tmp_path, register=None))
    assert result["ok"]
    assert result["entries"] == []


def test_deleting_the_register_cannot_silence_this_repos_gate(tmp_path):
    """The sharpened form of the finding, over THIS repo's real inputs.

    A contributor who removes the register *and* the
    `test_repo_register_is_loadable_and_non_empty` backstop in one change used
    to pass. Reconciling unconditionally is what makes the backstop a
    convenience rather than the only thing holding the gate up — so this test
    deliberately reproduces the repo's suppressions WITHOUT its register.
    """
    for name in (".trivyignore.yaml", ".trivyignore.yml", ".trivyignore"):
        src = REPO_ROOT / name
        if src.is_file():
            (tmp_path / name).write_text(src.read_text(encoding="utf-8"),
                                         encoding="utf-8")
            break
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "security.yml").write_text(
        (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(
            encoding="utf-8"),
        encoding="utf-8",
    )
    assert not (tmp_path / ar.REGISTER_NAME).exists()
    # State the premise explicitly. If this repo ever legitimately stops
    # suppressing anything, THIS is the assertion that should fail, naming the
    # real reason — not the one below, whose message would then assert a
    # precondition that had quietly become false.
    live = cli.reconcile(tmp_path)["discovered"]
    # Asserted PER CHANNEL, not repo-wide. A repo-wide `any()` stays true off
    # the semgrep channels alone, so once the Trivy entries lapse this test
    # would keep passing while silently no longer exercising the Trivy leg it
    # was written for — the exact rot the expiry filter makes possible.
    for channel in (ar.TARGET_TRIVY_IGNORE, ar.TARGET_SEMGREP_RULE):
        assert live.get(channel), (
            f"premise gone for {channel}: this repo no longer has a live "
            "suppression on that channel, so a deleted register has nothing to "
            "fail to record there. Fix the premise, do not delete the test."
        )

    # Driven through cmd_check, not reconcile(): reconcile() was never the bug.
    # The early return sat in FRONT of it, so a test that calls reconcile()
    # directly passes even with the hole wide open.
    assert cli.cmd_check(tmp_path) == 1, (
        "this repo has live suppressions; with the register deleted the gate "
        "must exit non-zero instead of reporting nothing to reconcile"
    )
    assert cli.reconcile(tmp_path)["unrecorded"], "the gate must name what is unrecorded"


def test_renewing_only_the_register_is_reported_as_stale(tmp_path):
    """Hole 2 at the gate level.

    The ignore entry has lapsed, so Trivy no longer suppresses; only the
    register was renewed. That must read as STALE (the record claims something
    that is not in place), never as "reconciled".
    """
    yesterday = (ar.today_utc() - timedelta(days=1)).isoformat()
    root = _repo(
        tmp_path,
        register=_register("CVE-LAPSED", ar.TARGET_TRIVY_IGNORE),
        trivy=f"vulnerabilities:\n  - id: CVE-LAPSED\n    expired_at: {yesterday}\n",
    )
    result = cli.reconcile(root)
    assert not result["ok"]
    assert result["stale"] == [(ar.TARGET_TRIVY_IGNORE, "CVE-LAPSED")]
    # Through the gate entry point too, so the row claiming "exit 1 + STALE"
    # is true of THIS test rather than only by composition with another one.
    assert cli.cmd_check(root) == 1


def test_a_lapsed_entry_is_told_to_renew_not_to_delete(tmp_path, capsys):
    """The STALE advice must fit the cause, or it destroys a live acceptance.

    A stale record has two causes that need opposite actions: the suppression
    was removed (delete the record) versus the ignore entry's own date lapsed
    (renew both). This repo walks into the second one on a schedule — its
    register `expires` and its `.trivyignore.yaml` `expired_at` are set to the
    SAME day (2026-12-22, 2027-01-28), and those lapse a day apart because a
    register entry is active ON its date while a Trivy entry is not. Printing
    "remove the register entry" there would delete an acceptance that is still
    doing its job.
    """
    yesterday = (ar.today_utc() - timedelta(days=1)).isoformat()
    root = _repo(
        tmp_path,
        register=_register("CVE-LAPSED", ar.TARGET_TRIVY_IGNORE),
        trivy=f"vulnerabilities:\n  - id: CVE-LAPSED\n    expired_at: {yesterday}\n",
    )
    assert cli.reconcile(root)["lapsed"] == {"CVE-LAPSED"}
    assert cli.cmd_check(root) == 1
    out = capsys.readouterr().out
    assert "still in the file" in out and "renew BOTH dates" in out
    assert "remove the register entry" not in out, (
        "that advice belongs to the OTHER cause of STALE and would delete a "
        "live acceptance here"
    )


def test_a_genuinely_removed_suppression_still_says_remove(tmp_path, capsys):
    """The other cause keeps its original advice — nothing regressed."""
    root = _repo(tmp_path, register=_register("gone.rule.id", ar.TARGET_SEMGREP_RULE))
    assert cli.reconcile(root)["lapsed"] == set()
    assert cli.cmd_check(root) == 1
    out = capsys.readouterr().out
    assert "remove the register entry" in out
    assert "renew BOTH dates" not in out


def test_an_unparseable_ignore_file_does_not_advise_deleting_records(
        tmp_path, capsys):
    """The THIRD cause of STALE — and the one most likely to destroy records.

    A YAML typo in the hand-authored ignore file makes the reader return an
    empty set, which is indistinguishable from "nothing is suppressed". Every
    Trivy acceptance in the register then reads as STALE, and the remove-the-
    record advice would delete real acceptances over a syntax error.
    """
    root = _repo(
        tmp_path,
        register=_register("CVE-BROKEN", ar.TARGET_TRIVY_IGNORE),
        trivy="vulnerabilities:\n  - id: [oops\n   broken",
    )
    result = cli.reconcile(root)
    assert result["ignore_unreadable"] is True
    assert cli.cmd_check(root) == 1
    out = capsys.readouterr().out
    assert "does not parse" in out and "check the ignore file's syntax" in out
    assert "Do NOT remove register entries" in out
    assert "remove the register entry, or restore" not in out


def test_a_missing_ignore_file_is_not_called_unreadable(tmp_path):
    """No file at all is a different thing from a file that will not parse."""
    root = _repo(tmp_path, register=_register("CVE-X", ar.TARGET_TRIVY_IGNORE))
    assert cli.reconcile(root)["ignore_unreadable"] is False


def test_lapsed_advice_is_scoped_to_the_trivy_channel(tmp_path, capsys):
    """A semgrep rule that happens to share a lapsed Trivy id keeps its own advice.

    `lapsed` holds bare rule strings, so matching without checking the target
    would hand Trivy-only advice ("renew expired_at: / exp:") to a channel that
    has no expiry field at all.
    """
    yesterday = (ar.today_utc() - timedelta(days=1)).isoformat()
    register = (
        "schema: 1\nacceptances:\n"
        "  - id: ar-collide\n    target: semgrep-rule-exclusion\n"
        "    rule: CVE-COLLIDE\n    expires: 2099-01-01\n"
        "    rationale_ref: ADR-271\n"
        "    statement: >-\n      A sufficiently long justification for the test.\n"
    )
    root = _repo(
        tmp_path, register=register,
        trivy=f"vulnerabilities:\n  - id: CVE-COLLIDE\n    expired_at: {yesterday}\n",
    )
    assert cli.reconcile(root)["lapsed"] == {"CVE-COLLIDE"}
    assert cli.cmd_check(root) == 1
    out = capsys.readouterr().out
    assert "semgrep-rule-exclusion: CVE-COLLIDE" in out
    assert "renew BOTH dates" not in out, (
        "the semgrep channel has no expiry field; Trivy advice does not apply")


# Discovery-layer parsing edge cases (`read_workflow_env`, `read_trivyignore_ids`,
# `discovered_suppressions`) live with the module they exercise, in
# `test_accepted_risk_scan.py`. This file owns the GATE.
