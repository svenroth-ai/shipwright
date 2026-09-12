"""Local preflight diff source + no-side-effect verdict reporting.

Backs `pr_review.py --base`/`--diff-file`: the same review logic the
required CI gate (FR-01.17, `.github/workflows/pr-review-run.yml`) runs
against a PUSHED PR, run earlier against a local branch that has not been
pushed or opened as a PR at all.

A PREFLIGHT, NEVER A WAIVER (trg-33d30377 is the failure mode this
guards against): nothing in this module posts a PR comment, posts a review
state, or dismisses a stale verdict, and nothing it writes is ever read by
`review_record_tier.decide()` — a local run cannot become a self-issued
permission slip for the CI gate it precedes. It only prints.

`--diff-file` sends the named file's content to the external review model
VERBATIM — unlike `--base`, an operator can point it at any local path, so
it is the caller's responsibility to never name a file that may contain a
secret (code review, 2026-09-12).

`--base <ref>` MUST NAME A REF YOU ALREADY TRUST as much as your own working
tree. `build_local_diff` stages it with `git add -A` in a private temporary
index — see that function's own docstring for why that step, unlike the
diff step after it, can execute a clean/filter driver `.gitattributes`
declares, using whatever `[filter "<name>"]` command is already configured
in YOUR OWN git config (local or global). This repo configures none, and no
Shipwright-scaffolded project does either, but a maintainer's personal
global config might (e.g. git-lfs) — checking out and reviewing an
unfamiliar contributor's branch before merge is exactly the case where that
config and that branch's `.gitattributes` could combine (dogfooded finding,
external gpt-5.6-luna run, 2026-09-12). No `git` flag disables this without
also losing untracked-file coverage (a hard requirement here), so this is a
documented, not eliminated, risk: know what filters your own config defines
before pointing `--base` at anything you have not already read.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404 - fixed argv, shell=False, no user-controlled input
import sys
import tempfile
from pathlib import Path

from pr_review_lib import safe_path
from pr_review_render import strip_display_unsafe

__all__ = ["PREFLIGHT_BANNER", "build_local_diff", "list_diff_paths", "log_files_sent",
           "post_local_result", "read_diff_file", "resolve_diff_mode"]

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*?) b/", re.MULTILINE)

PREFLIGHT_BANNER = (
    "[pr_review] LOCAL PREFLIGHT — advisory only. No PR comment, no review "
    "state, no recorded review pass. This cannot satisfy the required CI "
    "PR-review gate; that gate still reviews the pushed PR independently."
)

_GIT_CONTEXT_KEYS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def _controlled_git_env(index_file: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in _GIT_CONTEXT_KEYS:
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_INDEX_FILE"] = str(index_file)
    return env


def build_local_diff(project_root: Path, base_ref: str) -> tuple[str, str]:
    """One coherent merge-base -> working-tree diff: same private-temporary-
    index technique as F0's diff-coverage gate
    (`shared/scripts/tools/suite_worktree_diff.build_worktree_diff`) — a
    scratch index starts at the merge base and stages the working tree
    (``git add -A``: includes untracked, excludes ignored), so an unstaged or
    never-`git add`-ed file is reviewed too. Diffs against the MERGE BASE, not
    `base_ref`'s tip, so another PR that landed on `base_ref` meanwhile is
    never attributed to this change. Never touches the real index or HEAD;
    the working tree is read, never written.

    Untracked-but-not-ignored content is included BY DESIGN (the three
    findings this preflight exists to catch earlier all lived in exactly that
    file class) — the caller is expected to print the resulting path list
    (`list_diff_paths`) before sending it anywhere, so an operator running
    this by hand on a dirty tree sees what left the machine. In the
    `/shipwright-iterate` F11 wiring this runs AFTER F6 has committed
    everything, so the working tree is already clean and this is a
    theoretical exposure there, not a practical one.

    `--no-ext-diff` and `--no-textconv` keep the diff step non-executing: a
    diff/textconv driver configured via `.gitattributes` could otherwise run
    an arbitrary local command while comparing blobs (external review,
    2026-09-12). The preceding `git add -A` has no such flag and does run
    clean/filter drivers if configured — acceptable here because this is the
    caller's own already-trusted working tree (in the F11 wiring, run after
    F6 has committed), never an untrusted checkout.

    Returns ``(diff_text, error)``; ``error`` is empty on success.
    """
    root = Path(project_root).resolve()
    with tempfile.TemporaryDirectory(prefix="pr-review-local-") as tmp:
        index = Path(tmp) / "index"
        env = _controlled_git_env(index)

        def _git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(  # nosec B603 - fixed argv, shell=False
                ["git", "-C", str(root), *args], cwd=str(root), env=env,
                capture_output=True, text=True, errors="replace",
                shell=False, timeout=120)

        base = _git("merge-base", base_ref, "HEAD")
        if base.returncode != 0 or not (base.stdout or "").strip():
            detail = (base.stderr or base.stdout or "").strip()
            return "", (f"could not resolve merge base against {base_ref}: {detail}".rstrip()
                        or f"could not resolve merge base against {base_ref}")
        base_sha = base.stdout.strip()
        for git_args in (("read-tree", base_sha), ("add", "-A", "--", ".")):
            proc = _git(*git_args)
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                return "", f"git {' '.join(git_args)} failed: {detail}".rstrip()
        diff = _git("diff", "--cached", "--no-ext-diff", "--no-textconv",
                    "--binary", "--full-index", base_sha, "--")
        if diff.returncode != 0:
            detail = (diff.stderr or diff.stdout or "").strip()
            return "", f"could not build local diff: {detail}".rstrip()
        return diff.stdout or "", ""


def list_diff_paths(diff: str) -> list[str]:
    """Every file path named by a `diff --git a/<path> b/...` header, in
    order. Lets the caller print exactly what is about to leave the machine
    (external review, 2026-09-12) before a local diff — which, unlike a
    pushed PR's, may include untracked content — is sent to the model."""
    return _DIFF_HEADER_RE.findall(diff)


def log_files_sent(diff: str) -> None:
    """Print exactly which file sections `diff` is about to send to the
    model — the transparency line `list_diff_paths` exists for (external
    review, 2026-09-12), split out of `pr_review.main()` to keep that file
    under the source-size guideline."""
    sent = [safe_path(p) for p in list_diff_paths(diff)]
    shown = ", ".join(sent[:50]) + (f" (+{len(sent) - 50} more)" if len(sent) > 50 else "")
    print(f"[pr_review] LOCAL PREFLIGHT sending {len(sent)} file section(s): "
          f"{shown or 'none'}", file=sys.stderr)


def read_diff_file(path: Path) -> str:
    """Read a pre-built diff from disk as bytes, decoded explicitly.

    Mirrors `pr_review_gh.fetch_pr_diff`: `text=True`/default-open would run
    CPython's universal-newline translation and rewrite a lone CR to LF
    before any parser sees it, and a `diff --git` section boundary depends on
    that byte staying LF-only.
    """
    return path.read_bytes().decode("utf-8", "replace")


def resolve_diff_mode(pr_number: int | None, repo: str | None,
                      base: str | None, diff_file: Path | None) -> tuple[bool, str]:
    """Validate the CI-mode vs. local-preflight argument combination.

    Returns ``(local_mode, error)``; a non-empty ``error`` means the caller
    (`pr_review.main`) must refuse to run — returning `EXIT_USAGE`, never
    `EXIT_ERROR` — rather than guess which mode was intended. Kept as its own
    exit code so a misconfigured invocation can never read as the advisory
    "reviewer infra unavailable" case (see `EXIT_USAGE`'s docstring).
    """
    ci_mode = pr_number is not None or repo is not None
    # `argparse(type=Path)("")` -> `Path(".")`, which is truthy (Path has no
    # __bool__) — `if s` alone would accept an empty --diff-file as a valid
    # source (external review, 2026-09-12).
    local_sources = [s for s in (base, diff_file) if s and str(s).strip() not in ("", ".")]
    if ci_mode and local_sources:
        return False, ("--pr-number/--repo (CI mode) cannot be combined with "
                       "--base/--diff-file (local preflight)")
    if ci_mode:
        if pr_number is None or repo is None:
            return False, "--pr-number and --repo must be given together"
        return False, ""
    if len(local_sources) != 1:
        return False, ("exactly one of --base or --diff-file is required for the local "
                       "preflight (or pass --pr-number/--repo for CI mode)")
    return True, ""


def post_local_result(decision: str, exit_code: int, review: dict, body: str) -> int:
    """The local-mode analogue of `pr_review_verdict.finish_decision`: there
    is no PR to comment on, so print the fully rendered review to stdout and
    return `exit_code` unchanged. No posting, no dismissal — see module
    docstring.

    `render_comment`'s `summary` field is the one piece of `body` that
    bypasses its own control-character stripping (it is written as Markdown
    for GitHub, which is inert there) — unlike a PR comment, this reaches a
    real terminal, so `strip_display_unsafe` closes that here (code review,
    2026-09-12: relevant given `--diff-file` can point at untrusted content).
    """
    print(PREFLIGHT_BANNER, file=sys.stderr)
    print(strip_display_unsafe(body))
    summary_excerpt = str(review.get("summary", ""))[:300]
    print(f"[pr_review] LOCAL decision={decision} exit={exit_code} — {summary_excerpt!r}",
          file=sys.stderr)
    return exit_code
