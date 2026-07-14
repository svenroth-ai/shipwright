"""Scaffolding for the grade cross-repo contract gate.

The gate itself is `test_report_model_contract.py`; this is the subject it pins and the
machinery it pins with. Split out because the Kern test file is capped at 300 LOC.

The Command Center WebUI renders this report.

``grade.py --format json`` is ``json.dumps(dataclasses.asdict(model))``, and the WebUI's
"Grade your repo" screen renders that model **field-for-field** so the screen and the
downloadable HTML report cannot tell different stories. A field renamed or dropped here
does not fail loudly over there — it renders a half-empty card, or a plausible-but-wrong
one. Nobody in this repo would otherwise have a reason to know the WebUI is watching.

**Why the baseline is git and not a pin in this file.** A pin is editable in the same
change: rename a field, update the pin, and the diff is empty — the required bump
becomes "none" and any version passes. *Editing the pin erases the evidence.* So the
published fixture is frozen against ``origin/main`` (which a PR cannot rewrite) and the
gate derives the bump the diff obliges from THAT.

The pinned subject is the synthetic ``support.mixed_model`` rather than a real grade
run, deliberately: it is built by the real ``build_report_model`` factory and serialized
by the same ``asdict`` → ``json`` path as ``grade.py``, but it *guarantees* an ok/gap/n/a
mix, so nullable fields pin as ``number|null`` instead of whatever one repo happened to
produce. ``test_the_real_cli_conforms_to_the_pin`` then ties the actual CLI output back
to the pin, so the contract is not merely a statement about a dataclass.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from report_model import STATUS_VOCABULARY
from support import mixed_dims, mixed_model

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent
_CONTRACTS = _PLUGIN_ROOT / "tests" / "contracts"

CONTRACTS_DIR = "plugins/shipwright-grade/tests/contracts"
STEM = "grade-report"
CONSUMER = "The Command Center WebUI (github.com/svenroth-ai/shipwright-webui)"
ARTIFACT = "The grade report (grade.py --format json)"

# The fields the WebUI's Grade screen is documented to depend on (A08). Pinned by name
# as well as by shape: the skeleton would catch a rename, but this states WHY each one
# may not simply be dropped, in the place a person removing it would read.
LOAD_BEARING = {
    "dimensions[].status",          # drives the VISUAL; n/a = absent evidence, not a 0
    "dimensions[].detail",          # the per-row "how this was measured" disclosure
    "dimensions[].provenance.source",
    "dimensions[].provenance.mode",
    "dimensions[].would_light_up",
    "network_enabled",              # the receipt for "read-only, no account"
    "network_note",
    "network_enrichments[]",        # exactly what left the machine — never omit
    "honest_ceiling_note",          # reframes a low grade as a finding about the record
    "measurable_count",
    "na_count",
    "controls_shipwright_would_light[]",
    "schema_version",               # lets the consumer refuse an unknown shape honestly
}


def _load(name: str):
    """Load a shared contract module by PATH.

    Never via ``sys.path``: this plugin binds bare module names (``sanitize``, …) and
    ``scripts.lib`` (the compliance engine), so a shared package competing for those
    namespaces would shadow them in a combined pytest run (ADR-045). Registering under
    the bare name BEFORE exec is required twice over: ``@dataclass`` resolves its own
    module via ``sys.modules[cls.__module__]``, and ``contract_baseline`` falls back to
    ``from contract_skeleton import …`` when it has no parent package.
    """
    path = _REPO_ROOT / "shared" / "scripts" / "lib" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CE = _load("contract_skeleton")
CB = _load("contract_baseline")


def require_baseline_ref(ref: str = "origin/main") -> None:
    """The gate needs the immutable baseline. Skip locally, HARD-FAIL in CI.

    A gate that quietly no-ops when it cannot reach its baseline is a false green — the
    class of failure this repo has been bitten by before.
    """
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required in CI — install git on the runner")
        pytest.skip("git not available on this machine")
    done = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--verify", ref],
        capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                f"{ref} is unreachable, so the contract gate cannot verify its "
                "baseline. CI checks out with fetch-depth: 0 — if that changed, this "
                "gate went blind and must be fixed, not skipped."
            )
        pytest.skip(f"{ref} not available locally (git fetch origin main)")


def ungradeable_model():
    """A repo the grader cannot score at all — ``score`` and the grade come back empty.

    Pinned alongside the scored model because ``ReportModel.score`` is ``float | None``:
    a pin taken from a gradeable repo alone would say ``number``, and the first real
    ungradeable repo would emit ``null`` against a contract that forbade it.
    """
    from types import SimpleNamespace

    from report_model import build_report_model
    report = SimpleNamespace(
        grade="n/a", score=None, gradeable=False,
        verdict="Not gradeable — no measurable dimensions.",
        band_label="Not gradeable.", dimensions=mixed_dims(), reasons=[],
        verified_from="shipwright-grade heuristic @ deadbeefcafe1234")
    routing = SimpleNamespace(effective_mode="heuristic", state="absent",
                              reason="no .shipwright/ directory")
    return build_report_model(
        grade_report=report, routing=routing, target_display="empty-repo",
        head_sha="deadbeefcafe1234", events_truncated=False)


def live_contract() -> dict:
    """The contract as this working tree emits it: wire shape + closed vocabularies.

    The skeleton is merged across representative payloads so every union arm is
    observed — ``skeleton_of([a, b])[0]`` is the list-element merge, reused deliberately
    rather than pinning whatever one model happened to produce.
    """
    payloads = [
        dataclasses.asdict(mixed_model(
            network_enabled=True,
            network_note="queried github.com for CI runs and code-scanning alerts",
            network_enrichments=("ci-junit-pass-ratio", "code-scanning-sarif"),
        )),
        dataclasses.asdict(ungradeable_model()),
    ]
    return {
        "skeleton": CE.skeleton_of(payloads)[0],
        # A closed value domain the consumer BRANCHES on. Folded into the pinned object
        # as a joined token so a new status value reads as a retype — the one semantic
        # break the structural skeleton is otherwise blind to.
        "vocabularies": {"DimensionView.status": "|".join(sorted(STATUS_VOCABULARY))},
    }


def fixture_path(version: str) -> Path:
    return _CONTRACTS / f"{STEM}-{version}.json"
