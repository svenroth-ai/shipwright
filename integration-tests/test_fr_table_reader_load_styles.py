"""``fr_table_reader`` behaves identically under all three import styles.

Raised in external plan review (GPT, medium): "a new module can work in tests
yet fail in release tooling or hooks" — enumerate the execution modes of the
five consumers rather than reasoning about them.

That is the ADR-045 failure class, and it has bitten this repo before: an eager
``from lib.X import Y`` in a shared module resolves against whichever ``lib``
package is FIRST on ``sys.path``, so a module that imports cleanly from one
plugin's pytest session raises ``ModuleNotFoundError`` from another — CI red,
local green. One reader shared by five callers in three different import realms
is exactly the shape that trips it, so the load styles are tested, not argued.

The three styles, and who uses each:

* **flat** — ``import fr_table_reader`` with ``shared/scripts/lib`` on the path.
  Used by ``drift_parsers`` and ``_backfill_spec_parse`` in tool/test contexts.
* **package** — ``lib.fr_table_reader``, which is what the compliance
  collectors' ``_lib_loader`` produces for ``rtm`` and ``_requirement_parse``.
  Its relative sibling imports must resolve at IMPORT time, because
  ``_lib_loader`` restores the caller's own ``lib`` binding on the way out.
* **file location under a sentinel name** — ``spec_from_file_location``, which
  is how ``audit_adapters`` reaches shared code for Group I, and how
  ``drift_parsers`` reaches this module when IT was itself location-loaded.
  Here ``__package__`` is empty, so a relative import cannot work at all.

Each style is loaded in its own subprocess. Doing it in-process would leave
``sys.modules['lib']`` bound by whichever style ran first, which is precisely
the interference being tested for — an ordering discipline inside one process
is defeatable by pytest collection order (the same argument the golden corpus
makes for its per-realm subprocesses).

@FR-01.10
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "shared" / "scripts" / "lib"
COMPLIANCE = REPO_ROOT / "plugins" / "shipwright-compliance"

_SPEC = (
    "## Requirements\n"
    "| ID | Name | Priority | Description | Layers |\n"
    "| FR-01.01 | /run | Must | Orchestrate the pipeline | unit |\n"
    "### Removed Requirements\n"
    "| ID | Name | Priority | Description | Layers |\n"
    "| FR-01.09 | /gone | Should | Retired capability | e2e |\n"
)

_LOADERS = {
    # style -> python source that must bind `reader`
    "flat": f"""
import sys; sys.path.insert(0, {str(LIB)!r})
import fr_table_reader as reader
""",
    "package": f"""
import sys; sys.path.insert(0, {str(LIB.parent)!r})
import importlib
reader = importlib.import_module("lib.fr_table_reader")
""",
    "file_location": f"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location(
    "_sentinel_fr_table_reader", {str(LIB / "fr_table_reader.py")!r})
reader = importlib.util.module_from_spec(spec)
sys.modules["_sentinel_fr_table_reader"] = reader
spec.loader.exec_module(reader)
""",
    # The adversarial one: bind `lib` to the COMPLIANCE plugin's own lib package
    # BEFORE loading, then load by file location. A relative sibling import
    # would resolve into the wrong package here and raise.
    "file_location_with_foreign_lib_bound": f"""
import importlib, importlib.util, sys
sys.path.insert(0, {str(COMPLIANCE / "scripts")!r})
import lib  # noqa: F401  -- the compliance-local lib, now bound in sys.modules
spec = importlib.util.spec_from_file_location(
    "_sentinel_fr_table_reader", {str(LIB / "fr_table_reader.py")!r})
reader = importlib.util.module_from_spec(spec)
sys.modules["_sentinel_fr_table_reader"] = reader
spec.loader.exec_module(reader)
""",
}

_PROBE = """
import json
rows = reader.read_fr_rows({spec!r})
print(json.dumps([
    {{"id": r.id, "text": r.text, "priority": r.priority,
      "status": r.status, "layers": r.layers_cell}}
    for r in rows
]))
"""


# Reports the sibling-allowlist state from inside the loaded module. Run as a
# subprocess like every other probe here: importing the reader in-process would
# bind `sys.modules['lib']` for the whole session, which is the interference
# this module exists to keep out.
_ALLOWLIST_PROBE = """
import json
# Snapshot the import-time cache BEFORE probing the guard. `_sibling` memoizes
# into `_SIBLINGS`, so a guard that wrongly ALLOWS the undeclared name would
# also insert it here -- and the allowlist-vs-loaded comparison would then agree
# with itself and pass. Reading first is what keeps the two facts independent.
loaded = sorted(reader._SIBLINGS)
try:
    reader._sibling("os")
except ValueError as exc:
    refused = "_ALLOWED_SIBLINGS" in str(exc)
except Exception:
    refused = False
else:
    refused = False
print(json.dumps({
    "loaded": loaded,
    "declared": sorted(reader._ALLOWED_SIBLINGS),
    "refused": refused,
}))
"""


def _run_source(source: str, label: str):
    proc = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    assert proc.returncode == 0, (
        f"{label} load failed:\n{proc.stderr}"
    )
    return json.loads(proc.stdout)


def _run(style: str) -> list[dict]:
    return _run_source(_LOADERS[style] + _PROBE.format(spec=_SPEC), style)


_EXPECTED = [
    {"id": "FR-01.01", "text": "Orchestrate the pipeline", "priority": "Must",
     "status": "active", "layers": "unit"},
    {"id": "FR-01.09", "text": "Retired capability", "priority": "Should",
     "status": "removed", "layers": "e2e"},
]


@pytest.mark.parametrize("style", sorted(_LOADERS))
def test_the_reader_loads_and_parses_identically_under_every_import_style(style):
    assert _run(style) == _EXPECTED


@pytest.mark.parametrize("style", sorted(_LOADERS))
def test_the_declared_sibling_allowlist_matches_what_is_actually_loaded(style):
    """Reverse drift protection for ``_ALLOWED_SIBLINGS``.

    The allowlist is what lets ``_sibling``'s dynamic import carry a scanner
    suppression honestly: the name can only ever be one of five first-party
    modules. That argument collapses if the set is allowed to rot — a stale
    entry silently widens what the guard permits, and nothing else would notice,
    because an unused entry breaks nothing.

    ``_SIBLINGS`` is the import-time cache, so once the module has loaded it
    holds exactly the siblings really imported. Equality with the declared set
    pins both directions at once: no undeclared load, no unused declaration.
    Checked under every load style because ``_sibling`` takes a DIFFERENT branch
    per style — the relative-import branch is the one the guard now precedes.
    """
    state = _run_source(_LOADERS[style] + _ALLOWLIST_PROBE, style)
    assert state["loaded"] == state["declared"], (
        f"{style}: _ALLOWED_SIBLINGS disagrees with what was imported — "
        f"declared {state['declared']}, loaded {state['loaded']}"
    )


@pytest.mark.parametrize("style", sorted(_LOADERS))
def test_an_undeclared_sibling_name_is_refused_before_it_reaches_import(style):
    """The guard bites. Without this, ``_ALLOWED_SIBLINGS`` is documentation."""
    state = _run_source(_LOADERS[style] + _ALLOWLIST_PROBE, style)
    assert state["refused"], (
        f"{style}: _sibling('os') was not refused — an undeclared name can "
        f"reach import_module, and the nosemgrep suppression there is no longer "
        f"backed by a closed set"
    )


def test_the_reader_imports_none_of_the_five_parsers_it_replaced():
    """Keeps it a LEAF. A back-edge to any caller would be a circular import in
    at least one realm, and would resurface the coupling S4 removed."""
    source = (LIB / "fr_table_reader.py").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    for parser in (
        "drift_parsers", "_backfill_spec_parse", "rtm",
        "_requirement_parse", "group_i",
    ):
        assert f"import {parser}" not in body, parser
        assert f'"{parser}"' not in body, parser
