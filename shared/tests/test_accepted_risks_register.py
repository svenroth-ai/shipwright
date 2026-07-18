"""The enforcement seam for the accepted-risk register.

These tests ARE the gate. The register and the drift reconciler are libraries;
what makes them binding is that this file runs on the path CI already requires
(``shared/tests``). The first draft of this iterate shipped the reconciler with
nothing invoking it — which the external review correctly called out as
rebuilding the very defect the register exists to fix: an expiry nobody enforces
is a comment, not a control.

Two halves:

* **Live guards** — run against the REAL repo. They fail the build when a
  suppression exists with no record, when the register claims an acceptance that
  is no longer wired up, or when an acceptance is past its re-review date.
* **Negative controls** — synthetic repos proving each guard actually fires. A
  gate is only real once you have watched it go red on the bug it is meant to
  catch (conventions.md, iterate-2026-07-14-phase-invocation-mode).
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import accepted_risks as ar  # noqa: E402
from tools import accepted_risks_cli as cli  # noqa: E402


# ---------------------------------------------------------------------------
# Live guards — these are the actual CI gate
# ---------------------------------------------------------------------------


def test_register_and_suppressions_agree():
    """Every suppression is recorded, and every record is a real suppression."""
    result = cli.reconcile(REPO_ROOT)
    problems = cli._format_check(result)
    assert result["ok"], (
        "Accepted-risk register drift in this repo:\n\n"
        + "\n".join(problems)
        + "\n\nReconcile with: uv run shared/scripts/tools/"
        "accepted_risks_cli.py check --project-root ."
    )


def test_no_acceptance_is_past_its_review_date():
    entries = ar.load_register(REPO_ROOT)
    overdue = ar.expired(entries, ar.today_utc())
    assert not overdue, (
        "Accepted risks are past their re-review date — fix the finding or renew "
        "`expires` with a fresh rationale:\n  - "
        + "\n  - ".join(f"{e.id} (due {e.expires}, ref {e.rationale_ref})" for e in overdue)
    )


def test_repo_register_is_loadable_and_non_empty():
    # If the register ever silently became empty, both guards above would pass
    # vacuously while every suppression went unrecorded.
    entries = ar.load_register(REPO_ROOT)
    assert entries, "this repo has accepted risks; the register must record them"
    assert all(e.rationale_ref for e in entries)


def test_every_seeded_rationale_ref_is_a_recorded_decision():
    for entry in ar.load_register(REPO_ROOT):
        assert ar.DECISION_REF_RE.search(entry.rationale_ref), entry.id


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
# Parsing edge cases the review flagged
# ---------------------------------------------------------------------------


def test_commented_env_lines_are_not_live_suppressions(tmp_path):
    # security.yml documents each channel in prose directly above the real
    # assignment; a naive line scan would read the comment as a suppression.
    root = _repo(
        tmp_path,
        register="schema: 1\nacceptances: []\n",
        workflow_env="          # SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: documented.only\n",
    )
    assert cli.reconcile(root)["ok"]


def test_workflow_with_actions_expressions_is_parsed(tmp_path):
    # `yaml.safe_load` chokes on an unquoted `${{ }}`; the targeted extractor
    # must not (external review, Gemini).
    root = _repo(
        tmp_path,
        register=_register("some.rule.id", ar.TARGET_SEMGREP_RULE),
        workflow_env=(
            "          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n"
            "    if: ${{ github.ref == 'refs/heads/main' }}\n"
        ),
    )
    assert cli.reconcile(root)["ok"]


@pytest.mark.parametrize(
    "raw,expected",
    [('"1"', True), ("true", True), ("on", True), ('"0"', False), ("", False)],
)
def test_toggle_truthiness_matches_the_producer(tmp_path, raw, expected):
    # The toggle is on/off per gh_action_tag_owner's own truthiness set, which
    # this gate imports rather than re-deriving — so "on" must count too.
    root = _repo(
        tmp_path,
        register="schema: 1\nacceptances: []\n",
        workflow_env=f"          {cli.ACCEPT_GH_ACTION_TAGS_ENV}: {raw}\n",
    )
    found = cli.discovered_suppressions(root)[ar.TARGET_SEMGREP_TOGGLE]
    assert bool(found) is expected, raw


def test_classic_flat_trivyignore_is_read(tmp_path):
    # The scanner honours `.trivyignore`; the old compliance parser did not, so
    # a repo using it had suppression with zero visibility.
    (tmp_path / ".trivyignore").write_text(
        "# a comment\nCVE-2026-1\nCVE-2026-2  # trailing\n", encoding="utf-8")
    assert cli.read_trivyignore_ids(tmp_path) == {"CVE-2026-1", "CVE-2026-2"}


def test_yaml_trivyignore_wins_over_flat(tmp_path):
    (tmp_path / ".trivyignore").write_text("CVE-FLAT\n", encoding="utf-8")
    (tmp_path / ".trivyignore.yaml").write_text(
        "vulnerabilities:\n  - id: CVE-YAML\n", encoding="utf-8")
    assert cli.read_trivyignore_ids(tmp_path) == {"CVE-YAML"}
