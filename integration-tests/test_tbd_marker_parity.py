"""`/shipwright-adopt`'s `TBD_MARKER` and `group_i_tbd_age.TBD_MARKER` must
never drift apart (iterate-2026-09-06-fr-hygiene-touched-rows).

`spec_document.py` (shipwright-adopt) OWNS the literal it emits for an FR it
could derive no acceptance criteria for, now a named constant rather than an
inline string precisely so this can be pinned; `group_i_tbd_age.TBD_MARKER`
(shipwright-compliance) matches it verbatim, by design, rather than fuzzily —
see that module's docstring. Nothing else enforces the two stay byte-identical
across the plugin boundary, so a reword on either side would silently stop I8
from ever firing again, with no error anywhere. Each side is imported in its
own subprocess (ADR-045: both plugins ship a top-level `lib` package, so
importing both `lib.spec_document` and the compliance-local `lib` in one
process is the collision this pattern avoids — see
`test_fr_table_shape_convergence.py` for the same isolation).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_hex(snippet: str) -> str:
    """Run ``snippet`` and return its stdout as a hex string. The marker
    contains an em dash (U+2014); round-tripping it through a child process's
    stdout under the platform's default encoding can raise on a runner whose
    locale cannot represent it. Hex is ASCII-only and has no leading/trailing
    whitespace to strip, so the comparison below is exact and portable."""
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=True,
    )
    return proc.stdout.strip()


def test_adopt_tbd_literal_matches_the_compliance_i8_marker():
    adopt_hex = _run_hex(
        "import sys, pathlib\n"
        "root = pathlib.Path.cwd()\n"
        "sys.path.insert(0, str(root / 'plugins' / 'shipwright-adopt' / 'scripts'))\n"
        "from lib.spec_document import TBD_MARKER\n"
        "print(TBD_MARKER.encode('utf-8').hex())\n",
    )
    compliance_hex = _run_hex(
        "import sys, pathlib\n"
        "root = pathlib.Path.cwd()\n"
        "sys.path.insert(0, str(root / 'plugins' / 'shipwright-compliance' / 'scripts'))\n"
        "from audit.group_i_tbd_age import TBD_MARKER\n"
        "print(TBD_MARKER.encode('utf-8').hex())\n",
    )
    assert adopt_hex == compliance_hex


def test_an_all_tbd_adoption_still_renders_the_marker_under_an_fr_heading():
    """Pins the CONTRACT, not just the constant (doubt review, medium): I8
    reads the marker by its position under a `### FR-xx.yy` heading
    (`group_i_tbd_age._FR_HEADING_RE`), via `git blame` on that exact line.
    `spec_document.py` used to render undifferentiated prose with NO per-FR
    headings at all when not one detected feature had an acceptance
    criterion — the common shape for a freshly adopted repo — so the parity
    test above could pass while I8 was structurally unable to ever fire on
    that shape. Renders through the real `_render_spec_md` (not a hand-typed
    fixture) with every feature carrying an empty ``acceptance_criteria``, and
    checks the marker actually sits on the line right after its FR's own
    heading — the shape `_FR_HEADING_RE` plus a `git blame` on the very next
    populated line depends on."""
    combined_hex = _run_hex(
        "import sys, pathlib\n"
        "root = pathlib.Path.cwd()\n"
        "sys.path.insert(0, str(root / 'plugins' / 'shipwright-adopt' / 'scripts'))\n"
        "from lib.spec_document import _render_spec_md, TBD_MARKER\n"
        "body = _render_spec_md(\n"
        "    project_name='Demo', split_name='01-adopted',\n"
        "    product_description='x',\n"
        "    features=[{'fr_id': 'FR-01.01', 'label': 'Sign in'}],\n"
        "    qr_items=[], constraints=[],\n"
        ")\n"
        "print((body + chr(0) + TBD_MARKER).encode('utf-8').hex())\n",
    )
    body, marker = bytes.fromhex(combined_hex).decode("utf-8").split("\0")
    match = re.search(r"^#{1,6}\s+FR-01\.01\b.*$", body, re.MULTILINE)
    assert match, "no FR-01.01 heading in the rendered spec"
    tail = body[match.end():]
    next_line = next((ln for ln in tail.splitlines() if ln.strip()), "")
    assert next_line.strip() == marker
