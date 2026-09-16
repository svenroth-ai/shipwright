"""Scope-chain and shadowing regression tests for
`shared/scripts/lib/triage_plain_append_scope.py` -- split out of
`test_triage_plain_append_scan_edge_cases.py` once it crossed 300 lines,
mirroring the production split of the scope engine into its own module
(`triage_plain_append_scope.py`) out of `triage_plain_append_scan.py`.

Each test here pins one round (5-8) of external review's finding against
`shared/scripts/lib/triage_plain_append_scan.py::find_plain_append_callers`
-- the public entry point, exercised end-to-end rather than against the
scope engine's internals directly, so a refactor of the engine cannot
silently stop proving the fix. All fixtures are synthetic (`tmp_path`).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_plain_append_scan import find_plain_append_callers  # noqa: E402


def test_a_same_named_parameter_in_an_unrelated_function_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """Round 5 external review (openai, medium) found a real false-positive
    risk in an earlier revision's unscoped `ast.walk`: a function-local
    `import triage` (a lazy-import helper, the real
    `suite_race_triage.py::_load_triage` idiom) made `triage` count as a
    module-wide alias, so an UNRELATED function's own parameter also named
    `triage` (the real `suite_race_triage.py::_open_ids(triage, ...)`
    shape) could be mistaken for the module. Scoping alias collection to
    the binding's own scope means the lazy-import helper no longer taints
    a sibling function's unrelated parameter.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    shadowed = scripts_dir / "lazy_import_producer.py"
    shadowed.write_text(
        "def _load_triage():\n"
        "    import triage\n"
        "    return triage\n"
        "\n"
        "def _open_ids(triage, project_root, keys):\n"
        "    return triage.append_triage_item(project_root, keys)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_function_local_import_is_still_found_in_the_same_function(
    tmp_path: Path,
) -> None:
    """Round 6 external review (openai, high) found the regression round 5's
    first fix introduced: restricting name collection to MODULE scope made
    an ordinary function-local `from triage import append_triage_item` --
    and the equivalent function-local `import triage` + attribute call --
    invisible even to a call in the SAME function, a real false negative
    handing a new producer an easy undetected path. The scope-chain fix
    must still find both: a name bound in a scope is visible to a call in
    THAT scope, not just the module's.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    bare = scripts_dir / "local_import_bare_producer.py"
    bare.write_text(
        "def emit(root):\n"
        "    from triage import append_triage_item\n"
        "    return append_triage_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    attribute = scripts_dir / "local_import_attribute_producer.py"
    attribute.write_text(
        "def emit(root):\n"
        "    import triage\n"
        "    return triage.append_triage_item(root, source='x', "
        "severity='low', kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {
        "shared/scripts/local_import_bare_producer.py",
        "shared/scripts/local_import_attribute_producer.py",
    }


def test_a_parameter_shadowing_a_module_level_triage_import_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """Round 7 external review (both providers): the round 5/6 scope-chain
    fix closed the NESTING direction but not SHADOWING -- `def emit(triage):
    triage.append_triage_item(...)`, with a module-level `import triage`
    that has nothing to do with `emit`'s own parameter, was still flagged.
    Real Python treats any local binding (a parameter, here) as making that
    name fully local to the function it appears in, blocking resolution to
    an outer scope's import entirely. `resolve` must stop at the first
    scope binding the name at all, not skip over a non-matching binding to
    keep looking further out.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    shadowed = scripts_dir / "parameter_shadow_producer.py"
    shadowed.write_text(
        "import triage\n"
        "def emit(triage):\n"
        "    return triage.append_triage_item('x')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_same_scope_reassignment_of_the_imported_name_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """Round 8 external review (openai, medium): an earlier revision checked
    the imported-name binding before any other same-scope binding, so
    `from triage import append_triage_item; append_triage_item =
    other_writer; append_triage_item(...)` was still flagged even though the
    name is reassigned before the call. Without control-flow order,
    `resolve` cannot know which binding the call actually reaches -- it
    must treat a same-scope conflict as AMBIGUOUS, not a hit.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    reassigned = scripts_dir / "reassigned_producer.py"
    reassigned.write_text(
        "from triage import append_triage_item\n"
        "def other_writer(*a, **k):\n"
        "    pass\n"
        "def emit(root):\n"
        "    append_triage_item = other_writer\n"
        "    return append_triage_item(root)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_a_comprehension_target_does_not_leak_into_the_enclosing_function(
    tmp_path: Path,
) -> None:
    """Round 8 external review (GLM, medium): comprehensions are their own
    lexical scope in Python 3 -- `[triage for triage in items]` must not
    make `triage` a local name of the ENCLOSING function, or a later,
    genuinely violating `triage.append_triage_item(...)` call in that same
    function would be missed as a false negative.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    real_producer = scripts_dir / "comprehension_producer.py"
    real_producer.write_text(
        "import triage\n"
        "def emit(items, root):\n"
        "    _ = [triage for triage in items]\n"
        "    return triage.append_triage_item(root, source='x', "
        "severity='low', kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/comprehension_producer.py"}
