"""A minimal VALID project, one phase at a time: what each phase skill leaves on disk.

The driven apply path (``single-session-apply``) runs the real phase gate: the phase
validators plus their canon checks. A test that drives a run therefore has to play the
phase-runner honestly and leave on disk what a well-behaved phase would — not a stub
``artifacts/<phase>.md``. ``write_phase`` does exactly that, phase by phase, so a test
calls it between ``single-session-next`` and ``single-session-apply`` and passes the
returned artifact list in the result contract.

Shared by two pytest roots (``integration-tests`` and ``plugins/shipwright-run/tests``),
so it imports nothing from either side: only the standard library, and the one template
the AGENTS.md check compares against, read by path. Both roots put THIS directory on
``sys.path`` and import ``minimal_valid_project``; the directory holds no ``lib``,
``scripts`` or ``tools`` package, so the import cannot shadow another root's package
(ADR-044: one test root per pytest process, and no shared package names across roots).

What each phase writes (the minimum its validator and canon checks accept):

    project    project config (complete, splits), one spec per split, the interview
               transcript and a complete grill trace, CLAUDE.md + AGENTS.md (Codex
               appendix), architecture/conventions/decision log
    design     one screen linking every FR, the design manifest, the design config
               (only when the test did not write one: a test that wants a split-less
               run writes ``{"splits": []}`` itself)
    plan       plan config, ``plan.md`` with a SECTION_MANIFEST, one well-formed section
               and the build config for the split (archiving the previous split's)
    build      the split's sections complete with a test, one work_completed per section
    test       ``shipwright_test_results.json`` (unit passed, smoke passed, e2e skipped
               with a reason)
    changelog  ``CHANGELOG.md`` with a released version, committed and tagged in git
    deploy     nothing of its own (the canon below is all its checks need)

And for every phase the canon a skill finishes with: a ``phase_history`` entry under a
run id the phase minted itself (as the real skills do; the gate resolves it, see
``orchestrator_pkg/gate_run_id.py``), an ADR naming the phase, a dashboard line. Canon C1's
evidence is that entry's terminal ``outcome: completed`` (a fallback C1 accepts), NOT a
``phase_completed`` event. That is a fixture choice over a real production property:
``record_event`` dedups ``phase_completed`` by ``(phase, splitId)`` within a session, so
when a real skill records its own end event first, the loop's end event for the same pair
(the one carrying ``phaseTaskId``) is dropped — a known event loss in driven runs, pinned by
``test_phase_gate_real_skill_canon.py``. The fixture skips the skill event so the tests that
pin the loop's tracked ``phase_started``/``phase_completed`` pair measure the loop. C1's event
lookup is not scoped per run or split either: any earlier ``phase_completed`` for the phase
satisfies it.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_SPLITS = ("01-core", "02-ui")
SECTION = "01-login"

_SPEC = (
    "## 2. Functional Requirements\n\n"
    "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
    "|---|---|---|---|---|---|---|\n"
    "| {fr} | Core | Login | Must | Users can sign in. | interview | unit |\n\n"
    "### {fr} — Login\n\n#### Acceptance Criteria\n"
    "- (E) Given a registered user, when they submit valid credentials, then they are signed in.\n"
)

_SECTION_BODY = (
    "# Section: {name}\n\nRequirements: {fr}\n\n"
    "## Overview\nSign users in.\n\n## Prerequisites\nNone.\n\n"
    "## Implementation Steps\n1. add the form\n2. call the auth API\n\n"
    "## Tests First\n- a unit test for the login handler\n"
)

_CLAUDE_MD = "# Demo app\n\nA minimal project used by the Shipwright phase-gate tests.\n"
_APPENDIX = Path(__file__).resolve().parents[1] / "templates" / "codex-agents-md-appendix.md"


def write_phase(
    project_root: Path, phase: str, split_id: Optional[str] = None, *,
    splits: Sequence[str] = DEFAULT_SPLITS, canon: bool = True,
) -> list[str]:
    """Write what ``phase`` (for ``split_id``) leaves on disk; return its artifact paths.

    ``splits`` is used by the project phase only (the splits it decomposes into); later
    phases read them back from the configs on disk, as the real skills do. ``canon=False``
    skips what a skill's FINALIZATION block writes (dashboard line, ``phase_history``), so a
    test can run that block's real commands instead (``test_phase_gate_real_skill_canon.py``);
    the ADR, written earlier in a real skill, stays. ``deploy`` has no artifacts of its own;
    any other unknown phase is a ``ValueError``.
    """
    if phase not in _PHASES and phase != "deploy":
        raise ValueError(f"no minimal artifacts for phase {phase!r}")
    root = Path(project_root)
    writer = _PHASES.get(phase)
    artifacts = writer(root, split_id, list(splits)) if writer else []
    _finish_phase(root, phase, split_id, canon=canon)
    return artifacts or ["shipwright_run_config.json"]


def trace(requirement_key: str = "login", *, outcome: str = "answered") -> dict[str, Any]:
    """A grill trace with every dimension answered (``outcome`` lets a test break one)."""
    dims = {d: "answered" for d in ("purpose", "boundaries", "failure", "out_of_scope")}
    return {
        "requirement_key": requirement_key,
        "requirement_text": "The system SHALL sign users in.",
        "surface": "project", "evidence": ["turn 3: login is required"],
        "dimensions": {**dims, "outcome": outcome, "glossary": "n/a:no new term introduced",
                       "rationale": "n/a:not hard to reverse"},
        "fit_criterion": "a valid email/password pair signs the user in",
        "glossary_delta": [], "confirmed_by": "user confirmed in turn 5", "terms_used": [],
    }


def write_trace(project_root: Path, *, outcome: str = "answered") -> Path:
    """(Re)write the project's one grill trace; returns its path."""
    path = Path(project_root) / ".shipwright" / "planning" / "grill-traces" / "login.json"
    _write(path, json.dumps(trace(outcome=outcome), indent=2))
    return path


# --- per-phase writers -------------------------------------------------------------------

def _fr(index: int) -> str:
    return f"FR-{index:02d}.01"


def _project(root: Path, _split: Optional[str], splits: list[str]) -> list[str]:
    scope = _read_json(root / "shipwright_run_config.json").get("scope") or "full_app"
    _write_json(root / "shipwright_project_config.json",
                {"status": "complete", "scope": scope,
                 "splits": [{"name": s} for s in splits]})
    for i, split in enumerate(splits, 1):
        _write(root / ".shipwright" / "planning" / split / "spec.md", _SPEC.format(fr=_fr(i)))
    _write(root / ".shipwright" / "planning" / "shipwright_project_interview.md",
           "# Interview\n\nturn 3: login is required\n")
    write_trace(root)
    _write(root / "CLAUDE.md", _CLAUDE_MD)
    _write(root / "AGENTS.md", _CLAUDE_MD + "\n" + _APPENDIX.read_text(encoding="utf-8"))
    for doc in ("architecture", "conventions"):
        _write(root / ".shipwright" / "agent_docs" / f"{doc}.md", f"# {doc.title()}\n\nMinimal.\n")
    return ["shipwright_project_config.json", ".shipwright/planning/shipwright_project_interview.md"]


def _project_splits(root: Path) -> list[str]:
    raw = _read_json(root / "shipwright_project_config.json").get("splits") or []
    return [s.get("name") if isinstance(s, dict) else s for s in raw]


def _design(root: Path, _split: Optional[str], _splits: list[str]) -> list[str]:
    splits = _project_splits(root)
    frs = ", ".join(_fr(i) for i in range(1, len(splits) + 1))
    designs = root / ".shipwright" / "designs"
    _write(designs / "screens" / "01-login.html",
           f"<!-- Requirements: {frs} -->\n<html><body><h1>Login</h1></body></html>\n")
    _write(designs / "design-manifest.md",
           "# Design Manifest\n\n## Screens\n\n| # | File | Linked FRs |\n|---|---|---|\n"
           f"| 1 | screens/01-login.html | {frs} |\n")
    if not (root / "shipwright_design_config.json").exists():
        _write_json(root / "shipwright_design_config.json", {"splits": splits})
    return [".shipwright/designs/design-manifest.md", ".shipwright/designs/screens/01-login.html"]


def _plan(root: Path, split_id: Optional[str], _splits: list[str]) -> list[str]:
    splits = _project_splits(root)
    split = split_id or splits[0]
    if split not in splits:   # never borrow another split's FR: that would fail confusingly
        raise ValueError(f"plan for split {split!r}, but the project defines {splits}")
    fr = _fr(splits.index(split) + 1)
    planning = root / ".shipwright" / "planning" / split
    _write_json(root / "shipwright_plan_config.json", {"status": "complete"})
    _write(planning / "plan.md",
           f"# Plan {split}\n\n<!-- SECTION_MANIFEST\n{SECTION}\nEND_MANIFEST -->\n\nCovers {fr}.\n")
    _write(planning / "sections" / f"{SECTION}.md", _SECTION_BODY.format(name=SECTION, fr=fr))
    build = _read_json(root / "shipwright_build_config.json")
    prior = build.get("current_split")
    if prior and prior != split and build.get("sections"):
        build[f"split_{prior.split('-', 1)[0]}_sections"] = build["sections"]
    build.update(current_split=split,
                 sections=[{"name": SECTION, "status": "pending", "tests_total": 0}])
    _write_json(root / "shipwright_build_config.json", build)
    return [f".shipwright/planning/{split}/plan.md",
            f".shipwright/planning/{split}/sections/{SECTION}.md"]


def _build(root: Path, _split: Optional[str], _splits: list[str]) -> list[str]:
    build = _read_json(root / "shipwright_build_config.json")
    for section in build.get("sections", []):
        section.update(status="complete", tests_total=1, tests_passed=1)
        _append_event(root, {"type": "work_completed", "source": "build",
                             "section": section["name"]})
    _write_json(root / "shipwright_build_config.json", build)
    return ["shipwright_build_config.json"]


def _test(root: Path, _split: Optional[str], _splits: list[str]) -> list[str]:
    _write_json(root / "shipwright_test_results.json", {
        "mode": "pipeline", "unit": {"total": 1, "passed": 1, "failed": 0},
        "smoke": {"status": "pass"},
        "e2e": {"skipped": True, "reason": "the fixture app has no browser surface"},
    })
    return ["shipwright_test_results.json"]


def _changelog(root: Path, _split: Optional[str], _splits: list[str]) -> list[str]:
    today = datetime.now(timezone.utc).date().isoformat()   # the tag below is cut today too
    _write(root / "CHANGELOG.md", f"# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - {today}\n\n"
           "### Added\n- 01-login: users can sign in\n")
    if not (root / ".git").exists():
        _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", "release 0.1.0")
    _git(root, "tag", "-f", "v0.1.0")
    return ["CHANGELOG.md"]


_PHASES = {"project": _project, "design": _design, "plan": _plan, "build": _build,
           "test": _test, "changelog": _changelog}


# --- the canon every phase finishes with ---------------------------------------------------

def _finish_phase(root: Path, phase: str, split_id: Optional[str], *, canon: bool) -> None:
    where = f" for {split_id}" if split_id else ""
    section = f"**Section:** {SECTION}\n\n" if phase == "build" else ""
    log = root / ".shipwright" / "agent_docs" / "decision_log.md"
    text = log.read_text(encoding="utf-8") if log.exists() else "# Decision Log\n"
    number = text.count("\n### ADR-") + 1
    _write(log, text + f"\n### ADR-{number:03d}: {phase} decisions{where}\n\n{section}"
           "**Status:** Accepted\n")
    if not canon:   # the rest is what a skill's finalization block writes
        return
    dashboard = root / ".shipwright" / "agent_docs" / "build_dashboard.md"
    text = dashboard.read_text(encoding="utf-8") if dashboard.exists() else "# Dashboard\n\n"
    _write(dashboard, text + f"- {phase}{where}: done\n")
    # The run id a SKILL mints for itself (``design-20261025-101500``), never the run's
    # ``runId``: the gate must accept the id the phase recorded during its task.
    now = datetime.now(timezone.utc)
    run_id = f"{phase}-{now.strftime('%Y%m%d-%H%M%S%f')}" + (f"-{split_id}" if split_id else "")
    entry: dict[str, Any] = {"run_id": run_id, "at": now.isoformat(), "outcome": "completed"}
    if split_id:
        entry["split"] = split_id
    if phase == "build":
        entry["sections"] = [{"id": SECTION}]
    config_path = root / "shipwright_run_config.json"
    config = _read_json(config_path)
    config.setdefault("phase_history", {}).setdefault(phase, []).append(entry)
    _write_json(config_path, config)


# --- io ------------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_event(root: Path, event: dict[str, Any]) -> None:
    with (root / "shipwright_events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**event, "ts": _now()}) + "\n")


def _git(root: Path, *args: str) -> None:
    # A clean git environment: a GIT_DIR inherited from a hook or CI step must not
    # point these commands at another repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=str(root), env=env, check=True, capture_output=True, timeout=60,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _write(path, json.dumps(data, indent=2))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
