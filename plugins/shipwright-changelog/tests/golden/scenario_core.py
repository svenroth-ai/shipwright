"""What a scenario is, and the release flow of today's prose as a sequence of replay steps.

A scenario builds a scratch project, drives it with a ``ReplayDriver`` and returns a :class:`Run`; its ``check``
asserts the ACs it names through ``oracle`` (independent re-statements of FR-01.09), and ``trace`` is the
normalized result that is compared with the committed ``*.trace.json`` (the oracle of programme P7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import golden_trace as gt

from . import oracle
from .driver_replay import MAIN_BRANCHES, ReplayDriver

# What a step may say besides golden_trace.OUTPUT_WHITELIST: the facts the first half of the scenarios assert.
WHITELIST = (*gt.OUTPUT_WHITELIST, "mode", "last_tag", "branch", "commits_since_tag", "previous_tag_has_release",
             "suggested", "version_reason", "legacy_bullets", "version_question")
# Generated or model-written content: its path and existence are recorded, its text is not (a model or a clock wrote it).
JUDGEMENT = (".shipwright/compliance/*", ".shipwright/events/*", ".shipwright/events/*/*", ".shipwright/runtime/*",
             ".shipwright/agent_docs/decision_log_index.md", "shipwright_events.jsonl",
             ".shipwright/agent_docs/build_dashboard.md",
             # shared templates the scratch copies in: their text is not the release's, and a template edit must not move 20 traces
             ".gitignore", "AGENTS.md")
FILES = ("CHANGELOG.md", "CHANGELOG-unreleased.d/*/*.md")
GOLDEN_DIR = Path(__file__).resolve().parent


@dataclass
class Run:
    scratch: Any
    driver: ReplayDriver
    results: list[gt.StepResult]
    ctx: dict[str, Any] = field(default_factory=dict)
    judgement: tuple[str, ...] = ()  # more generated paths a scenario's own set-up commits (their text is not the release's)

    def step(self, name: str, occurrence: int = 0) -> gt.StepResult:
        return [r for r in self.results if r.step == name][occurrence]

    def commands(self, key: str) -> list[dict[str, Any]]:
        return [c for c in self.driver.log if c["key"] == key]

    def gh_calls(self, *prefix: str) -> list[dict[str, Any]]:
        return [e for e in self.scratch.gh_argv_log() if e["argv"][:len(prefix)] == list(prefix)]

    def trace(self, literals: dict[str, str] | None = None) -> dict[str, Any]:
        return gt.collect(self.scratch, self.results, files=FILES, judgement_globs=(*JUDGEMENT, *self.judgement), literals=literals,
                          whitelist=WHITELIST)


@dataclass(frozen=True)
class Scenario:
    id: str
    layouts: tuple[str, ...]
    run: Callable[[Callable[..., Any], str], Run]  # (make_project, layout) -> Run
    check: Callable[[Run], None]
    literals: tuple[tuple[str, str], ...] = ()
    acs: tuple[str, ...] = ()  # the FR-01.09 ACs this scenario is tagged with: ``verify`` demands the oracle judged each

    def trace_name(self, layout: str) -> str:
        return f"{self.id}.{layout}.trace.json" if len(self.layouts) > 1 else f"{self.id}.trace.json"


def release_flow(driver: ReplayDriver, scratch: Any, autonomy: str = "guided", *, release_page: bool = True,
                 pipeline: bool = False, close: bool = False, before: Mapping[str, Callable[[], None]] | None = None,
                 skip: Sequence[str] = (), **prepare: Any) -> list[gt.StepResult]:
    """Step C to Step 7 in prose order; stops where a step failed, as a person following the prose would.
    ``pipeline``: a dispatched run (no preview, no merge: first-actions.md:17-22); ``close`` adds the phase-complete
    block; ``before`` runs a set-up hook just before a named step; ``skip`` leaves named steps out."""
    results = [driver.run_step("prepare", scratch, **prepare)]
    if results[0].output["status"] != "ok":
        return results
    version = results[0].output["version"]

    def step(name: str, **params: Any) -> gt.StepResult:
        if (before or {}).get(name):
            before[name]()
        result = driver.run_step(name, scratch, **params)
        results.append(result)
        return result

    step("aggregate", version=version, dry_run=True)  # SKILL.md:164 "Use --dry-run first"
    if step("aggregate", version=version).exit_code:
        return results
    if autonomy == "guided" and not pipeline:
        step("preview")  # SKILL.md:240; autonomous and unattended skip it (:237)
    step("fold-events")
    if step("sync", version=version).output["status"] != "ok" or step("evidence", version=version).output["status"] != "ok":
        return results
    if step("commit-and-tag", version=version).exit_code:
        return results
    waits = False  # F1b: a guided release leaves its PR open, so nothing is pushed or published until the PR is merged
    if scratch.git("rev-parse", "--abbrev-ref", "HEAD") not in MAIN_BRANCHES:
        if step("open-pr", version=version).exit_code:  # F4: no PR, no release: the tag stays local
            return results
        if step("record-event", version=version).exit_code:  # F6: a rejected push stops here (SKILL.md:341, the `&&` chain)
            return results
        if autonomy != "guided" and not pipeline:
            if step("merge-pr").exit_code:  # F4: an unmerged release is not published
                return results
        else:
            waits = autonomy == "guided" and not pipeline
    elif step("record-event", version=version).exit_code:
        return results
    if "push-tags" not in skip and not waits:
        if step("push-tags").exit_code:  # F4: a refused tag push ends the release before the page
            return results
    if release_page and not waits:
        step("release-page", version=version)
    if close:
        step("close-phase", version=version)
    return results


REGEN_ENV = "SHIPWRIGHT_GOLDEN_REGEN"


def trace_text(scenario: Scenario, layout: str, make_project: Callable[..., Any]) -> tuple[Run, str]:
    run = scenario.run(make_project, layout)
    oracle.ASSERTED.clear()
    scenario.check(run)
    missing = sorted(set(scenario.acs) - oracle.ASSERTED)
    assert not missing, f"{scenario.id} is tagged with {missing} but the oracle never judged them"
    return run, gt.dumps(run.trace(dict(scenario.literals)))


def verify(scenario: Scenario, layout: str, make_project: Callable[..., Any]) -> None:
    """Run the scenario, assert its ACs through the oracle, and compare its trace with the committed one.
    ``SHIPWRIGHT_GOLDEN_REGEN=1`` writes the trace instead (an iterate regenerates, the freeze test then guards it)."""
    _, text = trace_text(scenario, layout, make_project)
    path = GOLDEN_DIR / scenario.trace_name(layout)
    if os.environ.get(REGEN_ENV) == "1":
        assert os.environ.get("CI", "").lower() not in ("true", "1"), f"{REGEN_ENV} must never be set in CI"
        path.write_bytes(text.encode("utf-8"))
        return
    assert path.is_file(), f"{path.name} is missing: run once with {REGEN_ENV}=1"
    committed = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    if committed != text:  # name the first differing lines, so a red run on another OS says what moved
        import difflib
        lines = difflib.unified_diff(committed.splitlines(), text.splitlines(), "committed", "this run", n=1, lineterm="")
        raise AssertionError(f"{path.name} differs from this run's trace:\n" + "\n".join(list(lines)[:40]))
