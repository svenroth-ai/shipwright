"""An adapter-backed review closed ``unavailable`` must show the adapter's error.

``unavailable`` is the one ``review_not_run`` code that claims something about
the WORLD rather than about a rule: "the reviewer could not run". Typed by an
agent with nobody to ask, it is also the cheapest way to skip an external review
and still pass F11. So for the two passes ``external_review.py`` produces —
``plan`` and ``external_code`` (:data:`ADAPTER_REVIEW_TYPES`) — the claim must
be backed by what the adapter actually left behind, found by CONVENTION in the
run directory (no record field, no CLI flag: the canonical basenames in
``lib.review_payloads`` already pin where the adapter writes):

- ``<canonical raw>`` — the adapter's stdout, e.g. ``external-code-review-raw.json``;
- ``<canonical stem>.stderr.txt`` — its stderr, for a ``uv run`` that died
  before printing any JSON.

Evidence rule (:func:`artifact_problem`), in precedence order:

1. The raw file holds a JSON object (the first one opening a line, so stray
   text before or after the reply cannot hide it; a UTF-16 BOM — Windows
   PowerShell 5.1's ``>`` — is decoded) → it decides alone. It must be the
   adapter's own failure envelope (``success`` is JSON ``false`` or ``degraded``
   is JSON ``true`` — the exact types ``external_review.py`` writes). Any other
   object refuses the claim whatever stderr says: a reply that parses is the
   pass's answer, so a review that ran is recorded ``completed``.
2. Otherwise (raw absent, empty, or not JSON) → a non-empty stderr file is the
   evidence. Stray non-JSON stdout alone is NOT evidence: it proves nothing about
   a failure.

Both redirects truncate on every invocation (``>`` / ``2>``), so a retry that
succeeds overwrites the failure and the claim is refused — the artifact speaks
for the LAST attempt of the pass, by design.

One-directional by design: this refuses a false "could not run". A degraded
reply recorded ``completed`` is the review-record floor's business, not this
module's. Callers print paths only, never artifact content (stderr can carry
provider URLs).
"""

from __future__ import annotations

import codecs
import json
from pathlib import Path
from typing import Callable

try:
    from .review_payloads import CANONICAL_PAYLOAD_BASENAMES
    from .review_record_schema import is_safe_run_id
except ImportError:  # loaded with lib/ itself on sys.path
    from review_payloads import CANONICAL_PAYLOAD_BASENAMES  # type: ignore[no-redef]
    from review_record_schema import is_safe_run_id  # type: ignore[no-redef]

__all__ = [
    "ADAPTER_REVIEW_TYPES",
    "UNAVAILABLE",
    "artifact_paths",
    "artifact_problem",
    "delegated_while_unavailable",
    "unavailable_adapter_rows",
    "unavailable_rows",
    "write_time_error",
]

UNAVAILABLE = "unavailable"

#: The passes whose reviewer is ``external_review.py`` — the only ones with an
#: adapter whose error can be captured. ``unavailable`` on an internal row
#: (blocker #2, an autonomous run without spawn permission) is unchanged.
ADAPTER_REVIEW_TYPES = ("plan", "external_code")

Reader = Callable[[str], "bytes | None"]


def artifact_paths(run_id: str, review_type: str) -> tuple[str, str]:
    """``(raw, stderr)`` repo-relative POSIX paths for ``review_type``'s capture."""
    raw = CANONICAL_PAYLOAD_BASENAMES[review_type]
    base = f".shipwright/planning/iterate/{run_id}/"
    return base + raw, base + raw.rsplit(".", 1)[0] + ".stderr.txt"


def _decode(blob: bytes | None) -> str:
    """Text of a capture; a UTF-16 BOM (Windows PowerShell 5.1's `>` default) is honoured."""
    blob = blob or b""
    codec = "utf-16" if blob[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE) else "utf-8"
    return blob.decode(codec, errors="replace").lstrip("\ufeff").strip()


def _first_object(text: str) -> object:
    """The first JSON object opening a line: stray text before or after a reply must not hide it."""
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.startswith("{"):
            try:
                return json.JSONDecoder().raw_decode(text, offset)[0]
            except ValueError:
                pass
        offset += len(line)
    return None


def artifact_problem(run_id: str, review_type: str, read: Reader) -> tuple[str | None, str | None]:
    """``(problem, evidence_path)`` — ``problem`` is ``None`` when the capture backs the claim."""
    raw_rel, err_rel = artifact_paths(run_id, review_type)
    raw = _decode(read(raw_rel))
    reply = _first_object(raw)
    if isinstance(reply, dict):
        if reply.get("success") is False or reply.get("degraded") is True:
            return None, raw_rel
        return (f"{raw_rel} is not a failure envelope (`success` is not false and `degraded` is not "
                "true) — a reply that parses is the pass's own answer: if the review ran, record it "
                "completed (--from external-review-json), not unavailable"), raw_rel
    if _decode(read(err_rel)):
        return None, err_rel
    return (f"no captured adapter error: {raw_rel} is absent, empty or not a failure envelope, "
            f"and {err_rel} is absent or empty — capture the call's stdout AND stderr "
            "(campaign-step-3-5-plan-review.md → Unavailable) before claiming unavailable"), None


def unavailable_rows(record: dict) -> list[str]:
    """Every review type closed ``not_run`` / ``not_applicable`` with code ``unavailable``."""
    reviews = record.get("reviews") if isinstance(record, dict) else None
    if not isinstance(reviews, dict):
        return []
    return [t for t, e in reviews.items()
            if isinstance(e, dict) and e.get("reason_code") == UNAVAILABLE]


def delegated_while_unavailable(record: dict) -> bool:
    """``code`` is delegated to the orchestrator while ``external_code`` could not run.

    The one shape in which the medium+ code-review floor cannot be met at the
    runner's own F6-verify: the runner has no Agent tool, so its code review
    arrives at campaign-mode 3f-bis, which promotes ``code`` to ``completed``
    (with the reviewer's evidence) before any merge — or STRICT-STOPs. The
    external half normally carries the floor until then; when it was
    ``unavailable`` the run may still continue (operator decision §5.2), loudly.
    """
    reviews = record.get("reviews") if isinstance(record, dict) else None
    if not isinstance(reviews, dict):
        return False
    code, external = reviews.get("code") or {}, reviews.get("external_code") or {}
    return (code.get("status") == "not_run" and code.get("reason_code") == "delegated-to-orchestrator"
            and external.get("reason_code") == UNAVAILABLE)


def unavailable_adapter_rows(record: dict) -> list[str]:
    """The subset of :func:`unavailable_rows` that must carry a captured artifact."""
    return [t for t in unavailable_rows(record) if t in ADAPTER_REVIEW_TYPES]


def write_time_error(project_root: Path | str, run_id: str, review_type: str, reason_code: str | None) -> str | None:
    """The same rule at ``record_review_pass.py record`` time, over the working tree.

    ``None`` for anything but an adapter-backed ``unavailable`` row, and for an
    unsafe ``run_id`` (the record layer refuses that one itself, with its own message).
    """
    if reason_code != UNAVAILABLE or review_type not in ADAPTER_REVIEW_TYPES or not is_safe_run_id(run_id):
        return None
    root = Path(project_root)

    def read(rel: str) -> bytes | None:
        try:
            return (root / rel).read_bytes()
        except OSError:
            return None

    problem, _ = artifact_problem(run_id, review_type, read)
    return f"--reason-code unavailable on {review_type}: {problem}" if problem else None
