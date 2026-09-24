"""The 'opus' reviewer identity: local Claude CLI, with an OpenRouter fallback.

Split out as a sibling to ``external_review_default_legs.py`` (already near
the 300-line guideline) rather than folded into it. Exists so a
Codex-authored diff (``gpt-6-sol``) can be reviewed by a genuinely
cross-vendor model instead of another OpenAI-family model answering the
"openai" identity — see ``external_review_routing.DRIVER_ROSTERS``.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

try:  # bare: this directory is on sys.path
    from external_review_degraded import classify_reply
    from external_review_modes import render_user_prompt_as_stdin_refs
    from external_review_routing import ReviewModelPolicyError, resolve_reviewer_model
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_degraded":
        raise
    from lib.external_review_degraded import classify_reply  # type: ignore[no-redef]
    from lib.external_review_modes import (  # type: ignore[no-redef]
        render_user_prompt_as_stdin_refs,
    )
    from lib.external_review_routing import (  # type: ignore[no-redef]
        ReviewModelPolicyError,
        resolve_reviewer_model,
    )

CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS = 600
CLAUDE_CLI_DEFAULT_MAX_RETRIES = 1
_CLAUDE_VERSION_TIMEOUT_SECONDS = 15

# shared/config/claude_cli_empty_mcp.json — parents[0]=lib, [1]=scripts, [2]=shared.
_EMPTY_MCP_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "claude_cli_empty_mcp.json"
)

# This leg must always reach real Anthropic when the session is
# Codextender-routed (CODEXTENDER_ACTIVE set — see docs/hooks-and-pipeline.md):
# a bare `subprocess.run(argv, ...)` with no `env=` would otherwise inherit
# the parent session's ANTHROPIC_BASE_URL pointed at a local Codex-backed
# proxy, silently misrouting this leg too. Scrubbed ONLY under that
# condition, never unconditionally — a CI PR-review pass found that
# ANTHROPIC_AUTH_TOKEN in particular is also a legitimate way to
# authenticate directly with real Anthropic outside any proxy setup (e.g. an
# enterprise bearer-token credential with no separate ANTHROPIC_API_KEY); an
# unconditional scrub would silently break that installation's auth entirely
# (iterate-2026-09-23-codextender-monorepo-part-c). CODEXTENDER_ACTIVE is the
# one signal that actually distinguishes "these vars are a proxy override"
# from "this is the caller's own legitimate config" — scrubbing only ever
# removes an override that flag itself proves is in place.
_ANTHROPIC_ENV_SCRUB_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL")


def _real_anthropic_env() -> dict[str, str] | None:
    """A copy of the current environment with the Anthropic routing/model
    overrides removed when this session is Codextender-routed, so the spawned
    ``claude`` CLI always reaches real Anthropic instead of the Codex-backed
    proxy. Returns ``None`` (subprocess.run's own "inherit unchanged")
    outside Codextender, since these vars may be the caller's own
    legitimate, non-proxy configuration."""
    if not os.environ.get("CODEXTENDER_ACTIVE"):
        return None
    return {key: value for key, value in os.environ.items() if key not in _ANTHROPIC_ENV_SCRUB_KEYS}


def _resolve_claude_binary() -> str | None:
    """``shutil.which("claude")``, refusing two unsafe resolutions.

    Mirrors ``external_review_default_legs._resolve_codex_binary``'s cwd-guard
    (a reviewed repo could plant its own ``claude.exe`` at its root, since
    Windows implicitly searches cwd before PATH). **Additionally** refuses a
    resolved ``.cmd``/``.bat`` target outright — the real Windows npm install
    of the Claude CLI is exactly such a shim (``claude.cmd``). The untrusted
    diff/spec text itself never reaches argv (it rides stdin; only the
    rendered system+review *instructions* — never the diff — become the
    ``-p`` argument, via ``render_user_prompt_as_stdin_refs``), so this refusal
    is defense-in-depth rather than the sole safety mechanism: Python's
    ``subprocess`` argv quoting on Windows (``list2cmdline``) is not
    ``cmd.exe``-batch-safe, so ANY argv content reaching a ``.cmd``/``.bat``
    shim (even the instructions text, or a future caller that widens what
    goes via ``-p``) could break out of the argument and inject commands into
    the shim's own batch interpretation (the BatBadBut class). Refusing here —
    not just escaping harder — means this leg fails closed (falls back to
    OpenRouter) rather than attempting a fix that would need to out-guess
    `cmd.exe`.
    """
    found = shutil.which("claude")
    if found is None:
        return None
    try:
        resolved = Path(found).resolve()
        if resolved.parent == Path.cwd().resolve():
            return None
    except (OSError, RuntimeError):
        return None
    if resolved.suffix.lower() in (".cmd", ".bat"):
        return None
    return found


def is_claude_cli_available() -> tuple[bool, str]:
    """Whether the Claude CLI is installed (and not refused as an unsafe
    shim). Never raises. This is an installation/liveness probe only, not an
    auth check — unlike ``is_codex_available``, there is no documented
    ``claude login status``-equivalent to probe; an unauthenticated CLI
    surfaces as a runtime error from ``review_claude_cli`` instead, which is
    a known, disclosed limitation (falls back to OpenRouter on that failure
    only via the caller's own route resolution, not automatically retried
    here)."""
    claude_bin = _resolve_claude_binary()
    if not claude_bin:
        return False, "claude CLI not found on PATH (or refused as an unsafe .cmd/.bat shim)"
    try:
        result = subprocess.run(
            [claude_bin, "--version"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=_CLAUDE_VERSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "claude --version timed out"
    except OSError as exc:
        return False, f"claude --version check failed: {exc}"
    if result.returncode != 0:
        return False, f"claude --version exited {result.returncode}"
    return True, ""


def claude_cli_settings(config: dict) -> tuple[float, int]:
    """`(timeout_seconds, max_retries)` from `config["claude_cli"]`. Mirrors
    ``external_review_default_legs.codex_settings`` exactly, including the
    non-finite/non-positive timeout guard and the negative-retry clamp."""
    claude_cfg = config.get("claude_cli")
    claude_cfg = claude_cfg if isinstance(claude_cfg, dict) else {}
    max_retries = claude_cfg.get("max_retries", CLAUDE_CLI_DEFAULT_MAX_RETRIES)
    timeout = claude_cfg.get("timeout_seconds", CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except (TypeError, ValueError):
        timeout = CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS
    try:
        max_retries = max(0, int(max_retries))
    except (TypeError, ValueError):
        max_retries = CLAUDE_CLI_DEFAULT_MAX_RETRIES
    return timeout, max_retries


def review_claude_cli(content: str, context: str, system_prompt: str, user_prompt: str, config: dict) -> dict:
    """Send content for review via the local Claude CLI — the flat-cost route
    for the 'opus' reviewer identity under a Claude subscription.

    The diff/spec content and context ride over stdin as data (the Claude CLI
    headless contract has no way to pass the prompt itself over stdin); the
    rendered system+review instructions become the `-p` argument, with the
    template's real placeholders (``{DIFF}``/``{PLAN}``/``{BRIEF}``/``{SPEC}``
    — the same set every other leg's template uses, via
    ``external_review_modes.render_user_prompt_as_stdin_refs``) pointed at
    the stdin block instead of substituted inline — keeping the untrusted
    diff/spec text out of argv entirely is *why* this leg is safe even though
    ``_resolve_claude_binary`` cannot fully rule out a hostile shim; a shim
    that did slip through would still only see instructions text, never the
    diff.

    ``--mcp-config`` (pointed at a checked-in empty-``mcpServers`` file) plus
    ``--strict-mcp-config`` (a boolean flag — ignore every other MCP source)
    and ``--allowedTools ""`` close this leg's sandbox-parity gap with
    ``review_codex``'s ``--sandbox read-only --ignore-user-config
    --ignore-rules``: no MCP servers, no built-in tools, so a prompt-injected
    diff cannot make the reviewer *act*, only reply. ``--permission-mode
    dontAsk --max-turns 1`` bounds it to a single non-interactive turn.

    Retry scope matches ``review_codex``: only a successfully-run, degraded
    (empty/truncated) reply is retried; a transport-level failure is terminal
    on the attempt it occurs.
    """
    available, reason = is_claude_cli_available()
    if not available:
        return {"status": "error", "via": "claude_cli", "reason": reason}

    try:
        model_name = resolve_reviewer_model(config, "opus", "claude_cli")
    except ReviewModelPolicyError as exc:
        return {"status": "error", "via": "claude_cli", "reason": str(exc)}

    claude_bin = _resolve_claude_binary()
    if not claude_bin:
        return {"status": "error", "via": "claude_cli", "reason": "claude CLI not found on PATH (or refused as an unsafe .cmd/.bat shim)"}

    timeout, max_retries = claude_cli_settings(config)
    instructions = render_user_prompt_as_stdin_refs(user_prompt)
    full_prompt = f"{system_prompt}\n\n{instructions}"
    stdin_payload = f"<content>\n{content}\n</content>\n\n<context>\n{context}\n</context>\n"

    argv = [
        claude_bin, "--bare", "-p", full_prompt, "--model", model_name,
        "--output-format", "json", "--permission-mode", "dontAsk",
        "--max-turns", "1", "--mcp-config", str(_EMPTY_MCP_CONFIG_PATH),
        "--strict-mcp-config", "--allowedTools", "",
    ]

    result: dict = {"status": "degraded", "reason": "no attempt made", "via": "claude_cli"}
    for _attempt in range(max_retries + 1):
        try:
            proc = subprocess.run(
                argv, input=stdin_payload, capture_output=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                env=_real_anthropic_env(),
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "via": "claude_cli", "reason": f"claude CLI timed out after {timeout}s"}
        except OSError as exc:
            return {"status": "error", "via": "claude_cli", "reason": f"failed to launch claude: {exc}"}

        if proc.returncode != 0:
            stderr_line = next((ln for ln in reversed((proc.stderr or "").splitlines()) if ln.strip()), "")
            return {"status": "error", "via": "claude_cli", "reason": f"claude CLI exited {proc.returncode}: {stderr_line[:500]}"}

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return {"status": "error", "via": "claude_cli", "reason": f"could not parse claude CLI JSON output: {exc}"}

        feedback = payload.get("result") if isinstance(payload, dict) else None
        result = classify_reply(feedback if isinstance(feedback, str) else None, None, via="claude_cli")
        if result["status"] != "degraded":
            break
    return result


def resolve_opus_route(config: dict, *, has_openrouter_key: bool) -> tuple[str, str]:
    """Which route answers the 'opus' reviewer leg, and why.

    Returns ``(route, note)`` where route is 'claude_cli' | 'openrouter' |
    'none'. Mirrors ``external_review_default_legs.resolve_openai_route`` one
    link shorter — there is no "direct Anthropic API" leg, only the CLI and
    OpenRouter.
    """
    try:  # deferred: avoid an import cycle (external_review_config does not import this module)
        from external_review_config import opus_leg_provider
    except ModuleNotFoundError:
        from lib.external_review_config import opus_leg_provider  # type: ignore[no-redef]

    if opus_leg_provider(config) == "claude_cli":
        available, unavailable_reason = is_claude_cli_available()
        if available:
            return "claude_cli", ""
        fallback = "openrouter" if has_openrouter_key else "none"
        return fallback, (
            f"claude CLI unavailable ({unavailable_reason}); falling back to "
            f"{fallback if fallback != 'none' else 'no configured OPENROUTER_API_KEY — skipping this leg'}"
        )
    return ("openrouter" if has_openrouter_key else "none"), ""
