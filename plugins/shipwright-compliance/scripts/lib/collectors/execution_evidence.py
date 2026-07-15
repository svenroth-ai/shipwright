"""Per-test execution-evidence reader (traceability TT-EV — Spec §11 R1, closes G5).

Pure core: parse JUnit XML + Playwright JSON + Vitest reporter output into a
normalized, schema-validated per-test evidence index keyed to the ``test_links``
collector's stable ``path::name`` test ids. This is what makes "covered at a
layer" mean a tagged test that is **enabled AND observed passing** in that
layer's runner evidence — a green-but-*skipped* required-layer test is
``not_run`` (→ MISSING, never ``ok``). Filesystem discovery + the index writer +
CLI live in ``_execution_evidence_io.py``; nothing here touches the filesystem
except reading the frozen schema for validation.

The ``status`` / ``executed`` vocabulary is a VALIDATED FROZEN boundary: raw
runner statuses are runner-specific (``expected`` / ``unexpected`` / ``timedOut``
/ ``passed`` / ``pending`` …), so they are NORMALIZED into the closed index enums
at ingestion and an out-of-vocab value is coerced fail-closed
(``executed`` → ``not_run``, ``status`` → ``quarantined``) — never trusted. The
assembled index is validated against ``evidence_index_schema.json`` before it is
returned, so producer/schema drift blows up loud instead of shipping a corrupt
artifact. The committed artifact is derived/RTM-visibility only (R3).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

EVIDENCE_INDEX_VERSION = 2
# Frozen closed vocabularies — the single source of truth mirrored by both the
# evidence-index schema and traceability_schema.json's testLink enums.
STATUS_VOCAB = frozenset({"enabled", "skipped", "quarantined", "only"})
EXECUTED_VOCAB = frozenset({"pass", "fail", "not_run"})
_LAYER_VOCAB = frozenset({"unit", "integration", "e2e"})

# Cap the parsed JUnit size — a hostile/huge report (billion-laughs entity blow-up)
# fails closed to an empty parse rather than exhausting memory. We have no
# defusedxml dep and the reports are the repo's OWN runner output; the cap plus the
# fail-closed ParseError catch is the proportionate, dependency-free mitigation.
_MAX_XML_BYTES = 8 * 1024 * 1024
# Fail-closed reduction precedence when ONE test id appears more than once (retries,
# shards, multiple browser projects, duplicate names across reports): a failure is
# never hidden by a later pass, and a real (enabled) run is never masked by a skip.
_EXECUTED_RANK = {"fail": 3, "pass": 2, "not_run": 1}
_STATUS_RANK = {"enabled": 4, "quarantined": 3, "only": 2, "skipped": 1}


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "evidence_index_schema.json"


def _normalize_status(value: object) -> str:
    """Coerce to the frozen status vocab; an out-of-vocab value → ``quarantined``
    (held-out, can never combine with a pass to claim coverage ok — fail-closed)."""
    return value if value in STATUS_VOCAB else "quarantined"


def _normalize_executed(value: object) -> str:
    """Coerce to the frozen executed vocab; an out-of-vocab value → ``not_run``
    (an unrecognized runner outcome is never trusted as a pass — fail-closed)."""
    return value if value in EXECUTED_VOCAB else "not_run"


def _entry(status: object, executed: object, runner: str) -> dict:
    return {
        "status": _normalize_status(status),
        "executed": _normalize_executed(executed),
        "runner": runner,
    }


def _merge_into(results: dict, tid: str, entry: dict) -> None:
    """Fold ``entry`` into ``results[tid]`` under the fail-closed reduction precedence
    (a failure outranks a pass; a real run outranks a skip) so a duplicate test id
    across retries/shards/projects can never let a pass mask a failure."""
    prev = results.get(tid)
    if prev is None:
        results[tid] = entry
        return
    results[tid] = {
        "status": entry["status"] if _STATUS_RANK[entry["status"]] >= _STATUS_RANK[prev["status"]] else prev["status"],
        "executed": entry["executed"] if _EXECUTED_RANK[entry["executed"]] >= _EXECUTED_RANK[prev["executed"]] else prev["executed"],
        "runner": prev.get("runner") or entry.get("runner", ""),
    }


def _classname_to_path(classname: str | None) -> str:
    """Best-effort JUnit fallback when a ``<testcase>`` has no ``file`` attribute:
    ``tests.test_auth`` → ``tests/test_auth.py``. Preferred key is the ``file``
    attribute (pytest always emits it); this only guards odd reporters."""
    if not classname:
        return ""
    return classname.replace(".", "/") + ".py"


def read_junit(text: str) -> dict:
    """Parse a JUnit XML string into ``{path::name → evidence}`` (runner=pytest).

    A ``<skipped>`` child → skipped/not_run; a ``<failure>``/``<error>`` child →
    enabled/fail; otherwise enabled/pass.
    """
    out: dict = {}
    if len(text.encode("utf-8", "ignore")) > _MAX_XML_BYTES:
        return out  # oversized report → fail-closed empty parse
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    for tc in root.iter("testcase"):
        name = tc.get("name")
        file = tc.get("file") or _classname_to_path(tc.get("classname"))
        if not name or not file:
            continue
        if tc.find("skipped") is not None:
            status, executed = "skipped", "not_run"
        elif tc.find("failure") is not None or tc.find("error") is not None:
            status, executed = "enabled", "fail"
        else:
            status, executed = "enabled", "pass"
        _merge_into(out, f"{file}::{name}", _entry(status, executed, "pytest"))
    return out


def _playwright_state(spec: dict) -> tuple[str, str]:
    """Resolve a Playwright spec's runner-specific statuses to the frozen vocab."""
    tests = spec.get("tests", []) or []
    test_statuses = [t.get("status") for t in tests]
    result_statuses = [r.get("status") for t in tests for r in (t.get("results") or [])]
    if "passed" in result_statuses:
        return "enabled", "pass"
    if "skipped" in test_statuses or (result_statuses and set(result_statuses) <= {"skipped"}):
        return "skipped", "not_run"
    if "unexpected" in test_statuses or {"failed", "timedOut", "interrupted"} & set(result_statuses):
        return "enabled", "fail"
    return "enabled", "not_run"  # no observed result → fail-closed


def read_playwright(data: dict) -> dict:
    """Parse Playwright JSON-reporter output into ``{file::title → evidence}``.

    Recurses nested ``suites`` (describe blocks), carrying the file down from the
    enclosing file-suite so a nested spec still keys to its source file.
    """
    out: dict = {}

    def walk(suite: dict, file: str) -> None:
        file = suite.get("file") or file
        for spec in suite.get("specs", []) or []:
            title = spec.get("title")
            if title and file:
                _merge_into(out, f"{file}::{title}", _entry(*_playwright_state(spec), "playwright"))
        for sub in suite.get("suites", []) or []:
            walk(sub, file)

    for suite in data.get("suites", []) or []:
        walk(suite, suite.get("file", ""))
    return out


def read_vitest(data: dict) -> dict:
    """Parse Vitest (Jest-shaped) JSON-reporter output into ``{file::title → evidence}``."""
    out: dict = {}
    for tr in data.get("testResults", []) or []:
        file = tr.get("name")
        for a in tr.get("assertionResults", []) or []:
            title = a.get("title")
            if not (file and title):
                continue
            st = a.get("status")
            if st == "passed":
                status, executed = "enabled", "pass"
            elif st == "failed":
                status, executed = "enabled", "fail"
            else:  # skipped | pending | todo → never a pass
                status, executed = "skipped", "not_run"
            _merge_into(out, f"{file}::{title}", _entry(status, executed, "vitest"))
    return out


def validate_index(index: dict) -> None:
    """Fail-closed schema check: raise if the index is not evidence-index-v2-valid."""
    import jsonschema  # noqa: PLC0415 — compliance dep; lazy so light imports stay light

    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(index))
    if errors:
        raise ValueError("evidence index failed v2-schema validation: " + errors[0].message)


def build_index(
    *,
    junit: str | None = None,
    playwright: dict | None = None,
    vitest: dict | None = None,
    generated_at: str | None = None,
    source_reports: list[str] | None = None,
    waivers: list[dict] | None = None,
) -> dict:
    """Merge parsed runner evidence into one schema-validated index (pure; no writes).

    Cross-report merges also go through the fail-closed reduction, so a test id that
    a later report passes cannot mask an earlier failure. ``generated_at`` /
    ``source_reports`` (stamped by the io layer) make staleness auditable — a
    consumer/gate can see this index carries no fresh reports and refuse to trust
    a prior run's passes (R3: enforcing gates regenerate base+head themselves).
    ``waivers`` (operator-authored expiring waivers) are carried through verbatim so
    the layer gate (TT2/TT5) can honor a valid one via ``layer_satisfied``; a refresh
    of the machine results never silently drops them.
    """
    results: dict = {}
    for parsed in (
        read_junit(junit) if junit else {},
        read_playwright(playwright) if playwright else {},
        read_vitest(vitest) if vitest else {},
    ):
        for tid, entry in parsed.items():
            _merge_into(results, tid, entry)
    index: dict = {"schema_version": EVIDENCE_INDEX_VERSION, "results": results}
    if generated_at is not None:
        index["generated_at"] = generated_at
    if source_reports is not None:
        index["source_reports"] = sorted(source_reports)
    if waivers:
        index["waivers"] = waivers
    validate_index(index)
    return index


def normalize_index(raw: dict) -> dict:
    """Coerce an arbitrary/untrusted evidence index to the frozen vocab (fail-closed).

    The ingestion boundary for an *already-normalized* index (e.g. a hand-authored
    or merged ``test-evidence-index.json``): every ``status``/``executed`` is run
    through the closed-vocab coercion so a value like ``executed:"passed"`` can
    never be trusted as a real pass.
    """
    results: dict = {}
    for tid, ev in (raw.get("results") or {}).items():
        if not isinstance(ev, dict):
            continue
        entry = _entry(ev.get("status"), ev.get("executed"), "")
        if ev.get("runner"):
            entry["runner"] = str(ev["runner"])
        else:
            del entry["runner"]
        results[tid] = entry
    index: dict = {"schema_version": EVIDENCE_INDEX_VERSION, "results": results}
    if raw.get("waivers"):
        index["waivers"] = raw["waivers"]      # operator waivers survive normalization
    validate_index(index)
    return index


def waiver_state(waiver: dict, *, now: date | None = None) -> str:
    """``valid`` | ``expired`` | ``invalid``.

    A waiver missing any accountability field (layer/reason/owner/ticket/expires),
    naming an unknown layer, or carrying an unparseable date is ``invalid`` — an
    incomplete waiver is never honored (fail-closed).
    """
    required = ("layer", "reason", "owner", "ticket", "expires")
    if not isinstance(waiver, dict) or any(not str(waiver.get(k, "")).strip() for k in required):
        return "invalid"
    if waiver.get("layer") not in _LAYER_VOCAB:
        return "invalid"
    try:
        expires = date.fromisoformat(str(waiver["expires"]))
    except ValueError:
        return "invalid"
    today = now or datetime.now(timezone.utc).date()
    return "valid" if today <= expires else "expired"


def layer_satisfied(links: list[dict], *, waiver: dict | None = None, now: date | None = None) -> bool:
    """R1 layer decision for a gate: satisfied iff an enabled+pass link exists, else
    a VALID waiver honors it. An expired/invalid/absent waiver → fail-closed False."""
    if any(l.get("status") == "enabled" and l.get("executed") == "pass" for l in links):
        return True
    return waiver is not None and waiver_state(waiver, now=now) == "valid"
