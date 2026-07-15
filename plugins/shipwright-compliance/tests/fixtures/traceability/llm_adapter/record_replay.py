"""Stubbed record/replay LLM adapter — traceability backfill leg (offline).

DATA/harness support for the fixture package. The production backfill tool
(campaign TT6) adjudicates a residue of unmapped tests with an LLM; this adapter
replays canned responses from a cassette so that leg runs **offline and
deterministic** in CI, with golden outputs pinning it.

R4 data controls (encoded here so the fixture cannot drift from the policy):

* The request payload carries **only** ``test_path`` + ``test_title`` + the FR
  candidate list — never test bodies. :meth:`key_for` refuses a payload with any
  other key, so a body can never be hashed into a request.
* An LLM-alone/title-similarity verdict is **advisory**: the replayed response
  carries ``auto_write: false``. Only explicit-tag/exact-split corroboration may
  auto-write — the adapter never returns ``auto_write: true`` on its own.
* Replay-only by default; ``record=True`` without a live client raises, so an
  offline run can never silently fabricate a "recorded" success.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_ALLOWED_PAYLOAD_KEYS = frozenset({"test_path", "test_title", "candidate_frs"})
# R4 bounds the payload: paths/titles are short identifiers, never test bodies.
# A conservative cap makes a body smuggled into test_title/test_path a hard error.
_MAX_FIELD_LEN = 300
# candidate_frs is a small list of canonical FR ids — never a channel for a body.
_MAX_CANDIDATE_FRS = 32
_CANONICAL_FR_RE = re.compile(r"^FR-\d{2}\.\d{2}$")


class ReplayError(KeyError):
    """No recorded interaction, or record attempted offline."""


class RecordReplayAdapter:
    def __init__(self, cassette_path: str | Path, record: bool = False):
        self.cassette_path = Path(cassette_path)
        self.record = record
        if self.cassette_path.exists():
            self._data = json.loads(self.cassette_path.read_text(encoding="utf-8"))
        else:
            self._data = {"schema_version": 2, "interactions": {}}

    @staticmethod
    def key_for(payload: dict) -> str:
        """Stable sha256 of the R4-bounded payload (paths + titles + FR list only)."""
        extra = set(payload) - _ALLOWED_PAYLOAD_KEYS
        if extra:
            raise ValueError(f"payload carries disallowed keys (no test bodies, R4): {sorted(extra)}")
        for field in ("test_path", "test_title"):
            value = payload.get(field, "")
            if not isinstance(value, str):
                raise ValueError(f"{field} must be a string, not {type(value).__name__}")
            if len(value) > _MAX_FIELD_LEN:
                # A value this long is a test body, not a path/title — refuse it (R4).
                raise ValueError(f"{field} exceeds {_MAX_FIELD_LEN} chars ({len(value)}); looks like a body, not an identifier")
        frs = payload.get("candidate_frs", [])
        if not isinstance(frs, list):
            raise ValueError("candidate_frs must be a list")
        if len(frs) > _MAX_CANDIDATE_FRS:
            raise ValueError(f"candidate_frs has {len(frs)} entries; a body cannot hide in a bounded FR list (R4)")
        for fr in frs:
            # Every candidate MUST be a canonical FR id — a secret/body cannot be
            # smuggled through as a "short string" (R4). Rejects "password=secret",
            # arbitrary text, and content split across entries.
            if not (isinstance(fr, str) and _CANONICAL_FR_RE.match(fr)):
                raise ValueError(f"candidate_frs entries must be canonical FR ids (FR-XX.YY), got {fr!r}")
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def adjudicate(self, payload: dict) -> dict:
        """Return the recorded adjudication for ``payload`` (offline replay).

        ``auto_write`` is forced to ``False`` on every response: an LLM-alone
        verdict can NEVER authorize an automatic write here (R4). Auto-write
        requires separate explicit-tag/exact-split corroboration the adapter does
        not have — so even a cassette that (wrongly) recorded ``auto_write: true``
        cannot leak an authorization through this replay path.
        """
        key = self.key_for(payload)
        interactions = self._data.get("interactions", {})
        if key in interactions:
            resp = dict(interactions[key]["response"])
            resp["auto_write"] = False
            return resp
        if self.record:
            raise ReplayError("record mode requires a live LLM client, unavailable offline")
        raise ReplayError(f"no recorded interaction for {key} (replay-only)")
