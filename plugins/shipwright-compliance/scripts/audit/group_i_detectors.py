"""Group I's own vocabulary for the I1/I2/I3 prose detectors.

**Delegates to ``lib.fr_hygiene_detectors``** (iterate-2026-09-06-fr-hygiene-touched-rows),
the same move ``group_i_criteria.py`` already made for I6's criteria reader: a
second consumer — the diff-scoped, non-dodgeable F11 gate
(``shared/scripts/tools/verifiers/fr_hygiene.py``) — needs the identical
name/description hygiene vocabulary Group I's advisory checks use, and an F11
verifier must never cross-plugin-import this plugin's own ``scripts.audit``
package. This module keeps its own name and signature —
``violations``/``name_violations``/``description_violations``/``is_fold_candidate``
are Group I's own vocabulary — but the regexes and detection logic now live in
the shared module.

Loaded via ``load_shared_lib`` (ADR-045): a bare ``from lib import
fr_hygiene_detectors`` would bind ``sys.modules['lib']`` to the SHARED package
for the rest of the test session, shadowing this plugin's own ``lib`` package
(``thresholds.py``).

Pure: no I/O.
"""

from __future__ import annotations

from scripts.audit.audit_adapters import load_shared_lib

_detectors = load_shared_lib("fr_hygiene_detectors")


def violations(text: str) -> list[str]:
    """Kinds of implementation detail present in ``text`` (empty = clean)."""
    return _detectors.violations(text)


def name_violations(name: str) -> list[str]:
    """Implementation detail leaking into an FR *name* (§5)."""
    return _detectors.name_violations(name)


def description_violations(description: str) -> list[str]:
    """Implementation detail leaking into an FR *description* (§1)."""
    return _detectors.description_violations(description)


def is_fold_candidate(description: str) -> bool:
    """True when a row describes a change to another FR, not a capability (§3)."""
    return _detectors.is_fold_candidate(description)
