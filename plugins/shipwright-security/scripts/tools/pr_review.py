#!/usr/bin/env python3
"""Tier-3 PR reviewer — OpenRouter-backed code review for a single PR.

Invoked by `.github/workflows/pr-review.yml` for Tier-3 PRs only (external
contributors, sensitive paths, or the `needs-review` label). Tier 1/2 PRs
(iterate branches + Sven's manual PRs) are NEVER reviewed here — the tier
filter lives in the workflow's `decide` job and `/shipwright-iterate` Step 8
already covers them in the local subscription. See B4.5 in
`Spec/early-access-readiness-plan.md`.

Steps: fetch the PR diff (`gh pr diff`) → load system+user prompts → POST to
OpenRouter (`/chat/completions`, strict JSON) → parse the decision → post a
rendered comment + (best-effort) review state → exit per decision.

Usage:
    uv run scripts/tools/pr_review.py \
        --pr-number 42 --repo owner/repo \
        --prompt-dir shared/prompts/pr_reviewer

Environment:
    OPENROUTER_API_KEY          required — OpenRouter credential (never logged)
    SHIPWRIGHT_PR_REVIEW_MODEL  optional — model id (default below)
    GH_TOKEN / GITHUB_TOKEN     used by the `gh` CLI for diff + comment + review

Exit codes:
    0  decision approve | comment  (also: a truncated/partial review never blocks)
    1  decision block
    2  error (no key, OpenRouter down/rate-limited, JSON parse failure, unknown
       decision, prompt/diff fetch failure)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
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
    decision_to_exit,
    load_prompts,
    parse_review_response,
    render_comment,
    truncate_diff,
)

__all__ = [
    "EXIT_BLOCK", "EXIT_ERROR", "EXIT_OK", "MAX_DIFF_CHARS", "_redact",
    "build_messages", "decision_to_exit", "load_prompts", "parse_review_response",
    "render_comment", "truncate_diff", "DEFAULT_MODEL", "OPENROUTER_URL",
]


def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _post_openrouter(api_key: str, model: str, messages: list[dict], timeout: int) -> dict:
    """POST the chat-completion request to OpenRouter and return the parsed JSON body.

    Uses stdlib urllib so the script carries no third-party HTTP dependency — it
    runs under whatever environment `uv run` resolves on the CI runner.
    """
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers (optional, recommended).
            "HTTP-Referer": "https://github.com/svenroth-ai/shipwright",
            "X-Title": "Shipwright PR Review",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https URL
        body = resp.read().decode("utf-8")
    return json.loads(body)


def call_openrouter(api_key: str, model: str, messages: list[dict], timeout: int = 120) -> str:
    """Call OpenRouter and return the assistant message content string.

    Raises RuntimeError on transport failure (HTTP error, timeout) or an
    unexpected response shape — the caller maps that to exit 2.
    """
    try:
        data = _post_openrouter(api_key, model, messages, timeout)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — best-effort body read
            pass
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"OpenRouter request failed: {e}") from e
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected OpenRouter response shape: {e}") from e


def fetch_pr_diff(pr_number: int, repo: str) -> str:
    """Fetch the unified diff for a PR via the `gh` CLI."""
    proc = subprocess.run(
        ["gh", "pr", "diff", str(pr_number), "--repo", repo],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"`gh pr diff` failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def post_pr_comment(pr_number: int, repo: str, body: str) -> None:
    """Post the review comment to the PR via `gh pr comment` (stdin body)."""
    proc = subprocess.run(
        ["gh", "pr", "comment", str(pr_number), "--repo", repo, "--body-file", "-"],
        input=body,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"`gh pr comment` failed ({proc.returncode}): {proc.stderr.strip()}")


def post_pr_review_state(pr_number: int, repo: str, decision: str, summary: str) -> None:
    """Post a review state (best-effort): block -> request-changes, else -> comment.

    Deliberately never `--approve` (a bot approving its own org's PR is noise and
    can fail). The merge gate is the workflow job's exit code, not this state.
    """
    norm = (decision or "").strip().lower()
    flag = "--request-changes" if norm == "block" else "--comment"
    body = summary or "Automated Tier-3 review."
    subprocess.run(
        ["gh", "pr", "review", str(pr_number), "--repo", repo, flag, "--body", body],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _build_pr_meta(pr_number: int, repo: str, truncated: bool) -> str:
    return f"Repository: {repo}\nPR number: {pr_number}\nDiff truncated: {truncated}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tier-3 OpenRouter PR reviewer")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number to review")
    parser.add_argument("--repo", required=True, help="owner/repo slug")
    parser.add_argument(
        "--prompt-dir",
        default="shared/prompts/pr_reviewer",
        help="Directory holding the `system` and `user` prompt files",
    )
    parser.add_argument("--timeout", type=int, default=120, help="OpenRouter timeout (seconds)")
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

    diff, truncated = truncate_diff(diff)
    pr_meta = _build_pr_meta(args.pr_number, args.repo, truncated)
    messages = build_messages(system_prompt, user_prompt, diff, pr_meta)

    est_tokens = (len(system_prompt) + len(user_prompt) + len(diff)) // 4
    print(
        f"[pr_review] reviewing PR #{args.pr_number} with {model} "
        f"(~{est_tokens} input tokens, truncated={truncated})",
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
    body = render_comment(review, model=model, truncated=truncated)

    # Comment + review state are best-effort: a posting failure must not flip the
    # gate, which reflects the review DECISION (the exit code) not the side-effect.
    try:
        post_pr_comment(args.pr_number, args.repo, body)
    except Exception as e:  # noqa: BLE001
        print(_redact(f"[pr_review] failed to post PR comment: {e}", api_key), file=sys.stderr)
    try:
        post_pr_review_state(args.pr_number, args.repo, decision, str(review.get("summary", "")))
    except Exception as e:  # noqa: BLE001
        print(_redact(f"[pr_review] failed to post review state: {e}", api_key), file=sys.stderr)

    if truncated:
        # Partial review: never auto-block, surface for human review.
        print("[pr_review] diff was truncated — exiting 0 (comment-state).", file=sys.stderr)
        return EXIT_OK

    exit_code = decision_to_exit(decision)
    if exit_code == EXIT_ERROR:
        print(f"[pr_review] unknown decision '{decision}' — treating as error.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())
