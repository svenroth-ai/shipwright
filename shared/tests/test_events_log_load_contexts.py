"""``lib.events_log`` must import cleanly in every context it is LOADED in (AC15).

Split out of ``test_events_reader_record_boundary.py``: that module pins
record-boundary RECOVERY, this one pins the module-LOAD contract. Different
concern, and both files sit near the 300-line guideline.

WHY THIS EXISTS
---------------
Taking the shared record-boundary SSoT as a dependency made ``events_log``'s
import form load-context-sensitive, and TWO successive attempts shipped
BLOCKER-class defects that no other test would have caught:

* a plain ``from .jsonl_records import …`` broke 15 compliance tests — Group F
  execs this module BY FILE LOCATION under a sentinel name, where a relative
  import has no parent package;
* ``from lib.jsonl_records import …`` then bound ``sys.modules['lib']`` to
  SHARED's package during that exec, which ``audit_adapters.load_shared_lib``
  never restores — so every later compliance-local ``from lib.X`` would resolve
  against shared and raise;
* ``from jsonl_records import …`` needed ``shared/scripts/lib`` itself on
  sys.path, which no loader inserts — with ``lib`` pre-bound to a plugin ALL
  branches failed and the F5 arch-drift detective went dark.

These cases live in the SHARED suite deliberately: the failures they guard
surface in the compliance plugin's suite, so without them the shared suite stays
green while a "simplification" silently breaks the audit — exactly the
CI-red/local-green class ADR-045 warns about.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.events_log import resolve_events_path  # noqa: E402

_A = {
    "v": 1, "id": "evt-aaa", "ts": "2026-07-19T10:00:00+00:00",
    "type": "work_completed", "adr_id": "iterate-side-a", "run_id": "iterate-side-a",
}
_B = {
    "v": 1, "id": "evt-bbb", "ts": "2026-07-19T11:00:00+00:00",
    "type": "work_completed", "adr_id": "iterate-side-b", "run_id": "iterate-side-b",
}


def _write_concatenated(project_root: Path) -> Path:
    """One physical line holding TWO valid records."""
    path = resolve_events_path(project_root)
    path.write_text(json.dumps(_A) + json.dumps(_B) + "\n", encoding="utf-8")
    return path


def test_events_log_load_contexts(tmp_path: Path) -> None:
    """``events_log`` must import cleanly in all THREE load contexts.

    Drift guard for the import chain at the top of ``lib/events_log.py``. Taking
    the shared record-boundary SSoT as a dependency made this module's import
    form load-context-sensitive: a plain ``from .jsonl_records import …`` broke
    15 compliance tests through Group F, which loads this module BY FILE
    LOCATION under a sentinel name (no parent package -> relative import fails).

    This case lives in the SHARED suite deliberately. The failure it guards
    surfaces only in the compliance plugin's suite, so without it the shared
    suite stays green while a "simplification" of the chain silently breaks the
    audit — exactly the CI-red/local-green class ADR-045 warns about.
    """
    lib_dir = Path(__file__).resolve().parents[1] / "scripts" / "lib"
    module_path = lib_dir / "events_log.py"

    # Context 2 — file location under a sentinel name (audit_adapters).
    # `shared/scripts` is on sys.path (module header), so `lib.` resolves.
    spec = importlib.util.spec_from_file_location("_sentinel_events_log", module_path)
    assert spec is not None and spec.loader is not None
    sentinel = importlib.util.module_from_spec(spec)
    sys.modules["_sentinel_events_log"] = sentinel
    try:
        spec.loader.exec_module(sentinel)  # must not raise ImportError
        assert callable(sentinel.finalized_run_ids)
    finally:
        sys.modules.pop("_sentinel_events_log", None)

    # Context 2b — the REAL Group F shape: a plugin's own `lib` is already bound
    # to sys.modules when the sentinel exec runs. This is the case the first
    # version of this test missed: it ran where `lib` was already SHARED's, so a
    # `from lib.jsonl_records import ...` fallback passed here while failing in
    # production. Two separate rejected fallbacks died on exactly this shape.
    saved_lib = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    decoy_dir = tmp_path / "decoy_plugin_scripts" / "lib"
    decoy_dir.mkdir(parents=True)
    (decoy_dir / "__init__.py").write_text("", encoding="utf-8")  # NO jsonl_records
    saved_path = list(sys.path)
    try:
        for key in saved_lib:
            sys.modules.pop(key, None)
        sys.path.insert(0, str(decoy_dir.parent))
        import lib as decoy  # binds sys.modules['lib'] to the decoy plugin package
        assert Path(decoy.__file__).parent == decoy_dir, "decoy must own the `lib` name"

        spec2 = importlib.util.spec_from_file_location("_sentinel_events_log_2", module_path)
        mod2 = importlib.util.module_from_spec(spec2)
        sys.modules["_sentinel_events_log_2"] = mod2
        try:
            spec2.loader.exec_module(mod2)  # must not raise, and must not go dark
            # Assert BEHAVIOUR, not just that it imported: a fallback that bound
            # a stub would satisfy `callable(...)`. That "it loaded" assumption
            # is the same shape as the gap which let the first version of this
            # test miss the pollution defect entirely.
            _write_concatenated(tmp_path)
            assert mod2.finalized_run_ids(tmp_path) == {"iterate-side-a", "iterate-side-b"}
        finally:
            sys.modules.pop("_sentinel_events_log_2", None)

        # And it must NOT have hijacked the `lib` name away from the decoy —
        # that pollution is what breaks a plugin's own imports afterwards.
        assert Path(sys.modules["lib"].__file__).parent == decoy_dir, (
            "loading events_log must not rebind sys.modules['lib']"
        )
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            sys.modules.pop(key, None)
        sys.modules.update(saved_lib)

    # Context 3 — FLAT, `shared/scripts/lib` itself on sys.path. This is LIVE in
    # production, not hypothetical: `tools/backfill_test_links.py` inserts that
    # dir at sys.path[0] and imports `backfill_scan`, which then does a flat
    # `from events_log import resolve_events_path`. An earlier revision of this
    # test dropped this leg; it is kept ADDITIVE to 2b for that reason.
    saved_path = list(sys.path)
    saved_flat = {
        k: v for k, v in sys.modules.items()
        if k in ("events_log", "jsonl_records") or k == "lib" or k.startswith("lib.")
    }
    try:
        for key in saved_flat:
            sys.modules.pop(key, None)
        sys.path.insert(0, str(lib_dir))
        flat_spec = importlib.util.spec_from_file_location("events_log", module_path)
        flat = importlib.util.module_from_spec(flat_spec)
        sys.modules["events_log"] = flat
        flat_spec.loader.exec_module(flat)  # must not raise ImportError
        _write_concatenated(tmp_path)
        assert flat.finalized_run_ids(tmp_path) == {"iterate-side-a", "iterate-side-b"}
    finally:
        sys.path[:] = saved_path
        for key in ("events_log", "jsonl_records"):
            sys.modules.pop(key, None)
        sys.modules.update(saved_flat)


def test_sentinel_cache_is_keyed_per_copy_not_globally(tmp_path: Path) -> None:
    """Two copies of ``events_log.py`` in one process must NOT share one parser.

    The sentinel was originally a bare constant, so a second copy loading later
    would silently reuse the FIRST copy's ``jsonl_records``. That is the exact
    worktree-vs-plugin-cache drift the by-path (copy-local) resolution exists to
    prevent, so keying the cache globally would have re-opened it one level down.
    Keyed on a digest of the resolved parent directory instead.
    """
    lib_dir = Path(__file__).resolve().parents[1] / "scripts" / "lib"
    copy_dir = tmp_path / "copy" / "lib"
    copy_dir.mkdir(parents=True)
    for name in ("events_log.py", "jsonl_records.py"):
        shutil.copy2(lib_dir / name, copy_dir / name)

    sentinels = set()
    for src in (lib_dir, copy_dir):
        spec = importlib.util.spec_from_file_location(
            f"_sentinel_copy_{src.parent.name}", src / "events_log.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
            _write_concatenated(tmp_path)
            assert mod.finalized_run_ids(tmp_path) == {"iterate-side-a", "iterate-side-b"}
            sentinels |= {k for k in sys.modules if k.startswith("_shipwright_events_log_jsonl_records_")}
        finally:
            sys.modules.pop(spec.name, None)

    assert len(sentinels) >= 2, (
        f"each copy must cache its own parser; got {sentinels}"
    )
    for key in sentinels:
        sys.modules.pop(key, None)


def test_missing_sibling_raises_importerror_not_oserror(tmp_path: Path) -> None:
    """A missing ``jsonl_records.py`` must surface as ``ImportError``.

    ``spec_from_file_location`` does not stat the path, so without the explicit
    ``.is_file()`` check it returns a valid spec and ``exec_module`` raises
    ``FileNotFoundError`` — an ``OSError``, which sails straight through the
    ``except ImportError`` guards that callers such as ``backfill_scan`` use.
    """
    orphan_dir = tmp_path / "orphan" / "lib"
    orphan_dir.mkdir(parents=True)
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "scripts" / "lib" / "events_log.py",
        orphan_dir / "events_log.py",
    )  # deliberately WITHOUT jsonl_records.py

    spec = importlib.util.spec_from_file_location("_sentinel_orphan", orphan_dir / "events_log.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_sentinel_orphan"] = mod
    try:
        with pytest.raises(ImportError):
            spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("_sentinel_orphan", None)
