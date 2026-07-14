"""INTEGRATION (residue half): the multi-session removal is COMPLETE — and not overdone.

Failure-mode **(A)** of `iterate-2026-07-14-remove-multi-session`: *not enough was
removed*. A dangling import of a deleted module, or a `hooks.json` still registering a
hook whose script is gone — which makes Claude Code skip that plugin's hooks **entirely**,
silently disabling the rest of its chain. Neither is a type error; nothing else catches it.

Plus the blunt guard against failure-mode **(B)** — *too much was removed*: the
load-bearing modules that merely SOUNDED multi-session must still be on disk. The
behavioural half of (B) — that they still compose into a working pipeline — is
`test_single_session_sole_mode.py`.

Together these two files are the `cross_component` integration coverage for this iterate
(the flag is recomputed from the diff by the F11 verifier: 8 × `hooks.json`,
`**/hooks/*.py`, pipeline phase validators). They replace
`integration-tests/test_phase_hook_main_lifecycle.py`, which WAS that coverage and which
tested the very hooks this iterate deletes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The engine deleted by this iterate.
DELETED_MODULES = [
    "shared/scripts/hooks/phase_session_start.py",
    "shared/scripts/hooks/phase_session_stop.py",
    "shared/scripts/hooks/phase_user_prompt_validate.py",
    "shared/scripts/hooks/phase_context_blocks.py",
    "shared/scripts/lib/hook_session.py",
    "shared/scripts/lib/phase_event_emit.py",
]

# Everything the surviving pipeline still depends on. Each one was genuinely at risk of
# being cut as "multi-session residue":
#   * phase_task_lifecycle — its docstring SAID "multi-session pipeline", and every
#     mutator in it was called BY the deleted Stop hook. It is in fact SHARED, and is the
#     single-session loop's only path to mutating a phase task.
#   * phase_state_machine — same docstring problem; it plans every successor phase.
#   * gate_policy — owned the `multi_session` sentinel that kept gates inert.
#   * record_event / generate_handoff_on_stop — had multi-session callers, but the
#     components themselves are generic.
SURVIVING_MODULES = [
    "plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py",
    "plugins/shipwright-run/scripts/lib/phase_state_machine.py",
    "plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_loop.py",
    "plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_recovery.py",
    "shared/scripts/lib/gate_policy.py",
    "shared/scripts/tools/record_event.py",
    "shared/scripts/hooks/generate_handoff_on_stop.py",
]

# Live source only. Historical artifacts (.shipwright/runs/**), the CHANGELOG and
# decision log (provenance), and docs/ (which document the removal BY NAME, on purpose)
# are out of scope.
LIVE_SOURCE_ROOTS = ("plugins", "shared")

# The 8 pipeline phases. Each one is dispatched to a phase-runner subagent, so each one
# must recover its prior-phase context from the `phaseTaskId` the orchestrator hands it.
PHASE_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan", "shipwright-build",
    "shipwright-test", "shipwright-security", "shipwright-changelog", "shipwright-deploy",
]


def _live_files(suffixes: tuple[str, ...]):
    """Live, shipped source only.

    ``tests/`` is excluded on purpose: a test that asserts the ABSENCE of a launch card
    has to name the literal in its own assertion, and would otherwise flag itself.
    """
    for root in LIVE_SOURCE_ROOTS:
        for path in (REPO_ROOT / root).rglob("*"):
            if path.suffix not in suffixes or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            yield path


# --------------------------------------------------------------------------- #
# (A) Nothing left behind
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", DELETED_MODULES)
def test_deleted_module_is_gone(rel):
    assert not (REPO_ROOT / rel).exists(), f"{rel} was supposed to be deleted"


def test_no_live_source_imports_a_deleted_module():
    """An *import* of a deleted module is a hard load failure at hook/CLI startup.

    A comment or docstring that NAMES one is fine — the surviving code explains what it
    removed, and that prose is deliberate.
    """
    names = [Path(m).stem for m in DELETED_MODULES]
    offenders: list[str] = []
    for path in _live_files((".py",)):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for name in names:
                if name in stripped:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {stripped[:90]}")
    assert not offenders, (
        "live source still imports a deleted module:\n  " + "\n  ".join(offenders)
    )


def test_no_hooks_json_registers_a_deleted_hook():
    """Claude Code skips a plugin's hooks ENTIRELY when one fails to load, so a single
    stale registration silently disables that plugin's whole chain. This is the guard
    that makes a hook deletion safe: forget one manifest and it fails loudly."""
    deleted = {Path(m).name for m in DELETED_MODULES}
    offenders: list[str] = []
    for manifest in REPO_ROOT.glob("plugins/*/hooks/hooks.json"):
        raw = manifest.read_text(encoding="utf-8")
        for name in deleted:
            if name in raw:
                offenders.append(f"{manifest.relative_to(REPO_ROOT)} -> {name}")
    assert not offenders, (
        "hooks.json still registers a deleted script:\n  " + "\n  ".join(offenders)
    )


def test_no_live_source_emits_a_phase_launch_card():
    """The per-phase Continue is gone. A `claude --session-id` command emitted by live
    code or a shipped skill would send the user to an engine that no longer exists —
    they would paste it, a phase task would get claimed, and nothing could complete it."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _live_files((".py", ".md", ".json"))
        if "claude --session-id" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        "live source still renders a `claude --session-id` phase launch card:\n  "
        + "\n  ".join(offenders)
    )


def test_no_shipped_skill_gates_on_the_deleted_context_block():
    """The `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` block had exactly ONE producer: the
    deleted `phase_session_start` hook, which injected it into an external phase session.

    A phase skill that still says "if that block is in your context, you are in a pipeline
    — otherwise standalone" now has a trigger that can NEVER fire: the phase runner is a
    SUBAGENT, and no hook can inject anything into a subagent. It would silently take the
    standalone branch on every driven phase, and would directly CONTRADICT the phase-runner
    brief, which hands it a `phaseTaskId` and tells it to fetch its own context.

    All three reviewers (internal, GPT, Codex) flagged this independently. The skills now
    key on "the orchestrator handed you a phaseTaskId"; this guard keeps it that way.

    Matched CASE-INSENSITIVELY against a FAMILY of spellings, not one exact token.

    This guard has already failed once, exactly here. Its first cut matched the long
    `SHIPWRIGHT-PIPELINE-CONTEXT` and sailed straight past 8 skills whose *negative* branch
    still read "If NO `PIPELINE-CONTEXT` block is present, this is a standalone invocation"
    — the retarget had fixed only the positive branch, so a driven phase would STILL have
    dropped into standalone mode, and the guard was green the whole time (Codex, delta
    review). Then the same reviewer pointed out that matching one exact uppercase token
    would still miss a re-worded variant.

    A guard that matches a narrower string than the bug is worse than no guard: it
    certifies precisely what it cannot see. So match the class, not the instance.
    """
    dead_triggers = (
        "pipeline-context",
        "pipeline_context",
        "pipeline context block",
        "context block is present",
        "context block, you are",
    )
    offenders: list[str] = []
    for p in _live_files((".md",)):
        blob = p.read_text(encoding="utf-8", errors="ignore").lower()
        hits = [t for t in dead_triggers if t in blob]
        if hits:
            offenders.append(f"{p.relative_to(REPO_ROOT)} -> {hits}")
    assert not offenders, (
        "a shipped skill/prompt still gates Step-0 on the deleted context block — its "
        "producer is gone, so the branch can never fire. Check BOTH branches: the "
        "'you are in a pipeline' one AND the 'otherwise standalone' one:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_every_phase_skill_still_recovers_its_context_via_phase_task_id(plugin):
    """The POSITIVE half of the guard above (external review, GPT).

    Banning the dead trigger is not enough: a future edit could delete the Step-0 block
    outright and the negative assertion would still pass — while a phase-runner-dispatched
    skill silently stopped loading its prior-phase artifacts, which is the exact regression
    the retarget exists to prevent. So assert the REPLACEMENT survives, for every phase
    plugin: a `phaseTaskId`-keyed trigger AND the `get_phase_context.py` call.

    Both directions of drift are now covered — the repo's registry-driven SSoT rule.
    """
    skill_dir = REPO_ROOT / "plugins" / plugin / "skills"
    docs = list(skill_dir.rglob("*.md"))
    assert docs, f"{plugin}: no skill docs found"

    blob = "\n".join(d.read_text(encoding="utf-8", errors="ignore") for d in docs)
    assert "phaseTaskId" in blob, (
        f"{plugin}: no Step-0 block keys on the `phaseTaskId` the orchestrator hands the "
        f"phase-runner — a dispatched phase would silently take the standalone branch"
    )
    assert "get_phase_context.py" in blob, (
        f"{plugin}: Step-0 no longer calls get_phase_context.py, so a dispatched phase "
        f"would never load its prior-phase artifacts"
    )


def test_no_live_source_offers_multi_session_as_a_selectable_mode():
    """The literal survives as a *tombstone* (so a stale config fails closed with a
    migration message), but it must never be presented as something to choose."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _live_files((".md",))
        if "multi_session (deprecated)" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        "a shipped skill/prompt still offers multi_session as an option:\n  "
        + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# (B) Nothing load-bearing taken with it
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", SURVIVING_MODULES)
def test_load_bearing_module_survived(rel):
    assert (REPO_ROOT / rel).exists(), (
        f"{rel} is load-bearing for the surviving single-session pipeline and must not "
        f"have been deleted, however 'multi-session' its name or docstring once sounded"
    )


def test_phase_task_lifecycle_still_exposes_every_mutator_the_loop_needs():
    """The deleted Stop hook and the surviving loop call the SAME mutators. Deleting the
    hook must not have pruned any of them as 'now unused'."""
    src = (REPO_ROOT / "plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py").read_text(
        encoding="utf-8",
    )
    for fn in (
        "def claim_phase_task",
        "def complete_phase_task",
        "def mark_phase_failed",
        "def recover_phase_task",
        "def freeze_splits",
        "def plan_next_phase",
        "def validate_prerequisites",
        "def get_phase_task",
    ):
        assert fn in src, f"phase_task_lifecycle lost {fn!r} — the loop still calls it"
