"""Match keys and provenance — the half that decides what may be touched.

Every test here is a negative control for a way this could quietly do the wrong
thing. The two that matter most:

* an entry that has not declared its breadth matches NOTHING (loose matching
  would dismiss unrelated judgments — measured: 8 different judgments share the
  rule id ``py/unused-global-variable`` on this repo, and an open alert shared
  it too);
* an alert with no provenance marker is a human's dismissal and is never
  reopened (all 50 dismissals on this repo today are unmarked).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import alert_match as am  # noqa: E402
from accepted_risks import Acceptance  # noqa: E402


def entry(**over) -> Acceptance:
    base = dict(
        id="ar-test", target="github-dismissal", rule="py/unused-global-variable",
        expires=date(2027, 1, 1), rationale_ref="ADR-271",
        statement="a sufficiently long justification for the acceptance",
        scope={"tool": "CodeQL", "paths": ["a/b.py"]},
    )
    base.update(over)
    return Acceptance(**base)


def api_alert(**over) -> dict:
    payload = {
        "number": 7, "state": "open",
        "tool": {"name": "CodeQL"}, "rule": {"id": "py/unused-global-variable"},
        "most_recent_instance": {"location": {"path": "a/b.py"}},
    }
    payload.update(over)
    return payload


class TestAlertFromApi:
    def test_valid_payload_reduces_to_the_match_key(self):
        alert = am.alert_from_api(api_alert())
        assert alert.key == ("CodeQL", "py/unused-global-variable", "a/b.py")
        assert alert.number == 7 and alert.state == "open"

    @pytest.mark.parametrize("mutation", [
        {"tool": {}}, {"rule": {}}, {"most_recent_instance": {}},
        {"most_recent_instance": {"location": {}}}, {"number": "7"}, {"number": None},
    ])
    def test_any_missing_key_component_yields_none_not_a_partial(self, mutation):
        """An alert we cannot key is one we must not act on — a half-built key
        would match by accident."""
        assert am.alert_from_api(api_alert(**mutation)) is None

    @pytest.mark.parametrize("junk", [None, [], "alert", 42])
    def test_non_mapping_payload_is_rejected(self, junk):
        assert am.alert_from_api(junk) is None

    def test_line_number_is_not_part_of_the_key(self):
        """Lines drift on every edit above the finding; including one would
        manufacture permanent false drift."""
        moved = api_alert(most_recent_instance={
            "location": {"path": "a/b.py", "start_line": 999}
        })
        assert am.alert_from_api(moved).key == am.alert_from_api(api_alert()).key


class TestProvenance:
    def test_marker_round_trips(self):
        assert am.marker_in(f"why {am.marker_for('ar-x')}") == "ar-x"

    @pytest.mark.parametrize("comment", [
        "", None, 42, "a hand-written human rationale with no marker",
        "[shipwright-accepted-risk:]", "[shipwright-accepted-risk: ]",
    ])
    def test_unmarked_comment_reads_as_human(self, comment):
        """Absence of a marker is the signal. If this ever returned a value for
        a human comment, reopen would rewrite a person's judgment."""
        assert am.marker_in(comment) is None

    def test_dismissal_comment_carries_statement_ref_and_marker(self):
        text = am.dismissal_comment(entry())
        assert "sufficiently long justification" in text
        assert "ADR-271" in text and "2027-01-01" in text
        assert am.marker_in(text) == "ar-test"

    def test_long_statement_is_truncated_but_marker_survives(self):
        """Truncation must never eat the marker — an unmarked machine dismissal
        is indistinguishable from a human one and becomes irreversible."""
        text = am.dismissal_comment(entry(statement="x" * 4000))
        assert len(text) <= 280
        assert am.marker_in(text) == "ar-test"


class TestScopeProblem:
    def test_explicit_paths_are_accepted(self):
        assert am.scope_problem(entry()) is None

    def test_explicit_rule_wide_is_accepted(self):
        assert am.scope_problem(
            entry(scope={"tool": "Scorecard", "match": "rule-wide"})
        ) is None

    def test_undeclared_breadth_is_refused(self):
        """The central rule: breadth is declared, never inferred. There is no
        implicit 'it only matched one, so take it' — that silently widens the
        day a second alert appears."""
        problem = am.scope_problem(entry(scope={"tool": "CodeQL"}))
        assert problem and "declare breadth explicitly" in problem

    @pytest.mark.parametrize("scope,fragment", [
        ({}, "scope.tool is required"),
        ({"tool": ""}, "scope.tool is required"),
        ({"tool": "CodeQL", "paths": ["a"], "match": "rule-wide"}, "mutually exclusive"),
        ({"tool": "CodeQL", "paths": []}, "non-empty list"),
        ({"tool": "CodeQL", "paths": "a/b.py"}, "non-empty list"),
        ({"tool": "CodeQL", "paths": ["a", ""]}, "non-empty strings"),
        ({"tool": "CodeQL", "paths": ["a"], "dismissed_reason": "nah"}, "not one of"),
    ])
    def test_malformed_scopes_are_refused_with_a_reason(self, scope, fragment):
        problem = am.scope_problem(entry(scope=scope))
        assert problem and fragment in problem

    def test_default_dismiss_reason_is_a_valid_github_value(self):
        assert am.DEFAULT_DISMISS_REASON in am.DISMISS_REASONS
        assert am.dismiss_reason_for(entry()) == am.DEFAULT_DISMISS_REASON

    def test_explicit_dismiss_reason_is_carried(self):
        e = entry(scope={"tool": "CodeQL", "paths": ["a"],
                         "dismissed_reason": "false positive"})
        assert am.dismiss_reason_for(e) == "false positive"


class TestEntryMatches:
    def test_matches_on_tool_rule_and_listed_path(self):
        assert am.entry_matches(entry(), "CodeQL", "py/unused-global-variable", "a/b.py")

    @pytest.mark.parametrize("tool,rule,path", [
        ("Scorecard", "py/unused-global-variable", "a/b.py"),   # wrong tool
        ("CodeQL", "py/other-rule", "a/b.py"),                  # wrong rule
        ("CodeQL", "py/unused-global-variable", "other/z.py"),  # unlisted path
    ])
    def test_does_not_match_outside_its_declared_scope(self, tool, rule, path):
        assert not am.entry_matches(entry(), tool, rule, path)

    def test_same_rule_different_path_is_a_different_judgment(self):
        """The measured hazard: 8 unrelated judgments share one rule id, and an
        open alert shared it too. Path is what keeps them apart."""
        e = entry(scope={"tool": "CodeQL", "paths": ["shared/scripts/a.py"]})
        assert not am.entry_matches(
            e, "CodeQL", "py/unused-global-variable", "plugins/other/b.py"
        )

    def test_rule_wide_matches_every_path_for_that_tool_and_rule(self):
        e = entry(scope={"tool": "CodeQL", "match": "rule-wide"})
        assert am.entry_matches(e, "CodeQL", "py/unused-global-variable", "anything.py")
        assert not am.entry_matches(e, "Scorecard", "py/unused-global-variable", "x.py")

    def test_ambiguous_entry_matches_nothing_even_if_caller_forgets_to_check(self):
        """Defence in depth: the refusal is enforced at the match site too, so a
        caller that skips scope_problem still cannot dismiss anything."""
        e = entry(scope={"tool": "CodeQL"})
        assert not am.entry_matches(e, "CodeQL", "py/unused-global-variable", "a/b.py")


class TestTriageItemKey:
    def test_parses_tool_rule_and_file_dropping_the_line(self):
        assert am.triage_item_key("semgrep:py.lang.foo:src/a.py:42") == (
            "semgrep", "py.lang.foo", "src/a.py"
        )

    def test_check_id_containing_colons_is_parsed_from_both_ends(self):
        assert am.triage_item_key("semgrep:rules:sub:id:src/a.py:9") == (
            "semgrep", "rules:sub:id", "src/a.py"
        )

    @pytest.mark.parametrize("junk", [
        None, 42, "", "semgrep", "semgrep:rule", "semgrep:rule:file",
        ":rule:file:1", "semgrep::file:1", "semgrep:rule::1",
    ])
    def test_unparseable_keys_match_nothing(self, junk):
        """Fail closed: a key we cannot parse must not be dismissed by accident."""
        assert am.triage_item_key(junk) is None
