"""External review prompt loading (shared).

Loads the iterate_reviewer prompts from ``shared/prompts/iterate_reviewer/``.
Plan-mode prompts (``plan_reviewer/``) intentionally remain in the plan plugin —
they're plan-specific.

Single source: no fallback to plugin-local paths. If the iterate_reviewer
directory is missing, ``load_iterate_review_prompts`` returns ``("", "")``
(graceful degradation) instead of silently falling through to a stale copy.
"""

from __future__ import annotations

from pathlib import Path

# Default shared prompts root: shared/prompts/
# parents[0]=lib, [1]=scripts, [2]=shared, then prompts/.
_DEFAULT_PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def _load(prompts_root: Path, name: str, file: str) -> str:
    """Read ``prompts_root / name / file`` (or ``file.md`` fallback)."""
    path = prompts_root / name / file
    if not path.exists():
        path = path.with_suffix(".md")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_iterate_review_prompts(
    prompts_root: Path | str | None = None,
) -> tuple[str, str]:
    """Load (system, user) prompts for iterate-mode external review.

    Reads exclusively from ``<prompts_root>/iterate_reviewer/{system,user}``.
    Defaults to ``shared/prompts/`` when ``prompts_root`` is None.

    Returns ``("", "")`` if the directory or files don't exist.
    """
    root = Path(prompts_root) if prompts_root is not None else _DEFAULT_PROMPTS_ROOT
    return (
        _load(root, "iterate_reviewer", "system"),
        _load(root, "iterate_reviewer", "user"),
    )


def load_plan_review_prompts(plugin_root: Path | str) -> tuple[str, str]:
    """Load (system, user) prompts for plan-mode external review.

    Plan-mode prompts stay plugin-local — they're plan-specific. Reads from
    ``<plugin_root>/prompts/plan_reviewer/{system,user}``.

    Returns ``("", "")`` if the directory or files don't exist.
    """
    root = Path(plugin_root) / "prompts"
    return (
        _load(root, "plan_reviewer", "system"),
        _load(root, "plan_reviewer", "user"),
    )
