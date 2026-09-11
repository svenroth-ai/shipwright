"""Filesystem-facing wiring for ``_project_gate_extras.py``'s four pure
gate functions, split out of ``project_checks.py`` the moment that file
crossed the 300-LOC bloat-baseline guideline adding them (same precedent as
``grill_trace_glossary.py`` splitting out of
``verify_grill_trace_completeness.py``). Each ``check_*`` here reads
whatever filesystem state its gate needs and adapts the pure ``GateResult``
into a ``CheckResult``; ``project_checks.run_project_checks`` calls all
four in sequence, exactly like it calls ``check_grill_trace_completeness``.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import _project_gate_extras as _extras
from .common import CheckResult, Severity, read_run_config

# Mirrors PLANNING_DIRNAME in project_checks.py — kept as a literal here
# rather than imported, to avoid a circular import (project_checks imports
# THIS module).
_PLANNING_DIRNAME = ".shipwright/planning"


def _is_safe_split_name(name: object) -> bool:
    """A split ``name`` a hostile or corrupt manifest cannot turn into a
    path-traversal or a crash. External code review
    (e2-checks-project-elicitation, round 3, medium, openai): an
    unvalidated non-string / absolute / traversal name reaching
    ``planning_dir / name`` or ``sorted(names)`` (mixed types) raised
    instead of producing a failing ``CheckResult``. Checked against BOTH
    POSIX and Windows absolute-path rules regardless of host OS — found
    empirically that ``Path("/absolute").is_absolute()`` is ``False`` on
    Windows (a drive-relative path, not absolute there), which let
    ``planning_dir / "/absolute"`` re-anchor to the current drive's root
    and crash ``relative_to`` a step later instead of being filtered here.
    ``"."`` is rejected too (round 4, openai): it is a no-op join that
    silently resolves to the planning ROOT rather than any split dir —
    not a traversal, but not a split name either. Round 6 (both reviewers
    independently): ``is_absolute()`` alone misses Windows DRIVE-relative
    (``"C:foo"`` — has a drive, no root) and ROOT-relative (``"\\outside"``
    — has a root, no drive) names, neither of which pathlib calls
    "absolute" on Windows (it requires BOTH), but either re-anchors
    ``planning_dir / name`` away from the planning tree when joined —
    checked for directly via ``PureWindowsPath``'s own ``.drive``/``.root``."""
    if not isinstance(name, str) or not name:
        return False
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).is_absolute():
        return False
    win = PureWindowsPath(name)
    if win.drive or win.root:
        return False
    parts = Path(name).parts
    return bool(parts) and ".." not in parts and "." not in parts


def _declared_split_names(
    project_root: Path,
) -> tuple[set[str] | None, str | None]:
    """The project's OWN declared split names, from
    ``shipwright_project_config.json``'s (or, as a fallback,
    ``shipwright_run_config.json``'s) ``splits`` list — the exact same
    authoritative source ``check_manifest_splits_match_dirs`` already reads.
    Returns ``(names, manifest_error)``: ``names`` is ``None`` only when
    there is genuinely no manifest to read yet (config not written) — an
    empty set is a real, valid "zero splits declared" answer, distinct from
    that. ``manifest_error`` is set whenever the manifest exists but cannot
    be trusted as a split list — parse failure, a non-list ``splits`` value,
    or ANY declared name being invalid/unsafe (external code review,
    e2-checks-project-elicitation rounds 3-4; external Tier-3 review,
    PR #729): each used to fall through to "zero splits" or a silently-
    dropped subset, letting every spec-text gate pass vacuously over the
    rejected names. A mixed manifest is loud too now — a single unsafe
    entry must not evade the four gates just because a sibling was valid.

    External code review (round 2, high, both reviewers independently):
    directory enumeration under ``.shipwright/planning/`` cannot tell a
    split dir from a reserved non-split one (``campaigns/``, ``adr/``,
    ``iterate/``, ``grill-traces/``, ``01-adopted/`` for adopt-mode, and
    whatever else gets added later) — an ever-growing exclusion list
    chases every new reserved dir forever. The manifest is the one place
    that already knows which dirs ARE splits; reading it is not a parallel
    interpretation of "split", it is THE interpretation, shared with the
    existing WARNING-severity check.
    """
    data = read_run_config(project_root)
    path = project_root / "shipwright_project_config.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return None, f"shipwright_project_config.json could not be parsed: {exc}"
        if not isinstance(data, dict):
            # External code review (round 6, medium, both reviewers
            # independently): a syntactically valid but non-object config
            # (``[]``, ``null``, a bare scalar) used to fall through to
            # "zero splits declared" (SKIPPED) here, even though the SAME
            # non-object case already fails loud in ``_read_project_scope``
            # — the exact silent-pass inconsistency this module's own
            # docstrings claim were closed everywhere.
            return None, (
                f"shipwright_project_config.json is a {type(data).__name__}, "
                f"expected a JSON object"
            )
    if not path.exists() and not data:
        return None, None
    splits = data.get("splits") if isinstance(data, dict) else None
    if splits is None:
        splits = []
    if not isinstance(splits, list):
        return None, (
            f"shipwright_project_config.json's 'splits' is a "
            f"{type(splits).__name__}, expected a list of "
            f"{{'name': ...}} objects"
        )
    names: set[str] = set()
    rejected: list[object] = []
    for s in splits:
        raw_name = s.get("name") if isinstance(s, dict) else None
        if isinstance(s, dict) and _is_safe_split_name(raw_name):
            names.add(raw_name)
        else:
            # Every non-dict entry, and every dict entry whose "name" is
            # missing / null / empty / unsafe, is recorded — external code
            # review (round 5, medium, openai): a FALSY name (``null``,
            # ``""``) used to be filtered out before ever being counted as
            # rejected, so a manifest of nothing but null names read as
            # "declared zero splits" (SKIPPED) rather than "every declared
            # split was invalid" (loud failure).
            rejected.append(s if not isinstance(s, dict) else raw_name)
    if rejected:
        # External Tier-3 review, PR #729: a mixed manifest used to silently
        # drop rejected entries and check only the valid subset, letting an
        # unsafe declared name (e.g. `../escape`) evade every gate.
        return None, f"declared split entry(ies) invalid/unsafe: {rejected!r}"
    return names, None


def _read_spec_texts(project_root: Path) -> tuple[dict[str, str], list[str]]:
    """Every DECLARED split's ``spec.md``, keyed by a display-friendly
    relative path, plus the declared splits whose ``spec.md`` could not be
    read or was never written at all (or the manifest itself couldn't be
    trusted). An unreadable OR missing spec.md is NOT silently dropped
    (external plan/code review, e2-checks-project-elicitation, rounds
    1-4): a declared split whose spec.md cannot be read, or was never
    written, is exactly as unverifiable as one with zero rows, and treating
    either as "absent" let `no_empty_split` — and every other check keyed
    off this reader — pass vacuously over a split it never actually saw.

    Enumerates from the project's OWN ``splits`` manifest (round 2's fix,
    see ``_declared_split_names``), not the planning directory's raw
    contents — a directory-enumeration approach cannot distinguish a real
    split from a reserved non-split dir. Confirmed against the real
    producer (``split-heuristics.md`` line 47): even a single-unit project
    always gets a named split dir (``01-{project-name}/spec.md``), never a
    bare root-level ``spec.md`` — so a manifest with zero declared splits
    genuinely means "no requirements written yet", not a missed layout."""
    names, manifest_error = _declared_split_names(project_root)
    if manifest_error:
        return {}, [manifest_error]
    if not names:
        return {}, []
    planning_dir = project_root / _PLANNING_DIRNAME
    texts: dict[str, str] = {}
    unreadable: list[str] = []
    for name in sorted(names):
        spec_path = planning_dir / name / "spec.md"
        rel = str(spec_path.relative_to(project_root))
        if not spec_path.exists():
            unreadable.append(f"{rel} (missing)")
            continue
        try:
            texts[rel] = spec_path.read_text(encoding="utf-8")
        except OSError:
            unreadable.append(rel)
    return texts, unreadable


def _unreadable_result(name: str, unreadable: list[str]) -> CheckResult | None:
    if not unreadable:
        return None
    return CheckResult(
        name, False,
        f"unverifiable — not skipped (declared split's spec.md unreadable/"
        f"missing, or the splits manifest itself couldn't be read): {unreadable}",
    )


def _read_project_scope(
    project_root: Path, name: str,
) -> tuple[str | None, CheckResult | None, bool]:
    """``shipwright_project_config.json``'s ``scope`` field, shared by
    every scope-aware gate in this module (round 5 extraction — two gates
    had grown near-identical try/except blocks). Returns ``(scope,
    error_result, config_exists)``: a non-``None`` ``error_result`` must be
    returned by the caller UNCHANGED (fail-loud parse/shape failure,
    external code review round 4 low + round 5 medium); ``config_exists``
    lets a caller distinguish "nothing written yet" from a config that
    exists but has no ``scope`` key (``scope is None`` either way)."""
    path = project_root / "shipwright_project_config.json"
    if not path.exists():
        return None, None, False
    try:
        scope = json.loads(path.read_text(encoding="utf-8")).get("scope")
    except (json.JSONDecodeError, OSError) as exc:
        return None, CheckResult(
            name, False,
            f"unverifiable — shipwright_project_config.json could not be parsed: {exc}",
        ), True
    except AttributeError:
        return None, CheckResult(
            name, False,
            "unverifiable — shipwright_project_config.json is not a JSON object",
        ), True
    return scope, None, True


def check_basis_forbids_assumed(project_root: Path) -> CheckResult:
    """FR-01.02 #4 + #15 (merged) — see ``_project_gate_extras.basis_forbids_assumed``.

    **Greenfield only.** The ledger's own #4 text ("we banned `assumed`
    for greenfield") and #15's original allow-with-settlement text both
    scope this to a project being freshly authored — an "extension"
    project can carry a pre-existing, honestly-unconfirmed `assumed` row
    that this gate has no business relitigating. External code review
    (e2-checks-project-elicitation, round 5, medium, both reviewers
    independently): the wiring ran unconditionally, unlike #11's own
    scope carve-out, which was the exact inconsistency both reviewers
    named."""
    name = "Basis column forbids bare 'assumed' (FR-01.02 #4/#15)"
    scope, error, config_exists = _read_project_scope(project_root, name)
    if error:
        return error
    if config_exists and scope == "extension":
        return CheckResult(
            name, True, "extension scope — pre-existing Basis cells are not relitigated",
            severity=Severity.SKIPPED.value,
        )
    spec_texts, unreadable = _read_spec_texts(project_root)
    if bad := _unreadable_result(name, unreadable):
        return bad
    if not spec_texts:
        return CheckResult(name, True, "no spec.md written yet", severity=Severity.SKIPPED.value)
    result = _extras.basis_forbids_assumed(spec_texts)
    return CheckResult(name, result.ok, result.detail)


def check_criteria_free_of_implementation_detail(project_root: Path) -> CheckResult:
    """FR-01.02 #5 — see ``_project_gate_extras.criteria_free_of_implementation_detail``."""
    name = "acceptance criteria free of implementation detail (FR-01.02 #5)"
    spec_texts, unreadable = _read_spec_texts(project_root)
    if bad := _unreadable_result(name, unreadable):
        return bad
    if not spec_texts:
        return CheckResult(name, True, "no spec.md written yet", severity=Severity.SKIPPED.value)
    result = _extras.criteria_free_of_implementation_detail(spec_texts)
    return CheckResult(name, result.ok, result.detail)


def check_no_empty_split(project_root: Path) -> CheckResult:
    """FR-01.02 #10 — see ``_project_gate_extras.no_empty_split``."""
    name = "no split has zero active FR rows (FR-01.02 #10)"
    spec_texts, unreadable = _read_spec_texts(project_root)
    if bad := _unreadable_result(name, unreadable):
        return bad
    if not spec_texts:
        return CheckResult(name, True, "no spec.md written yet", severity=Severity.SKIPPED.value)
    result = _extras.no_empty_split(spec_texts)
    return CheckResult(name, result.ok, result.detail)


def check_starting_guidance_present(project_root: Path) -> CheckResult:
    """FR-01.02 #11 — see ``_project_gate_extras.starting_guidance_present``.

    Extension scope never writes CLAUDE.md / agent_docs (they already
    exist on the target repo) — same "Full Application only" carve-out
    ``step-8-completion.md`` items 3 and 4 already state in prose.
    """
    name = "starting guidance present and non-empty (FR-01.02 #11)"
    scope, error, config_exists = _read_project_scope(project_root, name)
    if error:
        return error
    if not config_exists:
        return CheckResult(name, True, "no project config yet", severity=Severity.SKIPPED.value)
    if scope == "extension":
        return CheckResult(
            name, True, "extension scope — CLAUDE.md/agent_docs pre-exist",
            severity=Severity.SKIPPED.value,
        )
    result = _extras.starting_guidance_present(project_root)
    return CheckResult(name, result.ok, result.detail)


__all__ = [
    "check_basis_forbids_assumed",
    "check_criteria_free_of_implementation_detail",
    "check_no_empty_split",
    "check_starting_guidance_present",
]
