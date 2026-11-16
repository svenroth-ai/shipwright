"""The sub-iterate spec a campaign planner writes for one unit.

Split from ``tools/campaign_init.py`` (on the bloat baseline at its cap). The one
non-obvious part is the optional ``Complexity:`` line: the operator's declared
tier for the unit, read back by ``declared_complexity`` as a classification floor
(``classify_complexity`` Stage 1 and the Step 3.4 re-check may raise it, never
lower it). Absent when the planner declares none, so a unit without one behaves
exactly as before.
"""

from __future__ import annotations

from declared_complexity import validate_declared


def unit_complexity(si: dict) -> str | None:
    """The validated declared level of one sub-iterate dict, or ``None``.

    Raises ``ValueError`` naming the unit for an unknown level, before anything
    is written.
    """
    if not isinstance(si, dict) or si.get("complexity") is None:
        return None
    try:
        level = validate_declared(si["complexity"])
        if level == "large":
            raise ValueError("'large' cannot run as a campaign unit (the runner stops at large); split the unit")
        return level
    except ValueError as exc:
        raise ValueError(f"sub-iterate {si.get('id')!r}: {exc}") from exc


def render_unit_spec(si: dict) -> str:
    """Markdown body of ``sub-iterates/<id>-<slug>.md``."""
    level = unit_complexity(si)
    declared = f"\nComplexity: {level}\n" if level else ""
    return f"""# Sub-Iterate: {si['id']} — {si.get('title', si['slug'])}
{declared}
## Scope

{si.get('scope', 'TBD')}

## Acceptance Criteria

{si.get('acceptance_criteria', '- [ ] TBD')}
"""
