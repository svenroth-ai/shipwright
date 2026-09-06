"""Sibling-module loader for ``fr_table_reader`` (bloat gate, PR #679).

Split out of ``fr_table_reader.py`` (crossed the 300-line guideline once the
reject accumulator grew a ``raw_digest`` field): this is a distinct concern
from FR-row parsing — it only answers "how does `fr_table_reader` reach its
own siblings under any of the three ways it gets imported", never anything
about table shape. Kept as its own module rather than folded into a more
generic helper because ``_ALLOWED_SIBLINGS`` is `fr_table_reader`'s own
declared precondition, not a reusable one.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SIBLINGS: dict[str, object] = {}

# The complete set of siblings `fr_table_reader` may load. Every call site
# passes a literal, so the dynamic import is safe by inspection today — but
# that is a property of the CALL SITES, while the scanner suppressions sit on
# `sibling` itself, so a future caller threading in argv or config would
# inherit them silently. Declaring the set makes the claim a precondition
# instead of a comment. The reverse direction — no stale entry permitting more
# than the module uses — is pinned in `test_fr_table_reader_load_styles.py`.
_ALLOWED_SIBLINGS = frozenset({
    "requirement_model", "fr_fold_map",
    "_fr_table_cells", "_fr_table_row", "_fr_table_columns",
})


def sibling(name: str, *, package: str):
    """Import a ``shared/scripts/lib`` sibling however the CALLER was loaded.

    Three load styles reach `fr_table_reader` in production (ADR-045): flat
    (``import fr_table_reader`` with ``shared/scripts/lib`` on the path),
    as a package member (``lib.fr_table_reader``, via the collectors'
    ``_lib_loader``), and by file location under a sentinel name (via
    ``audit_adapters.load_shared_lib``, which is how Group I reaches shared
    code). A bare relative import works only in the second; a bare flat import
    only in the first. Resolving per load style is what makes ONE reader usable
    from all five call sites — the alternative is five copies, which is the
    defect `fr_table_reader` removes.

    Resolved EAGERLY, at import time, and never at call time. Under the
    collectors' ``_lib_loader`` `fr_table_reader` is imported while
    ``sys.modules['lib']`` is temporarily bound to SHARED, and that binding is
    restored to the caller's own ``lib`` on the way out — so a lazy
    ``import_module(".requirement_model", "lib")`` would resolve against the
    compliance-local package and raise. Same trap ADR-045 documents; the fix
    is the timing.

    ``package`` is the caller's own ``__package__`` (passed in, not read here)
    — this loader is itself imported via a plain ``from . import`` / flat
    import, so its OWN ``__package__`` says nothing about how `fr_table_reader`
    was loaded.
    """
    if (mod := _SIBLINGS.get(name)) is not None:
        return mod
    if name not in _ALLOWED_SIBLINGS:
        raise ValueError(f"{name!r} is not in _ALLOWED_SIBLINGS")
    if package:
        # Name is constrained to _ALLOWED_SIBLINGS above — first-party module
        # identifiers only, never untrusted input.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        mod = importlib.import_module(f".{name}", package)
    else:
        lib_dir = str(Path(__file__).resolve().parent)
        added = lib_dir not in sys.path
        if added:
            sys.path.insert(0, lib_dir)
        try:
            # First-party hardcoded module identifiers only; no untrusted input.
            # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
            mod = importlib.import_module(name)
        finally:
            if added:
                sys.path.remove(lib_dir)
    _SIBLINGS[name] = mod
    return mod


__all__ = ["sibling"]
