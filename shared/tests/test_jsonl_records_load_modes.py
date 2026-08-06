"""``lib.jsonl_records`` must import under BOTH load modes (ADR-045).

iterate-2026-08-06-p2-19c-corruption-absence gave the module its first
intra-package dependency (``atomic_write``, for the durable read of IT-1 audit
finding 5). ``shared_lib_loader.load_shared_lib`` — which ``triage.py`` and
``plugins/shipwright-compliance/scripts/audit/_events_read.py`` both use to reach
this module — states in its own docstring that the path-load fallback is *"only
safe for lib modules with no intra-package imports"*. So the dependency has to be
spelled two ways, and both spellings need pinning:

* **package mode** — ``shared/scripts`` on ``sys.path``, imported as
  ``lib.jsonl_records``; the relative import resolves.
* **sentinel mode** — a plugin's own ``scripts/lib`` shadows shared's, so
  ``load_shared_lib`` execs this file by path under a private name with **no
  package context**; the relative import cannot resolve and the fallback runs.

Each mode runs in an isolated subprocess (``-I``): a same-process probe passes on
the other mode's ``sys.modules`` leftovers and proves nothing. A guard test fails
if the subprocesses stop running at all, so this cannot decay into a silent skip.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_SCRIPTS = _SHARED / "scripts"


def _run(code: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-c", textwrap.dedent(code)],
        cwd=str(cwd), capture_output=True, text=True, timeout=60,
    )


def test_package_mode_import_resolves_the_durable_reader(tmp_path: Path) -> None:
    """The ordinary case: ``lib.jsonl_records`` with shared/scripts on the path."""
    result = _run(
        f"""
        import sys
        sys.path.insert(0, {str(_SCRIPTS)!r})
        from lib.jsonl_records import durable_read_text, read_jsonl_records
        print("MODE=package", durable_read_text.__name__, read_jsonl_records.__name__)
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "MODE=package durable_read_text read_jsonl_records" in result.stdout


def test_sentinel_mode_import_resolves_the_durable_reader(tmp_path: Path) -> None:
    """The shadowed case ``load_shared_lib`` exists for — no package context.

    A plugin's own ``lib`` package wins on ``sys.path`` and does not carry
    ``jsonl_records``, so the loader falls back to exec-ing the file by path.
    """
    shadow = tmp_path / "plugin_scripts"
    (shadow / "lib").mkdir(parents=True)
    (shadow / "lib" / "__init__.py").write_text("", encoding="utf-8")

    result = _run(
        f"""
        import sys
        sys.path.insert(0, {str(_SCRIPTS)!r})
        sys.path.insert(0, {str(shadow)!r})   # the shadowing `lib` wins
        import lib
        assert "plugin_scripts" in lib.__file__, lib.__file__

        from shared_lib_loader import load_shared_lib
        mod = load_shared_lib("jsonl_records")
        # The fallback ran, not the happy path. Asserted by NAMESPACE rather than
        # by the old flat sentinel name: trg-dc013d82 made the fallback load into a
        # private PACKAGE (so a lib module may hold a relative sibling import), which
        # renamed `_shipwright_shared_lib_jsonl_records` to `_shipwright_shared_lib.jsonl_records`.
        # The guarantee this pins is unchanged; only the spelling of the proxy moved.
        assert mod.__name__.startswith("_shipwright_shared_lib"), mod.__name__
        assert "lib.jsonl_records" not in sys.modules, "the shadowed package import won"
        print("MODE=sentinel", mod.durable_read_text.__name__)
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "MODE=sentinel durable_read_text" in result.stdout


def test_sentinel_mode_actually_reads_a_store(tmp_path: Path) -> None:
    """Importing is not using — the fallback reader must work, not merely bind.

    A module can import cleanly and still explode on first call if the fallback
    bound the wrong object.
    """
    shadow = tmp_path / "plugin_scripts"
    (shadow / "lib").mkdir(parents=True)
    (shadow / "lib" / "__init__.py").write_text("", encoding="utf-8")
    store = tmp_path / "store.jsonl"
    store.write_bytes(b'{"event":"append","id":"trg-1"}\n}{broken\n')

    result = _run(
        f"""
        import sys
        sys.path.insert(0, {str(_SCRIPTS)!r})
        sys.path.insert(0, {str(shadow)!r})
        from shared_lib_loader import load_shared_lib
        mod = load_shared_lib("jsonl_records")
        out = mod.read_jsonl_records({str(store)!r})
        assert [r["id"] for r in out.records] == ["trg-1"], out.records
        assert len(out.corrupt) == 1, out.corrupt
        print("MODE=sentinel-read OK")
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "MODE=sentinel-read OK" in result.stdout


def test_triage_integrity_sentinel_mode_works(tmp_path: Path) -> None:
    """``triage_integrity`` takes the same fallback, and takes it IN PRODUCTION.

    ``triage._iter_raw_lines_at`` calls ``load_shared_lib("triage_integrity")`` on
    every store read, so under a shadowing plugin ``lib`` the except-branch runs on
    the hot path — unlike ``jsonl_records``', which the earlier tests reach through
    the loader too but which was the only module pinned. Stage-2 code review found
    the comment claiming this was covered while nothing exercised it.
    """
    shadow = tmp_path / "plugin_scripts"
    (shadow / "lib").mkdir(parents=True)
    (shadow / "lib" / "__init__.py").write_text("", encoding="utf-8")
    store = tmp_path / "triage.jsonl"
    store.write_bytes(b'{"event":"append","id":"trg-1"}\n}{broken\n')

    result = _run(
        f"""
        import sys
        sys.path.insert(0, {str(_SCRIPTS)!r})
        sys.path.insert(0, {str(shadow)!r})
        from shared_lib_loader import load_shared_lib
        mod = load_shared_lib("triage_integrity")
        # The fallback ran, not the happy path. Asserted by NAMESPACE rather than
        # by the old flat sentinel name: trg-dc013d82 made the fallback load into a
        # private PACKAGE (so a lib module may hold a relative sibling import), which
        # renamed `_shipwright_shared_lib_triage_integrity` to `_shipwright_shared_lib.triage_integrity`.
        # The guarantee this pins is unchanged; only the spelling of the proxy moved.
        assert mod.__name__.startswith("_shipwright_shared_lib"), mod.__name__
        assert "lib.triage_integrity" not in sys.modules, "the shadowed package import won"
        frags = mod.store_corruption({str(store)!r})
        assert len(frags) == 1, frags
        assert mod.is_triage_record({{"event": "append", "id": "trg-1",
                                     "ts": "t", "source": "s", "severity": "low",
                                     "kind": "bug", "title": "t", "status": "triage"}})
        assert not mod.is_triage_record({{"event": "append"}})
        # The delivery leaf it composes must resolve through the same fallback.
        assert mod.store_facts({str(store)!r}, {str(store)!r},
                               applied_statuses=("triage",))[1] == set()
        print("MODE=triage-integrity-sentinel OK")
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "MODE=triage-integrity-sentinel OK" in result.stdout


def test_the_subprocess_probe_can_fail(tmp_path: Path) -> None:
    """Guard: the tests above are only evidence while the probe still bites.

    If the harness silently stopped running Python, every assertion above would
    pass vacuously on an empty stdout comparison. This proves a failure is visible.
    """
    result = _run("raise SystemExit(7)", tmp_path)
    assert result.returncode == 7
