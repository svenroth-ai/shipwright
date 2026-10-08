"""Step 3.4 takes its diff-size rule from shared/, never a local copy.

``review_threshold_bridge`` loads ``shared/scripts/lib/review_diff_threshold.py``
by path (ADR-044/045). These tests pin that the re-exported names ARE the shared
ones and that ``diff_change_set`` counts with the same path filter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import diff_change_set as dcs  # noqa: E402
import diff_risk_recheck as drr  # noqa: E402
import review_threshold_bridge as bridge  # noqa: E402

_REPO = Path(__file__).resolve().parents[3]


@pytest.mark.covers("FR-01.11")
def test_the_bridge_loads_the_shared_module_not_a_copy():
    assert bridge.SHARED_SOURCE.resolve() == (
        _REPO / "shared" / "scripts" / "lib" / "review_diff_threshold.py").resolve()
    shared = sys.modules[bridge._MODULE_NAME]
    assert drr.PLAN_REVIEW_DIFF_LOC_THRESHOLD == shared.DIFF_LOC_THRESHOLD == 100
    assert drr.exceeds_diff_threshold is shared.exceeds_diff_threshold
    assert dcs.is_counted_path is shared.is_counted_path
    assert dcs.numstat_changed_lines is shared.numstat_changed_lines


@pytest.mark.covers("FR-01.11")
def test_a_shared_tree_missing_a_name_raises_a_named_import_error():
    stale = type(sys)("stale_shared")
    with pytest.raises(ImportError, match="shared tree older than the iterate plugin - run update-marketplace.sh"):
        bridge._require(stale, "numstat_changed_lines")


@pytest.mark.covers("FR-01.11")
def test_no_local_threshold_literal_left_in_the_plugin_lib():
    text = (LIB / "diff_risk_recheck.py").read_text(encoding="utf-8")
    assert "PLAN_REVIEW_DIFF_LOC_THRESHOLD = " not in text


@pytest.mark.covers("FR-01.11")
def test_step_3_4_numstat_count_skips_finalization_records():
    raw = "60\t0\t.shipwright/agent_docs/iterates/x.json\0" "3\t2\tsrc/a.py\0"
    paths, loc = dcs.parse_numstat_z(raw)
    assert paths == [".shipwright/agent_docs/iterates/x.json", "src/a.py"]
    assert loc == 5


@pytest.mark.covers("FR-01.11")
def test_step_3_4_untracked_count_skips_finalization_records(tmp_path):
    (tmp_path / "CHANGELOG-unreleased.d").mkdir()
    (tmp_path / "CHANGELOG-unreleased.d" / "x.md").write_text("a\nb\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("a\nb\nc\n", encoding="utf-8")
    assert dcs.untracked_loc(tmp_path, ["CHANGELOG-unreleased.d/x.md", "new.py"]) == 3
