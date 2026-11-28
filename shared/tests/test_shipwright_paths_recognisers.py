"""R1c-3: what RECOGNISES a moving file by its path sees it in the new place too (BRIEF 12.12 (a)).

R1c-2 made every reader and writer find a moving file through ``path()``. What was left recognised a file by
its root name: derived/run-written snapshot sets, the churn allowlist, review-size and section bookkeeping
sets, the sensitive-path regex, the skip-review set, the project markers, the compliance producer inputs,
the fold's pathspec and the phase-context hints. Each case below puts the path in its new place and asks the
real recogniser. Before R1c-3 every one of them answered "not mine".
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "scripts"))

from lib import shipwright_paths as sp  # noqa: E402
from lib.churn_merge import CHURN_ALLOWLIST  # noqa: E402
from lib.compliance_refresh import CLASSIFICATION, EXCLUDED, RUN_WRITTEN  # noqa: E402
from lib.derived_snapshots import DERIVED_SNAPSHOTS, RESTORABLE_SNAPSHOTS  # noqa: E402
from lib.project_root import is_shipwright_project  # noqa: E402
from lib.review_diff_threshold import is_counted_path  # noqa: E402
from lib.section_file_list import is_framework_bookkeeping  # noqa: E402


def _new(key: str) -> str:
    return sp.new_rel(key)


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod   # register before exec (dataclasses / self-imports)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.covers("FR-01.11")
def test_the_run_written_ledger_is_a_derived_snapshot_in_either_place():
    for where in sp.known_rels("test_results"):
        assert where in DERIVED_SNAPSHOTS and where not in RESTORABLE_SNAPSHOTS   # never staged, never reset
        assert where in CHURN_ALLOWLIST and CLASSIFICATION[where] == RUN_WRITTEN and where in EXCLUDED


@pytest.mark.covers("FR-01.11")
def test_finalization_records_are_not_counted_or_attributed_in_the_new_place():
    assert not is_counted_path(_new("test_results"))
    assert is_framework_bookkeeping(_new("build_config"))
    assert is_counted_path("src/app.py") and not is_framework_bookkeeping("src/app.py")   # real code still counts


@pytest.mark.covers("FR-01.11")
def test_a_no_fr_label_covers_a_moved_file_exactly_as_it_covers_the_root_file():
    """The new place sits under ``.shipwright/**``, which every label covers as bookkeeping; without R1c-3 a
    ``docs`` iterate could edit a moved baseline or risk register it may not touch at the root (plan review)."""
    from lib.change_type_paths import unclassified_paths
    for key in ("bloat_baseline", "accepted_risks", "run_config", "dev_server"):
        new = sp.known_rels(key)[0]
        assert unclassified_paths([new], "docs", "generic") == [new], key   # reported as the path given
        assert unclassified_paths([sp.name(key)], "docs", "generic") == [sp.name(key)], key   # root: as before
        assert unclassified_paths([new], "tooling", "generic") == [], key
    assert unclassified_paths([_new("test_results")], "docs", "generic") == []   # a finalization record


@pytest.mark.covers("FR-01.11")
def test_a_project_whose_config_moved_is_still_a_project(tmp_path):
    (tmp_path / ".shipwright" / "config").mkdir(parents=True)
    assert not is_shipwright_project(tmp_path)
    (tmp_path / _new("run_config")).write_text("{}", encoding="utf-8")
    assert is_shipwright_project(tmp_path)   # no root stub needed (BRIEF 12.12 (a): CONFIG_MARKERS)


@pytest.mark.covers("FR-01.11")
def test_a_risk_register_or_bloat_baseline_in_the_new_place_is_a_sensitive_path():
    tier = _load("plugins/shipwright-security/scripts/tools/review_record_tier.py", "review_record_tier_r1c3")
    for key in ("accepted_risks", "bloat_baseline"):
        for where in sp.known_rels(key):
            assert tier.SENSITIVE_PATH_RE.match(where), where
    assert not tier.SENSITIVE_PATH_RE.match("docs/" + sp.name("bloat_baseline"))   # anchored, not a basename


@pytest.mark.covers("FR-01.11")
def test_the_ledger_is_skip_safe_only_where_it_lives_today():
    """Skip-safety LOOSENS the required review gate, so unlike every other set it does not run ahead of the move:
    a PR adding the ledger at the new place (which nothing creates before R3) still gets a review."""
    skip = _load("plugins/shipwright-security/scripts/lib/pr_review_skip_safety.py", "pr_review_skip_safety_r1c3")
    assert skip.is_safe_to_skip_review(sp.legacy_rel("test_results"))
    assert not skip.is_safe_to_skip_review(_new("test_results"))   # R3 flips this together with the move
    assert not skip.is_safe_to_skip_review("src/" + sp.name("test_results"))   # a planted name borrows nothing


@pytest.mark.covers("FR-01.11")
def test_the_compliance_producer_snapshots_both_places_and_reports_one(tmp_path):
    from tools import compliance_input_state as cis
    assert set(sp.known_rels("compliance_config")) <= set(cis.PRODUCER_STATE)
    p = tmp_path / _new("compliance_config")
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    inputs = cis.producer_inputs(tmp_path)
    assert _new("compliance_config") in inputs and sp.legacy_rel("compliance_config") not in inputs


@pytest.mark.covers("FR-01.11")
def test_the_fold_stages_the_sync_config_where_it_lives(tmp_path):
    from tools import fold_events
    folded = {"status": "folded_into_legacy", "mode": "emergency"}
    assert sp.name("sync_config") in fold_events._stage_paths(folded, str(tmp_path))   # unmigrated: the root
    assert fold_events._stage_paths({"status": "folded", "mode": "normal"}, str(tmp_path)) == [
        f"{fold_events.DROPS_DIR}/{fold_events.KEEP_NAME}"]   # a fold that does not touch it never resolves it
    p = tmp_path / _new("sync_config")
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    assert _new("sync_config") in fold_events._stage_paths({"status": "nothing_to_fold", "mode": "emergency"},
                                                            str(tmp_path))
    assert _new("sync_config") in fold_events._stage_paths(folded, str(tmp_path))


@pytest.mark.covers("FR-01.11")
def test_the_phase_context_points_a_skill_at_the_moved_file(tmp_path):
    from tools import get_phase_context as gpc
    assert gpc._where(["plan_config", ".shipwright/designs/"], tmp_path) == [
        sp.legacy_rel("plan_config"), ".shipwright/designs/"]   # unmigrated: the root, as before
    p = tmp_path / _new("plan_config")
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    assert gpc._where(["plan_config"], tmp_path) == [_new("plan_config")]


#: Production code that may still spell a moving file by ``rel()``: the resolver, and adopt's dry-run
#: preview, which names the file it WOULD create (creation keeps the root until R3 decides it).
_REL_ALLOWED = {"shared/scripts/lib/shipwright_paths.py", "plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py"}
#: Module constants kept on purpose: the legacy ledger name tests write (sets use ``TEST_RESULTS_RELS``).
_REL_KEPT = {("shared/scripts/lib/churn_merge.py", "test_results"),
             # skip-safety loosens a gate: root place only until R3 creates the new one (architecture review)
             ("plugins/shipwright-security/scripts/lib/pr_review_skip_safety.py", "test_results")}


def _production_py() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--", "plugins", "shared", "scripts"], capture_output=True, text=True,
                         cwd=str(REPO), check=True).stdout.split()
    return [f for f in out if f.endswith(".py") and "/tests/" not in f and not f.startswith("shared/testkit/")]


@pytest.mark.covers("FR-01.11")
def test_no_production_code_spells_a_moving_file_by_its_root_name():
    """The R1c-3 net (BRIEF 12.2 / item 10 (d)): once R3 flips ``rel()``, a ``rel()``/``legacy_rel()`` of a moving
    key in production code would name the wrong place. Recognisers use ``known_rels``, readers and writers
    ``path()``, labels ``name()``; the event log does not move."""
    moving = set(sp.keys_of(moves=True))
    hits = []
    for rel in _production_py():
        if rel in _REL_ALLOWED:
            continue
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"rel", "legacy_rel"}
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "_sp" and n.args):
                arg = n.args[0]
                key = arg.value if isinstance(arg, ast.Constant) else None   # a computed key may name any file
                if (key is None or key in moving) and (rel, key) not in _REL_KEPT:
                    hits.append(f"{rel}:{n.lineno}: _sp.{n.func.attr}({ast.unparse(arg)})")
    assert hits == [], "use known_rels (a set), path() (a read/write) or name() (a label):\n" + "\n".join(hits)


@pytest.mark.covers("FR-01.11")
def test_the_net_sees_a_root_spelling(tmp_path, monkeypatch):
    """Positive control: the scan above flags a planted ``_sp.rel`` of a moving key."""
    planted = "shared/scripts/lib/planted_r1c3.py"
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "_production_py", lambda: [planted])
    (tmp_path / planted).parent.mkdir(parents=True)
    (tmp_path / planted).write_text('X = {_sp.rel("run_config")}\n', encoding="utf-8")
    with pytest.raises(AssertionError, match="planted_r1c3.py:1"):
        test_no_production_code_spells_a_moving_file_by_its_root_name()
