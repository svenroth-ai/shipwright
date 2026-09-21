"""Codex-CLI transport for one internal review role.

The AC1 dispatch target when the driving harness cannot spawn an independent
Agent-tool subagent for spec-reviewer/code-reviewer/doubt-reviewer/
opus-plan-reviewer — either because this session IS Codex CLI itself, or its
own model has been redirected to a non-Anthropic backend. See
``.shipwright/planning/iterate/iterate-2026-09-13-codex-internal-review-transport.md``
for the full design and its Internal Plan Review findings, several of which
are load-bearing here:

* **Env is an explicit allowlist, never inherited** (finding #2, HIGH) —
  ``subprocess.run`` would otherwise hand the full ambient process
  environment (``OPENROUTER_API_KEY``/``OPENAI_API_KEY``/``GITHUB_TOKEN``/
  ``ANTHROPIC_API_KEY``) to an agentic, network-capable child process.
  ``--sandbox read-only`` blocks writes only, never reads or network.
* **Prompt is not the agent ``.md`` file verbatim** (finding #9, MEDIUM) —
  frontmatter is stripped and a transport addendum states what is
  unavailable in this standalone context (no writes, no
  ``behavior_snapshot.py``, no nested external-LLM call, no extra network)
  plus the untrusted-repo-content injection boundary.
* **Unique temp path, validated, THEN copied to the canonical basename**
  (finding #8) — the uniqueness is for collision-avoidance across the three
  sequential role calls, never a second payload-naming convention; an
  unvalidated file is never handed to ``record_review_pass.py``.
* **``max_retries=0`` by default** (finding #10) — an agentic retry on an
  already-large per-role timeout would double the worst case across three
  sequential role calls; a caller name has to opt in deliberately to retry.

**Accepted residual risk (doubt-reviewer, MEDIUM, 2026-09-17):** the env
scrub stops ambient *secrets* from reaching the child process, but
``--sandbox read-only`` — unlike the fully isolated, empty-scratch-``--cd``
shipped external-review leg — still lets the model *read* anything under
``worktree_root``, including dotfiles and credential caches the scrub itself
excludes from the environment (e.g. ``~/.ssh``, ``~/.aws/credentials``,
``.env*`` in the repo). A prompt-injected diff could ask the model to surface
such content inside a schema's free-text fields, which are shape- but not
content-constrained, and those fields are then written to a git-tracked
evidence file this repo commits and pushes. This is a known trade-off of
reviewing the real worktree (required so the reviewer can actually read the
change) rather than an isolated copy, not an oversight; it is not currently
mitigated beyond the injection-boundary instruction in the prompt itself.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ALWAYS package-qualified -- no bare-try-first fallback for ANY import in this
# module. codex_review_model_resolution.py unconditionally depends on
# model_tier_config.py, which only supports package-qualified loading (see
# that module's own comment); since this module in turn unconditionally
# imports codex_review_model_resolution, it can only ever finish loading with
# `shared/scripts` already on sys.path -- so a bare-try for the three imports
# below would be dead code, not a real fallback, the same constraint already
# collapsed one layer in (local PR-review preflight BLOCK,
# iterate-2026-09-19-codex-reviewer-session-override). Every real importer
# already puts `shared/scripts` on sys.path (grepped: review_via_codex.py,
# every test file importing `from lib import codex_review_transport`).
from lib.codex_review_model_resolution import resolve_codex_review_model
from lib.codex_review_prompt import (
    INJECTION_BOUNDARY,
    build_prompt,
    scrubbed_env,
    strip_frontmatter,
    validate_against_schema,
)
from lib.codex_review_roles import (
    CODEX_REVIEW_REASONING_EFFORT,
    CODEX_REVIEW_SANDBOX_MODE,
    REASONING_EFFORT_ROLES,
    ROLE_CANONICAL_BASENAMES,
    ROLE_SCHEMAS,
    transport_note_for,
)
from lib.external_review_default_legs import _resolve_codex_binary, is_codex_available

# The three REASONING_EFFORT_ROLES re-exports are listed below too -- both test modules read them off `transport.*` (code-reviewer, low, 2026-09-20).
__all__ = [
    "CODEX_REVIEW_MAX_RETRIES",
    "CODEX_REVIEW_MODEL",
    "CODEX_REVIEW_REASONING_EFFORT",
    "CODEX_REVIEW_SANDBOX_MODE",
    "CODEX_REVIEW_TIMEOUT_SECONDS",
    "REASONING_EFFORT_ROLES",
    "ROLE_CANONICAL_BASENAMES",
    "ROLE_SCHEMAS",
    "CodexReviewTransportError",
    "INJECTION_BOUNDARY",
    "build_prompt",
    "run_codex_review",
    "scrubbed_env",
    "strip_frontmatter",
]

#: Matches AGENTS.md's own operating policy (Internal Plan Review, resolved
#: 2026-09-17: kept same-vendor-by-design, mirroring Claude's own
#: opus-reviews-sonnet internal-cascade split) — distinct from `models.codex`
#: (`gpt-5.6-terra`, execution/finalization). The last-resort fallback when
#: nothing else names a value — see `codex_review_model_resolution.py` for
#: the full precedence chain (`model` argument > session env var > project
#: config > this constant) and the `_CODEX_MODEL_SLUG_PATTERN` allowlist
#: below for why an override can never reach `codex exec`'s argv unvalidated
#: (raise-before-launch lock, reinstated iterate-2026-09-18-codex-review-tier-config
#: after AC2 removed and this run's own predecessor found it insufficiently
#: enforced; see each run's own ADR).
CODEX_REVIEW_MODEL = "gpt-5.6-sol"

#: Syntactic allowlist for a Codex model slug — the ONLY shipwright-side
#: validation (no live catalog call; see the mini-plan's "Simplification
#: after architecture review"). Rejects shell metacharacters (`&`, `|`, `^`,
#: `"`, spaces) that would matter in a shell-interpreted context, even though
#: `subprocess.run` passes this as a single argv element, never through a
#: shell. A syntactically-valid but nonexistent slug is not caught here —
#: Codex's own launch failure IS the semantic check. `\A`/`\Z`, never `^`/`$`
#: — `$` matches before a trailing newline regardless of match method, so
#: `\Z` closes that gap at the pattern itself rather than depending on every
#: caller using `.fullmatch()` (doubt-reviewer MEDIUM, 2026-09-18).
_CODEX_MODEL_SLUG_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
#: Matches `external_review_default_legs.CODEX_DEFAULT_TIMEOUT_SECONDS` — one
#: role's worst case. The three-role sequential cascade this feeds (AC1's
#: dispatch sites) worst-cases at 3x = 1800s; the shell/tool call invoking
#: `review_via_codex.py` must be issued in a way that tolerates that (e.g. a
#: backgroundable call), not a short-lived foreground timeout (finding #10).
CODEX_REVIEW_TIMEOUT_SECONDS = 600
CODEX_REVIEW_MAX_RETRIES = 0


class CodexReviewTransportError(RuntimeError):
    """Raised for a caller mistake (e.g. an unknown role) — never for a
    runtime transport failure, which is reported in the returned dict so an
    orchestrating skill step can record `not_run` instead of crashing."""


def run_codex_review(
    role: str,
    worktree_root: Path,
    prompt: str,
    out_dir: Path,
    *,
    model: str | None = None,
    timeout: float = CODEX_REVIEW_TIMEOUT_SECONDS,
    max_retries: int = CODEX_REVIEW_MAX_RETRIES,
) -> dict[str, Any]:
    """Answer one review role via ``codex exec``.

    Returns ``{"status": "completed", "transport": "codex", "model": <str>, "transport_note": <str>,
    "canonical_path": <str>}`` on success (``transport_note`` via :func:`codex_review_roles.transport_note_for`
    -- also names effort/sandbox for a ``REASONING_EFFORT_ROLES`` role), or ``{"status": "error", "transport":
    "codex", "model": <str>, "reason": <str>}`` (no ``transport_note`` key) — never raises for a *runtime*
    failure, so the caller can record the review pass ``not_run`` with a concrete reason (finding #12) rather
    than crashing the whole run. A caller mistake (unknown role, invalid ``timeout``/``max_retries``, or a
    ``model`` that fails the syntactic allowlist) raises ``CodexReviewTransportError`` instead -- those are bugs
    in the caller, not something a review pass can meaningfully report `not_run` about. The returned dict's
    ``"model"`` key is always the EFFECTIVE model actually passed to ``codex exec`` — ``model`` given, or resolved
    per :func:`codex_review_model_resolution.resolve_codex_review_model`
    when it is ``None`` — never ambiguous, since there is no fallback
    substitution partway through a call.

    The resolved value is validated against :data:`_CODEX_MODEL_SLUG_PATTERN`
    and rejected BEFORE anything is launched — Codex's own model catalog is
    not consulted; a syntactically valid but nonexistent slug surfaces
    instead as this call's own ``codex exec`` launch failure.

    ``out_dir`` must be the run's own evidence directory
    (``.shipwright/planning/iterate/<run_id>/``) — the unique temp output
    path lives there and is deleted after use; only a schema-valid result is
    ever copied to the role's canonical basename.
    """
    if role not in ROLE_SCHEMAS:
        raise CodexReviewTransportError(f"unknown review role: {role!r}")
    if timeout <= 0:
        raise CodexReviewTransportError(f"timeout must be positive, got {timeout!r}")
    if max_retries < 0:
        raise CodexReviewTransportError(f"max_retries must be >= 0, got {max_retries!r}")
    # `str | None` is not runtime-enforced, and the allowlist is checked
    # UNCONDITIONALLY (incl. the hardcoded default, per AC33) rather than
    # only when `model is not None` -- both closing a non-string `model`
    # raising an undocumented TypeError and the default's formerly-unchecked
    # path (external code review, MEDIUM + LOW, 2026-09-18).
    if model is not None and not isinstance(model, str):
        raise CodexReviewTransportError(f"model must be a string or None, got {model!r}")
    # Precedence (arg > session env var > project config > default) lives in
    # codex_review_model_resolution.py.
    effective_model, model_source = resolve_codex_review_model(role, worktree_root, model, CODEX_REVIEW_MODEL)
    if not _CODEX_MODEL_SLUG_PATTERN.fullmatch(effective_model):
        # Never echo the raw value (doubt-reviewer HIGH, 2026-09-18) --
        # `model_source` is always a fixed literal, safe to include.
        raise CodexReviewTransportError(
            f"invalid Codex model slug from {model_source}: does not match "
            f"{_CODEX_MODEL_SLUG_PATTERN.pattern!r} ({len(effective_model)} characters)"
        )

    def _error(reason: str) -> dict[str, Any]:
        return {"status": "error", "transport": "codex", "model": effective_model, "reason": reason}

    # For `record_review_pass.py record --transport-note`.
    transport_note = transport_note_for(role, effective_model)

    try:
        schema = json.loads(ROLE_SCHEMAS[role].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _error(f"could not load role schema: {exc}")

    available, reason = is_codex_available(env=scrubbed_env())
    if not available:
        return _error(reason)
    codex_bin = _resolve_codex_binary()
    if not codex_bin:
        return _error("codex CLI not found on PATH")

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _error(f"could not create out_dir: {exc}")

    result: dict[str, Any] = _error("no attempt made")
    # A FRESH temp dir per attempt (mirroring external_review_default_legs.
    # review_codex, which opens its `TemporaryDirectory` inside its own
    # `for _attempt` loop) — a single dir shared across attempts left a stale
    # `-o` file behind after a failed attempt's harness wrote output before
    # exiting nonzero; a later attempt that then produced no output of its
    # own would read that stale file back as if it were the later attempt's
    # answer (doubt-reviewer, HIGH, 2026-09-17).
    #
    # The intermediate `-o` output is written by the codex HARNESS process
    # (not the read-only-sandboxed model — `--cd` governs what the model can
    # read, not where this tool writes), so it needs no relation to `out_dir`
    # at all. `out_dir` is `.shipwright/planning/iterate/<run_id>/`, a
    # git-TRACKED evidence directory this repo policies for canonical payload
    # basenames — a stray intermediate left behind by a killed backgrounded
    # call (the dispatch doc tells callers to background this, since one role
    # can take up to 600s) would get swept into the branch by the next `git
    # add -A` (code-reviewer REJECT, 2026-09-17). System temp carries no such
    # risk and is cleaned up unconditionally by the context manager.
    for _attempt in range(max_retries + 1):
        with tempfile.TemporaryDirectory(prefix=f"{role}-review-", ignore_cleanup_errors=True) as tmp_dir:
            tmp_path = Path(tmp_dir) / "review.json"
            argv = [
                codex_bin, "exec", "-m", effective_model, "--skip-git-repo-check",
                "--sandbox", CODEX_REVIEW_SANDBOX_MODE, "--ignore-user-config", "--ignore-rules",
                "--ephemeral", "--cd", str(worktree_root),
                "--output-schema", str(ROLE_SCHEMAS[role]), "-o", str(tmp_path),
            ]
            # `plan_review` (not in REASONING_EFFORT_ROLES) keeps its prior argv.
            if role in REASONING_EFFORT_ROLES:
                argv += ["-c", f"model_reasoning_effort={CODEX_REVIEW_REASONING_EFFORT}"]
            try:
                proc = subprocess.run(
                    argv, input=prompt, capture_output=True, encoding="utf-8",
                    errors="replace", timeout=timeout, env=scrubbed_env(),
                )
            except subprocess.TimeoutExpired:
                result = _error(f"codex exec timed out after {timeout}s")
                continue
            except OSError as exc:
                return _error(f"failed to launch codex: {exc}")

            if proc.returncode != 0:
                stderr_line = next(
                    (ln for ln in reversed((proc.stderr or "").splitlines()) if ln.strip()), "")
                result = _error(f"codex exec exited {proc.returncode}: {stderr_line[:500]}")
                continue

            try:
                raw = tmp_path.read_text(encoding="utf-8") if tmp_path.exists() else ""
            except OSError as exc:
                result = _error(f"could not read codex output: {exc}")
                continue
            if not raw.strip():
                result = _error("codex exec produced no output")
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                result = _error(f"codex output is not valid JSON: {exc}")
                continue
            schema_error = validate_against_schema(payload, schema)
            if schema_error:
                result = _error(f"codex output failed schema validation: {schema_error}")
                continue

            canonical_path = out_dir / ROLE_CANONICAL_BASENAMES[role]
            if canonical_path.is_symlink():
                # write_text follows symlinks — a committed symlink at this
                # path would write the validated payload through to wherever
                # it points, escaping out_dir (doubt-reviewer, LOW, 2026-09-17).
                return _error(f"refusing to write through a symlink at {canonical_path}")
            try:
                canonical_path.write_text(raw, encoding="utf-8")
            except OSError as exc:
                return _error(f"could not write canonical output: {exc}")
            result = {"status": "completed", "transport": "codex", "model": effective_model,
                      "transport_note": transport_note, "canonical_path": str(canonical_path)}
            break
    return result
