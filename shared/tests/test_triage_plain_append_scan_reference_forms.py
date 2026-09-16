"""Stored/returned bare-reference detection for
`shared/scripts/lib/triage_plain_append_scan.py` -- split out of
`test_triage_plain_append_scan_edge_cases.py` to keep that file under the
repo's 300-line guideline, the same reason it and its sibling
`test_triage_plain_append_scope.py` were split out of the original
`test_triage_plain_append_scan.py`.

Round 11 (external code review, req3-06 e5, medium): an earlier revision's
`_calls_plain_append` only inspected `ast.Call` nodes, so a producer that
reaches the plain, non-deduplicating `append_triage_item` via a stored or
returned bare reference instead of a direct call evaded the scan entirely --
a real bypass, not one of the module's named accepted gaps. The module
docstring's justification ("no producer in this repo's history has ever
reached the function this way") was also factually wrong: three live
compliance-plugin files already use exactly this idiom for the SAFE sibling
`append_triage_item_idempotent`
(`plugins/shipwright-compliance/scripts/audit/triage_bundle.py`,
`.../lib/sbom_generator.py`, `.../lib/test_evidence.py`). These tests pin
the fix: every scope-resolved LOAD is now checked, not only one used as
`Call.func` -- and prove the fix stays scoped to the PLAIN function's own
name, never the safe sibling. All fixtures are synthetic (`tmp_path`).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_plain_append_scan import find_plain_append_callers  # noqa: E402


def test_a_stored_reference_to_the_plain_function_is_found(tmp_path: Path) -> None:
    """`fn = triage.append_triage_item; fn(root)` must be caught -- the
    bare attribute on the right-hand side of the assignment is a LOAD, the
    same node shape a direct call's `Call.func` already was.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    stored = scripts_dir / "stored_reference_producer.py"
    stored.write_text(
        "import triage\n"
        "def emit(root):\n"
        "    fn = triage.append_triage_item\n"
        "    return fn(root, source='x', severity='low', kind='bug', "
        "title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/stored_reference_producer.py"}


def test_a_returned_reference_to_the_plain_function_is_found(tmp_path: Path) -> None:
    """Sibling to the stored-reference test above -- the exact bypass
    shape this repo's own compliance plugins use for the SAFE sibling
    function (`triage_bundle.py` returns `triage.append_triage_item_idempotent`
    as a bare attribute in a tuple, not a call). A producer returning the
    PLAIN function the same way must be caught.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    returned = scripts_dir / "returned_reference_producer.py"
    returned.write_text(
        "import triage\n"
        "def _triage_api():\n"
        "    return (triage.append_triage_item, triage.read_all_items)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/returned_reference_producer.py"}


def test_a_stored_reference_to_the_idempotent_sibling_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """The stored/returned-reference fix above must stay scoped to the
    PLAIN function's own name -- the real, live house idiom in this repo
    (`triage_bundle.py`, `sbom_generator.py`, `test_evidence.py`) stores
    and returns `triage.append_triage_item_idempotent`, the SAFE sibling,
    and must never be flagged.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    safe = scripts_dir / "idempotent_reference_producer.py"
    safe.write_text(
        "import triage\n"
        "def _triage_api():\n"
        "    return (triage.append_triage_item_idempotent, "
        "triage.read_all_items)\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()
