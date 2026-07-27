"""The requirement write-back declaration — one mechanism, two call sites.

The change workflow (``/shipwright-iterate``) already declares a requirement
impact per change and refuses to finish unless a requirements file was touched
or a one-line reason was given for touching none. Two phases had no equivalent,
and both are places where what is learned about the product must reach the
requirements rather than staying where it was learned:

* **design** — a feedback round writes back *pointers* (which screen stands for
  which requirement) but never *substance*. When a round changed what a screen
  or flow **does**, the requirement kept describing the older intent.
* **build** — when the approved mockup and the section description contradict
  each other, two criteria made the case unsatisfiable either way, so whichever
  the builder followed won silently. And "nothing outside the section", read
  literally, made a section that must touch something shared unbuildable.

This module is the **rule**: vocabulary, well-formedness, and the touch
predicate over a path list somebody else obtained. Where those paths come from is
a separate and load-bearing question — the CLI
(``tools/record_requirement_impact.py``) derives them from git and nothing else,
because a declaration that could name its own evidence would check nothing.

Where a declaration is stored and how it is read back lives in
:mod:`lib.requirement_impact_store`, so each side stays inside the 300-line
limit and the rule stays filesystem-free.

Vocabulary is imported from :mod:`lib.fr_classification` rather than restated, so
this declaration can never drift from the ``spec_impact`` gate it is modelled on.

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from lib.fr_classification import (
    SPEC_IMPACT_VALUES,
    is_behavior_affecting,
    is_valid_none_reason,
)

#: Canonical planning root, kept as one full literal rather than assembled from
#: segments: the artifact-path-canon lint matches the canonical string, and a
#: tuple of parts reads to it as a bare legacy reference. Same reasoning as
#: ``lib.fr_gates._PLANNING``.
PLANNING_ROOT = ".shipwright/planning"

#: The two phases that carry the declaration. ``iterate`` is deliberately absent
#: — it has its own, older gate (``record_event`` ``--spec-impact``) and folding
#: it in here would mean two write paths for one rule.
PHASE_VALUES: tuple[str, ...] = ("design", "build")

#: An FR id, anchored. Digit bounds match ``verifiers.plan_checks._FR_REF_RE``.
#: Anchoring is the point: the older FR gates accepted any non-empty string, so
#: a declaration could "name an FR" without naming one.
_FR_ID_RE = re.compile(r"^FR-\d{1,3}\.\d{1,3}$")

_ABS_WINDOWS_RE = re.compile(r"^[A-Za-z]:/")


def to_repo_relative_posix(path) -> str:
    """Normalize to a repo-relative POSIX string. Non-strings yield ``""``.

    Shared by every consumer that compares a declared path against a git-derived
    one; the two arrive with different separators and prefixes, and a mismatch
    there produces false failures rather than real ones.

    **Lossy on purpose.** Backslash and surrounding whitespace are legal in POSIX
    filenames, so a path using either is mangled here. That trade is taken
    knowingly: Windows separators are overwhelmingly the common case in this
    repo's inputs, and such filenames do not occur in the artifacts these
    consumers compare.
    """
    if not isinstance(path, str):
        return ""
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def is_requirement_spec(path) -> bool:
    """True iff ``path`` is a requirements file — ``.shipwright/planning/<split>/spec.md``.

    A *split* directory is required: ``.shipwright/planning/spec.md`` is not one,
    and neither is an iterate spec under ``.shipwright/planning/iterate/``, which
    is planning scratch for a single change rather than the requirement itself.
    Accepts Windows separators and a leading ``./`` because callers hand us paths
    from git, from prompts, and from operators.
    """
    text = to_repo_relative_posix(path)
    if not text.startswith(f"{PLANNING_ROOT}/") or not text.endswith("/spec.md"):
        return False
    # Strip the root and the trailing "/spec.md"; what remains must be a
    # non-empty directory path that is not the iterate scratch directory.
    middle = text[len(PLANNING_ROOT) + 1: -len("/spec.md")]
    if not middle:
        return False
    return middle.split("/", 1)[0] != "iterate"


def declaration_error(*, run_id, phase, scope, impact, reason, frs,
                      extras=None) -> dict | None:
    """Return an error dict if the declaration is malformed, else ``None``.

    Order matters: identity first (a record that cannot be filed is not worth
    validating), then vocabulary, then the two rules that carry the meaning —
    ``none`` costs a one-line reason, and a behaviour-affecting impact must name
    the requirement it affects.
    """
    if not isinstance(run_id, str) or not run_id.strip():
        return {
            "error": "requirement_impact_invalid_run_id",
            "detail": "--run-id must be a non-empty string identifying this run.",
        }
    if phase not in PHASE_VALUES:
        return {
            "error": "requirement_impact_invalid_phase",
            "detail": f"--phase must be one of {list(PHASE_VALUES)}, got {phase!r}.",
        }
    if not isinstance(scope, str) or not scope.strip():
        return {
            "error": "requirement_impact_invalid_scope",
            "detail": (
                "--scope must name the unit that declared this impact — a design "
                "round (e.g. 'round-2') or a build section (e.g. '01-auth')."
            ),
        }

    normalized_impact = str(impact or "").strip().lower()
    if normalized_impact not in SPEC_IMPACT_VALUES:
        return {
            "error": "requirement_impact_invalid_impact",
            "detail": (
                f"--impact must be one of {list(SPEC_IMPACT_VALUES)}, got {impact!r}."
            ),
        }

    fr_error = _fr_error(normalized_impact, frs)
    if fr_error is not None:
        return fr_error
    if not is_behavior_affecting(normalized_impact) and not is_valid_none_reason(reason):
        return {
            "error": "requirement_impact_none_requires_reason",
            "detail": (
                "--impact none must be justified with a one-line --reason "
                "(non-empty, single line, max 280 chars). 'none' is a "
                "classification, not a default."
            ),
        }

    if extras is not None:
        try:
            normalize_extras(extras)
        except ValueError as exc:
            return {"error": "requirement_impact_invalid_extra", "detail": str(exc)}
    return None


def _fr_error(normalized_impact: str, frs) -> dict | None:
    """The behaviour-affecting branch: an FR must be named, and be an FR id."""
    if not is_behavior_affecting(normalized_impact):
        return None
    fr_list = list(frs or [])
    if not fr_list:
        return {
            "error": "requirement_impact_requires_fr",
            "detail": (
                f"--impact {normalized_impact} says this changed what the product "
                "does, so it must name the requirement(s) it changed via --fr. "
                "Use --impact none with --reason if the change was appearance-only."
            ),
        }
    for fr in fr_list:
        if not isinstance(fr, str) or not _FR_ID_RE.match(fr):
            return {
                "error": "requirement_impact_malformed_fr",
                "detail": (
                    f"--fr {fr!r} is not an FR id (expected FR-<split>.<nn>, "
                    "e.g. FR-01.04). An id that names nothing cannot be traced."
                ),
            }
    return None


def touch_error(*, impact, changed_paths) -> dict | None:
    """Return an error dict if a behaviour-affecting impact touched no spec.

    ``changed_paths=None`` means *the evidence was unobtainable* (no git, no
    repository) and skips the check; an empty **list** means git answered and
    nothing qualified, which fails. Fail-open on *unavailable* is deliberately
    not fail-open on *unknown* — the same distinction ``fr_gates`` draws.
    """
    if not is_behavior_affecting(impact):
        return None
    if changed_paths is None:
        return None
    if any(is_requirement_spec(p) for p in changed_paths):
        return None
    return {
        "error": "requirement_impact_no_spec_touched",
        "detail": (
            f"--impact {str(impact).strip().lower()} declares the requirements "
            f"changed, but no {PLANNING_ROOT}/<split>/spec.md was touched. Correct "
            "the requirement, or declare --impact none with a --reason."
        ),
    }


def check_declaration(*, run_id, phase, scope, impact, reason, frs,
                      extras=None, changed_paths=None) -> dict | None:
    """Both checks, in order, first error wins. The single entry point.

    Callers never get the two separately: a write path that wired up one and
    forgot the other is the exact bypass ``fr_gates.run_fr_gates`` exists to
    prevent.
    """
    return (
        declaration_error(run_id=run_id, phase=phase, scope=scope, impact=impact,
                          reason=reason, frs=frs, extras=extras)
        or touch_error(impact=impact, changed_paths=changed_paths)
    )


def normalize_extras(extras) -> list[dict]:
    """Validate + normalize part (3)'s attributed extras to ``[{path, reason}]``.

    An extra is a file the section had to touch that its own plan did not list —
    permitted, but only as *the smallest change it needs*, and only when recorded
    as belonging to that section. The reason is therefore mandatory: an
    unexplained extra is indistinguishable from the unrequested work the rule
    forbids.

    Accepts ``"path=reason"`` strings (the CLI form) and ``{"path", "reason"}``
    dicts. Paths are normalized to repo-relative POSIX and de-duplicated
    first-wins. Raises ``ValueError`` on anything malformed so a corrupt record
    surfaces at the write boundary rather than on disk.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for raw in list(extras or []):
        path, reason = _split_extra(raw)
        norm = to_repo_relative_posix(path)
        if not norm:
            raise ValueError(f"attributed extra {raw!r} has no path")
        if norm.startswith("/") or _ABS_WINDOWS_RE.match(norm):
            raise ValueError(
                f"attributed extra path {norm!r} must be relative to the project root"
            )
        # Any ``..`` segment, not just a leading one: ``src/../../etc/passwd``
        # escapes just as surely, and a prefix-only guard would make the
        # "root-confined" claim false for the interesting case.
        if ".." in PurePosixPath(norm).parts:
            raise ValueError(f"attributed extra path {norm!r} escapes the project root")
        if not is_valid_none_reason(reason):
            raise ValueError(
                f"attributed extra {norm!r} needs a one-line reason "
                "(non-empty, single line, max 280 chars)"
            )
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"path": norm, "reason": reason.strip()})
    return out


def _split_extra(raw) -> tuple[object, object]:
    """Accept the CLI ``path=reason`` form and the structured dict form."""
    if isinstance(raw, dict):
        return raw.get("path"), raw.get("reason")
    if isinstance(raw, str):
        path, sep, reason = raw.partition("=")
        if not sep:
            raise ValueError(
                f"attributed extra {raw!r} has no reason — use "
                "'path=why this section had to touch it'"
            )
        return path, reason
    raise ValueError(f"attributed extra must be a string or object, got {raw!r}")
