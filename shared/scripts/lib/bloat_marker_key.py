"""Per-(session, agent) marker-file key for the bloat-gate wave.

Split out of ``bloat_baseline.py`` (2026-09-07) purely to keep that module
under its own 300-line ceiling — this is a single function, not a separate
concern; ``bloat_baseline`` re-exports it so ``_bb.marker_key`` keeps working
for both hook scripts.
"""

from __future__ import annotations

_MARKER_KEY_SAFE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def _encode_agent_component(agent_id: str) -> str:
    """Filesystem-safe, COLLISION-FREE encoding of ``agent_id``.

    Each byte outside the safe set (incl. a literal ``~``, the escape char
    itself) becomes ``~XX`` (two lowercase hex digits) — a bijection, so two
    DISTINCT ``agent_id`` values can never encode to the same string. A
    reviewed prior version blindly substituted every unsafe character with
    ``_``, which is lossy: ``"a/b"`` and ``"a:b"`` both became ``"a_b"``,
    silently pooling two different subagents back into one marker — the
    exact class of bug this whole fix exists to close (external review,
    2026-09-07)."""
    # NOT length-capped: a cap applied AFTER encoding would just move the
    # same collision risk to the truncation boundary (internal plan review,
    # 2026-09-07) — two distinct long agent_ids could still share a capped
    # prefix. `agent_id` is a short Claude Code-internal identifier, never
    # attacker-controlled arbitrary-length input, so an unbounded encode is
    # safe here.
    out: list[str] = []
    for ch in agent_id:
        if ch in _MARKER_KEY_SAFE_CHARS:
            out.append(ch)
        else:
            out.extend(f"~{b:02x}" for b in ch.encode("utf-8"))
    return "".join(out)


def marker_key(payload: dict | None, env_session_id: str | None = None) -> str:
    """Per-(session, agent) marker-file key for the bloat-gate wave.

    Claude Code sets ``agent_id`` only when the hook fires INSIDE a
    subagent call (e.g. a background ``Task`` like ``sub-iterate-runner``);
    it shares its ``session_id`` with its spawning session, so keying on
    ``session_id`` alone pools orchestrator + subagent into ONE marker
    file — a still in-flight subagent edit then blocks the orchestrator's
    own unrelated Stop on every turn (2026-09-07,
    campaign-req3-06-mechanics-webui). Suffixing with ``agent_id`` (when
    present) gives each agent its own marker, so the Stop gate only
    re-measures the calling agent's own edits.

    Falls back to ``env_session_id`` (``SHIPWRIGHT_SESSION_ID``, unset in
    hook subprocesses) then ``"unknown"`` when no payload ``session_id``
    (pre-existing session-scoping fix, 2026-05-29).

    Residual, accepted risk: a literal ``.`` inside ``session_id`` itself
    (never encoded, to keep the no-``agent_id`` key BYTE-IDENTICAL to every
    pre-existing marker filename and test) could in principle collide with a
    shorter ``session_id`` plus an ``agent_id`` suffix. Real Claude Code
    ``session_id`` values are UUIDs (hyphens, no dots), so this is not
    reachable in practice; not solved here because solving it would change
    the no-``agent_id`` filename shape, breaking backward compatibility.
    """
    sid = ""
    agent_id = ""
    if isinstance(payload, dict):
        raw_sid = payload.get("session_id")
        if isinstance(raw_sid, str) and raw_sid.strip():
            sid = raw_sid.strip()
        raw_agent = payload.get("agent_id")
        if isinstance(raw_agent, str) and raw_agent.strip():
            agent_id = raw_agent.strip()
    if not sid:
        sid = (env_session_id or "").strip()
    sid = sid or "unknown"
    if not agent_id:
        return sid
    return f"{sid}.{_encode_agent_component(agent_id)}"
