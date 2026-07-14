"""Drift protection: every driven phase skill resolves its invocation mode the ONE way.

The bug this pins (iterate-2026-07-14-phase-invocation-mode): all 7 orchestrator-driven
phase skills answered "am I a pipeline phase?" in prose, from the v1 fields `status` +
`current_step` — which the v2 pipeline never advances. Seven copies of a decision tree over
an unmaintained field, with no test looking at any of them. Nothing stopped it drifting,
and nothing would stop it coming back.

So this asserts BOTH directions of the registry:

  forward  — every driven phase's skill carries an invocation-mode section, and that
             section resolves the mode via `get_phase_context.py` (the canonical POSITIVE
             pattern) and contains no run-config-field predicate;
  reverse  — no skill outside the driven-phase registry carries such a section (a new
             phase plugin cannot quietly grow its own copy).

Prose-scanning is NOT behavioral coverage — `test_phase_invocation_mode_integration.py`
carries that. This test only guarantees the instructions cannot silently regress.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "plugins" / "shipwright-run" / "scripts" / "lib"))

from phase_task_lifecycle import PLUGIN_PHASE_MAP  # noqa: E402

# `security` is dispatched by no one: it was decoupled from the orchestrator
# (`sec-report-and-orchestrator-decouple`) and `phase_state_machine` never materialises a
# security phase_task. Its skill detects mode from the existence of
# shipwright_project_config.json, not from run-config state, so it is out of scope here.
NOT_ORCHESTRATOR_DRIVEN = {"security"}

DRIVEN_PHASES = {
    phase for phase in PLUGIN_PHASE_MAP.values() if phase not in NOT_ORCHESTRATOR_DRIVEN
}

# The EXACT files that must carry an invocation-mode section — not merely "each phase must
# have one somewhere".
#
# The per-phase form was evadable (Stage-3 doubt review): `build` and `test` carry the
# section in TWO files, so renaming the heading in `build/SKILL.md` and re-adding the v1
# predicate under the new name left the phase still "covered" by first-actions.md, while the
# renamed section was never scanned. Pinning the file list means a rename fails the forward
# test instead of silently disabling the gate.
REGISTERED_SECTION_FILES: dict[str, tuple[str, ...]] = {
    "project": ("skills/project/references/first-actions.md",),
    "design": ("skills/design/SKILL.md", "skills/design/references/invocation-mode.md"),
    "plan": ("skills/plan/SKILL.md", "skills/plan/references/first-actions.md"),
    "build": ("skills/build/SKILL.md", "skills/build/references/first-actions.md"),
    "test": ("skills/test/SKILL.md", "skills/test/references/first-actions.md"),
    "changelog": ("skills/changelog/SKILL.md",),
    "deploy": ("skills/deploy/SKILL.md",),
}

_PHASE_TO_PLUGIN = {phase: plugin for plugin, phase in PLUGIN_PHASE_MAP.items()}

# Narrow ON PURPOSE — used only for the REVERSE sweep ("has some other skill grown its own
# copy?"). Widening it to catch renames looked tempting but false-fires: `design` and
# `security` both have an unrelated `Detect Mode` heading (new-vs-continue design session;
# OSS-vs-Aikido backend). The rename evasion is closed by banning the v1 field names across
# the WHOLE registered file instead — see test_registered_file_never_names_a_v1_state_field.
_HEADING = re.compile(r"^(#{2,4})\s.*Detect Invocation Mode\s*$", re.MULTILINE)

# The v1 predicate, in every spelling a skill might reach for. Its absence is necessary
# but NOT sufficient — hence the positive pattern below.
_FORBIDDEN = (
    "current_step",
    "completed_steps",
    'status == "in_progress"',
)

# The canonical positive pattern: the verdict comes FROM the resolver, and `invocation_mode`
# is assigned from the returned `mode` — not merely "the helper is mentioned somewhere"
# (external code review, GPT: a skill could call the helper and still derive the mode from
# some other run-config field).
_REQUIRED = (
    "get_phase_context.py",
    "--phase-task-id",
    "invocation_mode",
    "mode",
)


def _skill_files() -> list[Path]:
    return sorted((_REPO / "plugins").glob("shipwright-*/skills/**/*.md"))


def _sections(path: Path) -> list[str]:
    """Every 'Detect Invocation Mode' section body in `path` (heading -> next same/higher
    heading)."""
    text = path.read_text(encoding="utf-8")
    out: list[str] = []
    for match in _HEADING.finditer(text):
        depth = len(match.group(1))
        rest = text[match.end():]
        nxt = re.search(rf"^#{{1,{depth}}}\s", rest, re.MULTILINE)
        out.append(rest[: nxt.start()] if nxt else rest)
    return out


def _files_with_section() -> dict[Path, list[str]]:
    return {p: secs for p in _skill_files() if (secs := _sections(p))}


def _phase_of(path: Path) -> str | None:
    """`plugins/shipwright-build/skills/...` -> `build`; None for a non-phase plugin.

    Returns None rather than raising: a non-phase plugin (e.g. shipwright-iterate) that
    grows an invocation-mode section must FAIL the reverse test with a readable message,
    not blow up the collector with a KeyError (Stage-3 doubt review).
    """
    plugin = path.relative_to(_REPO / "plugins").parts[0]
    return PLUGIN_PHASE_MAP.get(plugin)


def _registered_files() -> list[Path]:
    return [
        _REPO / "plugins" / _PHASE_TO_PLUGIN[phase] / rel
        for phase, rels in REGISTERED_SECTION_FILES.items()
        for rel in rels
    ]


def test_driven_phase_registry_matches_the_lifecycle_map():
    """If a phase plugin is added or renamed, this fails until the registry is revisited —
    so a new driven phase cannot silently ship without an invocation-mode contract."""
    assert DRIVEN_PHASES == {
        "project", "design", "plan", "build", "test", "changelog", "deploy",
    }
    assert NOT_ORCHESTRATOR_DRIVEN <= set(PLUGIN_PHASE_MAP.values())
    assert set(REGISTERED_SECTION_FILES) == DRIVEN_PHASES


@pytest.mark.parametrize(
    "path", _registered_files(), ids=lambda p: str(p.relative_to(_REPO)),
)
def test_registered_file_resolves_the_mode_via_the_shared_resolver(path: Path):
    """Forward: registry -> FILE (not merely -> phase).

    Pinning the FILE is what closes the rename evasion: the per-phase form let you retitle
    the section in `build/SKILL.md` and re-add the v1 predicate under the new name, while
    `build/references/first-actions.md` kept the phase "covered" and the renamed section was
    never scanned (Stage-3 doubt review).

    Asserted over the whole file, not a heading-delimited section, because `plan/SKILL.md`
    legitimately carries its step C as a checklist BULLET rather than a heading.
    """
    assert path.exists(), f"registered invocation-mode file is missing: {path}"
    body = path.read_text(encoding="utf-8")
    for needle in _REQUIRED:
        assert needle in body, (
            f"{path.relative_to(_REPO)} does not resolve the invocation mode via the shared "
            f"resolver (missing {needle!r}). The dispatch token is the authority: call "
            f"get_phase_context.py and assign `invocation_mode` from the returned `mode`."
        )


@pytest.mark.parametrize(
    "path", _registered_files(), ids=lambda p: str(p.relative_to(_REPO)),
)
def test_registered_file_never_names_a_v1_state_field(path: Path):
    """No skill may key its invocation mode on run-config state again. BINARY, whole-file.

    Two earlier cuts of this test were too clever and a negative control disproved both:
    a per-line negation heuristic (markdown wraps, so the disclaimer lands on another line),
    then a context-window heuristic (a section can hold BOTH the disclaimer AND a live
    predicate). Scoping to the section was ALSO evadable by renaming the heading.

    So: the v1 field names simply may not appear anywhere in a file that decides the
    invocation mode. Verified achievable — none of the 10 registered files mentions them.
    The rationale lives once, in `shared/scripts/lib/phase_invocation_mode.py`, and this gate
    has no judgement left to get wrong.
    """
    body = path.read_text(encoding="utf-8")
    for needle in _FORBIDDEN:
        assert needle not in body, (
            f"{path.relative_to(_REPO)} names {needle!r}. This file decides the invocation "
            f"mode, which is resolved ONLY from the phaseTaskId the orchestrator dispatched "
            f"(get_phase_context.py) — it must not read, or even discuss, run-config state "
            f"here. Put any rationale in shared/scripts/lib/phase_invocation_mode.py."
        )


def test_no_undriven_skill_carries_an_invocation_mode_section():
    """Reverse: file -> registry. Nothing outside the driven set may grow its own copy."""
    registered = set(_registered_files())
    strays = {
        str(p.relative_to(_REPO)): _phase_of(p)
        for p in _files_with_section()
        if p not in registered and _phase_of(p) not in NOT_ORCHESTRATOR_DRIVEN
    }
    assert not strays, (
        f"unregistered skill files carry an invocation-mode section: {strays}. Add them to "
        f"REGISTERED_SECTION_FILES (so they are gated) or remove the section."
    )
