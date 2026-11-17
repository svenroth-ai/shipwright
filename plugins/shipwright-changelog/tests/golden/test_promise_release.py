"""Promise tests for the whole release: AC01, AC04, AC12-AC15.

Each test drives a scratch project through the per-step driver interface (``ReplayDriver`` and ``release_flow``, the
prose order of the steps) and judges the outcome through ``oracle``. Green against the unchanged skill. Where a test
leans on the stub's argv log or state for a fact only the replay can see (the open request, the absence of an old
page), ``promise_list.json`` marks that part ``oracle: trace``. The helpers and constants a test uses are in THIS file,
because the promise lock hashes them with the test.
"""

from __future__ import annotations

import json

import pytest

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .scenario_core import release_flow

SLUG = "acme-fixture/widgets"
VERSION = "1.3.0"


def _flow(s, **kwargs):
    driver = ReplayDriver()
    return driver, release_flow(driver, s, **kwargs)


def _tag_made(s, version=VERSION):
    return f"v{version}" in s.git("tag").split()


def _messages_since(s, tag):
    raw = s.git("log", f"{tag}..HEAD", "--format=%B%x00")
    return [m.strip() for m in raw.split("\x00") if m.strip()]


@pytest.mark.covers("FR-01.09/AC01")
def test_ac01_a_release_run_leaves_a_readable_note_a_version_tag_and_an_open_request(make_project):
    s = ss.ready_release(make_project)
    _, results = _flow(s)
    assert all(r.exit_code == 0 for r in results), [(r.step, r.exit_code) for r in results]
    open_requests = [p for p in s.gh_state()["prs"] if p["state"] == "open"]  # the stub's state: the replay is the oracle here
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), bool(open_requests), outcome="prepared")
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", f"v{VERSION}"), VERSION)


CASES = [
    (None, [("app.txt", "feat: first feature")], "0.1.0"),
    ("v1.2.0", [("a.txt", "feat: a new capability"), ("b.txt", "fix: a defect")], "1.3.0"),
    ("v1.2.0", [("a.txt", "fix: a defect")], "1.2.1"),
    ("v1.2.0", [("a.txt", "feat(api)!: drop the v1 endpoints")], "2.0.0"),
    ("v0.3.0", [("a.txt", "feat!: rename the public option")], "0.4.0"),
]


@pytest.mark.parametrize(("tag", "commits", "want"), CASES)
@pytest.mark.covers("FR-01.09/AC04")
def test_ac04_the_proposed_version_follows_the_break_feature_fix_rule(make_project, tag, commits, want):
    s = make_project(tagged=tag is not None)
    if tag and tag != "v0.1.0":
        ss.tag(s, tag)
    ss.feature_branch(s, "work/next")
    for index, (path, message) in enumerate(commits):
        ss.commit(s, path, f"{index}\n", message)
    out = ReplayDriver().run_step("prepare", s).output
    assert out["status"] == "ok" and out["version"] == want
    oracle.check_ac04_version(out["version"], tag, _messages_since(s, tag) if tag else [])


def _manifests(s, old="1.2.0"):
    """A plain package.json and a catalog that names its version once and again per entry, both declared."""
    files = {
        "pkg/package.json": json.dumps({"name": "widgets", "version": old}, indent=2) + "\n",
        ".claude-plugin/marketplace.json": json.dumps({"name": "shop", "version": old, "plugins": [
            {"name": "one", "version": old}, {"name": "two", "version": old}]}, indent=2) + "\n",
    }
    for path, text in files.items():
        ss.commit(s, path, text, f"chore: manifest {path}")
    declared = {"published_manifests": [{"path": "pkg/package.json", "format": "package_json"},
                                        {"path": ".claude-plugin/marketplace.json", "format": "marketplace_json"}]}
    ss.commit(s, "shipwright_changelog_config.json", json.dumps(declared, indent=2) + "\n", "chore: declare manifests")
    return files


def _versions_at(s, rev):
    out = {}
    for path in ("pkg/package.json", ".claude-plugin/marketplace.json"):
        shown = s.run(["git", "show", f"{rev}:{path}"])
        out[path] = json.loads(shown.stdout).get("version") if shown.returncode == 0 else None
    return out


@pytest.mark.parametrize("left_stale", [False, True])
@pytest.mark.covers("FR-01.09/AC12")
def test_ac12_every_declared_manifest_carries_the_version_in_the_release_commit_before_the_tag(make_project, left_stale):
    s = ss.ready_release(make_project)
    files = _manifests(s)

    def put_the_old_version_back():
        (s.repo / "pkg/package.json").write_text(files["pkg/package.json"], encoding="utf-8", newline="\n")

    hooks = {"commit-and-tag": put_the_old_version_back} if left_stale else None
    _, results = _flow(s, before=hooks)
    assert (results[-1].step == "commit-and-tag" and results[-1].exit_code != 0) == left_stale
    rev = "HEAD" if left_stale else f"v{VERSION}"
    oracle.check_ac12_manifests(_versions_at(s, rev), VERSION, _tag_made(s))
    if left_stale:
        assert s.gh_state()["prs"] == []  # the person stops here: nothing was requested either


@pytest.mark.covers("FR-01.09/AC13")
def test_ac13_a_version_written_in_several_places_of_one_manifest_is_written_in_all_together(make_project):
    s = ss.ready_release(make_project)
    _manifests(s)
    synced = ReplayDriver().run_step("sync", s, version=VERSION)
    assert synced.exit_code == 0 and synced.output["status"] == "ok"
    oracle.check_ac13_nested(json.loads((s.repo / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")), VERSION)


def _page_flow(make_project, mode="ok", skip=()):
    s = ss.ready_release(make_project)
    s.env["SHIPWRIGHT_TEST_CONDENSE_FIXTURE_MODEL"] = mode
    driver, results = _flow(s, skip=skip)
    return s, driver, results


@pytest.mark.covers("FR-01.09/AC14")
def test_ac14_the_release_page_has_a_checked_summary_and_title_and_link_built_from_facts(make_project):
    s, _, results = _page_flow(make_project)
    page = [r for r in results if r.step == "release-page"][0]
    assert page.output["status"] == "ok"
    oracle.check_ac14_page(s.gh_state()["releases"], VERSION, SLUG)


@pytest.mark.covers("FR-01.09/AC14")
def test_ac14_a_summary_that_fails_the_shape_check_is_never_published(make_project):
    s, driver, results = _page_flow(make_project, "bad-shape")
    page = [r for r in results if r.step == "release-page"][0]
    assert page.output["status"] == "skipped"
    oracle.check_ac14_unchecked_not_published(s.gh_state()["releases"], VERSION, page.output["reason"])
    assert [c for c in driver.log if c["key"] == "release-page"] and not s.gh_state()["releases"]


@pytest.mark.covers("FR-01.09/AC15")
def test_ac15_a_release_page_that_cannot_be_created_does_not_undo_the_release_and_is_reported(make_project):
    s, _, results = _page_flow(make_project, skip=("push-tags",))  # the tag is not on the remote: the host refuses the page
    page = results[-1]
    assert page.step == "release-page" and page.exit_code == 0  # best effort: never a stop
    oracle.check_ac15_page_failed(s.gh_state()["releases"], VERSION, _tag_made(s), page.output["status"])
    assert s.git("log", "-1", "--format=%s", f"v{VERSION}") == f"chore(release): v{VERSION}"


@pytest.mark.covers("FR-01.09/AC15")
def test_ac15_an_earlier_version_gets_no_page_retroactively(make_project):
    s, _, results = _page_flow(make_project)
    assert all(r.exit_code == 0 for r in results)
    created = [e["argv"] for e in s.gh_argv_log() if e["argv"][:2] == ["release", "create"]]  # the stub's log: the replay is the oracle
    assert [argv[2] for argv in created] == [f"v{VERSION}"]
    oracle.check_ac15_no_backfill(s.gh_state()["releases"], created, ["v0.1.0", "v1.2.0"])
