"""Console output helpers for the verifier CLIs.

A neutral home for ``ensure_utf8_stdout`` so the load-bearing (already
size-capped) ``common.py`` does not have to grow — see the bloat-extraction
recipe: route a shared helper through a NEUTRAL new module rather than
ratcheting an oversize module upward.
"""

from __future__ import annotations

import sys


def ensure_utf8_stdout() -> None:
    """Pin ``sys.stdout`` to UTF-8 regardless of the console codepage.

    ``format_report`` details routinely carry non-ASCII — e.g. ``→`` emitted by
    ``check_architecture_documented`` ("convention → '## Convention Updates'").
    On Windows ``sys.stdout`` defaults to the legacy codepage (cp1252), so
    ``print(format_report(...))`` crashed with ``UnicodeEncodeError`` at the
    first such char — masking the verifier's actual results
    (iterate-2026-06-13-verifier-utf8-stdout). UTF-8 encodes all of Unicode, so
    the strict error handler can't raise.

    Mirrors ``triage_cli._ensure_utf8_stdout`` (PR #182). Call once at a CLI
    ``main()`` entry, BEFORE any stdout write — ``reconfigure`` rejects an
    encoding change after the stream has been written to.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass  # detached/closed stream — let the write surface the error
