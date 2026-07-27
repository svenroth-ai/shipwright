"""External review prompt loading (shared).

Three review modes share this module:

- ``load_iterate_review_prompts`` reads ``shared/prompts/iterate_reviewer/``
- ``load_code_review_prompts`` reads ``shared/prompts/code_reviewer/``
- ``load_plan_review_prompts`` reads ``<plugin_root>/prompts/plan_reviewer/``
  (plan-mode prompts intentionally stay plugin-local — they're plan-specific)

Single source per shared mode: no fallback to plugin-local paths. If the
directory is missing, the function returns ``("", "")`` (graceful
degradation). The CLI applies inline default prompts in that case.
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


def load_code_review_prompts(
    prompts_root: Path | str | None = None,
) -> tuple[str, str]:
    """Load (system, user) prompts for code-review-mode external review.

    Reads exclusively from ``<prompts_root>/code_reviewer/{system,user}``.
    Defaults to ``shared/prompts/`` when ``prompts_root`` is None.

    The user prompt template uses ``{DIFF}`` (not ``{PLAN}``) and ``{SPEC}``
    placeholders — both are substituted by the CLI before the provider call.

    Returns ``("", "")`` if the directory or files don't exist.
    """
    root = Path(prompts_root) if prompts_root is not None else _DEFAULT_PROMPTS_ROOT
    return (
        _load(root, "code_reviewer", "system"),
        _load(root, "code_reviewer", "user"),
    )


# ---------------------------------------------------------------------------
# Inline fallbacks — used when a prompt directory is missing entirely.
#
# These live here rather than inline in external_review.py so the defaults sit
# beside the loaders they back up (and so the CLI stays under its size
# baseline). Each carries the same VERDICT_INSTRUCTION as the on-disk prompt:
# the verdict is what makes two reviewers comparable, so a run that fell back
# to a default prompt must not silently lose it.
# ---------------------------------------------------------------------------

VERDICT_INSTRUCTION = (
    "\n\nEnd your reply with exactly one line, and nothing after it:\n"
    "SHIPWRIGHT_VERDICT: approve|revise|reject\n"
    "Use `approve` when the work is sound and any findings are refinements, "
    "`revise` when it works but needs specific changes first, and `reject` "
    "when the approach itself is wrong. Write the line exactly once — do not "
    "repeat or quote it elsewhere in your reply."
)

_DEFAULT_SYSTEM = {
    "iterate": (
        "You are a senior software architect reviewing an implementation approach "
        "for a single change to an existing application."
    ),
    "code": (
        "You are a senior software engineer auditing a code change against its "
        "specification. Focus on real defects (correctness, security, regressions, "
        "spec gaps, edge cases). Skip style and naming nits."
    ),
    "plan": "You are a senior software architect reviewing an implementation plan.",
}

_DEFAULT_USER = {
    "iterate": (
        "Review this implementation approach for a change to an existing application.\n\n"
        "## Change Specification:\n{SPEC}\n\n## Implementation Approach:\n{PLAN}\n\n"
        "Focus on: approach soundness, risks to existing functionality, "
        "missing dependencies, edge cases, and security concerns."
    ),
    "code": (
        "Review this code change against its specification.\n\n"
        "## Specification:\n{SPEC}\n\n## Code Diff:\n```diff\n{DIFF}\n```\n\n"
        "Identify concrete defects: spec gaps, correctness bugs, security issues, "
        "test quality, regressions, and unhandled edge cases. "
        "Skip style and naming nits."
    ),
    "plan": (
        "Review this implementation plan for a project.\n\n"
        "## Spec:\n{SPEC}\n\n## Plan:\n{PLAN}\n\n"
        "Identify: security issues, performance concerns, architecture problems, "
        "missing features, and edge cases not handled."
    ),
}


def default_review_prompts(mode: str) -> tuple[str, str]:
    """Inline (system, user) fallbacks for ``mode`` (plan | iterate | code)."""
    key = mode if mode in _DEFAULT_SYSTEM else "plan"
    return _DEFAULT_SYSTEM[key] + VERDICT_INSTRUCTION, _DEFAULT_USER[key]
