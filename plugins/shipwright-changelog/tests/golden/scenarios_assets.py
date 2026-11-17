"""S10, S11a/b, S12a/b/c: decision numbers, declared manifests and the release page.

S10 drives Step 4 alone; S11 and S12 run the whole release on the one configuration that can finish today
(``scenario_support.ready_release``; findings D21-D23). They record, not endorse, today's behaviour.
"""

from __future__ import annotations

import json
from typing import Any

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .scenario_core import Run, Scenario, release_flow

A = "FR-01.09/"
SLUG = "acme-fixture/widgets"
LITERALS = ()


def _s10(make_project, layout: str) -> Run:
    s = ss.ready_release(make_project)
    log = s.repo / ".shipwright" / "agent_docs" / "decision_log.md"
    ctx = {"log_before": log.read_text(encoding="utf-8")}
    ss.write_decision(s, "iterate-2026-11-03-a", "First parallel decision")
    ss.write_decision(s, "iterate-2026-11-03-b", "Second parallel decision")
    ctx["drops"] = len(list((s.repo / ".shipwright" / "agent_docs" / "decision-drops").glob("*.json")))
    driver = ReplayDriver()
    results = [driver.run_step("aggregate", s, version="1.3.0", fallback_bullets=[("Fixed", "A cherry-picked fix")])]
    ctx["log_after"] = log.read_text(encoding="utf-8")
    return Run(s, driver, results, ctx)


def _check_s10(run: Run) -> None:
    s = run.scratch
    assert run.step("aggregate").exit_code == 0 and run.commands("decisions")[0]["exit"] == 0
    left = len(list((s.repo / ".shipwright" / "agent_docs" / "decision-drops").glob("*.json")))
    assert run.ctx["drops"] == 2
    oracle.check_ac05_numbered(run.ctx["log_before"], run.ctx["log_after"], run.ctx["drops"], left)  # AC05
    assert "First parallel decision" in run.ctx["log_after"] and "Second parallel decision" in run.ctx["log_after"]
    # the cherry-pick fallback: written first by append_changelog_entry.py, it lands in [Unreleased] and is named back
    assert run.commands("fallback-append")[0]["exit"] == 0
    stderr = run.commands("aggregate")[-1]["stderr"]
    text = (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")
    oracle.check_ac09_named(stderr, ["A cherry-picked fix"], text, "1.3.0")


def _manifests(s: Any, old: str = "1.2.0") -> dict[str, str]:
    """Two declared manifests: a plain package.json and a catalog that names its version once and again per entry."""
    files = {
        "pkg/package.json": json.dumps({"name": "widgets", "version": old}, indent=2) + "\n",
        ".claude-plugin/marketplace.json": json.dumps({"name": "shop", "version": old, "plugins": [
            {"name": "one", "version": old}, {"name": "two", "version": old}]}, indent=2) + "\n",
    }
    for path, text in files.items():
        ss.commit(s, path, text, f"chore: manifest {path}")
    ss.commit(s, "shipwright_changelog_config.json", json.dumps({"published_manifests": [
        {"path": "pkg/package.json", "format": "package_json"},
        {"path": ".claude-plugin/marketplace.json", "format": "marketplace_json"}]}, indent=2) + "\n", "chore: declare manifests")
    return files


def _versions_at(s: Any, rev: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for path in ("pkg/package.json", ".claude-plugin/marketplace.json"):
        shown = s.run(["git", "show", f"{rev}:{path}"])
        out[path] = json.loads(shown.stdout).get("version") if shown.returncode == 0 else None
    return out


def _s11a(make_project, layout: str) -> Run:
    s = ss.ready_release(make_project)
    _manifests(s)
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), {})


def _check_s11a(run: Run) -> None:
    s = run.scratch
    assert all(r.exit_code == 0 for r in run.results), [(r.step, r.exit_code) for r in run.results]
    assert run.step("sync").output["pathspec"] == ["pkg/package.json", ".claude-plugin/marketplace.json"]
    tagged = "v1.3.0" in s.git("tag").split()
    oracle.check_ac12_manifests(_versions_at(s, "v1.3.0"), "1.3.0", tagged)  # AC12: in the release commit, checked before the tag
    catalog = json.loads(s.git("show", "v1.3.0:.claude-plugin/marketplace.json"))
    oracle.check_ac13_nested(catalog, "1.3.0")  # AC13: the top-level field and every catalog entry together
    assert s.git("log", "-1", "--format=%s", "v1.3.0") == "chore(release): v1.3.0"


def _s11b(make_project, layout: str) -> Run:
    s = ss.ready_release(make_project)
    files = _manifests(s)

    def write_did_not_land() -> None:  # the version of one manifest is put back before the commit reads the worktree
        (s.repo / "pkg/package.json").write_text(files["pkg/package.json"], encoding="utf-8", newline="\n")

    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s, before={"commit-and-tag": write_did_not_land}), {})


def _check_s11b(run: Run) -> None:
    s = run.scratch
    done = run.step("commit-and-tag")
    assert [r.step for r in run.results][-1] == "commit-and-tag" and done.exit_code != 0  # the person stops here
    stopped = run.commands("commit-and-tag")[0]
    assert "verify_mismatch" in stopped["stdout"] + stopped["stderr"], stopped  # the KIND of refusal: the commit lacks the version
    assert s.git("log", "-1", "--format=%s") == "chore(release): v1.3.0"  # the commit exists, the marking does not
    oracle.check_ac12_manifests(_versions_at(s, "HEAD"), "1.3.0", "v1.3.0" in s.git("tag").split())  # AC12: no tag
    assert run.gh_calls("pr") == []


def _page_run(make_project, mode: str = "ok", skip: tuple[str, ...] = ()) -> Run:
    s = ss.ready_release(make_project)
    s.env["SHIPWRIGHT_TEST_CONDENSE_FIXTURE_MODEL"] = mode
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s, skip=skip), {})


def _s12a(make_project, layout: str) -> Run:
    return _page_run(make_project)


def _check_s12a(run: Run) -> None:
    s, page = run.scratch, run.step("release-page")
    assert all(r.exit_code == 0 for r in run.results) and page.output["status"] == "ok"
    oracle.check_ac14_page(s.gh_state()["releases"], "1.3.0", SLUG)  # AC14: built from the recorded facts
    creates = [c["argv"] for c in run.gh_calls("release", "create")]
    assert [c[2] for c in creates] == ["v1.3.0"]
    oracle.check_ac15_no_backfill(s.gh_state()["releases"], creates, ["v0.1.0", "v1.2.0"])  # AC15: no old version gets a page


def _s12b(make_project, layout: str) -> Run:
    return _page_run(make_project, "bad-shape")


def _check_s12b(run: Run) -> None:
    page = run.step("release-page")
    assert page.output["status"] == "skipped" and run.gh_calls("release", "create") == []  # never published unchecked
    oracle.check_ac14_unchecked_not_published(run.scratch.gh_state()["releases"], "1.3.0", page.output["reason"])


def _s12c(make_project, layout: str) -> Run:
    return _page_run(make_project, skip=("push-tags",))  # the tag is not on the remote: the host refuses the page


def _check_s12c(run: Run) -> None:
    s, page = run.scratch, run.step("release-page")
    assert [r.step for r in run.results][-1] == "release-page" and page.exit_code == 0  # best-effort: never a stop
    assert page.output["status"] == "failed", page.output
    assert "not found on the remote" in run.commands("release-page")[0]["stdout"] + run.commands("release-page")[0]["stderr"]
    oracle.check_ac15_page_failed(s.gh_state()["releases"], "1.3.0", "v1.3.0" in s.git("tag").split(), page.output["status"])
    assert s.git("log", "-1", "--format=%s", "v1.3.0") == "chore(release): v1.3.0"  # the release is not undone


SCENARIOS = {
    "S10": Scenario("S10", ("drops",), _s10, _check_s10, acs=(f"{A}AC05", f"{A}AC09")),
    "S11a": Scenario("S11a", ("legacy",), _s11a, _check_s11a, acs=(f"{A}AC12", f"{A}AC13")),
    "S11b": Scenario("S11b", ("legacy",), _s11b, _check_s11b, acs=(f"{A}AC12",)),
    "S12a": Scenario("S12a", ("legacy",), _s12a, _check_s12a, acs=(f"{A}AC14", f"{A}AC15")),
    "S12b": Scenario("S12b", ("legacy",), _s12b, _check_s12b, acs=(f"{A}AC14",)),
    "S12c": Scenario("S12c", ("legacy",), _s12c, _check_s12c, acs=(f"{A}AC15",)),
}
