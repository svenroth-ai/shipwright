"""record — project a target into a replayable fixture (NETWORK for real repos).

``project_fixture`` is the shared core: given a resolved target it runs the real
projection (``grade_context_captured``) and serialises the pre-engine
``GradeInputs`` + report-extras + a redacted gh audit log into a versioned
fixture dict. It is deliberately transport-agnostic so the hermetic tests can
drive it against a *local* synthetic repo with no network, while ``record_repo``
adds the remote fetch@SHA for the real empirical manifest (remote-URL-only, so the
real runner never widens its accepted input to filesystem paths).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from gh_bridge import GhRunner, run_gh
from git_exec import remote_url
from grade_inputs_projector import grade_context_captured
from network_policy import resolve_network_policy
from repo_context import RepoContext
from resolve_target import ResolvedTarget

from calibration import SCHEMA_VERSION
from fetch import RecordingGh, open_target_at_sha
from replay import FIXTURES_DIR, record


class RecordError(RuntimeError):
    """A target could not be recorded into a replayable fixture."""


def project_fixture(
    target: ResolvedTarget,
    *,
    name: str,
    sha: str,
    allow_network: bool,
    gh: GhRunner | None = None,
) -> dict:
    """Project ``target`` → a versioned, JSON-serialisable fixture dict.

    Raises :class:`RecordError` if the target grades as *authoritative* (it owns a
    ``.shipwright/`` source) — the empirical set expects external cold repos, and
    caching a report-level shape for that case would diverge from the
    ``GradeInputs`` replay path. The recorder rejects it loudly instead.
    """
    gh = gh or run_gh
    context = RepoContext(target)
    policy = resolve_network_policy(
        allow_network=allow_network, allow_private=False,
        remote_url=remote_url(target.local_path), gh=gh)
    computation = grade_context_captured(context, policy=policy, gh=gh)
    if computation.grade_inputs is None or computation.report_extras is None:
        raise RecordError(
            f"{name}: graded as authoritative (a .shipwright/ source is present); "
            "the empirical calibration set expects external, cold OSS repos")

    # The target lives in a throwaway `.../repo` checkout, so the projector's
    # target_display is the temp-dir name — stamp the canonical owner/repo over it
    # so the gallery report is titled correctly. Build a COPY (never mutate the
    # frozen GradeComputation's dict — respect the immutability contract).
    report_extras = {**computation.report_extras, "target_display": name}
    audit = list(getattr(gh, "log", []))
    return {
        "schema_version": SCHEMA_VERSION,
        "repo": name,
        "sha": sha,
        "grade_inputs": dataclasses.asdict(computation.grade_inputs),
        "report_extras": report_extras,
        "gh_audit": audit,
    }


def record_repo(
    entry: dict,
    *,
    allow_network: bool = True,
    cache_dir: Path = FIXTURES_DIR,
) -> tuple[dict, Path]:
    """Fetch ``entry`` at its pinned SHA, project it, and write the fixture.

    Remote-URL-only: the manifest entry's ``url`` is fetched at ``pinned_sha`` into
    a throwaway checkout (never a local path). Returns ``(fixture, path)``.
    """
    name = str(entry["name"])
    url = str(entry["url"])
    sha = str(entry["pinned_sha"])
    gh = RecordingGh(run_gh)
    with open_target_at_sha(url, sha) as target:
        fixture = project_fixture(
            target, name=name, sha=sha, allow_network=allow_network, gh=gh)
    path = record(f"{name}@{sha}", fixture, cache_dir=cache_dir)
    return fixture, path
