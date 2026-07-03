"""Tests for Semgrep accepted-risk rule tailoring (opt-in, default-off).

Two suppression channels keep the CI self-scan quiet on by-design / accepted
findings WITHOUT weakening detection for anyone else. Both default OFF, so a
call with no env is the original pure transform:

  - SHIPWRIGHT_SEMGREP_EXCLUDE_RULES              exact check_id -> wholesale drop
  - SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS owner-scoped mutable-tag drop

The owner is read from the workflow FILE at the finding's line — NOT from
semgrep's ``extra.lines``, which is redacted to "requires login" when semgrep
runs unauthenticated (as CI does). The owner-scoped channel MUST keep flagging
third-party actions — that is the supply-chain guard the rule exists for.
See docs/security-ci-setup.md (§ Accepted-risk rule tailoring).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from semgrep_tailoring import (  # noqa: E402
    _accept_github_owned_action_tags,
    _action_owner_from_file,
    _is_github_owned_action_tag,
    _resolve_exclude_rule_ids,
    normalize_tailored,
)

# The real (doubled) registry check_ids from the actual weekly self-scan.
DEPENDABOT_RULE = (
    "package_managers.dependabot.dependabot-missing-cooldown"
    ".dependabot-missing-cooldown"
)
MUTABLE_TAG_RULE = (
    "yaml.github-actions.security.github-actions-mutable-action-tag"
    ".github-actions-mutable-action-tag"
)

_EXCLUDE_ENV = "SHIPWRIGHT_SEMGREP_EXCLUDE_RULES"
_ACCEPT_ENV = "SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS"


@pytest.fixture
def workflow(tmp_path):
    """A workflow with GitHub-owned (line 5, 6) and third-party (line 7) uses."""
    wf = tmp_path / "ci.yml"
    wf.write_text(
        "name: x\n"            # 1
        "jobs:\n"              # 2
        "  a:\n"               # 3
        "    steps:\n"         # 4
        "      - uses: actions/checkout@v4\n"           # 5  github-owned
        "      - uses: github/codeql-action/init@v3\n"  # 6  github-owned
        "      - uses: evilcorp/thing@v1\n",            # 7  third-party
        encoding="utf-8",
    )
    return wf


def _result(check_id, path, line, severity="WARNING"):
    # Note: extra.lines is deliberately "requires login" — the real anonymous
    # semgrep value — to prove the owner is sourced from the file, not the snippet.
    return {
        "check_id": check_id,
        "path": str(path),
        "start": {"line": line},
        "extra": {
            "message": "m",
            "severity": severity,
            "lines": "requires login",
            "metadata": {},
        },
    }


def _raw(*results):
    return {"results": list(results), "errors": []}


class TestActionOwnerFromFile:
    def test_reads_owner_from_file_line(self, workflow):
        assert _action_owner_from_file(str(workflow), 5) == "actions"
        assert _action_owner_from_file(str(workflow), 6) == "github"
        assert _action_owner_from_file(str(workflow), 7) == "evilcorp"

    def test_none_on_bad_inputs(self, workflow):
        assert _action_owner_from_file(str(workflow), 4) is None   # no uses on line
        assert _action_owner_from_file(str(workflow), 99) is None  # out of range
        assert _action_owner_from_file(str(workflow), None) is None
        assert _action_owner_from_file(None, 5) is None
        assert _action_owner_from_file(str(workflow / "nope"), 5) is None


class TestIsGithubOwnedActionTag:
    def test_github_owned_true(self, workflow):
        for line in (5, 6):
            f = {"rule": MUTABLE_TAG_RULE, "affected_file": str(workflow),
                 "affected_line": line}
            assert _is_github_owned_action_tag(f) is True

    def test_third_party_false(self, workflow):
        f = {"rule": MUTABLE_TAG_RULE, "affected_file": str(workflow),
             "affected_line": 7}
        assert _is_github_owned_action_tag(f) is False

    def test_other_rule_false(self, workflow):
        f = {"rule": "some.other.rule", "affected_file": str(workflow),
             "affected_line": 5}
        assert _is_github_owned_action_tag(f) is False

    def test_unreadable_kept(self):
        f = {"rule": MUTABLE_TAG_RULE, "affected_file": "does/not/exist.yml",
             "affected_line": 5}
        assert _is_github_owned_action_tag(f) is False  # -> KEEP (fail-safe)


class TestEnvResolution:
    def test_exclude_rules_empty_by_default(self, monkeypatch):
        monkeypatch.delenv(_EXCLUDE_ENV, raising=False)
        assert _resolve_exclude_rule_ids() == frozenset()

    def test_exclude_rules_parsed_and_validated(self, monkeypatch):
        monkeypatch.setenv(_EXCLUDE_ENV, f"{DEPENDABOT_RULE}, , bad/slash, ok.rule, .., a*b")
        got = _resolve_exclude_rule_ids()
        assert DEPENDABOT_RULE in got
        assert "ok.rule" in got
        assert "bad/slash" not in got
        assert ".." not in got
        assert "a*b" not in got

    def test_accept_gh_tags_default_off(self, monkeypatch):
        monkeypatch.delenv(_ACCEPT_ENV, raising=False)
        assert _accept_github_owned_action_tags() is False

    def test_accept_gh_tags_truthy_values(self, monkeypatch):
        for v in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv(_ACCEPT_ENV, v)
            assert _accept_github_owned_action_tags() is True, v
        for v in ("0", "false", "", "off", "nope"):
            monkeypatch.setenv(_ACCEPT_ENV, v)
            assert _accept_github_owned_action_tags() is False, v


class TestNormalizeTailored:
    def test_default_env_is_passthrough(self, workflow, monkeypatch):
        monkeypatch.delenv(_EXCLUDE_ENV, raising=False)
        monkeypatch.delenv(_ACCEPT_ENV, raising=False)
        raw = _raw(
            _result(DEPENDABOT_RULE, workflow, 1),
            _result(MUTABLE_TAG_RULE, workflow, 5),
        )
        assert len(normalize_tailored(raw)) == 2  # nothing suppressed unless opted in

    def test_wholesale_exclude_only(self, workflow, monkeypatch):
        monkeypatch.setenv(_EXCLUDE_ENV, DEPENDABOT_RULE)
        monkeypatch.delenv(_ACCEPT_ENV, raising=False)
        raw = _raw(
            _result(DEPENDABOT_RULE, workflow, 1),
            _result("keep.me", workflow, 2),
        )
        out = normalize_tailored(raw)
        assert [f["rule"] for f in out] == ["keep.me"]

    def test_partial_id_does_not_match(self, workflow, monkeypatch):
        # exact match only — the short form must NOT drop the doubled id
        monkeypatch.setenv(
            _EXCLUDE_ENV,
            "package_managers.dependabot.dependabot-missing-cooldown",
        )
        raw = _raw(_result(DEPENDABOT_RULE, workflow, 1))
        assert len(normalize_tailored(raw)) == 1

    def test_real_scan_shape_third_party_survives(self, workflow, monkeypatch):
        monkeypatch.setenv(_EXCLUDE_ENV, DEPENDABOT_RULE)
        monkeypatch.setenv(_ACCEPT_ENV, "1")
        raw = _raw(
            _result(DEPENDABOT_RULE, workflow, 1),        # wholesale -> drop
            _result(MUTABLE_TAG_RULE, workflow, 5),       # actions/*  -> drop
            _result(MUTABLE_TAG_RULE, workflow, 6),       # github/*   -> drop
            _result(MUTABLE_TAG_RULE, workflow, 7),       # evilcorp/* -> KEEP
        )
        out = normalize_tailored(raw)
        assert len(out) == 1
        assert out[0]["affected_line"] == 7
        assert out[0]["id"] == "semgrep-0001"  # renumbered contiguously

    def test_gh_accept_without_exclude_keeps_dependabot(self, workflow, monkeypatch):
        monkeypatch.delenv(_EXCLUDE_ENV, raising=False)
        monkeypatch.setenv(_ACCEPT_ENV, "1")
        raw = _raw(
            _result(DEPENDABOT_RULE, workflow, 1),   # not excluded -> KEEP
            _result(MUTABLE_TAG_RULE, workflow, 5),  # github-owned -> drop
        )
        out = normalize_tailored(raw)
        assert [f["rule"] for f in out] == [DEPENDABOT_RULE]
