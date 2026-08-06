"""AC9 — every mutating entry point funnels through a STRICT chokepoint.

Split from ``test_runconfig_corrupt_fail_closed.py`` for the 300-LOC budget, and
it stands on its own: the other suites assert what the code DOES with an unusable
config, these assert that no future edit can quietly route around the strict
reader. Both Stage-1 and Stage-2 review found real gaps here, so the pins are
kept together where the inventory they encode is visible.
"""
import ast
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import (  # noqa: E402
    cli_update_step,
    router,
    step_config_access,
    step_planning,
)
from orchestrator_pkg.config_io import RunConfigUnreadable  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402
from runconfig_corrupt_shapes import raiser, real_config, write  # noqa: E402

#: The reader no mutating path may reach.
_TOLERANT = "load_run_config"


@pytest.mark.parametrize("status", ["complete", "in_progress", "failed"])
def test_update_step_refuses_via_its_first_chokepoint(tmp_path, monkeypatch, status):
    """Make the STRICT reader refuse; every status must bail out.

    Covers ONE chokepoint three times: ``update_step`` refuses at its first
    statement, so ``_load_or_bootstrap`` is never reached. The second chokepoint
    is pinned separately below (Stage-2 review)."""
    write(tmp_path, json.dumps(real_config()))
    monkeypatch.setattr(
        step_config_access, "read_run_config",
        raiser(RunConfigUnreadable(tmp_path / CONFIG_NAME, "forced", "parse")),
    )

    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", status)


def test_load_or_bootstrap_is_pinned_independently(tmp_path, monkeypatch):
    """The SECOND chokepoint, reached directly so the first cannot mask it."""
    write(tmp_path, json.dumps(real_config()))
    monkeypatch.setattr(
        step_config_access, "read_run_config",
        raiser(RunConfigUnreadable(tmp_path / CONFIG_NAME, "forced", "parse")),
    )
    with pytest.raises(RunConfigUnreadable):
        step_planning._load_or_bootstrap(tmp_path, "plan")


def test_get_next_step_reads_through_step_planning_own_binding(tmp_path, monkeypatch):
    """``step_planning.read_run_config`` is used ONLY by ``get_next_step`` — the
    binding is inert for ``update_step``, so pin it where it actually applies."""
    write(tmp_path, json.dumps(real_config()))
    monkeypatch.setattr(
        step_planning, "read_run_config",
        raiser(RunConfigUnreadable(tmp_path / CONFIG_NAME, "forced", "parse")),
    )
    assert step_planning.get_next_step(tmp_path)["blocked"] is True


def test_no_mutating_module_imports_the_tolerant_reader():
    """AC9 as a property of the FILES, not a convention.

    Asserts on the module's AST, not ``hasattr``: a function-local import — the
    idiom ``router`` itself uses for these symbols — leaves the module attribute
    unset, so an attribute check would stay green through exactly the likeliest
    regression (Stage-3 review). An alias or an attribute call defeats it the
    same way; all three are ImportFrom / Name / Attribute nodes.

    Both guard modules are here because reverting either to the tolerant reader
    leaves every BEHAVIOURAL test green: the downstream chokepoints still raise,
    so exit codes and byte-identity still pass while the guard's own protection
    is gone. Verified by mutation (134 green, only this red)."""
    for module in (step_planning, step_config_access, cli_update_step, router):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        offenders = [
            node for node in ast.walk(tree)
            if (isinstance(node, ast.ImportFrom)
                and any(a.name == _TOLERANT for a in node.names))
            or (isinstance(node, ast.Name) and node.id == _TOLERANT)
            or (isinstance(node, ast.Attribute) and node.attr == _TOLERANT)
        ]
        assert not offenders, (
            f"{module.__name__} references the TOLERANT reader at line(s) "
            f"{[n.lineno for n in offenders]}; every read on this path can advance "
            "or change a run and must use read_run_config"
        )
