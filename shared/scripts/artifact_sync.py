#!/usr/bin/env python3
"""Artifact sync check — read-only drift detection.

Compares current code state against spec FRs using shipwright_sync_config.json mappings.
Output: JSON report of detected drift.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


def run_git(args, *, cwd, timeout=None, check=True):
    """``lib.git_base.run_git``, imported LAZILY behind this indirection.

    An eager module-level ``from lib.git_base import …`` in a ``shared/scripts/``
    top-level module is the ADR-045 anti-pattern: every plugin ships its own
    ``scripts/lib``, and an eager import binds ``sys.modules['lib']`` to whichever got
    there first — the shape that yields green-locally / red-in-CI. Deferring it here
    mirrors the guarded lazy import ``_emit_drift_to_triage`` uses below, and it stays
    a module-level NAME so tests can patch this one seam.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from lib.git_base import run_git as _run_git  # noqa: PLC0415

    kwargs = {"cwd": cwd, "check": check}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return _run_git(args, **kwargs)


#: A base ref followed ONLY by well-formed ancestry steps (``~``, ``~N``, ``^``,
#: ``^N``). `HEAD~1` matches; `HEAD~bogus` and `HEAD@{bad}` do not — their base
#: resolves, so matching on the base alone would classify them as missing history.
_ANCESTRY_REF = re.compile(r"(?P<base>[^~^@]+)(?:[~^]\d*)*")


def _git_unreadable(detail: str) -> dict:
    """The 'we could not determine drift' result.

    ``error`` is the load-bearing key: F1's consumer (``finalize_bundle._f1_record``)
    maps ``drift_detected: False`` to status ``ok``, so a git failure used to pass the
    drift gate as a clean tree. Kept ALONGSIDE ``drift_detected`` so the published
    shape is unchanged for every other reader.
    """
    return {
        "drift_detected": False,
        "error": f"could not read git diff — {detail}",
        "message": f"Could not read git diff ({detail})",
        "affected": [],
    }


def _nothing_to_compare_against(root: Path, ref: str) -> str:
    """``""`` when there IS something to compare; otherwise WHY there is not
    (``"shallow"`` / ``"history"`` — truthy either way).

    "git could not answer" and "there is nothing to compare against" are different
    failures and must not share an outcome. The default ref is ``HEAD~1..HEAD``, so a
    ONE-COMMIT repo (greenfield's first iterate) exits 128 — and calling that an error
    makes F1 ``failed``, aborting the whole bundle for a repo whose only sin is being
    new. ``HEAD`` is probed FIRST: if even that fails the repo is broken, not shallow.
    """
    if run_git(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
               cwd=root, check=False).returncode != 0:
        return ""
    short_history = False
    for endpoint in (p for p in ref.replace("...", "..").split("..") if p):
        if run_git(["rev-parse", "--verify", "--quiet", f"{endpoint}^{{commit}}"],
                   cwd=root, check=False).returncode == 0:
            continue
        # Benign ONLY for a well-formed ancestry walk off a RESOLVABLE base. A typo'd
        # name fails the base check; a malformed suffix (`HEAD~bogus`, `HEAD@{bad}`)
        # fails the shape check — its base resolves, so matching on the base alone let
        # it through (external review's follow-up).
        match = _ANCESTRY_REF.fullmatch(endpoint)
        if not match or run_git(
                ["rev-parse", "--verify", "--quiet", f"{match.group('base')}^{{commit}}"],
                cwd=root, check=False).returncode != 0:
            return ""  # unknown / malformed ref → the structured git error
        short_history = True
    if not short_history:
        return ""
    # SHALLOW differs from one-commit: the prior commits EXIST but were not fetched,
    # so the check silently did not run. The operator is told which (remedies differ).
    shallow = run_git(["rev-parse", "--is-shallow-repository"],
                      cwd=root, check=False).stdout.strip() == "true"
    return "shallow" if shallow else "history"


# ---------------------------------------------------------------------------
# AC-5 of iterate-2026-05-14-triage-producers-2: triage emission
# ---------------------------------------------------------------------------


def _emit_drift_to_triage(project_root, affected: list[dict]) -> int:
    """Append artifact-drift findings to ``.shipwright/triage.jsonl``.

    One triage item per affected mapping (an entry from ``detect_drift()``'s
    ``affected`` list — a sync_config pattern whose changed_files intersect
    with `git diff`). ``source="drift"``, severity="medium",
    kind="maintenance", ``dedup_key=f"drift:{pattern}:artifact"``.
    ``match_commit=False`` + ``window_seconds=None`` mirrors the
    check_drift.py producer (same semantics, different detection site).

    Best-effort: per-item errors logged to stderr, swallowed. Returns the
    number of NEW items appended.
    """
    if not affected:
        return 0

    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[drift] artifact_sync triage import failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 0

    appended = 0
    for mapping in affected:
        try:
            pattern = str(mapping.get("pattern") or "unknown")
            changed = mapping.get("changed_files") or []
            artifacts = mapping.get("artifacts") or []
            frs = mapping.get("frs") or []
            title = f"Drift: code in {pattern} changed without artifact update"[:160]
            detail = (
                f"changed_files: {', '.join(str(c) for c in changed)} | "
                f"affected_artifacts: {', '.join(str(a) for a in artifacts) or 'n/a'} | "
                f"affected_FRs: {', '.join(str(f) for f in frs) or 'n/a'}"
            )
            new_id = append_triage_item_idempotent(
                project_root,
                source="drift",
                severity="medium",
                kind="maintenance",
                title=title,
                detail=detail,
                # CONTRACT: the `:artifact` suffix is load-bearing. This
                # producer shares source="drift" with
                # `check_drift.py::_emit_drift_to_triage`, whose resolve
                # pass scopes itself to `:timestamp`/`:content` keys so it
                # never retracts THIS producer's items. Changing this
                # suffix would silently break that cross-producer contract.
                dedup_key=f"drift:{pattern}:artifact",
                match_commit=False,
                window_seconds=None,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] artifact triage emit failed: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


def detect_drift(project_root: str, ref: str = "HEAD~1..HEAD") -> dict:
    """Detect artifact drift by comparing git diff against sync config."""
    root = Path(project_root)

    # Load sync config
    config_path = root / "shipwright_sync_config.json"
    if not config_path.exists():
        return {
            "drift_detected": False,
            "message": "No shipwright_sync_config.json found — cannot check drift",
            "affected": [],
        }

    # WP8/F24: explicit UTF-8 (utf-8-sig tolerates an optional BOM from a
    # hand-edited config) — the canonical writer (lib/config.py) emits FR
    # titles / descriptions with ensure_ascii=False, so a missing encoding=
    # here crashes on the cp1252 Windows dev platform for any non-ASCII
    # (CJK / Cyrillic) FR title.
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    mappings = config.get("mappings", [])

    # Get changed files from git.
    #
    # Via lib.git_base.run_git rather than a bare subprocess.run, which had three
    # defects here and would have needed a fourth copy of that module's hygiene to
    # fix in place:
    #
    #  * ``text=True`` with no ``encoding=`` decodes with the LOCALE codec (cp1252
    #    on the Windows dev platform), so any non-Latin-1 path in the diff raised
    #    and the call read as a failed fetch. Lines 100-105 above fix exactly this
    #    class for the config read and it was missed one statement later.
    #  * no returncode check: a bad ref or a held ``.git/index.lock`` exits non-zero
    #    with empty stdout, which fell through to "No changes detected" — a git
    #    FAILURE reported as a clean tree, and F1 passes on it.
    #  * no timeout: a hung git blocked finalization indefinitely. run_git bounds it
    #    and kills + reaps the process.
    #
    # ``TimeoutExpired`` is a ``SubprocessError``, so the existing handler covers it.
    # The ENTIRE git conversation is inside the handler, not just the diff. The
    # unresolvable-ref probe runs three more `run_git` calls on a machine already
    # loaded enough that the diff failed, and each can raise `TimeoutExpired` — a
    # `SubprocessError`. Leaving it outside reintroduced the exact hole the
    # `ImportError` widening had just closed, one statement later: the traceback
    # escapes `detect_drift`, `main()` dies with a fourth exit code outside the
    # published 0/1/2 contract on non-JSON stdout, and `_f1_record` falls back to its
    # generic reason instead of the structured one this change added.
    try:
        result = run_git(["diff", "--name-only", ref], cwd=root, check=False)
        nothing_to_compare = (
            _nothing_to_compare_against(root, ref) if result.returncode != 0 else False
        )
    except (subprocess.SubprocessError, OSError, ImportError) as exc:
        # OSError (not just FileNotFoundError): a git that exists but is not runnable
        # raises PermissionError. ImportError: the lazy import can fail under an
        # ADR-045 `lib` shadow — the case the indirection exists for — and is not one.
        return _git_unreadable(f"{type(exc).__name__}")
    if result.returncode != 0:
        if nothing_to_compare:
            # A one-commit / shallow repo, or a ref that names nothing: a legitimate
            # no-op, NOT a failure. Reported WITHOUT the `error` key so F1 stays `ok`
            # and the finalization bundle is not aborted over it.
            detail = ("the checkout is SHALLOW — the drift check did not run; use "
                      "fetch-depth: 0 to enable it"
                      if nothing_to_compare == "shallow"
                      else "not enough history to compare against")
            return {
                "drift_detected": False,
                "message": f"Cannot resolve {ref} — {detail}",
                "affected": [],
            }
        return _git_unreadable(
            f"git exited {result.returncode}: {result.stderr.strip()[:200]}"
        )
    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    if not changed_files:
        return {"drift_detected": False, "message": "No changes detected", "affected": []}

    # Match changed files against mappings
    import fnmatch
    affected = []

    for mapping in mappings:
        pattern = mapping.get("pattern", "")
        matching_files = [f for f in changed_files if fnmatch.fnmatch(f, pattern)]
        if matching_files:
            affected.append({
                "pattern": pattern,
                "changed_files": matching_files,
                "artifacts": mapping.get("artifacts", []),
                "frs": mapping.get("frs", []),
                "category": mapping.get("category", "unknown"),
            })

    if affected:
        # Iterate-2 AC-5: mirror drift findings into .shipwright/triage.jsonl.
        # Best-effort — never changes the return shape or raises.
        try:
            _emit_drift_to_triage(root, affected)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[drift] artifact_sync top-level triage emission failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    return {
        "drift_detected": len(affected) > 0,
        "message": f"{len(affected)} mapping(s) affected" if affected else "No drift detected",
        "affected": affected,
        "changed_files_total": len(changed_files),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Artifact sync drift detection")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--mode", choices=["detect"], default="detect")
    parser.add_argument("--ref", default="HEAD~1..HEAD", help="Git ref range")
    args = parser.parse_args()

    result = detect_drift(args.project_root, args.ref)
    print(json.dumps(result, indent=2))
    if result.get("error"):
        # 2, distinct from the drift exit 1: "the check could not run" is not
        # "the check ran and found nothing", and F1 must not read it as the latter.
        sys.exit(2)
    sys.exit(0 if not result["drift_detected"] else 1)


if __name__ == "__main__":
    main()
