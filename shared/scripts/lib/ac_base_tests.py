"""Is an acceptance criterion already named by a test file that exists at the merge-base?

A behaviour-preserving refactor (``unchanged``) leaves the promise tests untouched, so the diff has no ADDED line naming the
AC; the tests that guard it were written earlier. This looks at the base tree (one ``git grep``) so such an AC is not
reported as untested. A ``restore`` is different - the fix must come with a test - and does not use this. Stdlib plus
:mod:`lib.ac_surface`.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.ac_surface import is_test_path, run_git

__all__ = ["ac_pattern", "named_in_base_tests"]


def ac_pattern(ac: str) -> re.Pattern[str]:
    """``FR-01.03.AC05`` or ``FR-01.03/AC05`` as a whole id: ``AC05`` does not match inside ``AC050``."""
    return re.compile("(?:" + "|".join(re.escape(f) for f in (ac, ac.replace(".AC", "/AC"))) + ")(?![0-9])")


def named_in_base_tests(project_root: str | Path, base: str, ac: str) -> bool:
    """True when a test file at ``base`` contains ``FR-01.03.AC05`` or ``FR-01.03/AC05``; false on no match or any git failure."""
    if not ac or not base:
        return False
    args = [a for form in (ac, ac.replace(".AC", "/AC")) for a in ("-e", form)]
    try:  # git does the cheap substring search; the whole-id check (no trailing digit) is made here, line by line
        out = run_git(project_root, "grep", "-n", "-F", *args, base, "--").decode("utf-8", "replace")
    except RuntimeError:  # git grep exits 1 when nothing matches
        return False
    pat = ac_pattern(ac)
    for line in out.splitlines():
        parts = line.split(":", 3)  # <ref>:<path>:<line number>:<text>
        if len(parts) == 4 and is_test_path(parts[1]) and pat.search(parts[3]):
            return True
    return False
