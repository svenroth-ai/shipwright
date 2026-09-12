"""Split-manifest reading for ``_project_gate_wiring.py``, split out the
moment that file crossed the 300-LOC bloat-baseline guideline again after
several Tier-3 PR-review rounds (PR #729) kept adding to its manifest-
reading logic specifically — the same precedent as ``_project_gate_wiring``
itself splitting out of ``project_checks.py``. Everything here is about
turning ``shipwright_project_config.json`` / ``shipwright_run_config.json``
into a trustworthy set of declared split names and their ``spec.md`` texts;
``_project_gate_wiring``'s ``check_*`` functions consume it but hold no
manifest-parsing logic of their own.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from .common import CheckResult

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
    checked for directly via ``PureWindowsPath``'s own ``.drive``/``.root``.
    Tier-3 review (PR #729): ``..``/``.`` segments were checked via the
    host-native ``Path(name).parts``, so a backslash-traversal name stayed
    one literal part on POSIX and passed; checked under both conventions now."""
    if not isinstance(name, str) or not name:
        return False
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).is_absolute():
        return False
    win = PureWindowsPath(name)
    if win.drive or win.root:
        return False
    posix_parts = PurePosixPath(name).parts
    if not posix_parts:
        return False
    for parts in (posix_parts, win.parts):
        if ".." in parts or "." in parts:
            return False
    return True


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
    or ANY declared name being invalid/unsafe (rounds 3-4; Tier-3 review,
    PR #729): each used to fall through to "zero splits" or a silently-
    dropped subset, letting every spec-text gate pass vacuously over the
    rejected names. A mixed manifest is loud too — one unsafe entry must
    not evade the four gates just because a sibling was valid.

    External code review (round 2, high, both reviewers independently):
    directory enumeration under ``.shipwright/planning/`` cannot tell a
    split dir from a reserved non-split one (``campaigns/``, ``adr/``,
    ``iterate/``, ``grill-traces/``, ``01-adopted/``, ...) — an
    ever-growing exclusion list chases every new reserved dir forever.
    The manifest already knows which dirs ARE splits; reading it is THE
    interpretation, shared with the existing WARNING-severity check.
    """
    run_config_path = project_root / "shipwright_run_config.json"
    path = project_root / "shipwright_project_config.json"
    if path.exists():
        # The authoritative source, checked FIRST. Tier-3 review (PR #729,
        # round 6): a prior version of this function read the run-config
        # FALLBACK unconditionally before this check, so a malformed
        # ``shipwright_run_config.json`` failed the gates loud even when
        # this, the real manifest, was present and perfectly valid — the
        # fallback must never take priority over, or block on, the
        # manifest it is a fallback FOR.
        source = "shipwright_project_config.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return None, f"{source} could not be parsed: {exc}"
        if not isinstance(data, dict):
            return None, f"{source} is a {type(data).__name__}, expected a JSON object"
    else:
        # Tier-3 review (PR #729, 3 rounds): ``read_run_config`` swallows a
        # ``JSONDecodeError`` into ``{}`` BY DESIGN (its own docstring: "a
        # missing or malformed file yields {}") — indistinguishable from a
        # genuinely absent file. Reading the fallback file directly, the
        # same way the branch above does, lets a malformed run-config
        # surface its own error instead of silently becoming "zero splits
        # declared". Only reached when the project config is ABSENT.
        source = "shipwright_run_config.json"
        data: object = {}
        if run_config_path.exists():
            try:
                data = json.loads(run_config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                return None, f"{source} could not be parsed: {exc}"
        if not isinstance(data, dict):
            return None, f"{source} is a {type(data).__name__}, expected a JSON object"
    if not path.exists() and not run_config_path.exists() and not data:
        return None, None
    splits = data.get("splits") if isinstance(data, dict) else None
    if splits is None:
        splits = []
    if not isinstance(splits, list):
        return None, (
            f"{source}'s 'splits' is a {type(splits).__name__}, "
            f"expected a list of {{'name': ...}} objects"
        )
    names: set[str] = set()
    rejected: list[object] = []
    for s in splits:
        raw_name = s.get("name") if isinstance(s, dict) else None
        if isinstance(s, dict) and _is_safe_split_name(raw_name):
            names.add(raw_name)
        else:
            # Every non-dict entry, and every dict entry whose "name" is
            # missing/null/empty/unsafe, is recorded (round 5): a FALSY
            # name used to be filtered before being counted as rejected,
            # misreading an all-null manifest as "zero splits declared".
            rejected.append(s if not isinstance(s, dict) else raw_name)
    if rejected:
        # Tier-3 review, PR #729: a mixed manifest used to silently drop
        # rejected entries and check only the valid subset.
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
    contents — directory enumeration can't distinguish a real split from a
    reserved non-split dir. Confirmed against ``split-heuristics.md`` line
    47: even a single-unit project always gets a named split dir, never a
    bare root-level ``spec.md`` — so zero declared splits genuinely means
    "no requirements written yet", not a missed layout."""
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
