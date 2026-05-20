"""Markdown table cell escaping.

Lives at ``shared/scripts/`` (top-level, NOT under ``shared/scripts/lib/``)
per ADR-045: cross-cutting helpers used from both ``shared/tests/`` and
``plugins/*/tests/`` must live outside the ``lib/`` namespace to avoid
the regular-package vs namespace-package collision.

Background
----------
The build dashboard (``shared/scripts/tools/update_build_dashboard.py``)
and the compliance reports (``plugins/shipwright-compliance/scripts/lib/
{rtm_generator,test_evidence,change_history}.py``) render iterate / build
events directly into GitHub-flavored markdown tables with f-string row
templates:

    | {intent} | {desc} | {tests} | {commit} | {frs} | {date} |

A literal ``|`` inside any of those values splits the row into one more
column than the header, shifting every subsequent cell by one. Empirically
observed in the shipwright-webui repo: an event with description
``"... env-flag (local|tailscale|open) unifies ..."`` moved Tests / Commit
/ FRs / Date one column to the right. The workaround there was to replace
the pipes in the producer's JSONL with slashes, but the renderer should be
robust on its own.

Newlines have the same row-breaking effect for the entire row (a literal
``\\n`` ends the row early, dropping every subsequent cell).
"""

from __future__ import annotations

# Order matters. Backslash MUST be escaped FIRST, otherwise the later
# ``|`` → ``\\|`` pass would itself double the backslash. After the
# backslash pass, every backslash already in the input has become
# ``\\\\``, so the pipe pass adding ``\\|`` is unambiguous.
_TABLE_CELL_TRANSFORMS: tuple[tuple[str, str], ...] = (
    ("\\", "\\\\"),
    ("|", "\\|"),
    ("\r\n", " "),
    ("\r", " "),
    ("\n", " "),
)


def escape_cell(value: object) -> str:
    """Escape ``value`` for safe rendering in a Markdown table cell.

    Applies the minimum set of substitutions that prevent the value from
    breaking the surrounding ``| ... | ... |`` row layout:

    * ``\\`` → ``\\\\`` (so the subsequent ``|`` → ``\\|`` substitution
      cannot collide with an upstream backslash)
    * ``|`` → ``\\|`` (the standard GFM escape — viewers render the
      pipe but parsers no longer treat it as a cell separator)
    * any of ``\\r\\n`` / ``\\r`` / ``\\n`` → space (collapses multi-line
      content onto the single physical line a table cell occupies)

    ``None`` becomes ``""``. Non-string scalars are coerced via ``str()``
    so callers can pass ints, bools, etc. without an extra wrap.

    Leading and trailing whitespace is preserved — callers can rely on
    ``f"| {escape_cell(x)} |"`` providing exactly one separator space.
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    for src, dst in _TABLE_CELL_TRANSFORMS:
        text = text.replace(src, dst)
    return text


__all__ = ["escape_cell"]
