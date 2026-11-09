"""Layout sentinel: fail closed on an event-log layout this plugin does not understand (issue 978, S7).

Mixed versions (DESIGN section 6): a plugin from step 2 on knows ``SUPPORTED_LAYOUTS``. When a repo
declares anything else (``events_layout`` in ``shipwright_sync_config.json`` set by a LATER plugin
generation) this plugin must neither write events nor produce release evidence: ``events_layout()``
alone would read the unknown value as ``legacy`` and silently write the wrong layout. Two refusals:

* unknown layout declaration -> :class:`UnsupportedEventsLayout` ("update the plugin");
* legacy write while drop files exist and the key is ABSENT -> :class:`UnsupportedEventsLayout`: the
  repo defaults to ``legacy`` yet already holds ``shipwright_events.d/*.jsonl`` -- a config that lost its
  key must not split the log. An EXPLICIT ``events_layout: legacy`` is a deliberate rollback (the folds
  set it, and may leave unfoldable corrupt drops behind) and is honoured, never a lockout.

Both are no-ops on a repo without drop files and with ``legacy``/``drops``/absent (the default). The
declaration is read raw with the TEST-ONLY env override deliberately ignored: the sentinel judges what
is committed, not what a harness forces.

Stdlib only; safe to flat-load (no package-relative imports).
"""

from __future__ import annotations

import json
from pathlib import Path

SUPPORTED_LAYOUTS = ("legacy", "drops")
SYNC_CONFIG = "shipwright_sync_config.json"
DROPS_DIR = "shipwright_events.d"
UPDATE_HINT = "Update the Shipwright plugins to a version that supports this layout."


class UnsupportedEventsLayout(RuntimeError):
    """The repo's event layout is one this plugin must not write or produce evidence for."""


def declared_layout(project_root: Path | str) -> object:
    """The raw ``events_layout`` value (``None`` = absent, unreadable or not an object)."""
    try:
        cfg = json.loads((Path(project_root) / SYNC_CONFIG).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return cfg.get("events_layout") if isinstance(cfg, dict) else None


def unsupported_layout(project_root: Path | str) -> str | None:
    """The unsupported declared value as text, or ``None`` when absent / supported."""
    try:
        cfg = json.loads((Path(project_root) / SYNC_CONFIG).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict) or "events_layout" not in cfg:
        return None
    value = cfg["events_layout"]  # an explicit JSON null is a declaration too, and an unknown one
    return None if isinstance(value, str) and value in SUPPORTED_LAYOUTS else repr(value)


def drops_present(project_root: Path | str) -> bool:
    """True when the drops folder holds at least one ``*.jsonl`` file."""
    folder = Path(project_root) / DROPS_DIR
    try:
        return any(p.suffix == ".jsonl" for p in folder.iterdir())
    except OSError:
        return False


def require_writable_layout(project_root: Path | str, effective_layout: str) -> None:
    """Raise unless an event may be written under ``effective_layout`` (what ``events_layout()`` answered)."""
    bad = unsupported_layout(project_root)
    if bad is not None:
        raise UnsupportedEventsLayout(
            f"events_layout {bad} is not supported by this plugin (supported: "
            f"{', '.join(SUPPORTED_LAYOUTS)}); refusing to write events. {UPDATE_HINT}")
    if effective_layout == "legacy" and declared_layout(project_root) is None and drops_present(project_root):
        raise UnsupportedEventsLayout(
            f"{DROPS_DIR}/ holds drop files but shipwright_sync_config.json has no events_layout key; "
            "refusing to append to shipwright_events.jsonl (it would split the log). Set events_layout "
            "to drops (or, for a deliberate rollback, to legacy).")


def evidence_refusal(project_root: Path | str, producer: str) -> dict | None:
    """A refusal record for a release-evidence producer, or ``None`` when it may run."""
    bad = unsupported_layout(project_root)
    if bad is None:
        return None
    return {"status": "refused_unsupported_events_layout", "producer": producer, "events_layout": bad,
            "supported": list(SUPPORTED_LAYOUTS),
            "error": f"{producer} will not produce release evidence for events_layout {bad}. {UPDATE_HINT}"}


def ensure_layout_key(project_root: Path | str) -> bool:
    """Write ``events_layout: legacy`` into the sync config when the key is absent (init / adopt).

    Never removes or overwrites an existing key ("absent = legacy" stays valid forever, but an
    explicit key survives a later plugin that changes the default). Creates a minimal config when
    none exists; leaves an unparsable one alone. Returns True when the file was written.
    """
    path = Path(project_root) / SYNC_CONFIG
    try:
        cfg = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except (OSError, ValueError):
        return False
    if not isinstance(cfg, dict) or "events_layout" in cfg or drops_present(project_root):
        return False  # drops present: writing "legacy" would switch the guard off over a live drops repo
    cfg["events_layout"] = "legacy"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return True
