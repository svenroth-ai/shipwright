#!/usr/bin/env python3
"""What the repository's own ``.gitleaks.toml`` says, and what that means.

Split out of ``gitleaks_config`` (which renders the config we HAND the scanner)
because reading the project's file is a different job from writing ours, and
keeping both in one module put it over the 300-line limit. The dependency runs
one way — ``gitleaks_config`` imports this, never the reverse — so the module
that decides *which* config to pass can ask what the project's file contains.

The distinction that matters to a caller: ``project_config_warning`` answers
"would the secret scan have an effective ruleset", which becomes a coverage
DEGRADATION; ``chains_to_another_file`` answers "does this config extend a
second file", which decides whether wrapping it is safe at all.
"""

from __future__ import annotations

import os
import tomllib

# Gitleaks auto-loads this filename from the scan source directory when no
# ``--config`` is given; it is what the host path reads, so it is the file the
# local path must extend.
PROJECT_CONFIG_NAME = ".gitleaks.toml"


def resolve_project_config(target: str) -> str | None:
    """Absolute path to the project's ``.gitleaks.toml`` at ``target``, if any.

    Keyed to the SCANNED target root rather than the process working directory
    — same contract as ``oss_backend._resolve_trivy_ignorefile``, because the
    CWD differs between CI and a local run while the scanned root does not.

    **Absolute, always.** Gitleaks resolves ``[extend] path`` against its own
    working directory, so a relative path here would point somewhere else — or
    nowhere — the moment the scan is launched from a different directory than
    the target. ``abspath`` is what makes the extend safe to emit.
    """
    candidate = os.path.abspath(os.path.join(target, PROJECT_CONFIG_NAME))
    return candidate if os.path.isfile(candidate) else None


def inspect_project_config(path: str) -> dict[str, bool]:
    """Report what a project ``.gitleaks.toml`` brings to the rule set.

    Returns ``{"parsed", "extends_default", "extends_other", "defines_rules"}``.

    This exists because of a real hazard in extend-mode. Gitleaks aborts when a
    config sets both ``extend.useDefault`` and ``extend.path``, so extending the
    project's file means the plugin can no longer force the built-in ruleset on:
    responsibility for it moves to that file. A project file authored purely to
    hold an ``[allowlist]``, with no ``[extend] useDefault = true`` and no rules
    of its own, therefore scans with almost NO secret rules.

    The host workflow already behaves that way (it loads the same file with no
    ``--config``), so this is not a new divergence — it is a pre-existing hole
    that extending makes visible. Naming it is the entire point of this
    plugin's coverage manifest: a class scanned with no rules is unexamined,
    not clean. An unparseable file returns ``parsed: False`` and is reported
    the same conservative way.
    """
    result = {
        "parsed": False,
        "extends_default": False,
        "extends_other": False,
        "defines_rules": False,
    }
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        return result
    if not isinstance(data, dict):
        return result
    result["parsed"] = True
    extend = data.get("extend")
    if isinstance(extend, dict):
        result["extends_default"] = bool(extend.get("useDefault"))
        result["extends_other"] = bool(extend.get("path") or extend.get("url"))
    rules = data.get("rules")
    result["defines_rules"] = isinstance(rules, list) and len(rules) > 0
    return result


def _brings_rules(path: str, _depth: int = 0) -> bool | None:
    """Does the config at ``path`` end up with an effective ruleset?

    ``True`` yes, ``False`` no, ``None`` cannot tell. Follows a LOCAL
    ``extend.path`` one hop — gitleaks' own ``maxExtendDepth`` is 2, so a deeper
    chain is not honoured by the scanner either — and refuses to guess about an
    ``extend.url``, which cannot be inspected offline.
    """
    info = inspect_project_config(path)
    if not info["parsed"]:
        return None
    if info["extends_default"] or info["defines_rules"]:
        return True
    if info["extends_other"]:
        if _depth >= 1:
            return None  # deeper than gitleaks itself follows
        chained = _chained_path(path)
        if chained is None:
            return None  # a URL, or an unresolvable path
        return _brings_rules(chained, _depth + 1)
    return False


def _chained_path(path: str) -> str | None:
    """Absolute local path this config extends, or ``None`` for a URL/absent."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        return None
    extend = data.get("extend") if isinstance(data, dict) else None
    if not isinstance(extend, dict) or extend.get("url"):
        return None
    target = extend.get("path")
    if not isinstance(target, str) or not target:
        return None
    resolved = target if os.path.isabs(target) else os.path.join(
        os.path.dirname(path), target)
    return resolved if os.path.isfile(resolved) else None


def project_config_warning(target: str) -> str | None:
    """Human-readable warning when the project's gitleaks config would leave the
    secret scan with (next to) no rules — otherwise ``None``.

    Callers annotate the ``secrets`` coverage row with this, so a scan running
    against an empty ruleset says so instead of reporting a clean class.
    """
    path = resolve_project_config(target)
    if path is None:
        return None
    info = inspect_project_config(path)
    if not info["parsed"]:
        return (
            f"{PROJECT_CONFIG_NAME} could not be parsed; the secret scan is "
            "running under whatever gitleaks makes of it"
        )
    brings_rules = _brings_rules(path)
    if brings_rules is None:
        # An un-inspectable extension (a URL, or a chain deeper than gitleaks
        # follows). Claiming clean here would be the false-clean this card
        # exists to remove, so it is reported as unverifiable.
        return (
            f"{PROJECT_CONFIG_NAME} extends a source that cannot be inspected "
            "offline, so whether the secret scan had an effective ruleset is "
            "unverifiable"
        )
    if brings_rules:
        return None
    return (
        f"{PROJECT_CONFIG_NAME} sets no rules and does not extend the gitleaks "
        "defaults ([extend] useDefault = true), so this scan looked for almost "
        "nothing — the same ruleset the host workflow uses for this repo"
    )


def class_degradations(target: str) -> dict[str, str]:
    """``{"secrets": <reason>}`` for ``scan_coverage.build_coverage``, or ``{}``.

    A DEGRADATION, not a footnote. The secret scan ran, but under a ruleset known
    to be ineffective, so its result cannot be trusted — and a class whose result
    cannot be trusted must not be reported `covered`. Annotating a `covered` row
    with a caveat was the bug: `is_complete()` stayed true, the report showed no
    banner, and the card said "every class was checked" while the detail beside
    it said the scan looked for almost nothing.

    One call site per scan entry point, so the signal cannot be wired into one
    report and forgotten in the other.
    """
    reason = project_config_warning(target)
    return {"secrets": reason} if reason else {}


def chains_to_another_file(target: str) -> bool:
    """Does the project's config at ``target`` extend a SECOND local file?

    Such a config cannot be wrapped. Measured against gitleaks 8.21.2 in CI
    (``test_a_project_config_that_is_already_a_chain_keeps_parity``): with both
    scans running at the repository root, the host — driven by the project's
    config directly — found the planted secret and the wrapped local scan found
    nothing. Adding our level on top of a chain that already used them leaves
    the built-in rules unreachable, so the local scan reports a clean repository
    where the host reports a secret.

    ``extend.url`` counts too. A remote extension spends the same level a local
    one does, so wrapping it breaks parity identically — and unlike the local
    case, nothing about it can be checked offline. (Its unverifiability as a
    RULESET question is separately reported by ``project_config_warning``.)
    """
    path = resolve_project_config(target)
    if path is None:
        return False
    return bool(inspect_project_config(path)["extends_other"])
