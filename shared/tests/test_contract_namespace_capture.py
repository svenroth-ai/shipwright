"""`shared.contracts.compliance` names its namespace capture out loud.

Iterate-2026-07-27-pytest-root-composition. The contract bootstraps by
prepending the shipwright-compliance plugin root to ``sys.path`` and then
importing ``scripts.lib.data_collector``. That prepend cannot help once
``scripts.lib`` is already bound: a REGULAR sub-package is cached in
``sys.modules`` and never re-resolves against ``sys.path``.

Before this change the operator saw ``ModuleNotFoundError: No module named
'scripts.lib.data_collector'`` -- which points at the compliance plugin,
the one place that is NOT at fault. These tests pin a diagnostic that names
the module that was captured and the directory that captured it.

The repo-root conftest guard covers pytest sessions; this covers every
other process, where no conftest runs.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_INIT = REPO_ROOT / "shared" / "scripts" / "tools" / "__init__.py"


def _run_python(body: str) -> subprocess.CompletedProcess:
    """Run a snippet in a pristine interpreter rooted at the repo."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# --------------------------------------------------------------------------- #
# AC4 -- a captured `scripts.lib` produces a NAMED error
# --------------------------------------------------------------------------- #

_CAPTURE_PREAMBLE = """
    import sys
    from pathlib import Path
    repo = Path.cwd()
    sys.path.insert(0, str(repo))
    # Exactly what pytest's prepend import mode does for shared/tests,
    # because shared/tests/__init__.py exists and shared/__init__.py does not.
    sys.path.insert(0, str(repo / "shared"))
    import scripts.lib          # binds to shared/scripts/lib and CACHES it
    try:
        from shared.contracts import compliance   # noqa: F401
    except ModuleNotFoundError as exc:
        # A SUBCLASS of ImportError, but the exact failure this change
        # exists to replace. Report it distinctly so a regression to the
        # old behaviour cannot masquerade as the new one.
        print("RAISED=ModuleNotFoundError")
        # Single line: the message is multi-line and the reader parses
        # `key=value` per line, so a raw newline would silently truncate it.
        print("MESSAGE=" + str(exc).replace("\\n", " "))
        sys.exit(3)
    except ImportError as exc:
        print("RAISED=ImportError")
        # Single line: the message is multi-line and the reader parses
        # `key=value` per line, so a raw newline would silently truncate it.
        print("MESSAGE=" + str(exc).replace("\\n", " "))
        sys.exit(2)
    except BaseException as exc:            # noqa: BLE001 - diagnostic only
        print("RAISED=" + type(exc).__name__)
        # Single line: the message is multi-line and the reader parses
        # `key=value` per line, so a raw newline would silently truncate it.
        print("MESSAGE=" + str(exc).replace("\\n", " "))
        sys.exit(4)
    print("RAISED=none")
    sys.exit(0)
"""


def _capture_outcome() -> tuple[int, str, str]:
    """Return ``(exit_code, exception_type, message)`` from the capture probe."""
    result = _run_python(_CAPTURE_PREAMBLE)
    fields = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line and line.startswith(("RAISED=", "MESSAGE="))
    )
    return result.returncode, fields.get("RAISED", ""), fields.get("MESSAGE", "")


def test_captured_scripts_lib_raises_named_importerror() -> None:
    code, raised, message = _capture_outcome()
    assert raised == "ImportError", (
        "AC4 requires an ImportError that NAMES the capture. "
        f"Got {raised or '<nothing>'} (exit {code}): {message}"
    )
    assert "scripts.lib" in message, message
    assert "shared" in message and "scripts" in message, (
        f"The error must name the directory that captured the module.\n{message}"
    )


def test_capture_error_does_not_blame_the_compliance_plugin() -> None:
    """The bare ModuleNotFoundError pointed at the one blameless place."""
    _, raised, message = _capture_outcome()
    assert raised != "ModuleNotFoundError", (
        "This is the pre-change behaviour: an error naming the compliance "
        f"plugin's missing symbol rather than the capture.\n{message}"
    )
    assert "No module named 'scripts.lib.data_collector'" not in message, message


def test_capture_error_explains_that_syspath_order_cannot_fix_it() -> None:
    """Without this, the next reader retries the prepend that already ran."""
    _, _, message = _capture_outcome()
    assert "sys.path" in message, message
    assert "cached" in message.lower() or "already" in message.lower(), message


# --------------------------------------------------------------------------- #
# AC4 (negative) -- an uncaptured process is unchanged
# --------------------------------------------------------------------------- #


def test_clean_process_imports_contract_normally() -> None:
    result = _run_python(
        """
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path.cwd()))
        from shared.contracts import compliance
        assert compliance.PHASE_REPORTS
        assert compliance.collect_all
        print("OK")
        """
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "OK" in result.stdout


# --------------------------------------------------------------------------- #
# AC5 -- the shared tools package no longer documents a false rule
# --------------------------------------------------------------------------- #


def test_tools_init_docstring_has_no_false_ordering_claim() -> None:
    """The old docstring asserted two things that cannot both be true.

    It claimed Python "prefers a regular package over a namespace package
    regardless of sys.path order" AND that adding a regular ``__init__``
    "lets plain sys.path ordering resolve the conflict". Once both
    candidates are regular packages, sys.path order is all that is left --
    and once one is cached, not even that applies.
    """
    text = TOOLS_INIT.read_text(encoding="utf-8")
    assert "lets plain sys.path ordering resolve the conflict" not in text, (
        "The self-contradictory claim is still present; it sends the next "
        "reader looking for a sys.path fix that cannot exist."
    )
