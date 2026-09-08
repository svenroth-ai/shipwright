"""The durable, per-FR decision record for ``Layers`` promotion (P3.5).

Lives at ``.shipwright/compliance/layer_promotion_ledger.json`` — tracked (not
a :data:`derived_snapshots.DERIVED_SNAPSHOTS` path, so an iterate commit keeps
it), append-only per requirement. It does two jobs the sub-iterate spec asks
for by name:

* **"with its evidence named"** — every mechanical promotion appends the
  ``required_layers`` it wrote and a fingerprint of the manifest node it read,
  so a later reader can see WHY, not just THAT.
* **"cannot silently demote" / "the run cannot author its own promotion
  approval"** — :func:`shared.scripts.tools.promote_required_layers` (the
  automated tool) only ever *appends* a ``"promoted"`` entry, and only for an
  FR with NO prior entry at all. Once an FR has ANY entry, that FR is out of
  the automated tool's authority forever: it either matches (silent no-op) or
  drifted (escalate — see ``layer_promotion.evaluate_fr``'s ``ledger_action``
  branches). The ONLY way to add a ``"demoted"`` entry, or to add a fresh
  ``"promoted"`` entry that OVERRIDES a prior one, is the human-operated CLI
  ``record_layer_promotion_decision.py`` — mirroring the CI supply-chain ack's
  two load-bearing properties (``diff_risk_recheck`` module docstring): the
  automated run never writes its own permission slip, and content — not mere
  presence — is what a later reader trusts.

One JSON file for the whole manifest (not per-run, unlike
``ci_supplychain_ack.json``): a promotion decision is a fact about the
REQUIREMENT, permanent until a human revisits it, not a fact about one run.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:  # Package context (shared/tests: `shared/scripts` on sys.path).
    from .atomic_write import durable_atomic_write
except ImportError:  # Loaded by file path.
    from atomic_write import durable_atomic_write  # type: ignore

LEDGER_SCHEMA_VERSION = 1

#: Sentinel distinguishing "no concurrency check requested" (the default —
#: existing callers, and every test that does not care) from an explicit
#: ``expected_snapshot=None`` (a check IS requested, and the file was absent
#: at load time). A bare ``None`` default cannot carry that distinction.
_UNCHECKED = object()

DEFAULT_LEDGER_RELPATH = ".shipwright/compliance/layer_promotion_ledger.json"

#: Closed vocabulary for an entry's ``action`` — the only two things anyone
#: (tool or operator) may ever record about an FR's binding.
ACTIONS = ("promoted", "demoted")

#: Closed vocabulary for ``decided_by`` — who is attesting this entry.
DECIDED_BY = ("tool", "operator")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _link_sort_key(link: object) -> tuple[str, str, str, str]:
    """Total over every link ``_test_links_requirements`` can produce, not
    merely over the common case (Stage-3 doubt-review round 3, P3.5
    post-push round): one test carrying both a ``@pytest.mark`` tag and a
    ``# @covers`` comment for the same FR files two links with identical
    ``id``/``path``/``ac_id``, differing only in ``tag_source`` — without it
    in the key, ``sorted``'s stability means their relative order (and so
    the digest) depends on collector emission order, not content. Adding it
    closes that gap outright rather than merely documenting it as
    deterministic-by-construction today."""
    if not isinstance(link, dict):
        return ("", "", "", "")
    return (
        str(link.get("id", "")), str(link.get("path", "")),
        str(link.get("ac_id", "")), str(link.get("tag_source", "")),
    )


def _canonical_tests(tests: dict) -> dict:
    """``tests`` with each layer's link list sorted by a stable key (Stage-2
    code-review finding, P3.5 post-push round): the collector's link order
    (set iteration / filesystem walk / parallel collection) is not evidence
    — reordering with no real outcome change must never move the digest."""
    return {
        layer: sorted(links, key=_link_sort_key) if isinstance(links, list) else links
        for layer, links in tests.items()
    }


def evidence_fingerprint(node: dict) -> str:
    """A content fingerprint over the manifest evidence a decision responds to.

    Scoped to ``coverage`` + ``tests`` only (never ``title``/``priority``/etc.
    — those do not bear on layer evidence) so an entry can be checked for
    staleness later: if the FR's evidence has moved on since this fingerprint
    was recorded, a decision made against the OLD state is not silently
    treated as still current. Canonical (sorted keys) JSON, so key order in
    the source manifest never changes the digest — and each layer's test-link
    list is also sorted (:func:`_canonical_tests`), so link ORDER never does
    either.
    """
    payload = {
        "coverage": node.get("coverage") or {},
        "tests": _canonical_tests(node.get("tests") or {}),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def default_ledger() -> dict:
    return {"schema_version": LEDGER_SCHEMA_VERSION, "decisions": {}}


def ledger_path(project_root: Path) -> Path:
    return Path(project_root) / DEFAULT_LEDGER_RELPATH


def ledger_lock_path(project_root: Path) -> Path:
    """The advisory-lock sidecar for the ledger at this project root — a
    caller wraps its OWN load→decide→write span in ``lib.file_lock.file_lock``
    on this path (Stage-3 doubt-review Medium finding, residual gap, P3.5
    post-push round): ``write_ledger``'s ``expected_snapshot`` compare only
    narrows the race (its re-read is not atomic WITH the replace); holding
    this lock across the whole span is what actually closes it."""
    return ledger_path(project_root).with_suffix(".json.lock")


def _parse_ledger(raw: bytes, path: Path) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), dict):
        raise ValueError(f"{path}: not a layer-promotion-ledger document ({{'decisions': {{}}}})")
    version = data.get("schema_version")
    if version != LEDGER_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version {version!r} is not the one this reader "
            f"knows ({LEDGER_SCHEMA_VERSION!r})"
        )
    # Validate on READ, not just on write (Stage-2 code-review Low 1+2, P3.5
    # post-push round): `append_decision` enforces the closed ACTIONS
    # vocabulary when a decision is recorded, but nothing previously checked
    # it on load. `evaluate_fr` branches only on the literal strings
    # "promoted"/"demoted" -- an unvalidated entry with a typo'd or foreign
    # `action` (e.g. "demote") silently fell through to the NO-ledger path,
    # letting the automated tool re-promote an FR that already carries a
    # decision -- the exact thing layer_promotion_ledger.py's own module
    # docstring says can never happen once an FR has ANY entry. Failing
    # closed here also fixes `latest_decision`'s raw AttributeError/KeyError
    # on a corrupted `decisions[fr_id]` (not a list, or a list of non-dicts)
    # -- the same defect class `_canonical_layer_tokens` closed last round.
    for fr_id, history in data["decisions"].items():
        if not isinstance(history, list):
            raise ValueError(f"{path}: decisions[{fr_id!r}] is not a list")
        for entry in history:
            if not isinstance(entry, dict):
                raise ValueError(f"{path}: decisions[{fr_id!r}] contains a non-object entry")
            if entry.get("action") not in ACTIONS:
                raise ValueError(
                    f"{path}: decisions[{fr_id!r}] entry has an unrecognised "
                    f"action {entry.get('action')!r} (expected one of {ACTIONS!r})"
                )
            # Sibling of the action check above, same class, same fix site
            # (Stage-2 code-review Low 1, P3.5 post-push round): a
            # hand-corrupted `required_layers` (e.g. `[null, "unit"]`) used
            # to pass this loader unnoticed and only surface later as a bare
            # `ValueError` out of `layer_promotion._canonical_layer_tokens`
            # -- reachable, uncaught by `_plan_and_apply_locked`'s
            # `(OSError, LayerCellWriteError)` clause, escaping `main()` as
            # an uncaught traceback instead of the CLI's normal JSON error
            # shape. Validating the element type here makes that guard
            # unreachable-by-construction and gives both CLIs the normal
            # error shape for free.
            required_layers = entry.get("required_layers")
            if required_layers is not None and (
                not isinstance(required_layers, list)
                or not all(isinstance(layer, str) for layer in required_layers)
            ):
                raise ValueError(
                    f"{path}: decisions[{fr_id!r}] entry has a required_layers "
                    f"that is not a list of strings: {required_layers!r}"
                )
    return data


def load_ledger(path: Path) -> dict:
    """Read the ledger, or a fresh empty one when the file does not exist yet.

    Raises ``ValueError`` on a schema version this reader does not know, on a
    body that is not the ``{"decisions": {...}}`` shape, on a per-entry
    ``action`` outside the closed :data:`ACTIONS` vocabulary, or on a
    ``required_layers`` that isn't a list of strings — fail closed rather
    than guess at an unknown future shape or silently treat an unrecognised
    entry as no entry at all.
    """
    path = Path(path)
    if not path.is_file():
        return default_ledger()
    return _parse_ledger(path.read_bytes(), path)


def load_ledger_with_snapshot(path: Path) -> tuple[dict, bytes | None]:
    """The ledger and its raw on-disk bytes, from ONE read (Stage-3
    doubt-review Medium finding, P3.5 post-push round): two independent
    reads left a window where a veto lands AFTER the first read populates
    the returned ledger but BEFORE the second captures the snapshot —
    missing from the in-memory ledger AND present in the snapshot, so
    :func:`write_ledger`'s pre-replace compare matches and the write erases
    the veto with no trace. Every caller needing both uses this — no
    standalone snapshot-only reader survives to be paired with a separate
    ``load_ledger`` call by mistake (Low 2, Stage-2 code-review, P3.5
    post-push round: the split reader had zero production callers left).
    """
    path = Path(path)
    if not path.is_file():
        return default_ledger(), None
    raw = path.read_bytes()
    return _parse_ledger(raw, path), raw


class ConcurrentLedgerEditError(RuntimeError):
    """The ledger changed on disk between a caller's ``load_ledger`` and its
    ``write_ledger`` — refused rather than silently overwriting whatever
    landed in between (Stage-2 code-review finding, P3.5 post-push round):
    the load-append-write sequence had no guard while the LESS load-bearing
    spec.md write already had one (``layer_promotion_apply.
    ConcurrentSpecEditError``), on the ONE artifact — an operator's recorded
    veto — that can never be reconstructed if silently lost."""


def write_ledger(path: Path, ledger: dict, *, expected_snapshot: bytes | None = _UNCHECKED) -> None:
    """Atomic write — an interrupted write must never leave a half-file that
    fails every subsequent read for a reason unrelated to any real decision.

    When ``expected_snapshot`` is given (via :func:`load_ledger_with_snapshot`,
    taken right alongside the caller's own load), the file on disk is
    re-read immediately before the replace and the write is refused with
    :class:`ConcurrentLedgerEditError` if it no longer matches — mirroring
    ``layer_promotion_apply.write_promotion_files``'s ``ConcurrentSpecEditError``
    symmetry, but for the ledger itself rather than for a spec.md."""
    path = Path(path)
    if expected_snapshot is not _UNCHECKED:
        current = path.read_bytes() if path.is_file() else None
        if current != expected_snapshot:
            raise ConcurrentLedgerEditError(
                f"{path} changed on disk since this write was planned — "
                "refusing to overwrite a decision recorded in between; "
                "re-run to recompute against the current ledger"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    durable_atomic_write(path, body)


def latest_decision(ledger: dict, fr_id: str) -> dict | None:
    """The most recently recorded entry for ``fr_id``, or ``None``."""
    history = ledger.get("decisions", {}).get(fr_id) or []
    return history[-1] if history else None


def fingerprint_drifted(entry: dict | None, node: dict) -> bool:
    """Whether ``node``'s CURRENT evidence no longer matches the fingerprint
    ``entry`` was recorded against (external code review, glm/medium, P3.5
    round 1: "the fingerprint is recorded but consumed by nothing").

    ``False`` when there is no entry, or the entry carries no fingerprint at
    all (an older/foreign record) — drift is only ever a positive claim about
    evidence that moved, never inferred from an absence. Callers decide what
    a drift MEANS for their action: a promotion's drift is a hard
    contradiction; a demotion's drift is one HALF of what makes its veto
    "exitable" (spec L25/L40, Stage-1 spec-review finding, P3.5) — an
    operator veto recorded against ONE evidence state must not re-escalate
    forever against that same unchanged state, but a genuinely NEW evidence
    state the operator never saw is exactly the case the veto cannot have
    considered. The caller (``lib.layer_promotion.evaluate_fr``'s
    ``demoted`` branch) ANDs this with its own ``predicate_holds`` before
    re-escalating (Stage-1 spec-review round 2): drift alone is not enough —
    drift TOWARD worse evidence stays a decided skip, since nothing is
    promotable and the veto's "new situation" premise does not hold.
    """
    if entry is None:
        return False
    recorded = entry.get("evidence_fingerprint")
    if recorded is None:
        return False
    return recorded != evidence_fingerprint(node)


def append_decision(
    ledger: dict, fr_id: str, *, action: str, decided_by: str,
    required_layers: list[str] | None = None, run_id: str | None = None,
    reason: str = "", escalation_reason_code: str | None = None,
    evidence_fingerprint: str | None = None,
) -> dict:
    """Append a new decision entry for ``fr_id`` and return it.

    Never overwrites or removes a prior entry — the history is the audit
    trail a "cannot silently demote" claim has to point at. Validates the
    closed vocabularies so a typo'd ``action``/``decided_by`` fails loudly
    here rather than being read back as an unrecognised state later.
    """
    if action not in ACTIONS:
        raise ValueError(f"action {action!r} not in {ACTIONS}")
    if decided_by not in DECIDED_BY:
        raise ValueError(f"decided_by {decided_by!r} not in {DECIDED_BY}")
    entry = {
        "action": action,
        "decided_by": decided_by,
        "recorded_at": now_iso(),
        "reason": reason,
    }
    if required_layers is not None:
        entry["required_layers"] = list(required_layers)
    if run_id is not None:
        entry["run_id"] = run_id
    if escalation_reason_code is not None:
        entry["escalation_reason_code"] = escalation_reason_code
    if evidence_fingerprint is not None:
        entry["evidence_fingerprint"] = evidence_fingerprint
    ledger.setdefault("decisions", {}).setdefault(fr_id, []).append(entry)
    return entry


__all__ = [
    "LEDGER_SCHEMA_VERSION",
    "DEFAULT_LEDGER_RELPATH",
    "ACTIONS",
    "DECIDED_BY",
    "ConcurrentLedgerEditError",
    "now_iso",
    "evidence_fingerprint",
    "default_ledger",
    "ledger_path",
    "ledger_lock_path",
    "load_ledger",
    "load_ledger_with_snapshot",
    "write_ledger",
    "latest_decision",
    "fingerprint_drifted",
    "append_decision",
]
