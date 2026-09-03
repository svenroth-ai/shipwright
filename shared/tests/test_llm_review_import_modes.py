"""`llm_review` must import under BOTH of its live module names (AC-6)
(iterate-2026-08-01-llm-review-truncation-guard).

The module is reached two ways, and both ship:

* bare ``import llm_review`` — shipwright-adopt's Layer-3 ``review_runner``,
  after putting ``shared/scripts/lib`` on ``sys.path``.
* ``from lib.llm_review import …`` — ``shared/scripts/tools/review_assistant_ui_plan.py``,
  after putting ``shared/scripts`` on ``sys.path``.

This matters because the fix added a sibling import to ``llm_review``. A bare
sibling import raises ``ModuleNotFoundError`` under the ``lib.`` name — the
ADR-045 trap: green on the adopt path, broken on the other. Verified empirically
before the import was written, and pinned here so it stays fixed.

Each mode runs in a FRESH, ISOLATED interpreter. Same-process checks are
worthless here: whichever mode ran first populates ``sys.modules`` and
``sys.path``, so the second passes on the first's leftovers and proves nothing.
``-I`` additionally drops inherited ``PYTHONPATH`` and the implicit cwd entry,
so the probe measures the path it was given and nothing else.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_LIB_DIR = _SHARED / "scripts" / "lib"

_IMPORT_PROBE = """
import sys
sys.path.insert(0, {path!r})
{stmt}
print("OK", run_review.__module__)
"""


def _probe_import(path: Path, stmt: str) -> subprocess.CompletedProcess:
    code = textwrap.dedent(_IMPORT_PROBE).format(path=str(path), stmt=stmt)
    return subprocess.run(
        # -I = isolated: ignore PYTHONPATH and the implicit '' cwd entry, so the
        # only importable location is the one the probe inserts.
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(_SHARED),
    )


def test_llm_review_imports_as_a_bare_module():
    """How shipwright-adopt's Layer-3 review_runner loads it."""
    got = _probe_import(_LIB_DIR, "from llm_review import run_review")
    assert got.returncode == 0, got.stderr
    assert got.stdout.startswith("OK llm_review")


def test_llm_review_imports_as_lib_llm_review():
    """How shared/scripts/tools/review_assistant_ui_plan.py:53 loads it."""
    got = _probe_import(_SHARED / "scripts", "from lib.llm_review import run_review")
    assert got.returncode == 0, got.stderr
    assert got.stdout.startswith("OK lib.llm_review")


def test_the_two_modes_resolve_distinct_module_names():
    """Guard against a probe that passes for the wrong reason.

    If both invocations reported the same ``__module__``, one of them would be
    reusing the other's binding rather than exercising its own path — the
    failure mode isolation exists to prevent. Assert they differ.
    """
    bare = _probe_import(_LIB_DIR, "from llm_review import run_review")
    qualified = _probe_import(_SHARED / "scripts", "from lib.llm_review import run_review")

    assert bare.stdout.strip() != qualified.stdout.strip()


def test_external_review_default_legs_imports_qualified_as_the_first_touch():
    """``lib.external_review_default_legs`` must import standalone, package-qualified,
    even when nothing else in the ``external_review`` family has run yet in this process.

    Every OTHER path that reaches this module first imports ``lib.external_review_config``
    (whose own module-level code adds ``shared/scripts/lib`` to ``sys.path`` as a side
    effect), which masks an import-order bug in this module's own try/except fallback: its
    bare imports must list ``external_review_degraded`` FIRST, matching the ``except
    ModuleNotFoundError as exc: if exc.name != "external_review_degraded"`` guard — a
    reordered bare import list whose first entry fails under a DIFFERENT name makes the
    guard re-raise instead of falling through to the ``lib.``-qualified imports below it.
    Reproduced and pinned after PR #672's Tier-3 review caught it by static reading; the
    two general-purpose probes above did not, because they route through
    ``lib.external_review_config`` first.
    """
    code = (
        f"import sys; sys.path.insert(0, {str(_SHARED / 'scripts')!r})\n"
        "from lib.external_review_default_legs import review_codex\n"
        "print('OK', review_codex.__module__)\n"
    )
    got = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True, text=True, timeout=60, cwd=str(_SHARED),
    )
    assert got.returncode == 0, got.stderr
    assert got.stdout.startswith("OK lib.external_review_default_legs")


def test_nested_module_not_found_is_not_mistaken_for_the_sibling(tmp_path):
    """A dependency missing inside the sibling must escape, not trigger fallback."""
    shutil.copy(_LIB_DIR / "llm_review.py", tmp_path)
    (tmp_path / "external_review_degraded.py").write_text(
        "import nested_missing_dependency\n", encoding="utf-8"
    )
    code = (
        f"import sys; sys.path.insert(0, {str(tmp_path)!r}); "
        "\ntry:\n import llm_review\n"
        "except ModuleNotFoundError as exc:\n print(exc.name)\n"
    )
    got = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True, text=True, timeout=60, cwd=str(_SHARED),
    )
    assert got.returncode == 0, got.stderr
    assert got.stdout.strip() == "nested_missing_dependency"
