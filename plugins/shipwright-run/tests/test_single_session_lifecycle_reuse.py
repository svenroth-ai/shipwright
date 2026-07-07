"""Lifecycle-reuse CONTRACT test (SS1 AC4): the single-session scaffold reuses
``phase_task_lifecycle`` and adds NO parallel completion path — no direct
run_config mutation.

Campaign 2026-07-07-single-session-pipeline / SS1.

Three guarantees:
  1. FORWARD reuse — every entrypoint the SS3 orchestrator is allowed to call
     resolves to a real callable in ``phase_task_lifecycle``.
  2. NO parallel completion path (structural, code-only via ``ast``) — no module
     in the ``single_session`` package CALLS a phase-task mutator or a
     run_config writer. The lifecycle entrypoints appear only as STRING data in
     the registry, never as executed code.
  3. NO direct run_config mutation (behavioral) — every loop-state operation
     leaves an existing ``shipwright_run_config.json`` byte-identical and
     creates none when absent.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
import single_session  # noqa: E402
from orchestrator import create_config  # noqa: E402
from single_session import LIFECYCLE_COMPLETION_ENTRYPOINTS  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    advance_pointer,
    init_loop_state,
    record_dispatch,
    save_loop_state,
    set_status,
)

_PKG_DIR = Path(single_session.__file__).resolve().parent

# Phase-task mutators + run_config writers the SS1 scaffold must never CALL
# itself (SS3's orchestrator does, via the lifecycle). Checked as code
# identifiers only — string data in the registry does not count.
_FORBIDDEN_CODE_IDENTIFIERS = frozenset({
    "save_run_config",
    "create_config",
    "atomic_write_json",   # the run_config_store JSON writer
    "_write_config",
    "claim_phase_task",
    "complete_phase_task",
    "mark_phase_failed",
    "recover_phase_task",
    "freeze_splits",
    "plan_next_phase",
    "phase_task_lifecycle",  # the scaffold names entrypoints as strings, not imports
})


# ---- 1. forward reuse ----


def test_every_completion_entrypoint_resolves_in_lifecycle():
    assert LIFECYCLE_COMPLETION_ENTRYPOINTS, "registry must not be empty"
    for name in LIFECYCLE_COMPLETION_ENTRYPOINTS:
        fn = getattr(phase_task_lifecycle, name, None)
        assert callable(fn), f"{name!r} is not a callable in phase_task_lifecycle"


def test_completion_entrypoints_are_the_expected_mutators():
    # Reverse guard: exactly the terminal-transition + planning entrypoints,
    # nothing bespoke sneaked in.
    assert set(LIFECYCLE_COMPLETION_ENTRYPOINTS) == {
        "complete_phase_task",
        "mark_phase_failed",
        "recover_phase_task",
        "plan_next_phase",
    }


# ---- 2. no parallel completion path (code-only ast scan) ----


def _code_identifiers(source: str) -> set[str]:
    """Identifiers REFERENCED IN CODE (never string/doc/comment literals)."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_single_session_package_never_calls_a_mutator_or_run_config_writer():
    py_files = sorted(_PKG_DIR.glob("*.py"))
    assert py_files, "single_session package has no modules?"
    for py in py_files:
        idents = _code_identifiers(py.read_text(encoding="utf-8"))
        offenders = idents & _FORBIDDEN_CODE_IDENTIFIERS
        assert not offenders, (
            f"{py.name} references forbidden code identifier(s) {sorted(offenders)} — "
            f"the SS1 scaffold must reuse phase_task_lifecycle, not add a parallel "
            f"completion path or mutate run_config"
        )


def test_registry_names_are_present_as_string_data_not_code():
    """Sanity: the entrypoint names DO appear in the package (as string data),
    proving the ast scan above passes because they're data, not because they're
    absent entirely."""
    init_src = (_PKG_DIR / "__init__.py").read_text(encoding="utf-8")
    for name in LIFECYCLE_COMPLETION_ENTRYPOINTS:
        assert f'"{name}"' in init_src, f"{name} should be declared as string data"


# ---- 3. no direct run_config mutation (behavioral) ----


def test_loop_state_ops_leave_existing_run_config_byte_identical(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    rc_path = tmp_project / "shipwright_run_config.json"
    before = rc_path.read_bytes()

    st = init_loop_state("run-a1b2c3d4", current_phase_task_id="ptk-seed01")
    save_loop_state(tmp_project, st)
    st = record_dispatch(st)
    save_loop_state(tmp_project, st)
    st = advance_pointer(st, completed_phase_task_id="ptk-seed01", next_phase_task_id="ptk-next02")
    save_loop_state(tmp_project, st)
    st = set_status(st, "complete")
    save_loop_state(tmp_project, st)

    assert rc_path.read_bytes() == before, "loop-state ops must not mutate run_config"


def test_loop_state_save_does_not_create_run_config(tmp_project):
    save_loop_state(tmp_project, init_loop_state("run-a1b2c3d4"))
    assert not (tmp_project / "shipwright_run_config.json").exists(), (
        "loop-state persistence must never create a run_config"
    )
    assert (tmp_project / ".shipwright" / "run_loop_state.json").exists()
