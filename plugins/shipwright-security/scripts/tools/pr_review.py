#!/usr/bin/env python3
"""Tier-3 PR reviewer — OpenRouter-backed code review for a single PR.

Invoked by `.github/workflows/pr-review-run.yml` (stage 2 of the two-stage
review, FR-01.17) for Tier-3 PRs only (external contributors, sensitive paths,
or the `needs-review` label). Tier 1/2 PRs (iterate branches + the maintainer's
own hand-opened PRs) are NEVER reviewed here — the tier filter lives in stage
2's `tier` step, which reads labels/author/changed-paths from the API in
default-branch code, and `/shipwright-iterate` Step 8 already covers them in the
local subscription.
Stage 1 runs from the PR head and is never trusted. See B4.5 in
`Spec/early-access-readiness-plan.md`.

Steps: fetch the PR diff (`gh pr diff`) → load system+user prompts → POST to
OpenRouter (`/chat/completions`, strict JSON) → parse the decision → post a
rendered comment + (best-effort) review state → exit per decision.

Usage: pr_review.py --pr-number N --repo owner/repo --prompt-dir shared/prompts/pr_reviewer

Environment:
    OPENROUTER_API_KEY          required — OpenRouter credential (never logged)
    SHIPWRIGHT_PR_REVIEW_MODEL  optional — model id (default below)
    GH_TOKEN / GITHUB_TOKEN     used by the `gh` CLI for diff + comment + review

Exit codes:
    0  decision approve | comment
    1  block — also when nothing/not everything was reviewed (fails closed)
    2  error (no key, OpenRouter down, JSON parse failure, unknown decision)
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

# Pure review-logic helpers live in the lib module (no network / no subprocess)
# so this tool stays small and the logic is unit-testable. Re-exposed here so
# `pr_review.<symbol>` keeps working for callers and tests.
from pr_review_lib import (  # noqa: E402
    EXIT_BLOCK,
    EXIT_ERROR,
    EXIT_OK,
    MAX_DIFF_CHARS,
    _redact,
    build_messages,
    build_pr_meta,
    decision_to_exit,
    filter_generated_paths,
    load_prompts,
    nothing_reviewed_summary,
    parse_review_response,
    render_comment, safe_path,
    truncate_diff,
)
from pr_review_diff_filter import count_sections  # noqa: E402
# The two I/O boundaries each own a module — `gh` subprocess and OpenRouter HTTP.
# Re-exported here so existing call sites and their monkeypatch targets
# (`pr_review.fetch_pr_diff`, `pr_review.call_openrouter`, ...) are unchanged.
from pr_review_gh import (  # noqa: E402
    fetch_pr_diff,
    post_pr_comment,
    post_pr_review_state,
)
from pr_review_openrouter import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    OPENROUTER_URL,
    call_openrouter,
)

# The re-export surface: every name a caller or test is entitled to reach
# through `pr_review.<symbol>`. Kept complete on purpose — a name that is
# imported above but missing here reads as private while tests patch it.
__all__ = [
    "EXIT_BLOCK", "EXIT_ERROR", "EXIT_OK", "MAX_DIFF_CHARS", "_redact",
    "build_messages", "build_pr_meta", "count_sections", "decision_to_exit",
    "fetch_pr_diff", "filter_generated_paths", "load_prompts",
    "nothing_reviewed_summary", "parse_review_response", "post_pr_comment",
    "post_pr_review_state", "render_comment", "safe_path", "truncate_diff",
    "call_openrouter", "DEFAULT_MODEL", "DEFAULT_TIMEOUT", "OPENROUTER_URL"]


def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _post_verdict(args, api_key: str, body: str, decision: str, summary: str) -> None:
    """Post the comment + review state. Best-effort: a posting failure must not
    flip the gate, which reflects the review outcome (the exit code), not the
    side-effect. Shared so every fail-closed path leaves the same trail — a red
    check with no comment tells the reader nothing."""
    for fn, call_args, what in (
        (post_pr_comment, (args.pr_number, args.repo, body), "PR comment"),
        (post_pr_review_state, (args.pr_number, args.repo, decision, summary), "review state"),
    ):
        try:
            fn(*call_args)
        except Exception as e:  # noqa: BLE001
            print(_redact(f"[pr_review] failed to post {what}: {e}", api_key), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tier-3 OpenRouter PR reviewer")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number to review")
    parser.add_argument("--repo", required=True, help="owner/repo slug")
    parser.add_argument(
        "--prompt-dir",
        default="shared/prompts/pr_reviewer",
        help="Directory holding the `system` and `user` prompt files",
    )
    # One default, defined with the transport it belongs to (pr_review_openrouter).
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="OpenRouter timeout (seconds)")
    args = parser.parse_args(argv)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[pr_review] OPENROUTER_API_KEY is not set — cannot review.", file=sys.stderr)
        return EXIT_ERROR
    model = os.environ.get("SHIPWRIGHT_PR_REVIEW_MODEL", DEFAULT_MODEL)

    try:
        system_prompt, user_prompt = load_prompts(args.prompt_dir)
    except OSError as e:
        print(_redact(f"[pr_review] failed to read prompt dir: {e}", api_key), file=sys.stderr)
        return EXIT_ERROR

    try:
        diff = fetch_pr_diff(args.pr_number, args.repo)
    except Exception as e:  # noqa: BLE001 — subprocess / runtime errors are varied
        print(_redact(f"[pr_review] failed to fetch PR diff: {e}", api_key), file=sys.stderr)
        return EXIT_ERROR

    # Drop producer-generated artifacts (compliance MDs, agent-docs, changelog
    # drops, state logs, prior review records — NOT dependency lockfiles, which
    # left this set in iterate-2026-07-27-pr-review-forged-boundary: on an
    # untrusted PR the lockfile is the supply-chain surface)
    # BEFORE the truncation check: they dominate a shipwright PR
    # diff (~82% of chars on PR #310) but carry no reviewable logic, so keeping
    # them would trip the size cap and fail the review closed on ordinary
    # medium+ iterates. The excluded list is surfaced to the model (pr_meta) +
    # humans (comment) — transparent, never silent. See triage trg-e1c554d9.
    diff, excluded = filter_generated_paths(diff)

    # ...but "everything was generated" is not a review. This script runs ONLY
    # when the tier step decided the PR needs one (needs-review label, sensitive
    # path, or external contributor — an ordinary internal churn PR takes the
    # `decide false "internal PR"` branch and never reaches here). So a filtered
    # diff that came back empty means a PR that had to be reviewed was handed to
    # the model as nothing at all — and the system prompt answers an empty diff
    # with `approve` plainly: a green required check over an unread change. The
    # shape that matters is a fork PR touching only producer-generated artifacts.
    # The invariant is "the reviewer saw at least one file section" — NOT the
    # narrower "everything was filtered". An empty fetch, a `gh` body with no
    # `diff --git` header at all, and a fully-filtered PR are the same failure
    # from the model's side.
    if not count_sections(diff):
        summary = nothing_reviewed_summary(excluded)
        # `model=` names who reviewed. On this branch nobody did — we return
        # before call_openrouter — so the footer must not attribute the verdict
        # to a model that was never sent anything.
        _post_verdict(args, api_key,
                      render_comment({"decision": "block", "summary": summary},
                                     model="no model — nothing was sent",
                                     truncated=False,
                                     excluded_generated=excluded), "block", summary)
        print(f"[pr_review] {summary}", file=sys.stderr)
        return EXIT_BLOCK

    reviewed = truncate_diff(diff)
    diff, truncated = reviewed.text, reviewed.incomplete
    missing = {"omitted": reviewed.omitted, "partial": reviewed.partial,
               "unidentified": reviewed.unidentified}
    pr_meta = build_pr_meta(args.pr_number, args.repo, truncated, excluded, **missing)
    try:
        messages = build_messages(system_prompt, user_prompt, diff, pr_meta)
    except ValueError as e:
        # A template that lost a placeholder. Mapped like every other boundary
        # in main() — redacted, EXIT_ERROR — rather than escaping as a raw
        # traceback that happens to exit non-zero.
        print(_redact(f"[pr_review] {e}", api_key), file=sys.stderr)
        return EXIT_ERROR

    est_tokens = (len(system_prompt) + len(user_prompt) + len(diff)) // 4
    print(
        f"[pr_review] reviewing PR #{args.pr_number} with {model} "
        f"(~{est_tokens} input tokens, truncated={truncated}, "
        f"generated-excluded={len(excluded)})",
        file=sys.stderr,
    )

    try:
        raw = call_openrouter(api_key, model, messages, args.timeout)
    except Exception as e:  # noqa: BLE001 — any transport/shape failure is a non-blocking error
        print(_redact(f"[pr_review] OpenRouter call failed: {e}", api_key), file=sys.stderr)
        return EXIT_ERROR

    try:
        review = parse_review_response(raw)
    except ValueError as e:
        print(
            _redact(f"[pr_review] could not parse review JSON: {e}\n--- raw response ---\n{raw}", api_key),
            file=sys.stderr,
        )
        return EXIT_ERROR

    decision = str(review.get("decision", ""))
    # A truncated diff is a PARTIAL review — we never saw the whole change. For a
    # required gate on an untrusted (external/sensitive) PR, neither auto-passing
    # nor trusting the partial verdict is safe: a large diff must not be able to
    # BYPASS review by exceeding the size cap. Fail CLOSED — force a
    # request-changes state + non-zero exit (below) so a human must review; a
    # maintainer can apply the `skip-pr-review` label after a manual look. The red
    # required check is also what lets the gh-pr-ci triage producer surface the PR
    # as a tracked follow-up. (Until iterate-2026-06-17-pr-review-truncation-
    # failclosed this returned EXIT_OK — a silent size-bypass of the gate.)
    effective_decision = "block" if truncated else decision
    body = render_comment(
        review, model=model, truncated=truncated, excluded_generated=excluded, **missing)

    _post_verdict(args, api_key, body, effective_decision,
                  str(review.get("summary", "")))

    if truncated:
        # Partial review fails closed — needs human (see comment above).
        # Sanitised like every sink: a raw Git path can carry terminal escapes.
        unseen = ", ".join(safe_path(p) for p in reviewed.omitted + reviewed.partial)
        extra = f" (+{reviewed.unidentified} unnamed)" if reviewed.unidentified else ""
        print(
            "[pr_review] diff exceeded the review limit — failing closed (needs human "
            f"review). Not reviewed in full: {unseen or 'unidentifiable'}{extra}. Apply "
            "the `skip-pr-review` label after a manual review to override.",
            file=sys.stderr)
        return EXIT_BLOCK

    exit_code = decision_to_exit(decision)
    if exit_code == EXIT_ERROR:
        print(f"[pr_review] unknown decision '{decision}' — treating as error.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())
