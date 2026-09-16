"""Core call-shape detection tests for
`shared/scripts/lib/triage_plain_append_scan.py` -- plain calls, attribute
calls, and import aliasing. The registry allowlist and its reverse-drift
guard against the LIVE repo live in the sibling
`test_triage_append_producer_registry.py`; false-positive avoidance, named
accepted-gap pins, and file-readability edge cases live in the sibling
`test_triage_plain_append_scan_edge_cases.py` (split out once this file
crossed 300 lines, the same reason `test_triage_precondition_registry.py`
was split from `test_triage_precondition_callers.py`). All fixtures here are
synthetic (`tmp_path`), so this file never depends on what the real tree
currently contains.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_plain_append_scan import find_plain_append_callers  # noqa: E402


def test_idempotent_calls_are_not_mistaken_for_plain_calls(
    tmp_path: Path,
) -> None:
    """`append_triage_item_idempotent(...)` must never trip the plain-call
    scan. An AST comparison of the CALLED NAME (not a substring/regex on the
    open paren) is what removes the ambiguity -- a naive text scan could
    misfire on a reformatted, multi-line call.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    clean = scripts_dir / "clean_producer.py"
    clean.write_text(
        "from triage import append_triage_item_idempotent\n"
        "def emit(root):\n"
        "    return append_triage_item_idempotent(\n"
        "        root, source='x', severity='low', kind='bug', title='t',\n"
        "        detail='d', dedup_key='k',\n"
        "    )\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()


def test_attribute_form_call_is_also_found(tmp_path: Path) -> None:
    """`triage.append_triage_item(...)` (module-qualified) must be caught too
    -- several real producers in this repo call the sibling
    `append_triage_item_idempotent` this way, so the scanner must recognise
    both call shapes identically.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    qualified = scripts_dir / "qualified_producer.py"
    qualified.write_text(
        "import triage\n"
        "def emit(root):\n"
        "    return triage.append_triage_item(root, source='x', "
        "severity='low', kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/qualified_producer.py"}


def test_an_aliased_import_of_the_bare_name_is_still_found(
    tmp_path: Path,
) -> None:
    """`from triage import append_triage_item as write_item` must be caught.

    External plan review (both providers, iterate-2026-09-16-e5) found this
    gap in an earlier revision: matching only the literal name
    `append_triage_item` let a renamed import evade the scan entirely, since
    the call site (`write_item(...)`) never spells the real name anywhere.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    aliased = scripts_dir / "aliased_producer.py"
    aliased.write_text(
        "from triage import append_triage_item as write_item\n"
        "def emit(root):\n"
        "    return write_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == {"shared/scripts/aliased_producer.py"}


def test_an_aliased_import_of_the_idempotent_sibling_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """The alias map is keyed on the REAL name, not merely "any alias" --
    aliasing the idempotent sibling must not be misread as the plain call.
    """
    scripts_dir = tmp_path / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    aliased = scripts_dir / "aliased_idempotent_producer.py"
    aliased.write_text(
        "from triage import append_triage_item_idempotent as write_item\n"
        "def emit(root):\n"
        "    return write_item(root, source='x', severity='low', "
        "kind='bug', title='t', detail='d', dedup_key='k')\n",
        encoding="utf-8",
    )
    found = find_plain_append_callers(tmp_path, bases=("shared/scripts",))
    assert found == set()
