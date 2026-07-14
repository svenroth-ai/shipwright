"""CROSS-REPO CONTRACT GATE — the Command Center WebUI renders this snapshot.

``.shipwright/adopt/snapshot.json`` is what the WebUI's adopt screen reads to show the
operator *"what's already here"* (stack, conventions, tests, CI) **before** anything is
written. A key renamed or dropped here does not fail loudly over there — it renders a
half-empty card. See ``skills/adopt/SKILL.md`` → "Cross-repo contract".

**Why the baseline is git.** A pin is editable in the same change: rename a key, update
the pin, and the diff is empty — so the required bump becomes "none" and any version
passes. The published fixture is therefore frozen against ``origin/main``, which a PR
cannot rewrite, and the gate derives the obliged bump from THAT.

**What is pinned, and what is deliberately NOT.** Unlike grade's ``ReportModel``, this
snapshot is only *partly* a fixed record. Several subtrees are **maps keyed by whatever
was detected** — ``stack.frontend`` is ``{"react": "^18"}`` in one repo and
``{"vue": ...}`` in the next; ``folders.loc_by_layer`` is keyed by layer name. Pinning
their interiors would pin *content*, not contract: the gate would fire on every repo
that happens to use a different framework, and people would learn to ignore it.

So those subtrees are declared OPAQUE and pinned by kind only. **The contract for them is
that the consumer must ITERATE them, never index a fixed key.** Everything else — the
top-level record, and every fixed-key subtree the WebUI reads — is pinned to full depth,
which is what closes the nested-drift hole a top-level-only pin would leave open.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent
_CONTRACTS = _PLUGIN_ROOT / "tests" / "contracts"

for _p in (_PLUGIN_ROOT / "scripts" / "tools", _PLUGIN_ROOT / "scripts" / "lib",
           _PLUGIN_ROOT / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from analyze_codebase import SNAPSHOT_SCHEMA_VERSION, analyze  # noqa: E402
from contract_repos import bare_repo, require_git, rich_repo  # noqa: E402

CONTRACTS_DIR = "plugins/shipwright-adopt/tests/contracts"
STEM = "adopt-snapshot"
CONSUMER = "The Command Center WebUI (github.com/svenroth-ai/shipwright-webui)"
ARTIFACT = "The adopt snapshot (.shipwright/adopt/snapshot.json)"

# Detector-keyed maps: the KEYS are the finding (which framework, which layer), so their
# interiors are not a contract. Pinned by kind; the consumer must iterate, never index.
OPAQUE = (
    "stack.auth", "stack.backend", "stack.database", "stack.frontend", "stack.runtime",
    "folders.loc_by_layer",
)

# The fields the WebUI's adopt screen is documented to read (A08: Stack / Routes / Tests
# / Conventions / CI). Named here so that someone deleting one reads WHY it matters.
LOAD_BEARING = {
    "schema_version", "project_root", "stack.primary_language", "profile.matched",
    "conventions.linter", "conventions.formatter", "conventions.typescript",
    "test_frameworks.unit.framework", "test_frameworks.e2e",
    "ci_pipeline.provider", "ci_pipeline.workflows[]",
    "folders.layers[].name", "folders.layers[].paths[]",
    "commands.dev", "commands.build", "commands.test",
    "git.commits_total",
}


def _load(name: str):
    """Load a shared contract module by PATH — never via ``sys.path`` (ADR-045).

    Registered under the bare name BEFORE exec: ``@dataclass`` resolves its own module
    through ``sys.modules``, and ``contract_baseline`` falls back to
    ``from contract_skeleton import ...`` when it has no parent package.
    """
    path = _REPO_ROOT / "shared" / "scripts" / "lib" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CE = _load("contract_skeleton")
CB = _load("contract_baseline")


def _require_baseline_ref(ref: str = "origin/main") -> None:
    """A gate that no-ops when it cannot reach its baseline is a false green."""
    require_git()
    done = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--verify", ref],
        capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                f"{ref} is unreachable, so the contract gate cannot verify its baseline. "
                "CI checks out with fetch-depth: 0 — if that changed, this gate went "
                "blind and must be fixed, not skipped."
            )
        pytest.skip(f"{ref} not available locally (git fetch origin main)")


def _prune_opaque(skeleton, prefix: str = ""):
    """Replace each OPAQUE subtree with a kind token — pin the shape, not the finding."""
    if isinstance(skeleton, dict):
        out = {}
        for key, sub in skeleton.items():
            path = f"{prefix}.{key}" if prefix else key
            if path in OPAQUE:
                out[key] = "<opaque:object>" if isinstance(sub, dict) else "<opaque>"
            else:
                out[key] = _prune_opaque(sub, path)
        return out
    if isinstance(skeleton, list):
        return [_prune_opaque(item, f"{prefix}[]") for item in skeleton]
    return skeleton


def live_contract(tmp_path: Path) -> dict:
    """The contract as this working tree emits it, merged across the fixture repos.

    Nullability is NOT recorded as a sidecar list here. It used to be, and that list was
    never actually diffed: ``flatten`` walks an array by its first element, so a list of
    paths collapsed to ONE leaf, and adding a path to it produced an empty diff. A
    container becoming nullable would then have read as "no bump required" -- while the
    consumer, told to keep rendering, indexed into null. Nullability now lives inside the
    skeleton (``object|null``), where the ordinary retype => major rule sees it.
    """
    snapshots = [
        analyze(rich_repo(tmp_path / "rich"), ["node_modules"], None),
        analyze(bare_repo(tmp_path / "bare"), [], None),
        # --profile-hint is part of the documented invocation and adds `profile.source`.
        # Without this arm the key is absent from the pin and a rename of it is invisible.
        analyze(rich_repo(tmp_path / "hinted"), [], "supabase-nextjs"),
    ]
    # skeleton_of([...])[0] is the list-element merge: it unions the arms, so an optional
    # field pins as string|null instead of whichever repo came first.
    merged = CE.skeleton_of(snapshots)[0]
    # project_root is an absolute temp path -- a VALUE, not a shape. The skeleton records
    # only its type ("string"), so the pin stays machine-independent.
    return {"skeleton": _prune_opaque(merged)}


def fixture_path(version: str) -> Path:
    return _CONTRACTS / f"{STEM}-{version}.json"


class TestPublishedFixture:
    def test_a_fixture_exists_for_the_declared_version(self):
        assert fixture_path(SNAPSHOT_SCHEMA_VERSION).is_file(), (
            f"SNAPSHOT_SCHEMA_VERSION is {SNAPSHOT_SCHEMA_VERSION!r} but there is no "
            f"{STEM}-{SNAPSHOT_SCHEMA_VERSION}.json. A version the consumer cannot look "
            "up is not a contract."
        )

    def test_the_live_snapshot_matches_the_fixture(self, tmp_path: Path):
        pinned = json.loads(
            fixture_path(SNAPSHOT_SCHEMA_VERSION).read_text(encoding="utf-8"))
        assert pinned["contract"] == live_contract(tmp_path), (
            "The emitted snapshot no longer matches the contract fixture for "
            f"schema_version {SNAPSHOT_SCHEMA_VERSION}. Do not 'fix' this by editing "
            "the published fixture — add a new versioned one and bump the version."
        )

    def test_the_pin_has_no_unpinned_arrays(self, tmp_path: Path):
        weak = CE.empty_array_paths(live_contract(tmp_path)["skeleton"])
        assert weak == [], (
            f"these arrays pin no element type: {weak}. Extend the rich fixture repo so "
            "the detector actually produces one — an empty array is a weak pin that "
            "would let a nested change through while looking like coverage."
        )

    def test_the_pin_has_no_null_only_leaves(self, tmp_path: Path):
        # The null twin of the empty-array guard. A leaf no fixture ever populates pins
        # as bare "null": its production shape (an object, a string) goes UNPINNED, so a
        # rename inside it is invisible -- and the published contract actively tells the
        # consumer the field is always null when in production it is not.
        blind = CE.null_only_paths(live_contract(tmp_path)["skeleton"])
        assert blind == [], (
            f"these leaves were only ever observed as null: {blind}. Make the rich "
            "fixture repo fire the detector so the real shape gets pinned."
        )


class TestTheGate:
    """The half that cannot be satisfied by editing a file in the same PR."""

    def test_published_fixtures_are_frozen_against_main(self):
        # Driven from what origin/main PUBLISHED, not from what the working tree still
        # has: a glob over local files would skip a deleted fixture and pass vacuously.
        _require_baseline_ref()
        for version in CB.published_fixtures(_REPO_ROOT, CONTRACTS_DIR, STEM):
            reason = CB.frozen_fixture_diff(
                _REPO_ROOT, f"{CONTRACTS_DIR}/{STEM}-{version}.json")
            assert reason is None, reason

    def test_the_shape_change_forces_the_bump_it_obliges(self, tmp_path: Path):
        _require_baseline_ref()
        baseline = CB.published_baseline(_REPO_ROOT, CONTRACTS_DIR, STEM)
        if baseline is None:
            # "Nothing published yet" is a real state exactly once -- the commit that
            # introduces the contract. Afterwards it means someone renamed CONTRACTS_DIR
            # or STEM and silently disarmed the gate, because a skipped gate is green.
            assert not CB.any_published_contract(_REPO_ROOT), (
                "origin/main publishes contract fixtures, but none under "
                f"{CONTRACTS_DIR}/{STEM}-*.json. The gate is looking in the wrong place "
                "and has disarmed itself -- fix the constants, do not skip."
            )
            pytest.skip("origin/main publishes no contract yet (bootstrap commit)")
        base_version, base_fixture = baseline
        CE.require_bump(
            base_fixture["contract"], live_contract(tmp_path),
            base_version, SNAPSHOT_SCHEMA_VERSION,
            consumer=CONSUMER, artifact=ARTIFACT,
        )


class TestLoadBearingFields:
    def test_every_documented_field_is_in_the_snapshot(self, tmp_path: Path):
        paths = set(CE.flatten(live_contract(tmp_path)["skeleton"]))
        missing = sorted(LOAD_BEARING - paths)
        assert not missing, f"{CONSUMER} reads these and they are gone: {missing}"

    def test_schema_version_is_written_into_the_snapshot(self, tmp_path: Path):
        snapshot = analyze(bare_repo(tmp_path / "b"), [], None)
        assert snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION


class TestBackwardCompatibility:
    """``schema_version`` is ADDITIVE — nothing in this repo may come to require it."""

    def test_readers_still_accept_a_snapshot_written_before_the_version_existed(
        self, tmp_path: Path
    ):
        # An older /shipwright-adopt wrote no schema_version. Re-adopting must not force
        # a re-scan, so every in-repo reader has to tolerate its absence.
        snapshot = analyze(rich_repo(tmp_path / "rich"), [], None)
        legacy = {k: v for k, v in snapshot.items() if k != "schema_version"}
        assert "schema_version" not in legacy
        # The readers index the snapshot with .get()/[] on the keys they need; none of
        # them may key on schema_version. Assert that directly on the source.
        for reader in ("scripts/tools/generate_adoption_artifacts.py",
                       "scripts/checks/validate_adoption.py",
                       "scripts/lib/ci_workflow_scaffolder.py"):
            source = (_PLUGIN_ROOT / reader).read_text(encoding="utf-8")
            assert 'snapshot["schema_version"]' not in source
            assert "snap['schema_version']" not in source
