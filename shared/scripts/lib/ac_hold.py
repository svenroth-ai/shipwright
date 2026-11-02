"""The one escalation that holds ONLY its own unit, the signal that a run is unattended, and the operator signature.

A sub-iterate that must ask (an existing AC changed or removed, no single FR owns the new AC, a new area of the
product) cannot be built until the operator answers. Under a campaign that stops THAT unit - ``running -> held``,
``record`` exits 0 - while the rest of the wave still builds and merges. Every other escalation keeps the
whole-wave STRICT-STOP (exit 3). The hold needs a well-formed escalation: ``status: escalated``, the reason code,
and a non-empty ``ac_questions`` whose every ``question_sha256`` is RECOMPUTED here from the stable content of the
question (the escalation's ``bind_id``, the item index, ``kind``, the original ``promise`` text and the canonical JSON
of ``options``) and must match (``cmd_record`` additionally requires a claimed unit of a sub-iterate loop). The
rendered question text is NOT part of the hash: a moved catalog or a model wording it differently on resume must not
invalidate a signed answer. Campaign finalize step 5 prints the open ``ac_questions``.

**What is enforced, plainly.** ``answered_via`` and ``unattended`` are SELF-REPORTED. *Unattended* is read from
state the agent does not type - ``SHIPWRIGHT_LOOP_ID`` together with ``SHIPWRIGHT_LOOP_UNIT_ID`` (exported by the
orchestrator), or a per-unit worktree ``<main>/.worktrees/campaign-<slug>--<unit>`` (split at the LAST ``--``; the
orchestrator worktree ``campaign-<slug>`` and any other folder are attended). An unattended run refuses inline answers,
and ``ac_decision.py answer`` refuses to run there unless ``SHIPWRIGHT_AC_OPERATOR_CHANNEL`` is set (the orchestrator
shell needs it to answer). ``answer`` signs each answer with an HMAC under a per-user key
(``~/.shipwright/ac_operator.key``, created on first use with mode 0600, never regenerated); ``decide`` records
``answered_via: operator`` only for a valid signature and ``self-reported`` for an unsigned or mismatching file answer.
**The signature is a guard against accident and casual forgery, not authentication: a determined agent with shell
access can read the key.** F11 warns for an unattended asked decision that is not operator-signed; it never blocks a PR.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

AC_HOLD_REASON = "ac_question_requires_operator"
OPERATOR_ENV = "SHIPWRIGHT_AC_OPERATOR_CHANNEL"
KEY_ENV = "SHIPWRIGHT_AC_KEY_FILE"
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNIT_WORKTREE = re.compile(r"^campaign-.+--.+$")


def question_sha(bind_id: str, index: int, kind: str, promise: dict, options: dict) -> str:
    """sha256 over the stable content of a question (see the module docstring); never the rendered text."""
    canon = json.dumps([bind_id, index, kind, promise, options], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def is_ac_hold(result: object) -> bool:
    """True for a well-formed AC-question escalation: reason code, non-empty ``ac_questions``, every sha256 recomputed and matching."""
    if not (isinstance(result, dict) and result.get("status") == "escalated" and result.get("reason_code") == AC_HOLD_REASON):
        return False
    qs, bind = result.get("ac_questions"), result.get("bind_id", "")
    return (isinstance(qs, list) and bool(qs) and isinstance(bind, str) and all(
        isinstance(q, dict) and isinstance(q.get("question"), str) and isinstance(q.get("item"), int) and not isinstance(q.get("item"), bool)
        and isinstance(q.get("kind"), str) and isinstance(q.get("promise"), dict) and isinstance(q.get("options"), dict)
        and isinstance(q.get("question_sha256"), str) and _SHA.match(q["question_sha256"])
        and q["question_sha256"] == question_sha(bind, q["item"], q["kind"], q["promise"], q["options"]) for q in qs))


def is_unit_worktree(root: Path) -> bool:
    """True for ``<main>/.worktrees/campaign-<slug>--<unit>``: split at the LAST ``--``, and the orchestrator worktree ``campaign-<slug>``
    must exist beside it (an orchestrator whose own slug contains ``--`` has no such sibling, so it stays attended)."""
    if root.parent.name != ".worktrees" or not _UNIT_WORKTREE.match(root.name):
        return False
    slug, _, unit = root.name.rpartition("--")
    return bool(unit) and slug != "campaign" and (root.parent / slug).is_dir()


def is_unattended(project_root: str | Path = "") -> bool:
    """True when the campaign loop environment is set (both variables) or the root is a per-unit campaign worktree."""
    if os.environ.get("SHIPWRIGHT_LOOP_ID") and os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID"):
        return True
    return bool(project_root) and is_unit_worktree(Path(project_root).resolve())


def operator_channel_open() -> bool:
    """True when the operator-side tool marked this process (a guard, not authentication)."""
    return bool(os.environ.get(OPERATOR_ENV))


def key_path() -> Path:
    return Path(os.environ[KEY_ENV]) if os.environ.get(KEY_ENV) else Path.home() / ".shipwright" / "ac_operator.key"


def _read_key(path: Path) -> bytes | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"the signing key {path} cannot be read ({exc}); fix or remove it by hand - it is never regenerated automatically") from exc
    try:
        key = bytes.fromhex(text)
    except ValueError:
        key = b""
    if len(key) < 16:
        raise RuntimeError(f"the signing key {path} is empty or malformed; fix or remove it by hand - it is never regenerated automatically")
    return key


def _read_key_or_none(path: Path) -> bytes | None:
    try:
        return _read_key(path)
    except RuntimeError:
        return None


def load_key(create: bool = False) -> bytes | None:
    """The per-user signing key. Created on first ``answer`` (``create``) with ``O_EXCL`` and mode 0600; an existing key is re-read, never replaced.

    Absent (and not created) is ``None``; an existing but unreadable, empty or malformed file raises ``RuntimeError`` with a clear message.
    """
    path = key_path()
    key = _read_key(path)
    if key is not None or not create:
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another process created it first: use theirs (it may still be being written)
        for _ in range(40):
            got = _read_key_or_none(path)
            if got:
                return got
            time.sleep(0.05)
        return _read_key(path)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key.hex() + "\n")
    if os.name == "posix":
        os.chmod(path, 0o600)
    return key


def sign(key: bytes, sha: str, choice: str, text: str) -> str:
    return hmac.new(key, f"{sha}\n{choice}\n{text}".encode("utf-8"), hashlib.sha256).hexdigest()


def signature_ok(key: bytes | None, entry: dict) -> bool:
    """True when the file answer carries a signature that matches its question, choice and text under ``key``."""
    sig = entry.get("signature")
    return bool(key) and isinstance(sig, str) and hmac.compare_digest(
        sig, sign(key, str(entry.get("question_sha256")), str(entry.get("choice")), str(entry.get("text") or "")))
