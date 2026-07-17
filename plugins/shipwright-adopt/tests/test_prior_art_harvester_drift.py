"""Iterate 2 Sub-2A: prior_art_harvester drift detection.

When CONTRIBUTING.md references sibling directories that are excluded
from adoption (--exclude-path) or do not exist in the project,
harvest_conventions must annotate the harvested body with a drift
marker so the downstream conventions.md surfaces the stale reference
to a reviewer.

Background: the 2026-05-02 self-adoption found CONTRIBUTING.md
referenced `cd webui/client && npm ci` although webui had moved to a
separate repo. The harvester copied the section verbatim into
conventions.md, where it persisted as silent drift until manually
caught in audit. This guard makes the drift visible.
"""

from __future__ import annotations
import pytest

import sys
from pathlib import Path

# Make the plugin's lib importable when pytest is invoked from monorepo root.
_PLUGIN_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_LIB))

from prior_art_harvester import harvest_conventions  # type: ignore[import-not-found]

DRIFT_MARKER_TOKEN = "adopt-drift"


def _write_contributing(tmp_path: Path, content: str) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text(content, encoding="utf-8")


@pytest.mark.covers("FR-01.13")
def test_excluded_path_in_code_block_is_annotated(tmp_path: Path) -> None:
    """Path under an --exclude-path entry must be flagged."""
    _write_contributing(
        tmp_path,
        "## Setup\n\n```bash\ncd webui/client && npm ci\n```\n",
    )
    # webui/ is excluded — harvester should annotate
    result = harvest_conventions(tmp_path, excludes=["webui/"])
    assert result is not None
    assert DRIFT_MARKER_TOKEN in result.content
    assert "webui/client" in result.content  # the original ref is still there


@pytest.mark.covers("FR-01.13")
def test_nonexistent_path_in_code_block_is_annotated(tmp_path: Path) -> None:
    """Path that doesn't exist on disk must be flagged."""
    _write_contributing(
        tmp_path,
        "## Setup\n\n```bash\ncd nonexistent/dir && npm ci\n```\n",
    )
    result = harvest_conventions(tmp_path, excludes=None)
    assert result is not None
    assert DRIFT_MARKER_TOKEN in result.content


@pytest.mark.covers("FR-01.13")
def test_existing_path_no_drift_marker(tmp_path: Path) -> None:
    """If the path exists and is not excluded, no drift annotation."""
    (tmp_path / "scripts").mkdir()
    _write_contributing(
        tmp_path,
        "## Setup\n\n```bash\ncd scripts && ls\n```\n",
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert DRIFT_MARKER_TOKEN not in result.content


@pytest.mark.covers("FR-01.13")
def test_default_excludes_none_is_backwards_compatible(tmp_path: Path) -> None:
    """Calling without excludes (legacy callers) still works; no annotation
    when paths exist."""
    (tmp_path / "src").mkdir()
    _write_contributing(
        tmp_path,
        "## Conventions\n\n```bash\ncd src && uv sync\n```\n",
    )
    # Old-style call without excludes kwarg
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert DRIFT_MARKER_TOKEN not in result.content


@pytest.mark.covers("FR-01.13")
def test_url_in_code_block_not_annotated(tmp_path: Path) -> None:
    """Code blocks may reference https URLs; those must not be flagged
    as missing paths."""
    _write_contributing(
        tmp_path,
        "## Install\n\n```bash\ncurl -L https://example.com/install.sh | bash\n```\n",
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert DRIFT_MARKER_TOKEN not in result.content
