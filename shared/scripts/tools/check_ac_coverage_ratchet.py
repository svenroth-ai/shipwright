#!/usr/bin/env python3
"""AC COVERAGE RATCHET — feeder (a) of P3.7's two feeder checks (campaign
``req3-04c-ac-identity-wave2``, SPEC §8 E2).

Design: ``.shipwright/planning/iterate/2026-09-10-p3-7-feeder-checks.md``.

**The asymmetry, stated where a reader of THIS file meets it.** SPEC §8 E2
splits P3.7 into two checks with OPPOSITE blocking semantics, and the split
is deliberate, not an oversight:

* **This check — "AC without a test" — is ANTI-RATCHETED.** P3.6's own
  measurement (design doc §2.1) found 259 of 268 minted ACs unbound TODAY.
  A hard block on that population would be a blanket blocker on day one, not
  a gate — so this check only blocks a NEW, un-grandfathered addition to the
  unbound population, exactly the ``shared/scripts/lib/anti_ratchet.py``
  block rule the bloat gate already uses (*"a measurement that exceeds its
  baseline blocks; an existing baseline entry does not"*), adapted from a
  per-file LOC ceiling to a per-AC set membership: an unbound AC not already
  in ``shipwright_ac_coverage_baseline.json`` is the ratchet.
* **Its sibling, ``check_orphan_ac_binding.py`` ("a test whose AC
  vanished") — is HARD from day one, no baseline at all.** There IS no
  legacy backlog for that predicate: nothing has ever checked whether a
  ``@covers`` tag's AC id still exists, so there is nothing to grandfather.
  *A gate needs a baseline only when it has a legacy backlog to forgive*
  (P3.6 design doc §7, the same argument that makes P3.7(b) hard).

Exit codes (matching the family's dialect):

* ``0`` — clean: no unbound AC outside the baseline.
* ``1`` — RATCHET: at least one unbound AC is not in the baseline.
* ``2`` — infrastructure fault (unreadable manifest, corrupt baseline, ...).

A JSON verdict goes to stdout on every path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from verifiers._ac_baseline_growth import baseline_grown_since_parent  # noqa: E402
from verifiers._ac_binding_state import read_binding_state, spec_path_by_fr  # noqa: E402
from verifiers._keystone_ac_digest import MANIFEST_RELPATH, ReadError, require_manifest_shape  # noqa: E402
from verifiers.stdio import ensure_utf8_stdout  # noqa: E402

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INFRA = 2

BASELINE_RELPATH = "shipwright_ac_coverage_baseline.json"


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


def _infra(reason: str) -> dict:
    return {"gate": "ac_coverage_ratchet", "status": "infra_fault", "error": reason}


def _read_head_manifest(project_root: Path) -> dict:
    path = project_root / MANIFEST_RELPATH
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReadError(
            f"the regenerated {MANIFEST_RELPATH} could not be read ({exc}). This gate must run "
            "AFTER the manifest-regeneration step in the same job."
        ) from exc
    except ValueError as exc:
        raise ReadError(f"{MANIFEST_RELPATH} in the worktree is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReadError(f"{MANIFEST_RELPATH} in the worktree is not a JSON object")
    return require_manifest_shape(manifest, "in the worktree")


def _read_worktree_spec_texts(project_root: Path, manifest: dict) -> dict[str, str | None]:
    """``{spec_path: text or None}`` for every path the manifest names — the
    WORKTREE's own bytes, never git-show: this check answers "what is bound
    RIGHT NOW", and the workflow step that invokes it runs at the checked-out
    HEAD commit after manifest regeneration, so the worktree IS that commit.

    Three-way, matching ``read_binding_state``'s own contract (external code
    review, openai, HIGH): a genuinely absent file reads as ``""`` (proceed,
    zero criteria), never the same as ``None`` (a real read fault — I/O or a
    non-UTF-8 spec file, which ``read_text`` raises as ``UnicodeDecodeError``,
    a ``ValueError`` subclass, not ``OSError`` — which ``read_binding_state``
    now raises on rather than silently excluding)."""
    out: dict[str, str | None] = {}
    for spec_path in set(spec_path_by_fr(manifest).values()):
        path = project_root / spec_path
        try:
            out[spec_path] = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            out[spec_path] = ""
        except (OSError, ValueError):
            out[spec_path] = None
    return out


def _ac_str(key: tuple[str, str]) -> str:
    return f"{key[0]}/{key[1]}"


BASELINE_SCHEMA_VERSION = 1


def _load_baseline(path: Path) -> tuple[set[str], str | None]:
    """``(baselined ac-strings, error)``. Absent -> ``(set(), None)`` — an
    EMPTY grandfathered set, which blocks EVERY unbound AC: fail CLOSED,
    deliberately the OPPOSITE default from ``anti_ratchet.load_baseline_
    override``'s absent-baseline behaviour (design doc §4 — a coverage
    baseline this gate itself owns and was never committed means "check
    against nothing grandfathered", not "nothing to check"). Present-but-
    corrupt -> a non-None error (also fail CLOSED — a corrupt baseline must
    not silently disable the gate).

    ``schema_version`` (external plan review, glm, low): tolerated absent
    (pre-dates this key) but rejected if PRESENT and not the version this
    reader understands — a future format change (e.g. per-entry provenance)
    must not be silently misread as today's flat string list.

    Every entry in ``unbound`` must be a string (external code review, glm,
    medium): a non-string entry — a hand-edited or half-migrated baseline —
    used to be silently filtered out, which could silently shrink the
    grandfathered set (false NEW blocks) or mask real corruption. Now it is
    a non-None error, same as any other malformed-shape case."""
    if not path.is_file():
        return set(), None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return set(), f"{path} is not readable/valid JSON: {exc}"
    if not isinstance(doc, dict) or not isinstance(doc.get("unbound"), list):
        return set(), f"{path} does not have the expected {{'unbound': [...]}} shape"
    version = doc.get("schema_version", BASELINE_SCHEMA_VERSION)
    if version != BASELINE_SCHEMA_VERSION:
        return set(), (
            f"{path} declares schema_version {version!r}; this reader only understands "
            f"{BASELINE_SCHEMA_VERSION!r}"
        )
    entries = doc["unbound"]
    if not all(isinstance(x, str) for x in entries):
        return set(), f"{path}'s 'unbound' list contains a non-string entry"
    return set(entries), None


def _write_baseline(path: Path, unbound: set[str]) -> None:
    path.write_text(
        json.dumps({
            "$comment": (
                "P3.7 feeder (a) baseline (SPEC §8 E2) — the grandfathered 'AC without a "
                "test' population. Regenerate via `check_ac_coverage_ratchet.py --write`. "
                "Shrinking this list (binding an AC) is always welcome and needs no "
                "justification; an entry is removed automatically the next time this is "
                "regenerated after that AC gains a binding. Refresh PERIODICALLY (not just "
                "when adding a new violation) — a stale entry for an AC that has since "
                "regressed (bound, then unbound again) stays silently grandfathered until "
                "the baseline is regenerated; see the design doc's Known Limitations."
            ),
            "schema_version": BASELINE_SCHEMA_VERSION,
            "unbound": sorted(unbound),
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="AC coverage ratchet (P3.7 feeder a)")
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--baseline", default=None, type=Path,
                         help=f"override {BASELINE_RELPATH} (tests / local reproduction)")
    parser.add_argument("--write", action="store_true",
                         help="(re)generate the baseline from the CURRENT unbound population "
                              "instead of gating; exits 0")
    parser.add_argument("--check-baseline-growth", action="store_true",
                         help="ALSO block if the baseline's own committed bytes grew since "
                              "--parent-sha (push-only auxiliary signal for a same-PR self-"
                              "grandfathered entry, trg-91532c29/trg-e69bf1ba finding 6; see "
                              "verifiers/_ac_baseline_growth.py for what this does and does "
                              "not close). Rejected combined with --write.")
    parser.add_argument("--parent-sha", default=None,
                         help="the commit to diff the baseline against for "
                              "--check-baseline-growth — pass the push event's `before` SHA "
                              "in CI (covers every commit a multi-commit push introduced, not "
                              "just the immediate parent). Defaults to resolving HEAD~1 for "
                              "local/manual invocation.")
    args = parser.parse_args(argv)
    if args.write and args.check_baseline_growth:
        # External code review (glm, low): a subtle, silently-ambiguous
        # combination — growth computed against a baseline this same run is
        # about to overwrite — is worse than a loud usage error.
        parser.error("--check-baseline-growth cannot be combined with --write")
    project_root = Path(args.project_root).resolve()
    baseline_path = args.baseline or (project_root / BASELINE_RELPATH)
    try:
        return _run_gate(project_root, baseline_path, args.write, args.check_baseline_growth,
                          args.parent_sha)
    except Exception as exc:  # last-resort fault boundary, same pattern the family uses
        return _emit(_infra(f"unexpected gate fault: {exc!r}"), EXIT_INFRA)


def _run_gate(project_root: Path, baseline_path: Path, write: bool,
              check_growth: bool = False, parent_sha: str | None = None) -> int:
    try:
        head_manifest = _read_head_manifest(project_root)
        spec_texts = _read_worktree_spec_texts(project_root, head_manifest)
        state = read_binding_state(spec_texts, head_manifest)
    except ReadError as exc:
        return _emit(_infra(str(exc)), EXIT_INFRA)
    unbound = {_ac_str(k) for k in state.unbound}

    if write:
        _write_baseline(baseline_path, unbound)
        return _emit({
            "gate": "ac_coverage_ratchet", "status": "baseline_written",
            "baseline": str(baseline_path), "unbound_count": len(unbound),
            "warnings": state.warnings,
        }, EXIT_OK)

    baselined, baseline_error = _load_baseline(baseline_path)
    if baseline_error:
        return _emit(_infra(baseline_error), EXIT_INFRA)

    new_violations = sorted(unbound - baselined)
    # informational, never blocks: baselined AC no longer in `unbound` -- either it gained a
    # binding, OR it was deleted/renumbered out of the minted population entirely (Stage-2
    # code review, low: this field cannot distinguish the two; both read as "resolved").
    resolved = sorted(baselined - unbound)
    warnings = list(state.warnings)

    grown: list[str] = []
    if check_growth:
        grown, growth_warnings = baseline_grown_since_parent(
            project_root, baseline_path, baselined, parent_sha,
        )
        warnings += growth_warnings

    payload = {
        "gate": "ac_coverage_ratchet",
        "unbound_count": len(unbound),
        "baseline_count": len(baselined),
        "new_unbound": new_violations,
        "resolved_since_baseline": resolved,
        "warnings": warnings,
    }
    if check_growth:
        payload["baseline_grew_since_parent"] = grown
    if new_violations or grown:
        payload["status"] = "blocked"
        remedies = []
        if new_violations:
            remedies.append(
                "the AC(s) in `new_unbound` have no test binding and are not in the "
                f"grandfathered baseline ({baseline_path}). Either bind them (add a "
                "`@covers FR-xx/ACnn` tag to the test(s) that exercise them), or — if this is "
                "genuinely pre-existing backlog the baseline missed — regenerate it via "
                "`--write` and commit the result in this same PR with a stated reason."
            )
        if grown:
            remedies.append(
                "the AC(s) in `baseline_grew_since_parent` were newly added to the committed "
                "baseline in THIS commit — a PR unbinding an AC and grandfathering it via "
                "`--write` in the same PR. Bind the AC instead of grandfathering it, or get "
                "the grandfathering explicitly re-reviewed and re-pushed with a stated reason "
                "rather than letting it land silently."
            )
        payload["remedy"] = " ".join(remedies)
        return _emit(payload, EXIT_BLOCKED)
    payload["status"] = "clean"
    return _emit(payload, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised by the subprocess smoke test
    raise SystemExit(main())
