"""Suppression discovery — what is *actually* in effect, not what is written.

``accepted_risk_scan`` answers one question for the drift gate and the
compliance dashboard alike: which suppressions are live right now? Getting that
wrong in the permissive direction is silent — the gate reports the register
"reconciled" while the scanner has already stopped suppressing, which is exactly
the state that renewing only the register's date produces.

The expiry rules here are Trivy's, not ours, and are mirrored from its source
rather than from its prose (``pkg/result/ignore.go``):

* an entry lapses when ``ExpiredAt.Before(now)``, and ``ExpiredAt`` parses with
  layout ``2006-01-02`` — midnight — so in date terms an entry lapses **from**
  its date, not the day after;
* both ignore-file forms carry one: ``expired_at:`` in the YAML form,
  ``exp:YYYY-MM-DD`` as a field in the classic flat form.

Origin: iterate-2026-07-31-accepted-risk-gate-holes.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import accepted_risk_scan as scan  # noqa: E402
import accepted_risks as ar  # noqa: E402

_NOW = date(2026, 6, 22)
_LAPSED = "2026-06-01"
_LIVE = "2099-01-01"


def _yaml(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".trivyignore.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def _flat(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".trivyignore").write_text(body, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# YAML form — `expired_at`
# ---------------------------------------------------------------------------


def test_lapsed_yaml_entry_is_not_an_active_suppression(tmp_path):
    root = _yaml(tmp_path, f"vulnerabilities:\n  - id: CVE-X\n    expired_at: {_LAPSED}\n")
    assert scan.read_trivyignore_ids(root, now=_NOW) == set(), (
        "Trivy stopped applying this entry; counting it lets the gate call the "
        "register reconciled against a suppression that is not in effect"
    )


def test_unexpired_and_undated_yaml_entries_stay_active(tmp_path):
    root = _yaml(
        tmp_path,
        f"vulnerabilities:\n  - id: CVE-LIVE\n    expired_at: {_LIVE}\n"
        "  - id: CVE-FOREVER\n",
    )
    # No `expired_at` means "always valid" per Trivy's own docs — not "lapsed".
    assert scan.read_trivyignore_ids(root, now=_NOW) == {"CVE-LIVE", "CVE-FOREVER"}


def test_expiry_boundary_matches_trivys_own_rule(tmp_path):
    """Lapsed FROM the date, because Trivy parses it to midnight.

    This is deliberately one day earlier than ``Acceptance.is_expired``, which
    keeps the REGISTER's own due date active on the day itself. The two answer
    different questions and must not be collapsed into one helper.
    """
    root = _yaml(tmp_path, "vulnerabilities:\n  - id: CVE-X\n    expired_at: 2026-06-22\n")
    assert scan.read_trivyignore_ids(root, now=date(2026, 6, 21)) == {"CVE-X"}
    assert scan.read_trivyignore_ids(root, now=date(2026, 6, 22)) == set()
    # ... while the register's own semantics keep that same date active:
    assert ar.Acceptance(
        id="x", target=ar.TARGET_TRIVY_IGNORE, rule="CVE-X",
        expires=date(2026, 6, 22), rationale_ref="ADR-271", statement="x" * 25,
    ).is_expired(date(2026, 6, 22)) is False


def test_unparseable_expiry_keeps_the_entry_active(tmp_path):
    """Fail-safe direction: unreadable date => treat as no expiry.

    An entry counted as ACTIVE merely has to be recorded in the register. One
    counted as absent would report a live suppression as STALE and send the
    operator to delete a register entry that is doing its job.
    """
    root = _yaml(tmp_path, "vulnerabilities:\n  - id: CVE-X\n    expired_at: whenever\n")
    assert scan.read_trivyignore_ids(root, now=_NOW) == {"CVE-X"}


def test_expiry_is_read_from_both_a_yaml_date_and_a_string(tmp_path):
    """PyYAML yields a `date` for an unquoted value and a `str` for a quoted one.

    The flat form can only ever yield a `str`. One promoted, polymorphic
    ``coerce_date`` covers both rather than a second parser drifting from it
    (external review, Gemini).
    """
    assert ar.coerce_date(date(2026, 6, 1)) == date(2026, 6, 1)
    assert ar.coerce_date("2026-06-01") == date(2026, 6, 1)
    quoted = _yaml(tmp_path, f'vulnerabilities:\n  - id: CVE-X\n    expired_at: "{_LAPSED}"\n')
    assert scan.read_trivyignore_ids(quoted, now=_NOW) == set()


# ---------------------------------------------------------------------------
# Classic flat form — Trivy's `exp:` field
# ---------------------------------------------------------------------------


def test_flat_trivyignore_honours_trivys_exp_field(tmp_path):
    root = _flat(
        tmp_path,
        f"CVE-LAPSED exp:{_LAPSED}\nCVE-LIVE exp:{_LIVE}\nCVE-NOEXP\n",
    )
    assert scan.read_trivyignore_ids(root, now=_NOW) == {"CVE-LIVE", "CVE-NOEXP"}


def test_flat_trivyignore_id_excludes_the_exp_field(tmp_path):
    """The id is a field, not the whole line.

    Before this fix the reader returned ``'CVE-LIVE exp:2099-01-01'`` as the id,
    so it could never match a register ``rule`` — a permanent false UNRECORDED.
    """
    root = _flat(tmp_path, f"CVE-LIVE exp:{_LIVE}\n")
    assert scan.read_trivyignore_ids(root, now=_NOW) == {"CVE-LIVE"}


def test_flat_trivyignore_skips_blank_and_comment_lines(tmp_path):
    """Blank, whitespace-only and comment-only lines yield no id.

    Splitting a line into fields must happen AFTER the comment is stripped, or a
    `#`-only line becomes a discovered suppression and a blank one raises
    (external review, GPT + Gemini).
    """
    root = _flat(
        tmp_path,
        "# a full-line comment\n\n   \n# exp:2020-01-01\nCVE-1  # trailing\n",
    )
    assert scan.read_trivyignore_ids(root, now=_NOW) == {"CVE-1"}


# ---------------------------------------------------------------------------
# The `now` seam
# ---------------------------------------------------------------------------


def test_discovery_honours_an_injected_now(tmp_path):
    """One resolved date flows through the whole operation.

    Callers that pass an explicit ``now`` (the compliance dashboard does) must
    get an answer derived from it, not from the wall clock — otherwise the same
    inputs render differently either side of midnight.
    """
    root = _yaml(tmp_path, "vulnerabilities:\n  - id: CVE-X\n    expired_at: 2026-12-22\n")
    before = scan.discovered_suppressions(root, now=date(2026, 6, 22))
    after = scan.discovered_suppressions(root, now=date(2027, 1, 1))
    assert before[ar.TARGET_TRIVY_IGNORE] == {"CVE-X"}
    assert after[ar.TARGET_TRIVY_IGNORE] == set()


def test_discovery_defaults_to_today(tmp_path):
    yesterday = (ar.today_utc() - timedelta(days=1)).isoformat()
    root = _yaml(
        tmp_path,
        f"vulnerabilities:\n  - id: CVE-GONE\n    expired_at: {yesterday}\n"
        f"  - id: CVE-HERE\n    expired_at: {_LIVE}\n",
    )
    assert scan.read_trivyignore_ids(root) == {"CVE-HERE"}


def _workflow(tmp_path: Path, env: str) -> Path:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "security.yml").write_text(
        "jobs:\n  scan:\n    steps:\n      - env:\n" + env, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Workflow-env and file-precedence parsing. Moved here from
# test_accepted_risks_register.py (which owns the GATE) so that every test of
# this module's readers lives with the module.
# ---------------------------------------------------------------------------


def test_commented_env_lines_are_not_live_suppressions(tmp_path):
    # security.yml documents each channel in prose directly above the real
    # assignment; a naive line scan would read the comment as a suppression.
    root = _workflow(
        tmp_path,
        "          # SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: documented.only\n")
    assert scan.discovered_suppressions(root)[ar.TARGET_SEMGREP_RULE] == set()


def test_workflow_with_actions_expressions_is_parsed(tmp_path):
    # `yaml.safe_load` chokes on an unquoted `${{ }}`; the targeted extractor
    # must not (external review, Gemini).
    root = _workflow(
        tmp_path,
        "          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n"
        "    if: ${{ github.ref == 'refs/heads/main' }}\n")
    assert scan.discovered_suppressions(root)[ar.TARGET_SEMGREP_RULE] == {
        "some.rule.id"}


@pytest.mark.parametrize(
    "raw,expected",
    [('"1"', True), ("true", True), ("on", True), ('"0"', False), ("", False)],
)
def test_toggle_truthiness_matches_the_producer(tmp_path, raw, expected):
    # The toggle is on/off per gh_action_tag_owner's own truthiness set, which
    # this module imports rather than re-deriving — so "on" must count too.
    root = _workflow(tmp_path, f"          {scan.ACCEPT_GH_ACTION_TAGS_ENV}: {raw}\n")
    found = scan.discovered_suppressions(root)[ar.TARGET_SEMGREP_TOGGLE]
    assert bool(found) is expected, raw


def test_classic_flat_trivyignore_is_read(tmp_path):
    # The scanner honours `.trivyignore`; the old compliance parser did not, so
    # a repo using it had suppression with zero visibility.
    root = _flat(tmp_path, "# a comment\nCVE-2026-1\nCVE-2026-2  # trailing\n")
    assert scan.read_trivyignore_ids(root) == {"CVE-2026-1", "CVE-2026-2"}


def test_yaml_trivyignore_wins_over_flat(tmp_path):
    _flat(tmp_path, "CVE-FLAT\n")
    _yaml(tmp_path, "vulnerabilities:\n  - id: CVE-YAML\n")
    assert scan.read_trivyignore_ids(tmp_path) == {"CVE-YAML"}


def test_expiry_does_not_reach_the_semgrep_channels(tmp_path):
    """Only the Trivy ignore file carries a per-entry date.

    The `SHIPWRIGHT_SEMGREP_*` env vars have no expiry at all, so nothing there
    may be silently dropped by an expiry rule.
    """
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "security.yml").write_text(
        "jobs:\n  scan:\n    steps:\n      - env:\n"
        "          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n",
        encoding="utf-8",
    )
    found = scan.discovered_suppressions(tmp_path, now=date(2099, 1, 1))
    assert found[ar.TARGET_SEMGREP_RULE] == {"some.rule.id"}
