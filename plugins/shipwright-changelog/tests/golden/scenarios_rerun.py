"""S6, S7a-c, S8, S9: running Step 4 again, legacy bullets, and the dry run.

Step 4 is driven alone (``aggregate``), on a repository tagged ``v1.2.0`` with a ``CHANGELOG.md`` that already holds
that release. ``references/rerunning-a-release.md`` is the contract the oracle checks: a converging re-run is a
success that writes nothing, ``--release-date`` decides the heading's date, and a refusal changes nothing at all.
"""

from __future__ import annotations

from typing import Any

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .scenario_core import Run, Scenario

HISTORY = "# Changelog\n\n## [1.2.0] - 2026-01-15\n\n### Added\n\n- Earlier feature\n"
ORIGINAL_DATE = "2026-01-15"
VERSION = "1.3.0"
LITERALS = ((ORIGINAL_DATE, "original_date"),)


def _base(make_project, history: str = HISTORY) -> Any:
    s = make_project()
    ss.write_changelog(s, history)
    ss.tag(s, "v1.2.0")
    ss.feature_branch(s, "work/next")
    ss.commit(s, "feat.txt", "f\n", "feat: a new capability")
    return s


def _drop(s: Any, bullet: str = "A new capability readers can use", run_id: str = "iterate-2026-11-01-a") -> None:
    ss.write_drop(s, "Added", bullet, run_id=run_id)


def _agg(driver: ReplayDriver, s: Any, results: list, **params: Any):
    result = driver.run_step("aggregate", s, version=VERSION, **params)
    results.append(result)
    return result


def _changelog(s: Any) -> str:
    return (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")


def _s6(make_project, layout: str) -> Run:
    s, driver, results, snaps = _base(make_project), ReplayDriver(), [], {}
    _drop(s)
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    snaps["first"] = _changelog(s)
    _drop(s)  # an interruption left the drops pending: the same bullet is there again
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    snaps["same_date"] = _changelog(s)
    _drop(s)
    _agg(driver, s, results)  # no --release-date: today
    snaps["today"] = _changelog(s)
    _drop(s)
    _agg(driver, s, results, release_date=ORIGINAL_DATE)  # the rule: pass the original date explicitly
    snaps["restored"] = _changelog(s)
    _agg(driver, s, results)  # nothing pending now: a safe no-op
    snaps["noop"] = _changelog(s)
    return Run(s, driver, results, snaps)


def _check_s6(run: Run) -> None:
    snaps, actions = run.ctx, [(r.output["section_action"], r.output["changelog_updated"]) for r in run.results]
    assert actions == [("inserted", True), ("unchanged", False), ("replaced", True), ("replaced", True), ("none", False)]
    assert all(r.exit_code == 0 for r in run.results)
    oracle.check_ac06_placement(HISTORY, snaps["first"], VERSION)
    assert snaps["same_date"] == snaps["first"]  # AC07: converges, bytes unchanged
    for name in ("first", "same_date", "today", "restored", "noop"):
        oracle.check_ac07_once(snaps[name], VERSION)  # one version appears exactly once, every time
    assert f"## [{VERSION}] - {ORIGINAL_DATE}" in snaps["first"]
    assert f"## [{VERSION}] - {ORIGINAL_DATE}" not in snaps["today"]  # a replace adopts today's date ...
    assert snaps["restored"] == snaps["first"] and snaps["noop"] == snaps["first"]  # ... unless the original is passed


def _refusal(run: Run, *words: str) -> None:
    """A refusal exits non-zero, names the disagreement, and changes NOTHING: not CHANGELOG.md, not a drop (AC08)."""
    s = run.scratch
    refused = run.step("aggregate", 1)
    assert refused.exit_code == 1 and refused.output["status"] == "failed"
    stderr = run.commands("aggregate")[-1]["stderr"].lower()
    assert all(w in stderr for w in words), stderr
    assert ss.digest(s) == run.ctx["after"], "a refused run changed something on disk"


def _s7a(make_project, layout: str) -> Run:
    s, driver, results = _base(make_project), ReplayDriver(), []
    _drop(s)
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    _drop(s, "A bullet the recorded section does not have", run_id="iterate-2026-11-02-b")  # the drops now disagree
    ctx = {"after": ss.digest(s)}
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    return Run(s, driver, results, ctx)


def _check_s7a(run: Run) -> None:
    _refusal(run, VERSION, "not what the pending entries say")  # AC08: stops, names the version AND the kind of conflict
    assert (run.scratch.repo / "CHANGELOG-unreleased.d" / "Added" / "iterate-2026-11-02-b_001.md").is_file()  # the pending drop survives


def _s7b(make_project, layout: str) -> Run:
    withdrawn = HISTORY.replace("# Changelog\n\n", f"# Changelog\n\n## [{VERSION}] - {ORIGINAL_DATE} [YANKED]\n\n"
                                "### Added\n\n- A new capability readers can use\n\n")
    s, driver, results = _base(make_project, withdrawn), ReplayDriver(), []
    _drop(s)  # the body is exactly what the drop renders: only the marking is in the way
    ctx = {"after": ss.digest(s)}
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    return Run(s, driver, results, ctx)


def _check_s7b(run: Run) -> None:
    refused = run.step("aggregate")
    assert refused.exit_code == 1 and "yanked" in run.commands("aggregate")[-1]["stderr"].lower()  # AC08: the marking it would erase
    assert ss.digest(run.scratch) == run.ctx["after"]


def _s7c(make_project, layout: str) -> Run:
    twice = HISTORY.replace("# Changelog\n\n", f"# Changelog\n\n## [{VERSION}] - {ORIGINAL_DATE}\n\n### Added\n\n- One\n\n"
                            f"## [{VERSION}] - 2026-01-10\n\n### Added\n\n- Two\n\n")
    s, driver, results = _base(make_project, twice), ReplayDriver(), []
    _drop(s)
    ctx = {"after": ss.digest(s)}
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    return Run(s, driver, results, ctx)


def _check_s7c(run: Run) -> None:
    refused = run.step("aggregate")
    assert refused.exit_code == 1 and "2 sections" in run.commands("aggregate")[-1]["stderr"].lower()  # AC07: two claim it
    assert ss.digest(run.scratch) == run.ctx["after"] and _changelog(run.scratch).count(f"## [{VERSION}]") == 2


def _s8(make_project, layout: str) -> Run:
    legacy = HISTORY.replace("# Changelog\n\n", "# Changelog\n\n## [Unreleased]\n\n- Old bullet one\n- Old bullet two\n\n")
    s, driver, results = _base(make_project, legacy), ReplayDriver(), []
    _drop(s)
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    return Run(s, driver, results, {})


def _check_s8(run: Run) -> None:
    s, stderr = run.scratch, run.commands("aggregate")[-1]["stderr"]
    assert run.step("aggregate").output["legacy_bullets"] == 2
    assert "WARNING" in stderr and "Old bullet one" in stderr and "Old bullet two" in stderr  # AC09: each one named back
    text = _changelog(s)
    new = dict(oracle.sections(text))[VERSION]
    assert "Old bullet" not in new  # not folded in silently ...
    assert text.count("- Old bullet one") == text.count("- Old bullet two") == 1  # ... and not lost: still under [Unreleased]


def _s9(make_project, layout: str) -> Run:
    s, driver, results = _base(make_project), ReplayDriver(), []
    _drop(s)
    before = ss.digest(s)
    _agg(driver, s, results, dry_run=True, release_date=ORIGINAL_DATE)
    ctx = {"before": before, "after_dry": ss.digest(s)}
    _agg(driver, s, results, release_date=ORIGINAL_DATE)
    return Run(s, driver, results, ctx)


def _check_s9(run: Run) -> None:
    assert run.ctx["after_dry"] == run.ctx["before"]  # AC10: nothing on disk changed, no file added, none deleted
    dry, real = run.step("aggregate", 0), run.step("aggregate", 1)
    assert dry.output["changelog_updated"] is False and real.output["changelog_updated"] is True
    shown = run.commands("aggregate-dry")[0]["stdout"]
    assert '"section_written"' in shown and "A new capability readers can use" in shown  # the full result can be seen first
    assert oracle.groups(oracle.sections(_changelog(run.scratch))[0][1]) == {"Added": ["A new capability readers can use"]}


SCENARIOS = {
    "S6": Scenario("S6", ("drops",), _s6, _check_s6, LITERALS),
    "S7a": Scenario("S7a", ("drops",), _s7a, _check_s7a, LITERALS),
    "S7b": Scenario("S7b", ("drops",), _s7b, _check_s7b, LITERALS),
    "S7c": Scenario("S7c", ("drops",), _s7c, _check_s7c, LITERALS),
    "S8": Scenario("S8", ("drops",), _s8, _check_s8, LITERALS),
    "S9": Scenario("S9", ("drops",), _s9, _check_s9, LITERALS),
}
