"""License-resolution sentinels for the SBOM collectors.

Two distinct non-license outcomes — kept apart on purpose so the SBOM can
answer "is this repo license-sound?" instead of "what did the scanner do?":

- ``UNKNOWN_LICENSE`` — the package WAS resolved (a dist-info / lockfile entry
  exists) but declares **no** license. A genuine concern: surfaced in triage
  and in the SBOM doc.
- ``NOT_INSTALLED`` — the package could not be resolved at all (no ``.venv``
  dist-info, no lockfile + ``node_modules`` entry). A property of the *scan
  environment*, not the repo. Never **triaged** (not actionable repo drift).
  But on the SBOM doc it renders ``-`` and (AR-04) is **counted among
  unresolved licenses** in the summary, the pie's ``unknown`` slice, and the
  honest verdict -- so the report never claims "all permissive" while a ``-``
  row remains.

A single home for both constants so resolver (python + npm), collector, and
doc generator agree on the exact strings.
"""

from __future__ import annotations

UNKNOWN_LICENSE = "unknown"
NOT_INSTALLED = "not-installed"
