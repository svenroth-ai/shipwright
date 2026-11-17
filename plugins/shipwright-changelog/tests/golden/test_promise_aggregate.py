"""Promise tests for what Step 4 (the aggregation) promises: AC02, AC03, AC05-AC11 (aggregation half).

Each test states one promise of FR-01.09 in the words of its test name, drives the project through the per-step driver
interface (``ReplayDriver.run_step``) only, and judges the result through ``oracle`` - code that shares nothing with the
tools it judges. Green against the unchanged skill. The promise lock (stop 2) hashes each test together with the helpers
and constants of THIS file, so they are written here and not imported.
"""

from __future__ import annotations

import pytest

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver

HISTORY = "# Changelog\n\n## [1.2.0] - 2026-01-15\n\n### Added\n\n- Earlier feature\n"
DATE = "2026-01-15"
VERSION = "1.3.0"
NEW = "A new capability readers can use"


def _project(make_project, history=HISTORY):
    s = make_project()
    ss.write_changelog(s, history)
    ss.tag(s, "v1.2.0")
    ss.feature_branch(s, "work/next")
    ss.commit(s, "feat.txt", "f\n", "feat: a new capability")
    return s


def _aggregate(s, **params):
    driver = ReplayDriver()
    result = driver.run_step("aggregate", s, version=VERSION, release_date=DATE, **params)
    return driver, result


def _changelog(s):
    return (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")


def _stderr(driver):
    return [c for c in driver.log if c["key"] == "aggregate"][-1]["stderr"]


@pytest.mark.covers("FR-01.09/AC02")
def test_ac02_entries_are_grouped_by_the_kind_of_change_and_read_as_bullets(make_project):
    s = _project(make_project)
    ss.write_drop(s, "Added", NEW)
    ss.write_drop(s, "Fixed", "A defect no longer happens", run_id="iterate-2026-11-02-b")
    _, done = _aggregate(s)
    assert done.exit_code == 0
    first = oracle.sections(_changelog(s))[0]
    assert first[0] == VERSION
    oracle.check_ac02_grouped(first[1], {"Added": [NEW], "Fixed": ["A defect no longer happens"]})


@pytest.mark.covers("FR-01.09/AC03")
def test_ac03_nothing_since_the_last_release_says_so_and_stops(make_project):
    s = make_project()
    ss.tag(s, "v0.2.0")  # HEAD is already released
    before = ss.digest(s)
    driver = ReplayDriver()
    stopped = driver.run_step("prepare", s)
    assert stopped.output["status"] == "stop"
    oracle.check_ac03_stops(stopped.output["reason"].replace("_", " "), ["no unreleased changes"], ss.digest(s) == before,
                            set(s.git("tag").split()) != {"v0.1.0", "v0.2.0"})


@pytest.mark.covers("FR-01.09/AC03")
def test_ac03_commits_but_nothing_recorded_is_refused_and_writes_nothing(make_project):
    s = make_project()
    ss.feature_branch(s, "work/next")
    ss.commit(s, "api.txt", "1\n", "feat: something that was never recorded as a drop")
    before = ss.digest(s)
    driver = ReplayDriver()
    assert driver.run_step("prepare", s).output["status"] == "ok"
    refused = driver.run_step("aggregate", s, version="0.2.0")
    assert refused.exit_code == 1
    oracle.check_ac03_stops(_stderr(driver), ["nothing to release", "empty release"], ss.digest(s) == before,
                            s.git("tag").split() != ["v0.1.0"])


@pytest.mark.covers("FR-01.09/AC05")
def test_ac05_decision_numbers_are_given_once_at_release_in_one_continuing_run(make_project):
    s = ss.ready_release(make_project)
    log = s.repo / ".shipwright" / "agent_docs" / "decision_log.md"
    before = log.read_text(encoding="utf-8")
    ss.write_decision(s, "iterate-2026-11-03-a", "First parallel decision")
    ss.write_decision(s, "iterate-2026-11-03-b", "Second parallel decision")
    pending = len(list((s.repo / ".shipwright" / "agent_docs" / "decision-drops").glob("*.json")))
    assert pending == 2
    assert ReplayDriver().run_step("aggregate", s, version=VERSION).exit_code == 0
    left = len(list((s.repo / ".shipwright" / "agent_docs" / "decision-drops").glob("*.json")))
    oracle.check_ac05_numbered(before, log.read_text(encoding="utf-8"), pending, left)


@pytest.mark.covers("FR-01.09/AC06")
def test_ac06_the_new_section_goes_above_the_latest_release_and_older_text_stays(make_project):
    s = _project(make_project)
    ss.write_drop(s, "Added", NEW)
    assert _aggregate(s)[1].exit_code == 0
    oracle.check_ac06_placement(HISTORY, _changelog(s), VERSION)


@pytest.mark.covers("FR-01.09/AC07")
def test_ac07_writing_a_version_again_replaces_its_section_and_it_appears_once(make_project):
    s = _project(make_project)
    ss.write_drop(s, "Added", NEW)
    _aggregate(s)
    first = _changelog(s)
    ss.write_drop(s, "Added", NEW)  # an interruption left the same entry pending
    again = _aggregate(s)[1]
    assert again.exit_code == 0
    assert _changelog(s) == first  # converges: same entries, same date, same bytes
    oracle.check_ac07_once(_changelog(s), VERSION)


@pytest.mark.covers("FR-01.09/AC07")
def test_ac07_two_sections_for_one_version_stop_the_write_and_change_nothing(make_project):
    twice = HISTORY.replace("# Changelog\n\n", f"# Changelog\n\n## [{VERSION}] - {DATE}\n\n### Added\n\n- One\n\n"
                            f"## [{VERSION}] - 2026-01-10\n\n### Added\n\n- Two\n\n")
    s = _project(make_project, twice)
    ss.write_drop(s, "Added", NEW)
    before = ss.digest(s)
    driver, refused = _aggregate(s)
    assert refused.exit_code == 1
    oracle.check_ac07_refused(before, ss.digest(s), _stderr(driver), [VERSION, "2 sections"])


@pytest.mark.covers("FR-01.09/AC08")
def test_ac08_a_section_that_disagrees_with_the_pending_entries_stops_the_write_and_says_so(make_project):
    s = _project(make_project)
    ss.write_drop(s, "Added", NEW)
    _aggregate(s)
    ss.write_drop(s, "Added", "A bullet the recorded section does not have", run_id="iterate-2026-11-02-b")
    before = ss.digest(s)
    driver, refused = _aggregate(s)
    assert refused.exit_code == 1
    oracle.check_ac08_refused(before, ss.digest(s), _stderr(driver), [VERSION, "not what the pending entries say"])


@pytest.mark.covers("FR-01.09/AC08")
def test_ac08_a_withdrawn_marking_is_never_erased_and_the_refusal_names_it(make_project):
    withdrawn = HISTORY.replace("# Changelog\n\n", f"# Changelog\n\n## [{VERSION}] - {DATE} [YANKED]\n\n### Added\n\n- {NEW}\n\n")
    s = _project(make_project, withdrawn)
    ss.write_drop(s, "Added", NEW)
    before = ss.digest(s)
    driver, refused = _aggregate(s)
    assert refused.exit_code == 1
    oracle.check_ac08_refused(before, ss.digest(s), _stderr(driver), ["yanked"])


@pytest.mark.covers("FR-01.09/AC09")
def test_ac09_entries_written_the_old_way_are_named_back_not_folded_and_not_lost(make_project):
    legacy = HISTORY.replace("# Changelog\n\n", "# Changelog\n\n## [Unreleased]\n\n- Old bullet one\n- Old bullet two\n\n")
    s = _project(make_project, legacy)
    ss.write_drop(s, "Added", NEW)
    driver, done = _aggregate(s)
    assert done.exit_code == 0 and done.output["legacy_bullets"] == 2
    oracle.check_ac09_named(_stderr(driver), ["Old bullet one", "Old bullet two"], _changelog(s), VERSION)


@pytest.mark.covers("FR-01.09/AC10")
def test_ac10_a_preview_shows_the_whole_result_and_changes_nothing_on_disk(make_project):
    s = _project(make_project)
    ss.write_drop(s, "Added", NEW)
    before = ss.digest(s)
    driver, shown = _aggregate(s, dry_run=True)
    assert shown.exit_code == 0 and shown.output["changelog_updated"] is False
    preview = [c for c in driver.log if c["key"] == "aggregate-dry"][0]["stdout"]
    oracle.check_ac10_unchanged(before, ss.digest(s), preview, [NEW])


@pytest.mark.covers("FR-01.09/AC11")
def test_ac11_preparing_the_release_text_publishes_nothing_aggregation_half(make_project):
    """Only the aggregation half of AC11: the whole promise is red in guided and driven runs today (finding D2)."""
    s = _project(make_project)
    ss.write_drop(s, "Added", NEW)
    tags_before = s.git("--git-dir", s.origin.as_posix(), "tag").split()
    assert _aggregate(s)[1].exit_code == 0
    remote_tags = s.git("--git-dir", s.origin.as_posix(), "tag").split()
    assert remote_tags == tags_before and f"v{VERSION}" not in remote_tags  # no new marking left the machine
    state = s.gh_state()
    assert state["prs"] == [] and not state["releases"]
    oracle.check_ac11_not_published(state, tag_on_remote=f"v{VERSION}" in remote_tags, pr_open=False)
