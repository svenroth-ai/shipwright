"""The infrastructure-test catalog (`shared/config/infra_test_paths.json`) is valid and names real files.

The F11 tag gate reads this file at the merge-base, so a typo or a vanished file would silently stop
licensing a ``covers_none`` declaration. Both directions are checked: every entry parses as an exact path
and exists, and no entry repeats.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "shared" / "scripts"))

from tools.verifiers._tag_binding_infra_pass import CATALOG_PATH, parse_catalog  # noqa: E402


@pytest.mark.covers("FR-01.11/AC55")
def test_catalog_parses_without_warning_and_every_entry_is_a_real_file():
    paths, warning = parse_catalog((_ROOT / CATALOG_PATH).read_text(encoding="utf-8"))

    assert warning is None
    assert paths, "the catalog must name the harness test files"
    for entry in sorted(paths):
        assert (_ROOT / entry).is_file(), f"{entry} is in {CATALOG_PATH} but does not exist"


@pytest.mark.covers("FR-01.11/AC55")
def test_catalog_has_no_duplicate_entries():
    import json

    entries = json.loads((_ROOT / CATALOG_PATH).read_text(encoding="utf-8"))
    assert len(entries) == len(set(entries))
