"""Reader + validation for the scanner-agnostic accepted-risk register.

Before this module the only accepted-risk *due date* in the framework was
``expired_at`` inside ``.trivyignore.yaml`` — a Trivy SCA ignore file. A Semgrep
or CI-posture acceptance had nowhere to record an expiry, so webui registered a
Semgrep decision inside a Trivy ignore file to obtain one (an acknowledged
semantic stretch). ``shipwright_accepted_risks.yaml`` is the scanner-agnostic
record; this module is its single reader.

The validation is deliberately unforgiving. An acceptance silences a real
security signal, so a half-filled entry must be an ERROR, never a skipped row
that reads as "nothing accepted" — the failure mode where a suppression exists
with no record behind it.

Absent vs malformed is the load-bearing distinction (external review, GPT #8):
an ABSENT register is a legacy/fresh repo and reads as an empty register, while
a PRESENT-but-malformed one fails closed. Collapsing the two would let a broken
edit read as "all entries removed" and, downstream, license mass-dismissal.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import accepted_risks as ar  # noqa: E402

_VALID = """\
schema: 1
acceptances:
  - id: ar-2026-06-30-gh-owned-mutable-tags
    target: semgrep-policy-toggle
    rule: "yaml.github-actions.security.github-actions-mutable-action-tag"
    scope:
      owner: [actions, github]
    expires: 2026-12-30
    rationale_ref: "iterate-2026-07-18-unpin-actions-no-dependabot"
    statement: >-
      GitHub-owned actions stay on mutable tags by framework decision; pinning
      them would require a hosted updater to avoid tag rot.
"""


def _write(tmp_path: Path, text: str) -> Path:
    (tmp_path / ar.REGISTER_NAME).write_text(text, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# absent vs malformed (GPT #8) — the distinction the whole design rests on
# --------------------------------------------------------------------------


def test_absent_register_reads_as_empty(tmp_path):
    assert ar.register_exists(tmp_path) is False
    assert ar.load_register(tmp_path) == []


def test_malformed_yaml_fails_closed(tmp_path):
    _write(tmp_path, "acceptances: [oops\n  - broken")
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


def test_present_but_empty_document_fails_closed(tmp_path):
    # A truncated/emptied register must NOT read as "no acceptances" — that is
    # exactly the state that would silently un-record every suppression.
    _write(tmp_path, "")
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


def test_missing_acceptances_key_fails_closed(tmp_path):
    _write(tmp_path, "schema: 1\n")
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


def test_explicit_empty_list_is_valid(tmp_path):
    # Deliberately emptying the register is legitimate and distinguishable
    # from a truncated file: the key is present and the list is empty.
    _write(tmp_path, "schema: 1\nacceptances: []\n")
    assert ar.load_register(tmp_path) == []


def test_unknown_schema_fails_closed(tmp_path):
    _write(tmp_path, _VALID.replace("schema: 1", "schema: 99"))
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


# --------------------------------------------------------------------------
# happy path
# --------------------------------------------------------------------------


def test_valid_register_parses(tmp_path):
    entries = ar.load_register(_write(tmp_path, _VALID))
    assert len(entries) == 1
    e = entries[0]
    assert e.id == "ar-2026-06-30-gh-owned-mutable-tags"
    assert e.target == ar.TARGET_SEMGREP_TOGGLE
    assert e.expires == date(2026, 12, 30)
    assert e.scope == {"owner": ["actions", "github"]}
    assert "mutable tags" in e.statement


def test_expires_accepts_an_iso_string(tmp_path):
    _write(tmp_path, _VALID.replace("expires: 2026-12-30", 'expires: "2026-12-30"'))
    assert ar.load_register(tmp_path)[0].expires == date(2026, 12, 30)


# --------------------------------------------------------------------------
# per-field validation — every one of these is a negative control
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "old,new,why",
    [
        ("    expires: 2026-12-30\n", "", "missing expires"),
        ('    rationale_ref: "iterate-2026-07-18-unpin-actions-no-dependabot"\n', "",
         "missing rationale_ref"),
        ("target: semgrep-policy-toggle", "target: not-a-real-target", "unknown target"),
        ("expires: 2026-12-30", "expires: not-a-date", "unparseable date"),
        ('rationale_ref: "iterate-2026-07-18-unpin-actions-no-dependabot"',
         'rationale_ref: "TODO"', "filler rationale_ref"),
        ('rationale_ref: "iterate-2026-07-18-unpin-actions-no-dependabot"',
         'rationale_ref: "we talked about it"', "prose rationale_ref"),
        ("id: ar-2026-06-30-gh-owned-mutable-tags", 'id: ""', "empty id"),
    ],
)
def test_invalid_entry_is_an_error_not_a_skipped_row(tmp_path, old, new, why):
    _write(tmp_path, _VALID.replace(old, new))
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


def test_short_statement_is_rejected(tmp_path):
    text = _VALID.split("    statement:")[0] + '    statement: "x"\n'
    _write(tmp_path, text)
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


def test_duplicate_ids_are_rejected(tmp_path):
    _write(tmp_path, _VALID + _VALID.split("acceptances:\n")[1])
    with pytest.raises(ar.RegisterError):
        ar.load_register(tmp_path)


def test_rationale_ref_accepts_every_recorded_decision_form(tmp_path):
    for ref in ("ADR-260", "iterate-2026-07-18-unpin-actions-no-dependabot",
                "#285", "DO-NOT #25"):
        _write(tmp_path, _VALID.replace(
            '"iterate-2026-07-18-unpin-actions-no-dependabot"', f'"{ref}"'))
        assert ar.load_register(tmp_path)[0].rationale_ref == ref


# --------------------------------------------------------------------------
# expiry — evaluated against UTC, boundary inclusive (Gemini, low)
# --------------------------------------------------------------------------


def test_expiry_boundary_is_inclusive(tmp_path):
    entries = ar.load_register(_write(tmp_path, _VALID))
    e = entries[0]
    assert e.is_expired(date(2026, 12, 30)) is False, "due date itself is still active"
    assert e.is_expired(date(2026, 12, 31)) is True
    assert e.is_expired(date(2026, 12, 29)) is False


def test_expired_filters_the_list(tmp_path):
    entries = ar.load_register(_write(tmp_path, _VALID))
    assert ar.expired(entries, date(2027, 1, 1)) == entries
    assert ar.expired(entries, date(2026, 1, 1)) == []


def test_today_utc_is_a_date():
    assert isinstance(ar.today_utc(), date)


# --------------------------------------------------------------------------
# drift pin — the decision-ref recognizer is duplicated from the PR #401 gate
# on purpose (ADR-044: that verifier must stay self-contained). Pin both ends.
# --------------------------------------------------------------------------


def test_decision_ref_recognizer_matches_the_ci_supplychain_gate():
    from tools.verifiers import ci_supplychain as cs

    assert ar.DECISION_REF_RE.pattern == cs._DECISION_REF_RE.pattern, (
        "The accepted-risk register and the CI supply-chain ack gate must accept "
        "the SAME recorded-decision forms. One drifted — update both."
    )


# --------------------------------------------------------------------------
# target taxonomy — which targets a purely offline gate can reconcile
# --------------------------------------------------------------------------


def test_github_dismissal_is_not_statically_checkable():
    # A CodeQL/Scorecard acceptance has no source-controlled counterpart; it is
    # a live GitHub dismissal. It belongs in the register (it needs an expiry)
    # but cannot participate in an offline drift check.
    assert ar.TARGET_GITHUB_DISMISSAL in ar.TARGETS
    assert ar.TARGET_GITHUB_DISMISSAL not in ar.STATIC_TARGETS
    assert set(ar.STATIC_TARGETS) < set(ar.TARGETS)


# --------------------------------------------------------------------------
# Remaining validation + parse branches. These are error paths, and an error
# path nobody exercises is where fail-closed quietly becomes fail-open.
# --------------------------------------------------------------------------


def test_datetime_expires_is_narrowed_to_a_date(tmp_path):
    # PyYAML yields a datetime for a timestamp scalar, and datetime is a
    # SUBCLASS of date - checking date first would silently keep the time.
    _write(tmp_path, _VALID.replace("expires: 2026-12-30",
                                    "expires: 2026-12-30 08:30:00"))
    assert ar.load_register(tmp_path)[0].expires == date(2026, 12, 30)


def test_non_mapping_entry_is_rejected(tmp_path):
    _write(tmp_path, "schema: 1\nacceptances:\n  - just-a-string\n")
    with pytest.raises(ar.RegisterError, match="must be a mapping"):
        ar.load_register(tmp_path)


def test_missing_rule_is_rejected(tmp_path):
    _write(tmp_path, _VALID.replace(
        '    rule: "yaml.github-actions.security.github-actions-mutable-action-tag"\n',
        ""))
    with pytest.raises(ar.RegisterError, match="rule"):
        ar.load_register(tmp_path)


def test_non_mapping_scope_is_rejected(tmp_path):
    _write(tmp_path, _VALID.replace(
        "    scope:\n      owner: [actions, github]\n", "    scope: not-a-mapping\n"))
    with pytest.raises(ar.RegisterError, match="scope"):
        ar.load_register(tmp_path)


def test_non_mapping_document_is_rejected(tmp_path):
    _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ar.RegisterError, match="mapping"):
        ar.load_register(tmp_path)


def test_non_list_acceptances_is_rejected(tmp_path):
    _write(tmp_path, "schema: 1\nacceptances: nope\n")
    with pytest.raises(ar.RegisterError, match="must be a list"):
        ar.load_register(tmp_path)


def test_unreadable_register_fails_closed(tmp_path, monkeypatch):
    _write(tmp_path, _VALID)

    def _boom(*_a, **_kw):
        raise OSError("permission denied")

    monkeypatch.setattr(ar.Path, "read_text", _boom)
    with pytest.raises(ar.RegisterError, match="unreadable"):
        ar.load_register(tmp_path)


def test_register_path_helpers(tmp_path):
    assert ar.register_path(tmp_path).name == ar.REGISTER_NAME
    assert ar.register_exists(tmp_path) is False
    _write(tmp_path, _VALID)
    assert ar.register_exists(tmp_path) is True
