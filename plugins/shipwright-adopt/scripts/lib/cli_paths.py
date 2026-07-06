"""cli_paths — argparse path types that tolerate paste-artifact quotes.

``unquoted_path`` is an argparse ``type=`` callable: it strips a balanced
surrounding quote pair before constructing the :class:`~pathlib.Path`, so a
quoted ``--project-root`` (Explorer "Copy as path" wraps a path in literal
``"..."``; a shell-copied path may carry ``'...'``) resolves to the real
directory instead of a path with a stray quote embedded in it.

This intentionally duplicates the tiny ``strip_surrounding_quotes`` helper from
``shipwright-grade``'s ``normalize_input`` rather than importing a shared copy:
the adopt CLIs must stay importable without ``shared/`` on ``sys.path`` (the
plugin-cache ``../../shared`` delivery is itself the thing a sibling iterate
hardens), and ``shipwright-grade`` ships standalone. Keep the two copies in sync.
Mirrors the WebUI ``normalize-fs-path`` fix (shipwright-webui #195).
"""

from __future__ import annotations

from pathlib import Path

_QUOTES = ("'", '"')


def strip_surrounding_quotes(raw: str) -> str:
    """Trim whitespace and strip one *balanced* surrounding quote pair.

    Only a matching pair of surrounding single or double quotes is removed, and
    only one such pair. A real path never both begins and ends with the same
    quote character, so this is always safe; an inner apostrophe is preserved
    and a lone/mismatched quote is left untouched.
    """
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in _QUOTES:
        s = s[1:-1].strip()
    return s


def unquoted_path(value: str) -> Path:
    """argparse ``type=`` — a :class:`~pathlib.Path` with surrounding quotes removed."""
    return Path(strip_surrounding_quotes(value))
