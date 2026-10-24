"""The enforced phase gate has no production bypass but the recorded override (A5).

``--override-reason`` writes a validation record next to the completion; every other way
round the gate is a TEST seam. These pins scan the shipped code (``shared/scripts`` and every
``plugins/*/scripts``) so a seam cannot quietly become a production path.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

pytestmark = pytest.mark.covers("FR-01.01/AC02")

_REPO = Path(__file__).resolve().parents[3]
_FLAG = "ENFORCE_PHASE_GATE_DEFAULT"
_GATE_CALLS = {"apply_phase_result", "evaluate_gate"}
_DEFINITION = Path("plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py")


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _forwarded(node: ast.AST) -> bool:
    """``gate=gate``: apply handing its OWN (default-None) seam parameter on."""
    return isinstance(node, ast.Name) and node.id == "gate"


def _names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Attribute):
        return {target.attr}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_names(t) for t in target.elts))
    return set()


def _bypasses(tree: ast.AST, rel: Path) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "enforce_gate" and not _is_none(node.value):
            found.append(f"enforce_gate= at line {node.value.lineno}")
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in _GATE_CALLS and any(k.arg == "gate" and not (_is_none(k.value) or _forwarded(k.value))
                                           for k in node.keywords):
                found.append(f"{name}(gate=...) at line {node.lineno}")
            if name == "setattr" and any(isinstance(a, ast.Constant) and a.value == _FLAG
                                         for a in node.args):
                found.append(f"setattr(..., {_FLAG!r}) at line {node.lineno}")
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
        if any(_FLAG in _names(t) for t in targets):
            defining = (rel == _DEFINITION and isinstance(node, ast.Assign)
                        and isinstance(node.value, ast.Constant) and node.value.value is True)
            if not defining:
                found.append(f"assignment to {_FLAG} at line {node.lineno}")
    return found


def _shipped_files() -> list[Path]:
    roots = [_REPO / "shared" / "scripts", *(_REPO / "plugins").glob("*/scripts")]
    assert roots[1:], "no plugin scripts trees found: the scan would pass vacuously"
    return [p for root in roots for p in root.rglob("*.py")]


def test_no_shipped_code_switches_the_gate_off_or_swaps_it():
    """No shipped call passes ``enforce_gate`` or a ``gate=`` to the apply/gate entry points,
    and nothing but the definition (``= True``) assigns the default."""
    offenders = {}
    for path in _shipped_files():
        rel = path.relative_to(_REPO)
        hits = _bypasses(ast.parse(path.read_text(encoding="utf-8")), Path(rel.as_posix()))
        if hits:
            offenders[rel.as_posix()] = hits
    assert offenders == {}


@pytest.mark.parametrize("source", [
    "apply_phase_result(root, enforce_gate=False)",
    "x.apply_phase_result(root, gate=lambda *a, **k: ([], [], True))",
    "evaluate_gate(root, task, cfg, gate=fake)",
    "phase_gate.ENFORCE_PHASE_GATE_DEFAULT = False",
    "ENFORCE_PHASE_GATE_DEFAULT: bool = False",
    "setattr(phase_gate, 'ENFORCE_PHASE_GATE_DEFAULT', False)",
])
def test_the_scan_catches_each_bypass_shape(source):
    assert _bypasses(ast.parse(source), Path("plugins/x/scripts/y.py"))


@pytest.mark.parametrize("source", [
    "apply_phase_result(root, enforce_gate=None, gate=None)",
    "other(gate=fake)",
    "evaluate_gate(root, task, cfg, gate=gate)",
])
def test_the_scan_allows_the_defaults(source):
    assert _bypasses(ast.parse(source), Path("plugins/x/scripts/y.py")) == []


def test_the_definition_itself_is_the_one_allowed_assignment():
    assert _bypasses(ast.parse(f"{_FLAG} = True"), _DEFINITION) == []
    assert _bypasses(ast.parse(f"{_FLAG} = False"), _DEFINITION)


def test_every_phase_a_driven_run_can_dispatch_has_a_validator():
    """Enforcing means checked: a pipeline phase with no validator would pass ``not_checked``."""
    from orchestrator_pkg.config_factory import PIPELINE_STEPS
    from phase_validators import _VALIDATORS
    assert set(PIPELINE_STEPS) <= set(_VALIDATORS), set(PIPELINE_STEPS) - set(_VALIDATORS)
