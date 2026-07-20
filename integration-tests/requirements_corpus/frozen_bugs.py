"""The behaviours this corpus freezes as WRONG, on purpose — and the ones that
have since been fixed, with the step that fixed them.

Read this before "fixing" anything that looks broken in ``golden.json``.

A golden file cannot carry comments, so a future contributor could look at a
surprising cell, conclude it is a mistake, and correct it -- silently destroying
the baseline that campaign steps S2-S6 are measured against. This module is the
missing justification. Each entry names what is wrong, why it is NOT fixed here,
and which campaign step flips it; ``regen_golden.py`` embeds a copy into
``golden.json`` so the reader of the data file is pointed back here.

**Entries are never deleted when they flip.** A flipped entry keeps its ``what``
and ``mechanism`` and gains ``state="flipped"``, ``flipped_in`` (the run that did
it) and ``now`` (what the cell reads today). Deleting it would leave the golden
diff that flipped it unexplained forever, which is the same failure mode as an
uncommented surprising cell -- just displaced in time.

The two verdicts the campaign SPEC names are FV-1 and FV-2. FV-3, FV-4 and FV-5
were found while building this harness and are NOT in the SPEC; they were added
to S4's acceptance criteria and filed as a triage anchor so they could not be
lost if S4 were descoped.

**Status after S4** (``iterate-2026-07-20-one-header-driven-parser``): FV-1,
FV-3, FV-4 and FV-5 are flipped. FV-2 remains frozen and belongs to S6.
"""

from __future__ import annotations

_S4 = "iterate-2026-07-20-one-header-driven-parser"

FROZEN_BUGS: dict[str, dict] = {
    "FV-1": {
        "state": "flipped",
        "what": "A spec that parses to ZERO rows makes traceability check T1 "
                "SKIP rather than FAIL.",
        "mechanism":
            "traceability_checks.check_t1_all_spec_frs_mapped guards on "
            "`if not requirements:`. collect_requirements_from_planning returns "
            "[] for BOTH 'no planning directory' and 'spec present, every row "
            "failed to parse', so the guard cannot distinguish them and the "
            "FAIL branch below is unreachable on a zero-row parse. A table with "
            "its columns reordered is the realistic trigger: "
            "drift_parsers._FR_TABLE_RE pins Must|Should|May to data column 3.",
        "why_not_fixed":
            "This harness exists to prove S2-S4 are behaviour-preserving. "
            "Fixing the baseline here would leave nothing to measure against.",
        "flipped_by": "S4 (one header-driven row parser -- column order stops "
                      "being load-bearing, so a zero-row parse of a populated "
                      "spec becomes impossible)",
        "flipped_in": _S4,
        "now":
            "The `zero-row-parse` fixture parses to one requirement (FR-06.01) "
            "and T1 FAILs on it. `absent` and `empty` still SKIP, correctly, "
            "and their evidence string is now distinguishable from the "
            "populated case. "
            "HONEST LIMIT: the TRIGGER is removed, not the guard. "
            "`if not requirements:` still cannot tell 'no spec' from 'spec I "
            "could not read', and S4 opened NEW routes to that state -- a spec "
            "whose ids are all non-canonical (`FR-7`, `FR-1.1`), or whose "
            "requirements table has no header naming a Priority column, now "
            "parses to zero rows. What makes those DIAGNOSABLE rather than "
            "silent is the `invalid_ids` accumulator: every declined row is "
            "recorded with a reason, published on the manifest, so a zero-row "
            "parse can be told apart from an empty repo by looking. "
            "CORRECTION (S4 second round, from external code review): this "
            "note previously routed the fix to S5's stated AC, which reads "
            "'`_column_map` distinguishes no-spec-on-disk from "
            "spec-present-no-recognised-header'. That does NOT cover the C1 "
            "route -- there the spec IS on disk and the header IS recognised; "
            "only the row ids fail. S5's AC has been amended to name the third "
            "state explicitly, and a triage anchor filed, so the safety net "
            "actually covers the hole it is pointed at.",
        "cells": [
            ("parse.drift_parsers.parse_fr_table", "mixed-shape",
             ".shipwright/planning/06-reordered/spec.md"),
        ],
        "also_pinned_in": "test_requirements_corpus_false_verdicts.py",
    },
    "FV-2": {
        "state": "frozen",
        "what": "An empty requirement set reads GREEN across the audit plane -- "
                "'no requirements' is treated as 'nothing to audit'.",
        "mechanism":
            "Ten Tier-1 guards. The sharpest is NOT the one the campaign SPEC "
            "names: _group_d_traceability emits "
            "('pass', 'LOW', 'every active FR is covered at its required "
            "layers') -- a POSITIVE coverage claim over the empty set. Every "
            "other site at least says 'skip'. Note the repo already knows how "
            "to treat emptiness as a defect elsewhere (adopt_compliance A2 "
            "FAILs, campaign_status raises, design_checks returns not-ok), so "
            "this is a local inconsistency, not a house style.",
        "why_not_fixed": "Same as FV-1 -- it is the baseline. S4 deliberately "
                         "left it alone: it is pinned against the `absent` "
                         "fixture, which S4 does not touch.",
        "flipped_by": "S6 (one catalog at one path: 'no requirements found' "
                      "stops being a legitimate state)",
        "cells": [],  # pinned as prose, not as a matrix cell
        "also_pinned_in": "test_requirements_corpus_false_verdicts.py",
    },
    "FV-3": {
        "state": "flipped",
        "what": "The RTM can display the WRONG requirement text.",
        "mechanism":
            "drift_parsers and rtm are header-blind. When a row carries more "
            "cells than its header declares, regex group 4 fires and a LATER "
            "column is read as the requirement body. Given a 3-column header "
            "and the row `| FR-07.01 | ok | Should | extra | cells |`, both "
            "return text 'extra' instead of 'ok'. This is live wrong data in a "
            "shipped audit artifact, not merely a parse divergence.",
        "why_not_fixed":
            "Not in the campaign SPEC; found while building this harness. "
            "Fixing it here would change RTM output in the same commit that is "
            "supposed to establish the baseline.",
        "flipped_by": "S4 (a header-driven reader selects by column NAME, so a "
                      "row wider than its header can no longer shift the body)",
        "flipped_in": _S4,
        "now":
            "Both sites read the body from the column the header NAMES: "
            "`07-header-blind/FR-07.01` and `malformed/FR-01.03` now return "
            "'ok'. The second site is worth noting -- the same bug had two "
            "occurrences in the corpus and only one was originally described.",
        "cells": [
            ("parse.drift_parsers.parse_fr_table", "mixed-shape",
             ".shipwright/planning/07-header-blind/spec.md"),
        ],
        "found_by": "iterate-2026-07-18-requirements-golden-corpus",
    },
    "FV-4": {
        "state": "flipped",
        "what": "Group I silently audits NOTHING when a table header says 'FR' "
                "instead of 'ID'.",
        "mechanism":
            "group_i._column_map requires cells[0] == 'id' exactly. On the "
            "traceability-fixture shape `FR | Description | Priority | Layers` "
            "it returns None, the column mapping stays None, and every row in "
            "the file is dropped. All four naming-hygiene checks then report "
            "against zero rows -- and zero rows is itself a green state (FV-2).",
        "why_not_fixed": "Not in the campaign SPEC; found here. Same baseline "
                         "argument as FV-3.",
        "flipped_by": "S4 (one header-driven reader, one accepted id column)",
        "flipped_in": _S4,
        "now":
            "A header row is recognised by naming a Priority column, not by its "
            "FIRST cell, so the id column may be headed `ID`, `FR`, or anything "
            "else. `05-fixture-fr` yields FR-05.01 instead of nothing.",
        "cells": [
            ("parse.group_i._scan_one_spec", "mixed-shape",
             ".shipwright/planning/05-fixture-fr/spec.md"),
        ],
        "found_by": "iterate-2026-07-18-requirements-golden-corpus",
    },
    "FV-5": {
        "state": "flipped",
        "what": "Group I drops requirement rows that appear after any heading.",
        "mechanism":
            "group_i._scan_one_spec resets `mapping = None` at EVERY heading, "
            "table-related or not. An FR row under a later heading without a "
            "repeated header row is silently dropped. In the `edge` fixture "
            "group_i loses FR-01.20 (under '## Next'); all four other parsers "
            "keep it.",
        "why_not_fixed": "Not in the campaign SPEC; found here.",
        "flipped_by": "S4",
        "flipped_in": _S4,
        "now":
            "The column map is set by a header ROW and replaced only by the "
            "next header row; headings do not reset it. group_i keeps FR-01.20. "
            "This is the rule that replaced BOTH extremes -- group_i's "
            "reset-at-every-heading and _requirement_parse's never-reset-at-all "
            "were the two ends of the same axis.",
        "cells": [
            ("parse.group_i._scan_one_spec", "edge",
             ".shipwright/planning/01-live/spec.md"),
        ],
        "found_by": "iterate-2026-07-18-requirements-golden-corpus",
    },
}

# Bugs the campaign SPEC already named. The rest were found building this.
SPEC_NAMED = ("FV-1", "FV-2")

#: Ids whose baseline cells have been corrected, newest campaign step last.
#:
#: **These are METADATA guards, not behavioural ones.** Both are derived from the
#: ``state`` field in this file, so a test asserting ``STILL_FROZEN == ("FV-2",)``
#: fails only if someone edits this dict — it cannot notice FV-2's behaviour
#: changing underneath it. The behavioural freeze is carried entirely by the
#: three ``test_fv2_*`` assertions in
#: ``test_requirements_corpus_false_verdicts.py``. S6 flips FV-2: change those
#: three FIRST and let this tuple follow, never the reverse.
FLIPPED = tuple(k for k, v in FROZEN_BUGS.items() if v["state"] == "flipped")
STILL_FROZEN = tuple(k for k, v in FROZEN_BUGS.items() if v["state"] == "frozen")


def as_json_block() -> dict:
    """The reader-facing copy embedded into golden.json."""
    return {
        "_read_me": (
            "Cells listed under a state='frozen' entry are WRONG ON PURPOSE. Do "
            "not correct them -- they are the baseline the remaining campaign "
            "steps are measured against. A state='flipped' entry records a "
            "baseline that HAS been corrected and by which run. Full "
            "rationale: integration-tests/requirements_corpus/frozen_bugs.py"
        ),
        "bugs": {
            bug_id: {
                "state": info["state"],
                "what": info["what"],
                "flipped_by": info["flipped_by"],
                "flipped_in": info.get("flipped_in"),
                "now": info.get("now"),
                "cells": [list(c) for c in info["cells"]],
            }
            for bug_id, info in FROZEN_BUGS.items()
        },
    }
