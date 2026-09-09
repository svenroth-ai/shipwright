#!/usr/bin/env python3
"""Was a commit's per-requirement `tests`/`coverage` evidence produced by the
SAME real GitHub Actions CI run that `ci_provenance.resolve_ci_verification`
already confirmed for the manifest's STRUCTURE? P3.5 restart
(campaign req3-04c-ac-identity-wave2,
`.shipwright/planning/iterate/2026-09-09-p3-5-promote-layers-per-fr-restart.md`).

`ci_provenance.resolve_ci_verification`'s own docstring states its scope
precisely: `verified` means a real CI run confirmed the committed manifest's
requirement/test-ID STRUCTURE was not fabricated or hand-edited — it does
NOT confirm the recorded `tests`/`coverage` VALUES are accurate, because the
comparison behind it (`compare_traceability_manifest.structural_diff`)
deliberately strips those fields (plus `acs`) before comparing. This module
closes exactly that remaining gap, composing with the existing predicate
rather than re-deriving trust from scratch (there is exactly ONE
unforgeability predicate in this system: `resolve_ci_verification`; this
module never re-implements the push/default-branch/success/step-success
filter, it only asks a further question about a run that predicate already
vetted).

**What's new:** `ci_manifest_drift_check.py` already regenerates
`.shipwright/compliance/test-traceability.json` IN PLACE, from that CI run's
real, fresh JUnit output, before comparing it structurally to the committed
one — and today discards it when the job ends. `ci.yml` now uploads that
regenerated file as a build artifact
(`EXECUTION_EVIDENCE_ARTIFACT_NAME`) whenever the drift check found no
structural drift. This module downloads that artifact from the EXACT
`run_id` `resolve_ci_verification` already trusts, and reads its
`tests`/`coverage` per requirement — never the local, mutable committed
file's own copies of those fields.

**Content-binding (the actual new unforgeability work, not just plumbing):**
a `verified` run's `run_id` alone is not enough to trust an artifact fetched
from it — GitHub's Jobs API reports only the LATEST attempt's conclusions
(`ci_provenance.py`'s own documented limitation), and a re-run can leave
more than one artifact sharing this name under the same `run_id`, one per
attempt that reached the upload step. Two defenses, at two different
layers: (1) `_find_unexpired_artifact` selects the NEWEST unexpired match
by `created_at`, and its download is then bound to THAT SPECIFIC
artifact's numeric `id` (`gh api .../actions/artifacts/{id}/zip`) — never
a second, independent by-NAME resolution (`gh run download --name`) that
`gh`/GitHub could resolve to a different attempt than the one selected
(external code review, openai/high + glm/medium, P3.5 restart round 2:
the FIRST attempt at this fix picked a specific artifact but then
discarded that selection at download time, making it inert). (2) before
that downloaded artifact is trusted at all, this module checks that (a)
its own `source_commit` field names the exact commit under evaluation,
AND (b) it structurally agrees with the CALLER-SUPPLIED committed
manifest (`compare_traceability_manifest.structural_diff(...) == ""`) —
the SAME public comparison `ci_manifest_drift_check.py` itself uses, not
a re-derived one. Either check failing is `error`, never a silent
`confirmed`. Layer (2) still cannot, by itself, distinguish between two
GENUINE attempts of the SAME commit (both would pass); layer (1) is what
narrows that — see Known Limitations for the honest remainder.

**Unforgeability property, one sentence:** faking a `confirmed`
:class:`ExecutionEvidence` requires forging GitHub's Artifacts API response
for the exact `run_id` that already passed `resolve_ci_verification`'s
push/default-branch/success/step-success filter, with content whose
`source_commit` names that same commit and whose requirement/test-ID
structure matches what that run's own structural check already confirmed —
the identical compromise boundary `ci_provenance.py`'s docstring states,
tightened (never widened) by the content-binding check above.

**Never reads the local tree for the committed manifest itself** — the
caller supplies `committed_manifest` (already read once, commit-pinned, by
`promote_required_layers.py`'s own `_read_committed_manifest`), so this
module's only local read is the (best-effort, `cwd`-pinned) `gh`
subprocess calls it already needs for the API/download traffic.

Three outcomes: `confirmed` (a verified run's artifact was found, downloaded,
parsed, and content-bound to `commit`/`committed_manifest`), `unavailable`
(structural verification itself is not `verified`, OR it IS `verified` but
no unexpired artifact by this name exists on that run — a defined,
non-fatal negative: the expected steady state for a `verified` commit that
predates this mechanism, or whose artifact has aged out of retention),
`error` (the query/download/parse pipeline itself could not complete, OR a
found-and-unexpired artifact still failed to download, OR the content-
binding check failed). Only `error` means "could not determine"; a caller
must NEVER treat it the same as `unavailable` for purposes of silently
skipping — see `promote_required_layers.py`'s own handling.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
from ci_provenance import _gh_api, resolve_ci_verification  # noqa: E402

# Cross-directory import (shared/scripts -> shared/scripts/tools), the SAME
# precedent `lib/layer_promotion.py` already uses for
# `tools.verifiers._layer_coverage_binding` -- both live under the same
# `shared/scripts` tree (not crossing into a plugin's own `scripts/`
# namespace, the actual ADR-044/045 hazard class), so this is not a new
# import-hazard shape. Uses the already-PUBLIC `structural_diff`, not the
# module's private `_load`/`_validate`/`_structural_view`.
from tools.compare_traceability_manifest import structural_diff  # noqa: E402

#: The literal name of the artifact `ci.yml` uploads -- the ONE place this
#: string is spelled; a CI-YAML-shape test pins the upload step's `name:`
#: against this constant, same discipline as `ci_provenance.PROVENANCE_STEP_NAME`.
EXECUTION_EVIDENCE_ARTIFACT_NAME = "traceability-manifest-regenerated"

#: The literal filename `actions/upload-artifact` preserves from the upload
#: step's `path:` (a single known file, not a directory) -- located by this
#: literal name inside the download dir, never `rglob` (round-2 hygiene fix:
#: the upload is a single known file, so the download layout is exact).
_MANIFEST_FILENAME = "test-traceability.json"

#: Artifact download can pull a multi-MB JSON on slow networks. Bounded so a
#: hung `gh` never stalls a caller — same bound `security_findings.py`
#: already uses for its own artifact download (not reused directly: see the
#: module docstring in the design doc for why this is a small, disclosed,
#: local duplication rather than an extension of that file).
_DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class ExecutionEvidence:
    status: str  # "confirmed" | "unavailable" | "error"
    detail: str
    run_id: int | None = None
    # Keyed by the committed manifest's own NAMESPACED top-level key
    # (`NN::FR-XX.YY`, i.e. `committed_manifest["requirements"]`'s own keys)
    # -- NOT by a requirement node's bare `id` field (`FR-XX.YY`). A
    # consumer must look this up by the manifest key it iterated to get the
    # node, never by `node["id"]` (round-3 post-push fix: an earlier
    # `promote_required_layers.plan_promotions` did exactly that mismatch,
    # so no lookup ever matched and every FR silently evaluated as "no CI
    # evidence" regardless of what CI actually confirmed).
    requirements: dict[str, dict] | None = None  # manifest_key -> {"tests": ..., "coverage": ...}


def _download_and_parse_artifact(
    artifact_id: int, *, owner: str, repo: str, cwd: Path,
) -> tuple[dict | None, str | None]:
    """``(parsed_json, None)`` on success, ``(None, detail)`` on any failure.

    Downloads the SPECIFIC artifact named by ``artifact_id`` — never by name
    (external code review, openai/high + glm/medium, P3.5 restart round 2,
    both independently: the round-2 "pick the newest by `created_at`" fix in
    :func:`_find_unexpired_artifact` was dead code with respect to WHICH
    BYTES actually get fetched, because `gh run download {run_id} --name
    ...` re-resolves the name to whatever artifact `gh`/GitHub itself picks
    across every attempt of that run, discarding the caller's own selection
    entirely). Uses the REST "download an artifact" endpoint directly
    (`gh api .../actions/artifacts/{artifact_id}/zip`, raw bytes to a file,
    unzipped locally) so the artifact actually read is the exact one
    :func:`_find_unexpired_artifact` chose — no second, independent
    name-based resolution step for `gh`/GitHub to disagree with.

    Downloads into a tempdir, reads the ONE expected file, and ALWAYS cleans
    up before returning — the read happens INSIDE this function, before
    cleanup, unlike a design that returns a `Path` into an already-deleted
    tempdir."""
    tmpdir = tempfile.mkdtemp(prefix="shipwright-execution-evidence-")
    try:
        zip_path = Path(tmpdir) / "artifact.zip"
        try:
            with zip_path.open("wb") as fh:
                result = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
                    ["gh", "api", f"repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"],
                    cwd=cwd, stdout=fh, stderr=subprocess.PIPE, timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                    shell=False,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"gh api artifact download failed to start: {exc}"
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace")
            return None, f"gh api artifact download exited {result.returncode}: {stderr.strip()[-500:]}"
        try:
            with zipfile.ZipFile(zip_path) as zf:
                try:
                    raw = zf.read(_MANIFEST_FILENAME)
                except KeyError:
                    return None, f"downloaded artifact zip did not contain {_MANIFEST_FILENAME!r}"
        except (OSError, zipfile.BadZipFile) as exc:
            return None, f"could not open downloaded artifact zip: {exc}"
        try:
            return json.loads(raw.decode("utf-8")), None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, f"could not parse downloaded {_MANIFEST_FILENAME!r}: {exc}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _execution_shape_error(raw_requirements: dict, expected_ids) -> str | None:
    """``None`` if every requirement in ``expected_ids`` has a `tests`/
    `coverage` shape `lib.layer_promotion.evaluate_fr` can consume without
    crashing AND both keys are genuinely PRESENT (not merely defaulted);
    else a human-readable detail naming the first violation.

    Runs against the RAW, un-normalized artifact requirement nodes —
    BEFORE any `node.get("tests") or {}`-style defaulting (external code
    review, openai/medium + glm/low, P3.5 restart round 2, both
    independently: validating the ALREADY-normalized `{}` fallback cannot
    tell "genuinely empty" apart from "missing/deleted/truncated", so a
    partially-corrupted or truncated upload — the very thing `ci.yml`'s
    `continue-on-error: true` on this step makes possible — silently
    resolved `confirmed` with empty `requirements`, i.e. every affected FR
    degrading to an ordinary skip instead of the required `error`). Checked
    only for ``expected_ids`` — the committed manifest's own requirement
    IDs, already proven present in the artifact by the caller's
    `structural_diff` check — so a requirement the artifact never claimed
    to cover in the first place is not treated as "missing" here.

    `evaluate_fr`'s own accessors (`(tests or {}).items()`, `for link in
    links`, `coverage.items()`) are not defensive against a non-dict
    `coverage`/`tests` or a non-list `tests[layer]`, and would raise deep
    inside the locked promotion span rather than surfacing here as a clean
    `error`. This is a pre-flight allowlist check, not a full schema
    validator — it only rules out the specific shapes those accessors
    cannot tolerate, mirroring how much `evaluate_fr` itself already
    assumes (e.g. it already tolerates a non-dict `link` item via its own
    `isinstance` guard, so this does not re-check that)."""
    for req_id in expected_ids:
        node = raw_requirements.get(req_id)
        if not isinstance(node, dict):
            return f"{req_id!r}: requirement node is {type(node).__name__}, expected an object"
        if "coverage" not in node:
            return f"{req_id!r}: coverage is missing from the artifact"
        coverage = node["coverage"]
        if not isinstance(coverage, dict):
            return f"{req_id!r}: coverage is {type(coverage).__name__}, expected an object"
        if "tests" not in node:
            return f"{req_id!r}: tests is missing from the artifact"
        tests = node["tests"]
        if not isinstance(tests, dict):
            return f"{req_id!r}: tests is {type(tests).__name__}, expected an object"
        for layer, links in tests.items():
            if not isinstance(links, list):
                return f"{req_id!r}: tests[{layer!r}] is {type(links).__name__}, expected a list"
    return None


def _find_unexpired_artifact(artifacts: list[Any], artifact_name: str) -> dict | None:
    """The NEWEST unexpired match by `created_at` — never merely the first
    entry the Artifacts API happens to return (external code review, openai/
    high, P3.5 restart round 2: a re-run can leave more than one artifact
    with this name under the same `run_id`, one per attempt that reached the
    upload step; `gh run download`'s own "last-writer-wins" behavior on a
    name collision is exactly the ordering this picks BY HAND, so a caller
    reading only the first list entry cannot depend on that assumption
    silently continuing to hold). This narrows, but does not by itself close,
    the cross-attempt exposure the content-binding check (`source_commit` +
    `structural_diff`) already partially covers — see the module docstring's
    Known Limitations for the honest remainder: two attempts of the SAME
    commit share `source_commit` and can share `structural_diff() == ""`
    even when their `tests`/`coverage` values disagree (e.g. a flake healed
    or worsened between attempts), so this defends against USING THE WRONG
    COMMIT's evidence, not against picking between two real runs of the
    right one. Malformed/missing `created_at` sorts last (empty string),
    never crashes."""
    candidates = [
        a for a in artifacts
        if isinstance(a, dict) and a.get("name") == artifact_name and not a.get("expired")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda a: a.get("created_at") or "")


def resolve_execution_evidence(
    commit: str, *, committed_manifest: dict, project_root: Path | str,
    workflow_file: str = "ci.yml", artifact_name: str = EXECUTION_EVIDENCE_ARTIFACT_NAME,
) -> ExecutionEvidence:
    """Was `commit`'s per-requirement `tests`/`coverage` evidence produced by
    the exact CI run `resolve_ci_verification` already trusts for structure?

    `committed_manifest` is the ALREADY-PARSED, commit-pinned manifest the
    caller read (never re-read here) — used only for the content-binding
    structural comparison against the downloaded artifact."""
    verification = resolve_ci_verification(commit, project_root=project_root, workflow_file=workflow_file)
    if verification.status in ("no_record", "not_verified"):
        return ExecutionEvidence(
            "unavailable",
            f"structural CI verification is {verification.status}: {verification.detail}",
            verification.run_id, None,
        )
    if verification.status == "error":
        return ExecutionEvidence(
            "error", f"structural CI verification could not complete: {verification.detail}",
            verification.run_id, None,
        )

    run_id = verification.run_id
    root = Path(project_root)
    owner_repo_str = github_api.owner_repo(root)
    if owner_repo_str is None or "/" not in owner_repo_str:
        return ExecutionEvidence("error", "could not resolve owner/repo from the origin remote", run_id, None)
    owner, repo = owner_repo_str.split("/", 1)

    artifacts_data = _gh_api(f"repos/{owner}/{repo}/actions/runs/{run_id}/artifacts?per_page=100", cwd=root)
    if not isinstance(artifacts_data, dict) or not isinstance(artifacts_data.get("artifacts"), list):
        return ExecutionEvidence("error", "could not list artifacts for the verified run", run_id, None)

    match = _find_unexpired_artifact(artifacts_data["artifacts"], artifact_name)
    if match is None:
        return ExecutionEvidence(
            "unavailable", f"no unexpired {artifact_name!r} artifact found on run {run_id}",
            run_id, None,
        )
    artifact_id = match.get("id")
    if not isinstance(artifact_id, int):
        return ExecutionEvidence(
            "error", f"selected artifact is missing a valid numeric 'id' field: {match.get('id')!r}",
            run_id, None,
        )

    artifact, download_error = _download_and_parse_artifact(artifact_id, owner=owner, repo=repo, cwd=root)
    if artifact is None:
        return ExecutionEvidence("error", f"selected artifact could not be retrieved: {download_error}", run_id, None)
    if not isinstance(artifact, dict):
        return ExecutionEvidence("error", "downloaded artifact is not a JSON object", run_id, None)

    if artifact.get("source_commit") != commit:
        return ExecutionEvidence(
            "error",
            f"downloaded artifact's source_commit {artifact.get('source_commit')!r} does not "
            f"match the resolved commit {commit!r} -- refusing to trust a possible cross-attempt "
            "artifact mismatch",
            run_id, None,
        )

    # Validated BEFORE `structural_diff` (round-3 post-push fix, code-reviewer
    # medium): `_structural_view` unconditionally calls
    # `data["requirements"].items()` -- a malformed top-level `requirements`
    # (e.g. a list, from a corrupted/adversarial upload) raised an uncaught
    # `AttributeError` here when this guard ran only AFTER the call below,
    # breaking this function's own documented three-outcome
    # (confirmed/unavailable/error) contract. `AttributeError` is also added
    # to the caught tuple below as belt-and-braces, since a malformed
    # per-requirement NODE (not the top-level dict) can raise the same way
    # one level deeper, inside `_structural_view`'s per-node `.items()`.
    raw_requirements = artifact.get("requirements")
    if not isinstance(raw_requirements, dict):
        return ExecutionEvidence("error", "downloaded artifact's 'requirements' is not an object", run_id, None)

    try:
        diff = structural_diff(committed_manifest, artifact)
    except (KeyError, TypeError, AttributeError) as exc:
        return ExecutionEvidence("error", f"downloaded artifact has an unexpected shape: {exc}", run_id, None)
    if diff:
        return ExecutionEvidence(
            "error",
            "downloaded artifact structurally disagrees with the committed manifest -- "
            "refusing to trust a possible cross-attempt artifact mismatch",
            run_id, None,
        )

    expected_ids = (committed_manifest.get("requirements") or {}).keys()
    shape_error = _execution_shape_error(raw_requirements, expected_ids)
    if shape_error is not None:
        return ExecutionEvidence(
            "error", f"downloaded artifact's execution-tier shape is invalid: {shape_error}", run_id, None,
        )

    requirements = {
        req_id: {"tests": raw_requirements[req_id]["tests"], "coverage": raw_requirements[req_id]["coverage"]}
        for req_id in expected_ids
    }
    return ExecutionEvidence(
        "confirmed", f"execution evidence confirmed from verified run {run_id}", run_id, requirements,
    )


__all__ = ["EXECUTION_EVIDENCE_ARTIFACT_NAME", "ExecutionEvidence", "resolve_execution_evidence"]
