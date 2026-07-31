"""What each refreshed document says about the state it describes.

Subject: ``shared/scripts/tools/compliance_provenance.py`` — the fixed-point
stamp and the ci-security scan provenance
(iterate-2026-07-31-derived-docs-at-release, AC-6 / AC-9 / AC-9b). Split from
``test_compliance_refresh_produce.py`` so neither file carries two subjects: that
one owns the loop and its refusals, this one owns what the delivered bytes CLAIM.
"""

from __future__ import annotations

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

import json  # noqa: E402

from _compliance_refresh_fixtures import (  # noqa: E402
    BASE, DASHBOARD, RUN, all_ok, head_sha, seed_repo,
)
from lib.churn_merge import CI_SECURITY_SUMMARY, COMPLIANCE_MDS  # noqa: E402
from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from source_state import parse_banner_line  # noqa: E402
from tools import compliance_provenance as prov_mod  # noqa: E402
from tools import compliance_refresh_produce as produce_mod  # noqa: E402


@pytest.fixture
def compliance_refresh_repo(tmp_path: Path) -> Path:
    """:func:`seed_repo` as a fixture — see that module for why it is declared
    here rather than shared."""
    return seed_repo(tmp_path / "repo")


def test_the_stamp_names_the_base_and_the_release_in_every_markdown_document(compliance_refresh_repo):
    payload = produce_mod.capture(compliance_refresh_repo)
    stamped, moved = prov_mod.stamp_fixed_point(payload, BASE, "v0.5.2")
    assert sorted(moved) == sorted(COMPLIANCE_MDS)
    for rel in sorted(COMPLIANCE_MDS):
        state = parse_banner_line(stamped[rel].decode("utf-8"))
        assert state.base == BASE[:12]
        assert state.release == "v0.5.2"
        assert state.run_id == RUN, "the existing run id survives the rewrite"


def test_the_json_members_are_left_untouched(compliance_refresh_repo):
    payload = produce_mod.capture(compliance_refresh_repo)
    stamped, moved = prov_mod.stamp_fixed_point(payload, BASE, "v0.5.2")
    for rel in sorted(REFRESH_SET - set(COMPLIANCE_MDS)):
        assert stamped[rel] == payload[rel]
        assert rel not in moved


def test_a_document_with_no_banner_is_left_alone_rather_than_guessed_at(compliance_refresh_repo):
    payload = {DASHBOARD: b"# dashboard\n\nno banner here\n"}
    stamped, moved = prov_mod.stamp_fixed_point(payload, BASE, "v0.5.2")
    assert stamped == payload
    assert moved == []


def test_an_on_demand_refresh_stamps_a_base_but_no_release(compliance_refresh_repo):
    """AC-9b. A documents-only branch shipped with no release and must not claim
    one."""
    stamped, _ = prov_mod.stamp_fixed_point(produce_mod.capture(compliance_refresh_repo), BASE, None)
    state = parse_banner_line(stamped[DASHBOARD].decode("utf-8"))
    assert state.base == BASE[:12]
    assert state.release is None


def test_stamping_still_leaves_exactly_one_banner_line(compliance_refresh_repo):
    stamped, _ = prov_mod.stamp_fixed_point(produce_mod.capture(compliance_refresh_repo), BASE, "v1")
    assert stamped[DASHBOARD].decode("utf-8").count("Source-State:") == 1


def test_a_release_value_cannot_forge_a_second_banner_line_through_re_sub(
    compliance_refresh_repo,
):
    """Stage-2 code review, medium.

    `re.sub` treats a STRING replacement as a template and expands backslash
    escapes in it, and `safe_run_id` permits backslashes. So a release value
    carrying `\x0a` rendered as one physical line, and the substitution then
    expanded it into a real newline — forging a second `Source-State:` line in the
    shipped document, from OUTSIDE the guarantee `banner_line` makes.
    """
    forged = "v1\x0aSource-State:\x20run=forged\x20base=1234567890ab"
    stamped, moved = prov_mod.stamp_fixed_point(
        produce_mod.capture(compliance_refresh_repo), BASE, forged)
    assert moved, "the fixture must actually stamp something"
    for rel in moved:
        text = stamped[rel].decode("utf-8")
        assert text.count("Source-State:") == 1, f"{rel} carries a forged banner"


def test_an_unknown_escape_in_a_release_value_does_not_raise(compliance_refresh_repo):
    r"""The accidental variant of the same defect: an unknown escape (`\d`, a
    Windows path fragment) raised `re.error` from inside the producer."""
    stamped, moved = prov_mod.stamp_fixed_point(
        produce_mod.capture(compliance_refresh_repo), BASE, r"v1\dev\build")
    assert moved
    for rel in moved:
        assert stamped[rel].decode("utf-8").count("Source-State:") == 1


# --- AC-6: the one document that does not derive from the tree ---------------


def test_ci_security_reports_its_class_and_the_scan_it_came_from(compliance_refresh_repo):
    (compliance_refresh_repo / CI_SECURITY_SUMMARY).write_text(
        json.dumps({"source": "security.yml#42",
                    "scan_date": "2099-01-01T00:00:00+00:00"}), encoding="utf-8")
    report = prov_mod.ci_security_report(compliance_refresh_repo, "HEAD")
    assert report["classification"] == "derives_from_ci_history"
    assert report["source"] == "security.yml#42"
    assert report["stale"] is False


def test_a_scan_older_than_the_base_commit_is_reported_stale(compliance_refresh_repo):
    (compliance_refresh_repo / CI_SECURITY_SUMMARY).write_text(
        json.dumps({"source": "security.yml#7",
                    "scan_date": "1999-01-01T00:00:00+00:00"}), encoding="utf-8")
    report = prov_mod.ci_security_report(compliance_refresh_repo, "HEAD")
    assert report["stale"] is True
    assert "predates" in report["note"]


def test_an_unreadable_ci_security_reports_unknown_not_fresh(compliance_refresh_repo):
    (compliance_refresh_repo / CI_SECURITY_SUMMARY).write_text("{not json",
                                                               encoding="utf-8")
    report = prov_mod.ci_security_report(compliance_refresh_repo, "HEAD")
    assert report["stale"] is None, "unknown must not collapse into False"
    assert "the committed copy stands" in report["note"]


def test_an_unresolvable_base_reports_freshness_as_unknown_not_fresh(
    compliance_refresh_repo,
):
    """A comparison that did not happen must not answer 'no'. ``BASE`` names no
    commit in this repo, so there is no date to compare against."""
    report = prov_mod.ci_security_report(compliance_refresh_repo, BASE)
    assert report["stale"] is None
    assert "not comparable" in report["note"]


def test_ci_security_never_fails_the_run(compliance_refresh_repo, monkeypatch):
    """AC-6. A release is not held for a scan that has not landed."""
    (compliance_refresh_repo / CI_SECURITY_SUMMARY).write_text(
        json.dumps({"source": "security.yml#1", "rows": ["x"] * 40,
                    "scan_date": "1999-01-01T00:00:00+00:00"}), encoding="utf-8")
    monkeypatch.setattr(produce_mod, "converge", lambda *a, **k: (True, 2, all_ok()))
    result, payload = produce_mod.produce(
        compliance_refresh_repo, RUN, head_sha(compliance_refresh_repo), None)
    assert result["status"] == "ok"
    assert result["ci_security"]["stale"] is True
    assert payload



