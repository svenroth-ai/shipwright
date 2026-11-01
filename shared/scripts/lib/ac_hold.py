"""The one escalation that holds ONLY its own unit, the signal that a run is unattended, and the operator signature.

A sub-iterate that must ask (an existing AC changed or removed, no single FR owns the new AC, a new area of the
product) cannot be built until the operator answers. Under a campaign that stops THAT unit - ``running -> held``,
``record`` exits 0 - while the rest of the wave still builds and merges. Every other escalation keeps the
whole-wave STRICT-STOP (exit 3). The hold needs a well-formed escalation: ``status: escalated``, the reason code,
and a non-empty ``ac_questions`` whose every ``question_sha256`` is RECOMPUTED here from the question text, the
item index and the escalation's ``bind_id`` and must match (``cmd_record`` additionally requires a claimed unit of
a sub-iterate loop). Anything else keeps exit 3. Campaign finalize step 5 prints the open ``ac_questions``.

**What is enforced, plainly.** ``answered_via`` and ``unattended`` are SELF-REPORTED. *Unattended* is read from
state the agent does not type - ``SHIPWRIGHT_LOOP_ID`` together with ``SHIPWRIGHT_LOOP_UNIT_ID`` (exported by the
orchestrator), or a per-unit worktree ``<main>/.worktrees/campaign-<slug>--<unit>`` (the orchestrator worktree
``campaign-<slug>`` and any other folder are attended). An unattended run refuses inline answers, and
``ac_decision.py answer`` refuses to run there unless ``SHIPWRIGHT_AC_OPERATOR_CHANNEL`` is set (the orchestrator
shell needs it to answer). ``answer`` signs each answer with an HMAC under a per-user key
(``~/.shipwright/ac_operator.key``, created on first use); ``decide`` records ``answered_via: operator`` only for a
valid signature and ``self-reported`` for an unsigned or mismatching file answer. **The signature is a guard
against accident and casual forgery, not authentication: a determined agent with shell access can read the key.**
F11 warns for any asked decision that is not operator-signed; it never blocks a PR.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

AC_HOLD_REASON = "ac_question_requires_operator"
OPERATOR_ENV = "SHIPWRIGHT_AC_OPERATOR_CHANNEL"
KEY_ENV = "SHIPWRIGHT_AC_KEY_FILE"
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNIT_WORKTREE = re.compile(r"^campaign-.+--.+$")


def question_sha(text: str, bind_id: str = "", index: int = 0) -> str:
    """sha256 binding an answer to the run's stable id, the item index and the exact question text."""
    return "sha256:" + hashlib.sha256(f"{bind_id}\n{index}\n{text}".encode("utf-8")).hexdigest()


def is_ac_hold(result: object) -> bool:
    """True for a well-formed AC-question escalation: reason code, non-empty ``ac_questions``, every sha256 recomputed and matching."""
    if not (isinstance(result, dict) and result.get("status") == "escalated" and result.get("reason_code") == AC_HOLD_REASON):
        return False
    qs, bind = result.get("ac_questions"), result.get("bind_id", "")
    return (isinstance(qs, list) and bool(qs) and isinstance(bind, str) and all(
        isinstance(q, dict) and isinstance(q.get("question"), str) and isinstance(q.get("item"), int) and not isinstance(q.get("item"), bool)
        and isinstance(q.get("question_sha256"), str) and _SHA.match(q["question_sha256"])
        and q["question_sha256"] == question_sha(q["question"], bind, q["item"]) for q in qs))


def is_unattended(project_root: str | Path = "") -> bool:
    """True when the campaign loop environment is set (both variables) or the root is a per-unit campaign worktree."""
    if os.environ.get("SHIPWRIGHT_LOOP_ID") and os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID"):
        return True
    if not project_root:
        return False
    here = Path(project_root).resolve()
    return here.parent.name == ".worktrees" and bool(_UNIT_WORKTREE.match(here.name))


def operator_channel_open() -> bool:
    """True when the operator-side tool marked this process (a guard, not authentication)."""
    return bool(os.environ.get(OPERATOR_ENV))


def key_path() -> Path:
    return Path(os.environ[KEY_ENV]) if os.environ.get(KEY_ENV) else Path.home() / ".shipwright" / "ac_operator.key"


def load_key(create: bool = False) -> bytes | None:
    """The per-user signing key; created on first ``answer`` when ``create``. ``None`` when absent (and not created)."""
    path = key_path()
    try:
        return bytes.fromhex(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        if not create:
            return None
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_text(key.hex() + "\n", encoding="ascii")
    return key


def sign(key: bytes, sha: str, choice: str, text: str) -> str:
    return hmac.new(key, f"{sha}\n{choice}\n{text}".encode("utf-8"), hashlib.sha256).hexdigest()


def signature_ok(key: bytes | None, entry: dict) -> bool:
    """True when the file answer carries a signature that matches its question, choice and text under ``key``."""
    sig = entry.get("signature")
    return bool(key) and isinstance(sig, str) and hmac.compare_digest(
        sig, sign(key, str(entry.get("question_sha256")), str(entry.get("choice")), str(entry.get("text") or "")))
