"""Does a requirement carry acceptance criteria at all? (Group I — I6)

Pure reader behind I6. Given a spec's text and an FR id, answer whether that
requirement has at least one real acceptance criterion.

**The rule this serves.** ``shared/fr-authoring.md`` §3a: a capability that
cannot be given acceptance criteria a single delivery would satisfy is too broad
and gets divided, and being unable to enumerate what would settle it is the
signal that it names several capabilities at once. Whether a requirement is
*too broad* is a judgement no parser can make. Whether it has **no criteria at
all** is observable, and that is the whole of what this module decides — hence
I6 is advisory, a warning that a human then judges.

**Delegates to ``lib.fr_criteria``** (campaign REQ3.04, sub-iterate R0). This
module used to carry its own walk, because ``spec_parser``'s
``compute_fr_coherence`` (behind ``check_s5_fr_coherence``) recognised only FR
bodies introduced by a ``**Acceptance Criteria:**`` bold label, while the
converged shape both ``/shipwright-project`` and ``/shipwright-adopt`` emit uses
``### FR-XX.YY — Title`` headings with bare bullets — so S5 reported every one
of this repo's own requirements as missing acceptance while each was fully
elaborated. That gap is now closed: ``spec_parser`` falls back to the same
reader this module uses, so all three FR-criteria consumers in this repo (S5,
the cross-layer fold-detection gate, and I6 here) agree on what counts as a
criterion — including the two anchor forms (``### FR-XX.YY — Title`` headings,
``**FR-XX.YY: Name**`` bold labels) and the rule that a ``| FR-XX.YY | … |``
table row is deliberately **not** an anchor: every spec states each id in its
requirements table, so a row that counted would make every requirement
trivially "have criteria". This module keeps its own name and signature —
``has_criteria`` / ``frs_without_criteria`` are I6's own vocabulary — but the
anchor matching, checkbox/marker stripping and placeholder rejection all live
in ``lib.fr_criteria`` now.

Loaded via ``load_shared_lib`` (ADR-045): a bare ``from lib import fr_criteria``
would bind ``sys.modules['lib']`` to the SHARED package for the rest of the
test session, shadowing this plugin's own ``lib`` package (``thresholds.py``).

Pure: no I/O except the one file read in ``frs_without_criteria``.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from scripts.audit.audit_adapters import load_shared_lib

fr_criteria = load_shared_lib("fr_criteria")


def has_criteria(content: str, fr_id: str) -> bool:
    """True when ``fr_id`` has at least one real acceptance criterion in ``content``."""
    return fr_criteria.has_criteria(content, fr_id)


def frs_without_criteria(project_root: Path, rows: Iterable) -> list[str]:
    """Ids among ``rows`` whose OWN spec file gives them no acceptance criteria.

    Judged per spec file, not pooled across the catalogue. Pooling would let an
    elaborated ``FR-01.01`` in one split silently satisfy a bare ``FR-01.01`` in
    another — and while I4 forbids exactly that duplication, I6 must not depend
    on another check having already passed to avoid reporting a false green.

    A spec that cannot be read reports its rows as missing rather than raising:
    Group I is detective-only, and an unreadable spec is a finding, not a crash.
    """
    by_file: dict[str, list] = defaultdict(list)
    for row in rows:
        by_file[row.spec_path].append(row)

    missing: set[str] = set()
    for spec_path, group in by_file.items():
        try:
            content = (project_root / spec_path).read_text(
                encoding="utf-8", errors="ignore",
            )
        except OSError:
            content = ""
        missing.update(r.id for r in group if not has_criteria(content, r.id))
    return sorted(missing)


__all__ = ["frs_without_criteria", "has_criteria"]
