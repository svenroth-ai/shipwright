"""S2b pass C4: ``_test_links_io.discover_specs`` skips a spec.md DIRECTORY.

This site lives outside the 15-site ``planning_discovery`` inventory (it checks
``.shipwright/agent_docs/spec.md`` directly, not through the shared helper), but
carried the same defect class as campaign S2b pass C1: gating on ``.exists()``
let a directory named ``spec.md`` reach ``discover_specs``' output list, which
would later explode at ``read_text()``. Fixed by gating on ``.is_file()``
instead, matching the ``require="is_file"`` the planning-split half of this
same function already uses (S2b pass B1).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors import _test_links_io as io  # noqa: E402


def test_discover_specs_skips_a_directory_named_agent_docs_spec_md(tmp_path):
    root = tmp_path / "proj"
    (root / ".shipwright" / "agent_docs" / "spec.md").mkdir(parents=True)
    specs = io.discover_specs(root)
    assert (root / ".shipwright" / "agent_docs" / "spec.md") not in specs


def test_discover_specs_still_finds_a_real_agent_docs_spec_md(tmp_path):
    root = tmp_path / "proj"
    top = root / ".shipwright" / "agent_docs" / "spec.md"
    top.parent.mkdir(parents=True)
    top.write_text("# top", encoding="utf-8")
    specs = io.discover_specs(root)
    assert top in specs
