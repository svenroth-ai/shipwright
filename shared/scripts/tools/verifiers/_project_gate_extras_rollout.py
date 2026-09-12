"""FR-01.02 #5 (:func:`criteria_free_of_implementation_detail`) and #10
(:func:`no_empty_split`) — split out of ``_project_gate_extras.py`` at the
300-LOC guideline the moment internal plan review's rollout-transition
revisions grew that file past cap (same precedent as every other split in
this gate family: ``_project_gate_wiring.py``/``_project_gate_manifest.py``,
``_project_gate_rollout.py``/``_project_gate_rollout_snapshot.py``).

* :func:`criteria_free_of_implementation_detail` — **#5** "No
  symbol/path/ADR/verb in the sentence." ``fr_hygiene_detectors.violations``
  (I1) already exists but is applied only to the FR Name/Description
  (``group_i`` advisory, ``check_fr_hygiene_on_touched_rows`` for
  /shipwright-iterate's own touched rows) — never to the acceptance
  CRITERIA text, and never as a block on /shipwright-project's own Step 8.
  Reuses the identical detector against every active FR's criteria.
  **Rollout-transition-aware, 2026-09-12 (`trg-9583d3a8`):** an optional
  ``rollout`` snapshot (``_project_gate_rollout_snapshot.RolloutSnapshot``)
  downgrades a hit to advisory, PER VIOLATING CRITERION, when that exact
  criterion string (post-parser) already existed on the SAME FR id/title at
  the gate's own rollout instant — see ``_project_gate_grace.py`` for the
  identity/membership rules and ``_project_gate_rollout.py`` for the
  rollout-resolution rationale.

  **Known, disclosed residual gap (internal plan review, opus, HIGH,
  `trg-9583d3a8` follow-up):** this transition rule only helps a project
  whose spec.md content already existed before the gate's own rollout
  instant. A `/shipwright-adopt` onboarding run AFTER that instant gets NO
  grace — and `plugins/shipwright-adopt/scripts/lib/test_acceptance_miner.py`
  mines `describe`/`it`/`test_*` labels straight from the target repo's own
  test files into acceptance-criteria bullets, which routinely carry exactly
  the code-symbol/HTTP-verb shapes this gate bans (measured directly against
  this gate: `"UserProfileCard: renders the avatar..."` and
  `"GET /api/users: returns 200..."` both trip `violations()`). This iterate
  does not fix that — it is a producer-vs-gate conflict for FUTURE
  onboardings, a different unit of work than grandfathering PRE-EXISTING
  content — and is tracked separately (see the ADR's Out of Scope section
  and the new triage card it mints).
* :func:`no_empty_split` — **#10** "Divided into cohesive parts, or
  single-unit." ``split-heuristics.md`` states the rule; nothing checked
  that a declared split actually carries at least one requirement. A split
  with zero active FR rows is not a cohesive part of anything.
  **Rollout-transition-aware, 2026-09-12 (`trg-9583d3a8`):** an optional
  ``rollout`` snapshot downgrades a hit to advisory when the split was
  already DECLARED in the project's own manifest (not merely "some file
  happens to sit at that path" — see ``_project_gate_grace.py``) at the
  gate's own rollout instant, with zero active FR rows then too.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import fr_criteria  # noqa: E402
from lib import fr_hygiene_detectors  # noqa: E402
from lib import fr_table_reader  # noqa: E402

from . import _project_gate_grace as _grace  # noqa: E402
from . import _project_gate_rollout as _rollout  # noqa: E402
from ._project_gate_extras import GateResult  # noqa: E402
from ._project_gate_rollout_snapshot import RolloutSnapshot  # noqa: E402

__all__ = [
    "criteria_free_of_implementation_detail",
    "no_empty_split",
]


# --------------------------------------------------------------------------- #
# #5 — acceptance criteria free of implementation detail
# --------------------------------------------------------------------------- #


def criteria_free_of_implementation_detail(
    spec_texts: dict[str, str],
    *,
    rollout: RolloutSnapshot | None = None,
) -> GateResult:
    hard_hits: list[str] = []
    graced_hits: list[str] = []
    for path, text in spec_texts.items():
        for row in fr_table_reader.read_active_fr_rows(text):
            # fr_criteria.py: legacy label-paragraph exception
            criteria = fr_criteria.criteria_for(text, row.id, strict=False)
            row_violations = [
                (criterion, found)
                for criterion in criteria
                if (found := fr_hygiene_detectors.violations(criterion))
            ]
            if not row_violations:
                continue
            # Per-criterion grace, computed once per row (identity/parsing is
            # the expensive part) — see _project_gate_grace.py.
            graced_criteria = _grace.graced_criteria_for_row(rollout, path, row)
            for criterion, found in row_violations:
                hit = f"{path}:{row.id} ({'/'.join(found)})"
                if criterion in graced_criteria:
                    graced_hits.append(hit)
                else:
                    hard_hits.append(hit)
    if hard_hits:
        shown = hard_hits[:5]
        suffix = f" (+{len(hard_hits) - 5} more)" if len(hard_hits) > 5 else ""
        detail = (
            f"{len(hard_hits)} acceptance criterion/criteria carry implementation "
            f"detail: {'; '.join(shown)}{suffix}"
        )
        if graced_hits:
            graced_shown = graced_hits[:5]
            graced_suffix = (
                f" (+{len(graced_hits) - 5} more)" if len(graced_hits) > 5 else ""
            )
            detail += (
                f"; {len(graced_hits)} other hit(s) predate the FR-01.02 #5 gate's own "
                f"rollout ({_rollout.GATE_ROLLOUT_AT_ISO}), unchanged since — granted "
                f"transition grace: {'; '.join(graced_shown)}{graced_suffix}"
            )
        return GateResult(False, detail)
    if graced_hits:
        shown = graced_hits[:5]
        suffix = f" (+{len(graced_hits) - 5} more)" if len(graced_hits) > 5 else ""
        return GateResult(
            False,
            f"{len(graced_hits)} acceptance criterion/criteria carry implementation detail, "
            f"but predate the FR-01.02 #5 gate's own rollout ({_rollout.GATE_ROLLOUT_AT_ISO}), "
            f"unchanged since — granted transition grace: {'; '.join(shown)}{suffix}",
            severity="warning", strict_exempt=True,
        )
    return GateResult(
        True,
        "no acceptance criterion carries a code symbol, file path, ADR "
        "number, iterate slug, or HTTP verb",
    )


# --------------------------------------------------------------------------- #
# #10 — no split with zero active requirements
# --------------------------------------------------------------------------- #


def no_empty_split(
    spec_texts: dict[str, str],
    *,
    rollout: RolloutSnapshot | None = None,
) -> GateResult:
    hard: list[str] = []
    graced: list[str] = []
    for path, text in spec_texts.items():
        if fr_table_reader.read_active_fr_rows(text):
            continue
        name = _grace.split_name_from_path(path)
        if _grace.split_predates_rollout(rollout, path, name):
            graced.append(path)
        else:
            hard.append(path)
    hard.sort()
    graced.sort()
    if hard:
        detail = (
            f"split(s) with zero active FR rows — not a cohesive part of "
            f"anything: {hard}"
        )
        if graced:
            detail += (
                f"; {len(graced)} other empty split(s) already declared+empty "
                f"at-or-before the FR-01.02 #10 gate's own rollout "
                f"({_rollout.GATE_ROLLOUT_AT_ISO}) — granted transition grace: {graced}"
            )
        return GateResult(False, detail)
    if graced:
        return GateResult(
            False,
            f"{len(graced)} split(s) with zero active FR rows, but already "
            f"declared+empty at-or-before the FR-01.02 #10 gate's own rollout "
            f"({_rollout.GATE_ROLLOUT_AT_ISO}) — granted transition grace: {graced}",
            severity="warning", strict_exempt=True,
        )
    return GateResult(
        True, f"{len(spec_texts)} split(s), each with at least one active FR row",
    )
