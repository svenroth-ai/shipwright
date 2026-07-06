"""normalize_input — sanitise a user-supplied target at the grader seam.

A single helper, ``strip_surrounding_quotes``, applied once at ``open_target``
(the input seam the grader drives — CLI, the ``/shipwright-grade`` command, and
the future npx CLI all flow through it). It removes the classic *paste artifact*
where a filesystem path or repo URL arrives wrapped in a balanced pair of
surrounding quotes:

- Windows Explorer "Copy as path" copies ``C:\\Users\\me\\repo`` as ``"C:\\Users\\me\\repo"``;
- pasting a URL out of a Markdown/README code span can carry ``'…'`` / ``"…"``.

Without this, the stray leading quote makes ``resolve_target``'s ``Path`` probe
and ``clone``'s scheme allowlist reject an otherwise-valid target with a hard
error. This mirrors the WebUI ``normalize-fs-path`` fix (shipwright-webui #195);
the downstream validation/escaping is deliberately left unchanged — only the
value handed to it is cleaned.
"""

from __future__ import annotations

_QUOTES = ("'", '"')


def strip_surrounding_quotes(raw: str) -> str:
    """Trim whitespace and strip one *balanced* surrounding quote pair.

    Only a matching pair of surrounding single or double quotes is removed, and
    only one such pair. A real filesystem path or URL never both begins *and*
    ends with the same quote character, so stripping a balanced pair is always
    safe; an inner apostrophe (``o'brien``) is preserved, and a lone or
    mismatched quote is left untouched. Non-``str`` input is returned unchanged
    (defensive — the seam should always pass a string).
    """
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in _QUOTES:
        s = s[1:-1].strip()
    return s
