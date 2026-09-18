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

try:  # bare: this directory is on sys.path
    from codex_review_prompt import (
        INJECTION_BOUNDARY,
        build_prompt,
        scrubbed_env,
        strip_frontmatter,
        validate_against_schema,
    )
    from codex_review_roles import ROLE_CANONICAL_BASENAMES, ROLE_SCHEMAS
    from external_review_default_legs import _resolve_codex_binary, is_codex_available
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name not in ("codex_review_prompt", "codex_review_roles", "external_review_default_legs"):
        raise
    from lib.codex_review_prompt import (  # type: ignore[no-redef]
        INJECTION_BOUNDARY,
        build_prompt,
        scrubbed_env,
        strip_frontmatter,
        validate_against_schema,
    )
    from lib.codex_review_roles import (  # type: ignore[no-redef]
        ROLE_CANONICAL_BASENAMES,
        ROLE_SCHEMAS,
    )
    from lib.external_review_default_legs import (  # type: ignore[no-redef]
        _resolve_codex_binary,
        is_codex_available,
    )

__all__ = [
    "CODEX_REVIEW_MAX_RETRIES",
    "CODEX_REVIEW_MODEL",
    "CODEX_REVIEW_TIMEOUT_SECONDS",
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
#: (`gpt-5.6-terra`, execution/finalization). The hardcoded default when
#: neither `shipwright_model_config.json`'s `codex_review`/`codex_plan_review`
#: keys nor a `--codex-model` override name a value (see `run_codex_review`'s
#: `model` parameter below).
#:
#: **Supersedes AC2** (iterate-2026-09-13-codex-internal-review-transport):
#: AC2 removed a public `model=` override here (external-review MEDIUM,
#: 2026-09-17) on the reasoning that an override nothing called was a soft
#: convention, not the raise-before-launch lock it required. This run
#: (iterate-2026-09-18-codex-review-tier-config) reinstates the parameter
#: with that lock actually enforced: `_CODEX_MODEL_SLUG_PATTERN` rejects a
#: syntactically-hostile value before it ever reaches `codex exec`'s argv,
#: so the override is used (config-axis parity with Claude's model-tier
#: config, per this run's spec) without reopening the argv-injection gap
#: AC2 was closing. See this run's ADR for the full reasoning.
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

    Returns ``{"status": "completed", "transport": "codex", "model": <str>,
    "canonical_path": <str>}`` on success (the canonical-basename file is
    already written and schema-validated), or ``{"status": "error",
    "transport": "codex", "model": <str>, "reason": <str>}`` — never raises
    for a *runtime* failure, so the caller can record the review pass
    ``not_run`` with a concrete reason (finding #12) rather than crashing the
    whole run. A caller mistake (unknown role, invalid ``timeout``/
    ``max_retries``, or a ``model`` that fails the syntactic allowlist)
    raises ``CodexReviewTransportError`` instead — those are bugs in the
    caller, not something a review pass can meaningfully report `not_run`
    about. The returned dict's ``"model"`` key is always the EFFECTIVE
    model actually passed to ``codex exec`` — ``model`` given, or
    :data:`CODEX_REVIEW_MODEL` when ``model`` is ``None`` — never ambiguous,
    since there is no fallback substitution partway through a call.

    ``model`` is validated against :data:`_CODEX_MODEL_SLUG_PATTERN` and
    rejected BEFORE anything is launched — Codex's own model catalog is not
    consulted (see module docstring, "Supersedes AC2"); a syntactically
    valid but nonexistent slug surfaces instead as this call's own
    ``codex exec`` launch failure.

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
    effective_model = model if model is not None else CODEX_REVIEW_MODEL
    if not _CODEX_MODEL_SLUG_PATTERN.fullmatch(effective_model):
        # Never echo the raw value: `_emit_error`'s `reason` (which wraps
        # this message) is interpolated by the dispatch doc into a
        # double-quoted shell argument, so an embedded `"` in an
        # operator-authored config value would break out of that quote
        # (doubt-reviewer HIGH, 2026-09-18).
        raise CodexReviewTransportError(
            f"invalid Codex model slug: does not match {_CODEX_MODEL_SLUG_PATTERN.pattern!r} "
            f"({len(effective_model)} characters)"
        )

    def _error(reason: str) -> dict[str, Any]:
        return {"status": "error", "transport": "codex", "model": effective_model, "reason": reason}

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
                codex_bin, "exec", "-m", effective_model, "--skip-git-repo-check", "--sandbox", "read-only",
                "--ignore-user-config", "--ignore-rules", "--ephemeral", "--cd", str(worktree_root),
                "--output-schema", str(ROLE_SCHEMAS[role]), "-o", str(tmp_path),
            ]
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
                      "canonical_path": str(canonical_path)}
            break
    return result
