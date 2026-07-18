"""Target inventory for the requirements golden corpus -- the SSoT.

Every claim this harness makes about "all 15 discovery paths" and "all 5
parsers" resolves here. The registry is pure data so that the parent pytest
process and each realm subprocess read the same inventory.

**Realms.** ``scripts`` and ``lib`` are ambiguous top-level package names in
this monorepo, bound to whichever plugin imports first (ADR-045). Importing
``group_i`` additionally reorders ``sys.path`` and evicts ``sys.modules['tools']``
at module level. Rather than police an import ORDER -- which pytest collection
can defeat, because another test module may import a target first -- each realm
is loaded in its own subprocess. Process boundaries dissolve the collision.

**Count.** 16 discovery entries + 5 parser entries, covering 15 distinct
discovery walks: ``group_i.scan_fr_rows`` appears twice to exercise both
sides of its keyword-only ``include_retired`` flag. Separately,
``rtm.collect_requirements`` is registered under BOTH dimensions -- it is
genuinely both a walk and a parser, and its two cells are identical by
construction, so do not go hunting for a difference between them. The campaign SPEC says nine discovery
walks; six more exist (``fr_gates``, ``adopt_compliance``, ``setup_adopt``,
``validate_adoption``, ``review_runner``, ``project/state``) and five of the
nine named paths pointed at ``shared/scripts/lib/compliance/``, a directory
that does not exist. Corrected here and in the campaign SPEC.

Three further sites share the walk SHAPE but target a different file and are
deliberately out of scope: ``plan_checks._find_planning_split_dirs`` (plan.md),
``project_checks`` (split enumeration), ``plan_compliance._find_review_state``
(external_review_state.json). Worth knowing that the FIRST of those is the only
implementation in the repo that filters non-dirs AND dotdirs AND ``iterate/``
-- none of the 15 below does.
"""

from __future__ import annotations

# --- realms -----------------------------------------------------------------
# ``paths``  prepended to sys.path, in order, before any import in this realm
# ``style``  how the realm's modules are loaded (see _collect_realm.py)

REALMS: dict[str, dict] = {
    "shared_lib": {
        # BOTH entries are required. The modules here are imported flat by name
        # (``import drift_parsers``), which needs ``shared/scripts/lib`` -- but
        # ``fr_gates`` lives inside lib/ and still reaches its siblings via
        # ``from lib.fr_classification import ...``, which needs the PARENT so
        # the ``lib`` package resolves (ADR-045). Production carries the same
        # dual form, so reproducing it here is faithful, not a workaround.
        "paths": ["shared/scripts", "shared/scripts/lib"],
        "style": "flat",
    },
    "shared_tools": {
        # verifiers/*.py use relative imports, so the package parent must be
        # importable as `verifiers`, not loaded by file path.
        "paths": ["shared/scripts", "shared/scripts/tools"],
        "style": "package",
    },
    "compliance": {
        "paths": ["plugins/shipwright-compliance"],
        "style": "package",
    },
    # group_i gets its OWN realm, separate from the collectors that share its
    # plugin. Importing it runs audit_adapters, which reorders sys.path and
    # evicts sys.modules['tools'] at module level -- and _requirement_parse
    # resolves shared libs through _lib_loader at CALL time, so a reordered
    # path could change what it resolves. Ordering group_i last within one
    # realm would also work, but only until someone reorders the registry;
    # a process boundary cannot be undone by an edit. (Caught in external
    # code review of this iterate.)
    "compliance_audit": {
        "paths": ["plugins/shipwright-compliance"],
        "style": "package",
    },
    "adopt": {
        "paths": ["plugins/shipwright-adopt"],
        "style": "by_path",
    },
    "project": {
        # state.py does `from .config import ...`, so it must load as a member
        # of the `lib` package, not by file path.
        "paths": ["plugins/shipwright-project/scripts"],
        "style": "package",
    },
    "design": {
        # setup-design-session.py is hyphenated -- not a valid identifier, so
        # it can only be reached via spec_from_file_location.
        "paths": ["plugins/shipwright-design/scripts"],
        "style": "by_path",
    },
}

# --- calling conventions ----------------------------------------------------
# project_root   fn(Path(root))
# planning_dir   fn(Path(root)/".shipwright"/"planning")
# text           fn(spec_text)
# text_kw        fn(spec_text, namespace=..., spec_path=...)
# text_split     fn(spec_text, split, spec_path)
# path_split     fn(Path(spec), split, spec_path)

DISCOVERY: tuple[dict, ...] = (
    {
        "id": "disc.drift_parsers.collect_requirements_from_planning",
        "realm": "shared_lib", "module": "drift_parsers",
        "attr": "collect_requirements_from_planning", "invoke": "project_root",
        "source": "shared/scripts/lib/drift_parsers.py",
        "note": "Guard is .exists() not .is_dir() -> raises on a planning FILE.",
    },
    {
        "id": "disc.spec_parser.read_top_level_spec",
        "realm": "shared_lib", "module": "spec_parser",
        "attr": "read_top_level_spec", "invoke": "project_root",
        "source": "shared/scripts/lib/spec_parser.py",
        "note": "Returns FILE TEXT, not paths. glob('*/spec.md') skips dotdirs.",
    },
    {
        "id": "disc.spec_parser._iter_spec_files",
        "realm": "shared_lib", "module": "spec_parser",
        "attr": "_iter_spec_files", "invoke": "project_root",
        "source": "shared/scripts/lib/spec_parser.py",
        "note": "GENERATOR. Special-cases iterate/ by yielding every *.md.",
    },
    {
        "id": "disc.fr_gates.collect_known_fr_ids",
        "realm": "shared_lib", "module": "fr_gates",
        "attr": "collect_known_fr_ids", "invoke": "project_root",
        "source": "shared/scripts/lib/fr_gates.py",
        "note": "Whole body in bare `except Exception` -> degrades silently.",
    },
    {
        "id": "disc.backfill_test_links.discover_specs",
        "realm": "shared_tools", "module": "backfill_test_links",
        "attr": "discover_specs", "invoke": "project_root",
        "source": "shared/scripts/tools/backfill_test_links.py",
        "note": "Clone of _test_links_io.discover_specs + a repo-root spec.md.",
    },
    {
        "id": "disc.adopt_compliance.check_a2_spec_has_frs",
        "realm": "shared_tools", "module": "verifiers.adopt_compliance",
        "attr": "check_a2_spec_has_frs", "invoke": "project_root",
        "source": "shared/scripts/tools/verifiers/adopt_compliance.py",
        "note": "UNSORTED rglob. One of the few sites that FAILs on empty.",
        "order_sensitive": True,
    },
    {
        "id": "disc.rtm.collect_requirements",
        "realm": "compliance", "module": "scripts.lib.collectors.rtm",
        "attr": "collect_requirements", "invoke": "project_root",
        "source": "plugins/shipwright-compliance/scripts/lib/collectors/rtm.py",
        "note": "No try/except on read_text at all; its claimed mirror catches OSError.",
    },
    {
        "id": "disc.rtm.collect_external_review_states",
        "realm": "compliance", "module": "scripts.lib.collectors.rtm",
        "attr": "collect_external_review_states", "invoke": "project_root",
        "source": "plugins/shipwright-compliance/scripts/lib/collectors/rtm.py",
        "note": "Targets external_review_state.json. Emits a NEGATIVE row per "
                "split lacking the marker -- only site with that behaviour.",
    },
    {
        "id": "disc._test_links_io.discover_specs",
        "realm": "compliance", "module": "scripts.lib.collectors._test_links_io",
        "attr": "discover_specs", "invoke": "project_root",
        "source": "plugins/shipwright-compliance/scripts/lib/collectors/_test_links_io.py",
        "note": "Cleanest of the 15: is_dir() guard, excludes iterate/.",
    },
    {
        "id": "disc.group_i.scan_fr_rows",
        "realm": "compliance_audit", "module": "scripts.audit.group_i",
        "attr": "scan_fr_rows", "invoke": "project_root",
        "source": "plugins/shipwright-compliance/scripts/audit/group_i.py",
        "note": "Only site with a keyword-only flag (include_retired).",
    },
    {
        # The other half of the keyword-only axis. Without this entry
        # include_retired=True is never exercised and the retired-row branch
        # -- which feeds I4, the ONLY Group I check that can emit `fail` -- is
        # unfrozen. (Caught in adversarial review.)
        "id": "disc.group_i.scan_fr_rows_include_retired",
        "realm": "compliance_audit", "module": "scripts.audit.group_i",
        "attr": "scan_fr_rows", "invoke": "project_root_include_retired",
        "source": "plugins/shipwright-compliance/scripts/audit/group_i.py",
        "note": "Same callable as above with include_retired=True.",
    },
    {
        "id": "disc.validate_adoption._validate_spec",
        "realm": "adopt", "module": "checks/validate_adoption.py",
        "attr": "_validate_spec", "invoke": "project_root",
        "source": "plugins/shipwright-adopt/scripts/checks/validate_adoption.py",
        "note": "UNSORTED rglob then [0] -- which spec is validated is "
                "filesystem-iteration-order dependent.",
        "order_sensitive": True,
    },
    {
        "id": "disc.setup_adopt._detect_existing_artifacts",
        "realm": "adopt", "module": "checks/setup_adopt.py",
        "attr": "_detect_existing_artifacts", "invoke": "project_root",
        "source": "plugins/shipwright-adopt/scripts/checks/setup_adopt.py",
        "note": "Emits project-root-relative POSIX strings into a mixed list.",
    },
    {
        "id": "disc.review_runner.run_review",
        "realm": "adopt", "module": "lib/review_runner.py",
        "attr": "run_review", "invoke": "source_only",
        "source": "plugins/shipwright-adopt/scripts/lib/review_runner.py",
        "note": "Walk is INLINE inside a function that calls an external LLM, "
                "so it is not behaviourally invocable. Frozen at SOURCE level "
                "instead -- a weaker guarantee, stated plainly rather than "
                "papered over. Same UNSORTED rglob-then-break as "
                "validate_adoption.",
    },
    {
        "id": "disc.state.detect_state",
        "realm": "project", "module": "lib.state",
        "attr": "detect_state", "invoke": "planning_dir",
        "source": "plugins/shipwright-project/scripts/lib/state.py",
        "note": "Takes the PLANNING DIR, not a project root -- only site that "
                "does. Unguarded iterdir -> raises when planning is absent.",
    },
    {
        "id": "disc.setup_design_session.find_specs",
        "realm": "design", "module": "checks/setup-design-session.py",
        "attr": "find_specs", "invoke": "project_root",
        "source": "plugins/shipwright-design/scripts/checks/setup-design-session.py",
        "note": "Returns planning-relative strings using the OS separator, and "
                "rglob -- the only site that sees a loose spec.md sitting "
                "directly in the planning dir.",
        # Its output really is platform-dependent, so the matrix stores the
        # posix form and the OS-separator behaviour is pinned in a dedicated
        # test. Baking the Windows form in would make CI (ubuntu) red on the
        # first run, and the obvious remedy -- regenerate -- is the habit this
        # corpus exists to prevent. (Caught in adversarial review.)
        "platform_sep": True,
    },
)

PARSERS: tuple[dict, ...] = (
    {
        "id": "parse.drift_parsers.parse_fr_table",
        "realm": "shared_lib", "module": "drift_parsers",
        "attr": "parse_fr_table", "invoke": "text_split",
        "source": "shared/scripts/lib/drift_parsers.py",
        "note": "POSITIONAL. Pins Must|Should|May to data column 3.",
    },
    {
        "id": "parse._backfill_spec_parse.parse_frs",
        "realm": "shared_lib", "module": "_backfill_spec_parse",
        "attr": "parse_frs", "invoke": "text",
        "source": "shared/scripts/lib/_backfill_spec_parse.py",
        "note": "MOVED since the campaign SPEC was written -- it named "
                "backfill_scan.py:181, which is now _load_events_fr_by_commit.",
    },
    {
        "id": "parse.rtm.collect_requirements",
        "realm": "compliance", "module": "scripts.lib.collectors.rtm",
        "attr": "collect_requirements", "invoke": "project_root",
        "source": "plugins/shipwright-compliance/scripts/lib/collectors/rtm.py",
        "note": "The only parser that cannot be string-driven; it walks. Its "
                "REGEX is byte-identical to drift_parsers'; the surrounding "
                "removed-section loop is a semantic clone, not a byte clone, "
                "and nothing enforces that half stays in sync.",
    },
    {
        "id": "parse._requirement_parse.parse_requirements",
        "realm": "compliance", "module": "scripts.lib.collectors._requirement_parse",
        "attr": "parse_requirements", "invoke": "text_kw",
        "source": "plugins/shipwright-compliance/scripts/lib/collectors/_requirement_parse.py",
        "note": "HEADER-DRIVEN. colmap is never reset -- the first "
                "priority-bearing header governs the whole file. Invalid "
                "priorities are silently coerced to 'Must'.",
    },
    {
        "id": "parse.group_i._scan_one_spec",
        "realm": "compliance_audit", "module": "scripts.audit.group_i",
        "attr": "_scan_one_spec", "invoke": "path_split",
        "source": "plugins/shipwright-compliance/scripts/audit/group_i.py",
        "note": "HEADER-DRIVEN and strict: requires cells[0] == 'id' exactly, "
                "and resets the mapping at EVERY heading.",
    },
)

TARGETS: tuple[dict, ...] = DISCOVERY + PARSERS

EXPECTED_DISCOVERY_COUNT = 16
EXPECTED_PARSER_COUNT = 5


def targets_for_realm(realm: str) -> list[dict]:
    return [t for t in TARGETS if t["realm"] == realm]
