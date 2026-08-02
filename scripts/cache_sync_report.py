#!/usr/bin/env python3
"""Human-facing rendering for the plugin-cache drift check.

Split from ``check_plugin_cache_sync.py`` so that deciding what is true and
deciding how to say it stay separate jobs — and so neither file has to trade
its reasoning away to fit under 300 lines. Everything here writes to stdout or
stderr and returns nothing; the exit code is the caller's business.
"""

from __future__ import annotations

import sys

#: Named in every verdict, human and machine, so the deferral stays visible
#: where the result is READ — not only in a docstring the operator won't open.
UNGATED = "plugins/ mirror (trg-5005bf57)"


def _basis_note(records: list[dict]) -> str:
    """Name the basis whenever it is NOT git, on EVERY branch that reports.

    A verdict established by walking a worked-in checkout means something
    different from one established from the index, and the difference must not
    be silent. It matters most on the drift branch: git refusing (say
    ``safe.directory`` on a UNC path) reverts the repo side to walking, the
    gitignored generated files reappear as phantom missing-from-cache, and the
    remedy printed beside them — re-run update-marketplace.sh — cannot put
    ``.coverage`` into the cache. Naming the basis is what makes that
    diagnosable instead of a wild goose chase.
    """
    bases = {r.get("basis", "") for r in records} - {"git", "", "n/a"}
    return f"; basis: {', '.join(sorted(bases))}" if bases else ""


def _version_basis_note(records: list[dict]) -> str:
    """Say so when a compared directory was GUESSED rather than looked up.

    Same rule as :func:`_basis_note`, applied to the other thing a verdict rests on: not
    how the repo side was read, but WHICH cache directory was read at all. Normally that
    comes from ``installed_plugins.json`` — the file the sync itself writes into — and
    saying so would be noise. When that lookup fails the check falls back to the highest
    cached version, which is the sync's target only by coincidence, and the printed remedy
    ("re-run update-marketplace.sh") is then the wrong instruction: re-syncing writes to
    the installed directory and cannot change the one being compared.
    """
    bases = {r.get("version_basis", "") for r in records} - {"installed_plugins", "", "n/a"}
    return f"; version dir chosen by {', '.join(sorted(bases))}" if bases else ""


def print_ok(result: dict) -> None:
    """Name every tree that was read, and count only what was truly compared.

    An OK that omits a tree overclaims; so does one that counts a tree it
    skipped. ``n/a`` is reported as ``n/a``, never folded into "in sync".
    """
    shared = result["shared"]
    shared_part = (
        "shared/ n/a (no shared/ in repo)" if shared["state"] == "n/a"
        else f"shared/ ({shared['tracked_count']} files)"
    )
    # Sum every compared tree, not just shared/, and state the OBSERVATION
    # rather than a cause: the commonest source is a local unpushed deletion,
    # where the sync did nothing wrong and the file is still on origin/main.
    records = [shared, *result["plugins"]]
    stale = sum(r.get("cache_only_count", 0) for r in records)
    unhashable = sum(r.get("unhashable_count", 0) for r in records)
    extra = ""
    if stale:
        extra += f"; {stale} cache file(s) with no repo counterpart"
    if unhashable:
        extra += f"; {unhashable} tracked file(s) could not be read"
    # On the GREEN branch too, and for the same reason `_basis_note` is: this is the
    # false-green half of the very symptom being fixed. A fresh higher version dir that
    # happens to match the repo reads as "in sync" while the tree runtime actually loads is
    # the stale installed one — an ok over a directory nobody runs.
    extra += _basis_note(records) + _version_basis_note(records)
    print(
        f"plugin-cache-sync: ok — {len(result['plugins'])} plugin(s) "
        f"and {shared_part} in sync. Not gated: {UNGATED}{extra}"
    )


def print_drift(result: dict) -> None:
    records = [result["shared"], *result["plugins"]]
    basis = _basis_note(records) + _version_basis_note(records)
    print(
        f"plugin-cache-sync: WARN — {result['drifted_count']} tree(s) drifted. "
        f"Run scripts/update-marketplace.sh to re-sync{basis}.",
        file=sys.stderr,
    )
    for entry in result["plugins"]:
        if entry["state"] != "ok":
            print(f"  - plugin {entry['plugin']}: {entry}", file=sys.stderr)
    if result["shared"]["state"] not in ("ok", "n/a"):
        print(f"  - shared/: {result['shared']}", file=sys.stderr)


def print_orphan_advisory(markers: list[str]) -> None:
    """Explain a drift verdict; never raise one, and never fire on a green.

    The caller prints this only alongside drift. On a healthy machine the
    markers are ALWAYS present — all 8 top-level subdirs of a fully intact
    cached ``shared/`` carried one, re-written by a recurring sweep after each
    re-sync removed them — because the marker means "not recognised as an
    installed plugin", permanently true of ``shared/``. A warning on 100% of
    the time is indistinguishable from an incident. Where it earns its place is
    on a drift: it separates "I forgot to re-sync" from "the cache manager took
    it", and only the second makes a partial reap the explanation — that state
    is not self-healed, because the SessionStart hook's sentinel survives it.

    Every marker is named. Truncating this list once hid ``shared/scripts`` —
    the directory whose reap breaks F11 — behind five alphabetically earlier
    paths, which is the one failure an advisory cannot afford.
    """
    if not markers:
        return
    print(
        f"plugin-cache-sync: advisory — the cache manager does not recognise "
        f"{len(markers)} gated cache dir(s) as installed plugins and has "
        f"flagged them (.orphaned_at): {', '.join(markers)}. Under shared/ "
        f"this is permanent and says nothing about THIS drift; on a plugin dir "
        f"it is unusual and worth reading as a cause. Either way nothing "
        f"self-heals a PARTIAL reap (the SessionStart hook's sentinel survives "
        f"it), so re-run scripts/update-marketplace.sh.",
        file=sys.stderr,
    )
