"""Terminal helper CLI for launching a fresh, armed Codex-driven session (R2 — M3, Step 7).

Composes the first-prompt envelope via ``codex_envelope_grammar.compose()``
and launches the real ``codex`` binary as an **argument-vector process call**
(``subprocess.run([...], shell=False)``) — never a shell-interpolated command
string. This is a hard requirement (external review, openai low-7): a
shell-built launch command risks injection from the composed prompt text,
since ``args`` (and therefore the envelope) can contain operator-supplied
content. Passing the envelope as one ``argv`` element sidesteps that whole
class of risk on every platform when the resolved binary is a real native
executable (``CreateProcess``/``list2cmdline`` on Windows, ``execvp``-style
on POSIX build the child process's argv directly, with no shell involved).

**"``shell=False`` means never a shell" is NOT true when the resolved binary
is a Windows ``.bat``/``.cmd`` shim** (R2 code review, 2026-09-22, empirically
confirmed against a real Windows ``.cmd`` file: ``a|b``/``c&d``-shaped argv
elements DO get re-split by an implicitly-invoked ``cmd.exe`` in that case,
even with ``shell=False`` and a list argv — a genuinely different failure
mode from the ``cmd.exe``-double-quoting bug R1b hit in
``codex_hooks_launcher.py``, which was about manually re-quoting a single
command *string*; this one is Windows' own ``CreateProcess`` routing a
``.bat``/``.cmd`` target through ``cmd.exe`` regardless of how the argv was
built). The envelope's own grammar (``codex_envelope_grammar.py``) contains
literal ``|`` characters, so an npm-global-installed ``codex`` resolving to a
``.cmd`` shim (exactly the shape R1b already hit for ``npx.cmd``) would
corrupt even a completely honest envelope, not just a crafted one. See
``_refuse_if_shell_shim`` below: this tool refuses to launch through a
``.bat``/``.cmd``-resolved binary rather than risk it.

The launch is **interactive** — this hands the real terminal to ``codex`` so
the operator can continue the session normally (this is why ``subprocess.run``
here does NOT pass ``capture_output``/``input=``, unlike the sibling
``codex exec`` one-shot pattern in ``external_review_default_legs.py``, which
captures a single non-interactive reply instead). This tool's job ends the
moment ``codex`` exits.

**Honest limitation — "existing session" detection.** This helper cannot
observe or prevent an operator manually continuing/resuming an existing
``codex`` session outside this tool entirely; it also cannot inspect Codex's
own internal session/resume state. The only signal available to it is
whether a still-live (unexpired) activation record already exists for the
resolved project root — a signal that a fresh session was started against
this project recently and has not yet expired. That is a heuristic, not a
guarantee: it will not catch every misuse, and a stale/expired record is
deliberately NOT treated as a block (an old record is exactly the ordinary,
expected state between sessions, matching the activation-record library's
own fail-open TTL contract, not a hazard).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import codex_envelope_grammar  # noqa: E402
from atomic_write import durable_read_text  # noqa: E402
from cmd_resolver import resolve_trusted_executable  # noqa: E402
from codex_activation_record import normalize_cwd  # noqa: E402

_RECORD_SUBDIR = (".shipwright", "runtime", "codex-activation")
#: Duplicated from ``codex_activation_mint.py``'s ``_ACCEPTED_SKILL_IDS``,
#: not imported: that module lives under a specific plugin's ``scripts/``
#: tree and shared code must not import a single plugin's internals
#: (ADR-044/045). Kept here ONLY to warn an operator before launch, not to
#: enforce -- this CLI is intentionally generic (any skill_id composes a
#: valid envelope); only the iterate mint hook decides what arms. A drift
#: between the two sets makes the warning stale, never wrong-blocking.
_KNOWN_ARMING_SKILL_IDS = frozenset({"shipwright-iterate:iterate"})

# Extensions Windows' CreateProcess routes through an implicit cmd.exe re-parse
# (see module docstring's "shell=False is not always shell-free" note) — never
# launch through one of these, whatever `codex` happens to resolve to.
_SHELL_SHIM_EXTENSIONS = frozenset({".bat", ".cmd"})


def _resolve_codex_binary() -> str | None:
    """Thin wrapper over ``cmd_resolver.resolve_trusted_executable`` (single
    source of truth for the BatBadBut cwd-hijack guard, R2 code review
    2026-09-22) — kept as its own private name/shape so existing test patches
    (``codex_activation_helper._resolve_codex_binary``) keep working
    unchanged. Mirrors ``external_review_default_legs._resolve_codex_binary``,
    which now delegates to the same shared function."""
    return resolve_trusted_executable("codex")


def _find_live_record(project_root: Path, *, now: float | None = None) -> str | None:
    """Return the session_id of an unexpired activation record already on
    disk for this project, or ``None`` if there isn't one. An expired record
    is deliberately ignored (see module docstring) -- it is the ordinary
    between-sessions state, not a signal anything is still live.

    Scans the NORMALIZED project root (code review, MEDIUM: this previously
    globbed the RAW ``--project-root`` argument's own ``.shipwright/...``
    subtree, which silently misses every record for the normal worktree
    case -- the hooks mint/consume through ``normalize_cwd()``'s git
    main-repo-root canonicalization, so a worktree's own subtree is never
    where the record actually lives)."""
    ts = time.time() if now is None else now
    target_cwd = normalize_cwd(str(project_root))
    record_dir = Path(target_cwd).joinpath(*_RECORD_SUBDIR)
    try:
        candidates = sorted(record_dir.glob("*.json"))
    except OSError:
        return None
    for path in candidates:
        try:
            payload = json.loads(durable_read_text(path))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("cwd") != target_cwd:
            continue
        expiry = payload.get("expiry")
        if not isinstance(expiry, (int, float)) or ts >= expiry:
            continue
        session_id = payload.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
    return None


def _build_launch_argv(codex_bin: str, envelope: str) -> list[str]:
    """The entire launch command as a list -- never joined into a string,
    never handed to a shell. This is the one function a test can assert
    against to pin "no shell interpolation, ever" without actually
    launching a process."""
    return [codex_bin, envelope]


def _refuse_if_shell_shim(codex_bin: str, envelope: str) -> str | None:
    """Return an error message (and refuse to launch) if ``codex_bin`` is a
    ``.bat``/``.cmd`` shim, else ``None``. See module docstring: Windows
    routes a ``.bat``/``.cmd`` target through an implicit ``cmd.exe``
    re-parse regardless of ``shell=False``/list-argv, which can corrupt the
    envelope's own ``|`` characters (or worse, on a maliciously-shaped
    envelope). Checked before every launch, not just as documentation --
    this is a safe, honest failure: the interactive launch is still pending
    a separate, deferred live-verification step anyway, so refusing loudly
    here costs nothing real and avoids launching through an unverified
    path. The composed envelope is echoed back so the operator can invoke
    ``codex`` with it manually instead of being stuck."""
    if Path(codex_bin).suffix.lower() not in _SHELL_SHIM_EXTENSIONS:
        return None
    return (
        f"error: codex resolved to a shell shim ({codex_bin!r}) -- launching through a "
        f".bat/.cmd target is not verified safe for this tool's argv content (see module "
        f"docstring). Invoke codex manually instead, passing this envelope as its first "
        f"prompt:\n\n{envelope}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-id", required=True, help="Skill id to embed in the envelope")
    parser.add_argument(
        "--args-json", default="{}", help="JSON object of skill arguments (default: {})"
    )
    parser.add_argument(
        "--project-root", required=True, help="Project root to launch codex into"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Launch even if a still-live activation record already exists for this project",
    )
    args = parser.parse_args(argv)

    try:
        skill_args = json.loads(args.args_json)
    except json.JSONDecodeError as exc:
        print(f"error: --args-json is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(skill_args, dict):
        print("error: --args-json must decode to a JSON object", file=sys.stderr)
        return 1

    try:
        envelope = codex_envelope_grammar.compose(args.skill_id, skill_args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.skill_id not in _KNOWN_ARMING_SKILL_IDS:
        print(
            f"warning: --skill-id {args.skill_id!r} is not one this tool knows arms the "
            f"iterate gate (known: {sorted(_KNOWN_ARMING_SKILL_IDS)}) -- the mint hook may "
            f"mint an UNARMED session for it. Launching anyway (this CLI does not enforce "
            f"the mint hook's own allowlist).",
            file=sys.stderr,
        )

    project_root = Path(args.project_root).resolve()

    if not args.force:
        live_session = _find_live_record(project_root)
        if live_session is not None:
            print(
                f"error: a still-live activation record already exists for this project "
                f"(session {live_session!r}). This helper's envelope is only meaningful as a "
                f"session's FIRST prompt -- if you intend to resume that session, don't use this "
                f"helper; if you intend a genuinely fresh session, pass --force.",
                file=sys.stderr,
            )
            return 1

    codex_bin = _resolve_codex_binary()
    if codex_bin is None:
        print("error: codex CLI not found on PATH", file=sys.stderr)
        return 1

    shim_refusal = _refuse_if_shell_shim(codex_bin, envelope)
    if shim_refusal is not None:
        print(shim_refusal, file=sys.stderr)
        return 1

    launch_argv = _build_launch_argv(codex_bin, envelope)
    try:
        proc = subprocess.run(launch_argv, cwd=str(project_root), shell=False)
    except OSError as exc:
        print(f"error: failed to launch codex: {exc}", file=sys.stderr)
        return 1
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
