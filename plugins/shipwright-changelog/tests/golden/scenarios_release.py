"""S1, S1t and S2g/S2a/S2u: a release from the first command to the release page.

Every scenario runs on a feature branch the remote already knows (an iterate branch pushed earlier), so the
prose's ``gh pr create`` before ``git push origin HEAD`` (finding D7) is not what these scenarios are about; the
fresh-branch order is S14a (the next unit). What they record about today's behaviour, not endorse:

* D2: the tag and the release page go out while the PR is still open (guided mode, and a driven run);
* D15: the PR body carries a literal ``\\n``;
* D22: a TRACKED bullet drop is deleted by the aggregation but not committed by Step 6's pathspec, so the
  release audit refuses the dirty tree and no tag is made (S1t);
* D23: Step 5.5 records an event and Step 6's pathspec does not name it: under the ``drops`` layout (the shipped
  default) it is an untracked file, under the ``legacy`` layout a tracked events file is modified; the same audit
  refusal ends the release at Step 6 (no tag, no PR). The one configuration that runs to the release page is the
  legacy layout with NO events file yet (a fresh repo: the event is not recorded at all), so S1 and S2 start there
  and both layouts are recorded as they are.
"""

from __future__ import annotations

import json
import sys

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .replay_commands import PLUGIN
from .scenario_core import Run, Scenario, release_flow

HISTORY = "# Changelog\n\n## [1.2.0] - 2026-01-15\n\n### Added\n\n- Earlier feature\n"


def _s1(make_project, layout: str) -> Run:
    s = make_project(events_layout=layout, tagged=False)
    ss.remove_events_file(s)  # D3: Step 7 creates the events file, untracked
    ss.feature_branch(s, "release/first")
    ss.commit(s, "app.txt", "one\n", "feat: first feature")
    ss.commit(s, "fix.txt", "two\n", "fix: first fix")
    ss.write_drop(s, "Added", "First feature of the product")
    ss.write_drop(s, "Fixed", "A first fix", run_id="iterate-2026-11-02-b")
    driver = ReplayDriver()
    ctx = {"commit_count": int(s.git("rev-list", "--count", "HEAD")), "layout": layout}
    return Run(s, driver, release_flow(driver, s), ctx)


def check_d23_refusal(run: Run) -> None:
    """D23: the release stops at Step 6 under the drops layout; nothing was tagged, opened or pushed."""
    s = run.scratch
    assert [r.step for r in run.results][-1] == "commit-and-tag" and run.step("commit-and-tag").exit_code != 0
    assert "release audit refuses a dirty working tree" in run.commands("commit-and-tag")[0]["stderr"]
    assert f"v{run.step('prepare').output['version']}" not in s.git("tag").split() and s.gh_state()["prs"] == []
    assert run.gh_calls("pr") == [] and run.gh_calls("release", "create") == []  # only setup's advisory `release view` ran
    assert any(line.startswith("?? .shipwright/events/") for line in s.git("status", "--porcelain").splitlines())
    note = oracle.sections((s.repo / "CHANGELOG.md").read_text(encoding="utf-8"))[0][1]
    oracle.check_ac01(note, tag_made=False, request_open=False, outcome="stopped")  # AC01: no marking, no request
    # D23, the writer: Step 5.5's compliance run records a `grade_snapshot` event (not a phase event) and leaves it untracked
    status = s.git("status", "--porcelain", "-uall")
    fresh = [p for p in (s.repo / ".shipwright" / "events" / "drops").glob("*.jsonl") if f"?? .shipwright/events/drops/{p.name}" in status]
    assert fresh and all('"type":"grade_snapshot"' in p.read_text(encoding="utf-8") for p in fresh), fresh


def _check_s1(run: Run) -> None:
    s, out = run.scratch, run.step("prepare").output
    assert (out["last_tag"], out["version"], out["version_reason"]) == (None, "0.1.0", "first release")  # AC04: no release yet
    oracle.check_ac04_version(out["version"], None, [])  # AC04, judged by the rule written out again in the oracle
    changelog = (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")
    section = oracle.sections(changelog)[0][1]
    oracle.check_ac02_grouped(section, {"Added": ["First feature of the product"], "Fixed": ["A first fix"]})
    oracle.check_drops_consumed([p.name for p in (s.repo / "CHANGELOG-unreleased.d").rglob("*.md")])  # Step 4: folded entries are gone
    if run.ctx["layout"] == "drops":
        return check_d23_refusal(run)
    assert all(r.exit_code == 0 for r in run.results), [(r.step, r.exit_code) for r in run.results]
    # AC01: a readable release note, a version marking and an open request - all three
    assert s.git("cat-file", "-t", "v0.1.0") == "tag"  # an annotated tag ...
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v0.1.0"), "0.1.0")  # ... on the release commit itself
    prs = s.gh_state()["prs"]
    assert [(p["head"], p["base"], p["title"], p["state"]) for p in prs] == [("release/first", "main", "Release v0.1.0", "open")]
    oracle.check_ac01(section, tag_made=True, request_open=prs[0]["state"] == "open", outcome="prepared")
    # D15: the body is the section behind a literal backslash-n pair, not a line break
    assert prs[0]["body"].startswith("## Changelog\\n\\n## [0.1.0]")
    # D3 (regression guard): the events file is committed, the tree ends clean
    # the audit may file an advisory compliance finding (.shipwright/triage.jsonl, untracked) on one OS and not another (S2 pins
    # it); D3 is about the events file, so everything else must be committed
    dirty = [line for line in s.git("status", "--porcelain").splitlines() if line != "?? .shipwright/triage.jsonl"]
    assert dirty == [], dirty
    event = s.git("log", "-1", "--format=%s", "--name-only", "HEAD")
    assert event.splitlines()[0] == "chore(release): record changelog event for v0.1.0"
    assert any(p.startswith(("shipwright_events.jsonl", ".shipwright/events/drops/")) for p in event.splitlines()[1:])
    # D4: with no tag the prose passes an empty --since and lists every commit; a model that writes `null` gets nothing
    listed = json.loads(run.commands("parse-commits")[0]["stdout"] or "[]")
    assert len(listed) == run.ctx["commit_count"]
    null = s.run([sys.executable, str(PLUGIN / "scripts" / "lib" / "git_utils.py"), "parse-commits", "--since", "null",
                  "--format", "json"])
    assert json.loads(null.stdout or "[]") == []
    # D2 (recorded, not endorsed): the tag is on the remote while the PR is open
    assert "refs/tags/v0.1.0" in s.git("ls-remote", "--tags", s.origin.as_posix())
    assert run.step("release-page").output["status"] == "ok"


def _s1t(make_project, layout: str) -> Run:
    s = make_project(events_layout=layout, tagged=False)
    ss.remove_events_file(s)  # so that the tracked drop is the only thing that dirties the tree
    ss.feature_branch(s, "release/first")
    ss.commit(s, "app.txt", "one\n", "feat: first feature")
    ss.write_drop(s, "Added", "First feature of the product", tracked=True)
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), {})


def _check_s1t(run: Run) -> None:
    s = run.scratch
    done = run.step("commit-and-tag")
    assert done.exit_code != 0 and done.output["status"] == "failed"
    assert "release audit refuses a dirty working tree" in run.commands("commit-and-tag")[0]["stderr"]
    assert s.git("tag") == "" and s.git("log", "-1", "--format=%s", "release/first").startswith("chore(release): v0.1.0")
    dirty = s.run(["git", "status", "--porcelain"]).stdout.splitlines()
    assert dirty == [" D CHANGELOG-unreleased.d/Added/iterate-2026-11-01-a_001.md"], dirty  # the deletion is not in the commit
    assert [r.step for r in run.results][-1] == "commit-and-tag" and run.gh_calls("pr") == []  # the person stops here
    oracle.check_ac01(oracle.sections((s.repo / "CHANGELOG.md").read_text(encoding="utf-8"))[0][1], tag_made=False,
                      request_open=False, outcome="stopped")  # AC01: the note exists, nothing marks or requests it


def _s1d(make_project, layout: str) -> Run:
    s = make_project(events_layout=layout, tagged=False)
    ss.remove_events_file(s)
    ss.feature_branch(s, "release/first")
    s.git("rm", "-q", "--", *ss.KEEP)  # a project with no tracked file in decision-drops/ or planning/adr/ (finding D21)
    s.git("commit", "-q", "-m", "chore: no tracked decision directories")
    ss.commit(s, "app.txt", "one\n", "feat: first feature")
    ss.write_drop(s, "Added", "First feature of the product")
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), {})


def _check_s1d(run: Run) -> None:
    s = run.scratch
    done = run.step("commit-and-tag")
    assert [r.step for r in run.results][-1] == "commit-and-tag" and done.exit_code != 0
    assert "did not match any files" in run.commands("commit-and-tag")[0]["stderr"]  # the whole commit aborts (SKILL.md:300 warns of it)
    assert s.git("tag") == "" and s.git("log", "-1", "--format=%s") == "feat: first feature" and run.gh_calls("pr") == []
    oracle.check_ac01(oracle.sections((s.repo / "CHANGELOG.md").read_text(encoding="utf-8"))[0][1], False, False, outcome="stopped")


def _s2(autonomy: str):
    def run(make_project, layout: str) -> Run:
        s = make_project(events_layout=layout)
        ss.remove_events_file(s)  # D23: the one configuration that can finish today's Step 6
        ss.set_autonomy(s, autonomy)
        ss.write_changelog(s, HISTORY)
        ss.tag(s, "v1.2.0")
        ss.feature_branch(s, "release/next")
        ss.commit(s, "feat.txt", "f\n", "feat: new capability")
        ss.commit(s, "fix.txt", "x\n", "fix: a defect")
        ss.write_drop(s, "Added", "A new capability readers can use")
        ss.write_drop(s, "Fixed", "A defect no longer happens", run_id="iterate-2026-11-02-b")
        ctx = {"before": HISTORY, "messages": ["feat: new capability", "fix: a defect"], "layout": layout}
        driver = ReplayDriver()
        return Run(s, driver, release_flow(driver, s, autonomy), ctx)
    return run


def _check_s2(autonomy: str):
    def check(run: Run) -> None:
        s = run.scratch
        out = run.step("prepare").output
        oracle.check_ac04_version(out["version"], out["last_tag"], run.ctx["messages"])  # AC04: a new capability, 1.x
        assert out["version"] == "1.3.0"
        # truth table, standalone x autonomy x {version, preview, pr-merge}: the replay's steps and outputs are the cells
        assert out["version_question"] == ("asked" if autonomy == "guided" else "auto-accepted")  # SKILL.md:142-150
        assert out["version"] == out["suggested"]  # every autonomy keeps the suggestion
        after = (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")
        oracle.check_ac06_placement(run.ctx["before"], after, "1.3.0")  # AC06 (a section above the 1.2.0 one, title intact)
        oracle.check_ac02_grouped(oracle.sections(after)[0][1], {"Added": ["A new capability readers can use"],
                                                                 "Fixed": ["A defect no longer happens"]})
        if run.ctx["layout"] == "drops":
            return check_d23_refusal(run)
        assert all(r.exit_code == 0 for r in run.results)
        names = [r.step for r in run.results]
        assert names.count("preview") == (1 if autonomy == "guided" else 0)
        merged = [p["state"] for p in s.gh_state()["prs"]]
        assert merged == (["open"] if autonomy == "guided" else ["merged"])
        assert (len(run.gh_calls("pr", "merge")) == 1) == (autonomy != "guided")
        assert s.git("rev-parse", "--abbrev-ref", "HEAD") == ("release/next" if autonomy == "guided" else "main")
        if autonomy != "guided":  # the tag is on origin's main once the PR is merged
            main = s.run(["git", "--git-dir", s.origin.as_posix(), "merge-base", "--is-ancestor", "v1.3.0", "main"])
            assert main.returncode == 0
    return check


SCENARIOS = {
    "S1": Scenario("S1", ("legacy", "drops"), _s1, _check_s1, acs=("FR-01.09/AC01", "FR-01.09/AC04")),
    "S1d": Scenario("S1d", ("legacy",), _s1d, _check_s1d, acs=("FR-01.09/AC01",)),
    "S1t": Scenario("S1t", ("legacy",), _s1t, _check_s1t, acs=("FR-01.09/AC01",)),
    "S2g": Scenario("S2g", ("legacy", "drops"), _s2("guided"), _check_s2("guided"),
                     acs=("FR-01.09/AC02", "FR-01.09/AC04", "FR-01.09/AC06")),
    "S2a": Scenario("S2a", ("legacy", "drops"), _s2("autonomous"), _check_s2("autonomous"),
                     acs=("FR-01.09/AC02", "FR-01.09/AC04", "FR-01.09/AC06")),
    "S2u": Scenario("S2u", ("legacy", "drops"), _s2("unattended"), _check_s2("unattended"),
                     acs=("FR-01.09/AC02", "FR-01.09/AC04", "FR-01.09/AC06")),
}
